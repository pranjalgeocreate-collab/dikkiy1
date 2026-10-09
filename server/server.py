#!/usr/bin/env python3
"""talktoy brain server.

The Pi posts a WAV of the child talking to /talk and gets a WAV of the reply.
  speech -> text   faster-whisper (small, CPU int8), English or Hindi
  text   -> reply  ElevenLabs Agent (eleven_brain.py) or DeepSeek, with persona.txt and a short memory
  reply  -> speech Piper / AI4Bharat offline, or ElevenLabs online; voice + speed picked on the dashboard (settings.json)
Dashboard of every exchange on http://<mac>:8700/
"""
import datetime, glob, hashlib, io, json, os, random, re, ssl, subprocess, threading, time, urllib.parse, urllib.request, wave

import certifi
from collections import defaultdict, deque

from flask import Flask, Response, jsonify, request
from faster_whisper import WhisperModel, decode_audio

import child_profile
import eleven_brain
import funquiz
import india
import skills
import stories
import voices
from voices import (speak, speak_cached, speak_skill, eleven_speak, get_voice, installed_voices,
                    script_lang, join_wavs, filler_path, DEVANAGARI, FFMPEG, FILLER_DIR)

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("TALKTOY_PORT", 8700))
DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.environ.get("TALKTOY_DEEPSEEK_MODEL", "deepseek-chat")
TLS = ssl.create_default_context(cafile=certifi.where())
LLMS = {"eleven": "ElevenLabs Agent · " + eleven_brain.LLM + " (needs wifi)",
        "deepseek": "DeepSeek · " + DEEPSEEK_MODEL + " (needs wifi)",
        "local": "Local · offline, no AI (no wifi needed)"}
# Local brain: stories, songs and skills only. Anything else gets this line instead of an AI answer.
LOCAL_LINE = {"en": "I know lots of stories and songs! Say, tell me a story, or sing a song, or ask me a maths question.",
              "hi": "मुझे बहुत सारी कहानियाँ और गाने आते हैं! बोलो, कहानी सुनाओ, गाना सुनाओ, या गणित का सवाल पूछो।",
              "as": "মই বহুত সাধু আৰু গান জানো! কোৱা, এটা সাধু কোৱা, নাইবা এটা গান শুনোৱা।",
              "mr": "मला खूप गोष्टी आणि गाणी येतात! सांग, गोष्ट सांग, गाणं ऐकव, किंवा गणिताचा प्रश्न विचार."}
# Stories are recorded once and then play offline. Assamese is recorded with ElevenLabs (the user preferred
# it to the offline voice on 09-30); if ElevenLabs can't be reached, speak() falls back to the offline voice.
STORY_VOICE = {"en": "child-en", "hi": "child-indic-hi", "as": "eleven-as-cgSgspJ2msm6clMCkdW9", "mr": "child-indic-hi"}
STORY_OFFLINE = {"as": "indic-as-female"}   # used (and saved under its own name) when ElevenLabs can't record
STORY_DIR = os.path.join(HERE, "stories_audio")
WHISPER_MODEL = os.environ.get("TALKTOY_WHISPER", "small")  # base garbles Hindi; small gets it right
SETTINGS = os.path.join(HERE, "settings.json")
LOG = os.path.join(HERE, "talklog.jsonl")
MEMORY_TURNS = 6          # child+toy exchanges remembered per toy
MAX_REPLY_CHARS = 320     # hard cap on what gets spoken
MAX_STORY_CHARS = 1400
MAX_UPLOAD = 4 * 1024 * 1024  # ~2 minutes of 16 kHz mono

PERSONA = open(os.path.join(HERE, "persona.txt")).read().strip()
SAY_AGAIN = {"mr": "माफ कर, मला नीट ऐकू आलं नाही. पुन्हा एकदा सांगशील का?", "as": "দুঃখিত, মই ভালদৰে শুনা নাপালোঁ। আকৌ এবাৰ ক'বানে?",
             "en": "Sorry, I didn't quite hear you. Can you say that again?",
             "hi": "माफ़ करना, मैंने ठीक से नहीं सुना। क्या तुम फिर से बोल सकते हो?"}
LLM_DOWN = {"mr": "अरे, आत्ता माझा मेंदू थोडा झोपला आहे. थोड्या वेळाने पुन्हा प्रयत्न कर!", "as": "অ', এতিয়া মোৰ মগজুটো অলপ টোপনিত আছে। অলপ পিছত আকৌ চেষ্টা কৰা!",
            "en": "Oh no, my thinking cap is off right now. Try again in a little bit!",
            "hi": "अरे, अभी मेरा दिमाग़ थोड़ा सो रहा है। थोड़ी देर बाद फिर से कोशिश करना!"}
LANG_RULE = {"en": "Reply ONLY in simple English, even if earlier messages were in Hindi, Assamese or Marathi.",
             "mr": ("The child is speaking Marathi. Reply ONLY in simple Marathi (मराठी) written in Devanagari script, "
                    "even if earlier messages were in another language. Do not use Hindi or English words."),
             "as": ("The child is speaking Assamese. Reply ONLY in simple Assamese (অসমীয়া) written in Assamese "
                    "script, using the Assamese letters ৰ and ৱ, even if earlier messages were in another language. "
                    "Do not use Bengali, Hindi or English words."),
             "hi": ("The child is speaking Hindi. Reply ONLY in simple Hindi written in Devanagari script, even if earlier "
                    "messages were in another language. Do not use English words or Roman letters.")}
HINDI_HINT = "नमस्ते। यह बच्चे और खिलौने की हिंदी में बातचीत है।"
MARATHI_HINT = "नमस्कार. हे मूल आणि खेळण्याचं मराठीतलं बोलणं आहे."  # steers Whisper to Devanagari, not Urdu script
MAX_TOKENS = {"en": 70, "hi": 160, "as": 180, "mr": 160}  # Devanagari costs ~2x the tokens per word
STORY_TOKENS = {"en": 320, "hi": 650, "as": 750, "mr": 650}
STORY_WORDS = re.compile(r"\b(story|stories|tale|kahani|kahaani)\b|कहानी|किस्सा|कथा|সাধু|কাহিনী|গল্প|गोष्ट", re.I)
STORY_RULE = ("The child asked for a story. Ignore the 1 to 3 sentence limit: tell ONE complete short story "
              "of 6 to 9 sentences with a beginning, a middle and a happy ending. Finish the story; never stop "
              "in the middle. No title, no lists, just the story told out loud.")
# Whisper invents these on silence or noise; treat them as "heard nothing".
PHANTOMS = {"", "you", "thank you", "thanks for watching", "bye", "okay", "hmm", "uh", "um"}

print("loading whisper", WHISPER_MODEL, flush=True)
stt = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
# English-only model: several times faster than "small" and just as good for English
WHISPER_EN = os.environ.get("TALKTOY_WHISPER_EN", "base.en")
print("loading whisper", WHISPER_EN, "(English)", flush=True)
stt_en = WhisperModel(WHISPER_EN, device="cpu", compute_type="int8")




def load_settings():
    s = {"voice_en": "en_US-lessac-medium", "voice_hi": "hi_IN-priyamvada-medium", "speed": 1.4, "llm": "eleven", "child_pitch": 1.3, "eleven_agent_id": "",
         "voice_as": "child-indic-as", "voice_mr": "eleven-mr-cgSgspJ2msm6clMCkdW9", "child_name": "", "child_age": 6,
         "bedtime_on": True, "bedtime_start": "21:00", "bedtime_end": "07:00",
         "safety_on": True, "blocked": skills.DEFAULT_BLOCKED}
    try:
        s.update(json.load(open(SETTINGS)))
    except Exception:
        pass
    if s["llm"] not in LLMS:   # e.g. the removed local llama
        s["llm"] = "eleven"
    return s


settings = load_settings()
voices.settings = settings   # voices.py's functions read/write this same dict by reference


get_voice(settings["voice_en"]); get_voice(settings["voice_hi"])

heavy = threading.Lock()   # one conversation at a time; the CPU can't do two well
history = defaultdict(lambda: deque(maxlen=MEMORY_TURNS * 2))
app = Flask(__name__)
import board                     # the dashboard's "Toy board" tab (ESP32-S3 setup over USB)
app.register_blueprint(board.bp)


def transcribe(wav_bytes, hint=None):
    """Returns (text, lang). With a language hint ("en"/"hi", e.g. the dashboard's picker) the
    detection pass is skipped; English then uses the fast English-only model."""
    audio = io.BytesIO(wav_bytes)
    if hint in ("en", "hi", "mr"):
        lang = hint
    else:
        _, _, probs = stt.detect_language(decode_audio(audio))
        probs = dict(probs)
        lang = "hi" if probs.get("hi", 0) > probs.get("en", 0) else "en"
        audio.seek(0)
    model = stt_en if lang == "en" else stt
    segments, _ = model.transcribe(audio, language=lang, beam_size=1, vad_filter=True,
                                 condition_on_previous_text=False,
                                 initial_prompt=HINDI_HINT if lang == "hi" else MARATHI_HINT if lang == "mr" else None)
    text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
    return ("" if re.sub(r"[^a-z ]", "", text.lower()).strip() in PHANTOMS and not DEVANAGARI.search(text)
            else text), lang


def clean_for_speech(text, limit=MAX_REPLY_CHARS):
    text = re.sub(r"[*_#`~>\[\]]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", text)   # emoji
    text = re.sub(r"\s+", " ", text).strip()
    ends = [text.rfind(p) for p in (".", "!", "?", "।")]
    if text and text[-1] not in ".!?।" and max(ends) > 20:  # LLM hit its token cap mid-sentence
        text = text[:max(ends) + 1]
    if len(text) > limit:  # cut at the last full sentence that fits
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("। "))
        text = cut[:end + 1] if end > 40 else cut.rsplit(" ", 1)[0] + "."
    return text


STORY_YES = re.compile(r"^\W*(?:go|go on|tell me|tell it|start)\b|^\W*(?:हो|होय|हो ना|सांग|হয়|হ'ব|বাৰু|কোৱা)", re.I)


def story_accepted(toy_id, heard):
    """'ok go' / 'yes' / 'हो' right after Dikkey offered a story ("...a story about a teddy bear instead?")."""
    past = [m["content"] for m in history[toy_id] if m["role"] == "assistant"]
    if not past or "?" not in past[-1] or not STORY_WORDS.search(past[-1]):
        return False
    return bool((YES.search(heard) or STORY_YES.search(heard)) and not NO.search(heard))


def think(toy_id, heard, lang):
    story = bool(STORY_WORDS.search(heard)) or story_accepted(toy_id, heard)
    system = PERSONA + "\n\n" + LANG_RULE[lang] + ("\n\n" + STORY_RULE if story else "")
    if settings.get("child_name"):
        system += f"\n\nThe child's name is {settings['child_name']}. Use their name in every reply, kindly."
    if settings.get("child_age"):
        system += f"\nThe child is {settings['child_age']} years old; match your words to that age."
    msgs = [{"role": "system", "content": system}, *history[toy_id], {"role": "user", "content": heard}]
    max_tokens = (STORY_TOKENS if story else MAX_TOKENS)[lang]
    if settings["llm"] == "eleven":
        if not settings.get("eleven_agent_id"):
            raise RuntimeError("no ElevenLabs agent id in settings.json")
        raw = eleven_brain.ask(settings["eleven_agent_id"], msgs, timeout=90 if story else 45)
    else:
        raw = ask_deepseek(msgs, max_tokens)
    reply = clean_for_speech(raw, MAX_STORY_CHARS if story else MAX_REPLY_CHARS)
    history[toy_id].append({"role": "user", "content": heard})
    history[toy_id].append({"role": "assistant", "content": reply})
    return reply


quizzes = defaultdict(dict)     # per-toy maths game state (see skills.quiz_*)
rng = random.Random()
SONG_DIR = os.path.join(HERE, "songs")
SONG_ASK = re.compile(r"song|sing|play|music|गाना|गीत|सुनाओ|बजाओ", re.I)


ABC_SONG_NAMES = ("abcd", "abc", "alphabet", "phonics", "a_for_apple", "a for apple", "abcd_song", "abc_song")
YES = re.compile(r"^\W*(?:yes|yeah|yep|yup|sure|ok|okay|please|yes please|of course|haan|han|ha)\b|"
                 r"^\W*(?:हाँ|हां|हा|जी|ज़रूर|जरूर|बिल्कुल|चलो|ठीक)", re.I)
NO = re.compile(r"^\W*(?:no|nope|nah|not now|no thanks|nahi|nahin)\b|^\W*(?:नहीं|ना|मत|अभी नहीं)", re.I)
pending_offer = {}   # toy_id -> song file the toy just offered to play
playlists = {}        # toy_id -> remaining song filenames for "play all songs" (see song_playlist)
PLAY_ALL_SONGS = re.compile(r"play all (?:the )?songs?|all (?:the )?songs?\b|play (?:the )?(?:whole|full) (?:song )?"
                            r"(?:list|library)|सार[ेी] गाने?\s*(?:बजाओ|सुनाओ)|सभी गाने?\s*(?:बजाओ|सुनाओ)", re.I)


def song_file(names):
    """First file in songs/ whose name (without extension) is one of `names`."""
    if not os.path.isdir(SONG_DIR):
        return None
    files = sorted(os.listdir(SONG_DIR))   # .mp3 sorts before .wav, so a real recording beats a code-made one
    for name in names:                     # names are in order of preference
        for f in files:
            stem, ext = os.path.splitext(f)
            if ext.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".aac") and stem.lower().replace("-", "_") == name:
                return f
    return None


def song_playlist():
    """Every distinct song in songs/, alphabetical. Symlinks (e.g. an English-name alias for a
    Hindi file) and same-stem duplicates (abcd.mp3 vs abcd.wav) count once, by their real file."""
    if not os.path.isdir(SONG_DIR):
        return []
    seen_targets, seen_stems, out = set(), set(), []
    for f in sorted(os.listdir(SONG_DIR)):
        stem, ext = os.path.splitext(f)
        if ext.lower() not in (".mp3", ".wav", ".m4a", ".ogg", ".aac") or stem.startswith("."):
            continue
        real = os.path.realpath(os.path.join(SONG_DIR, f))
        key = stem.lower().replace("_", " ").replace("-", " ")
        if real in seen_targets or key in seen_stems:
            continue
        seen_targets.add(real)
        seen_stems.add(key)
        out.append(f)
    return out




def song_credit(fname):
    """Optional songs/<name>.credit.txt, e.g. 'the Phonics Song by Mega Fun Kids Songs'."""
    path = os.path.join(SONG_DIR, os.path.splitext(fname)[0] + ".credit.txt")
    return open(path).read().strip()[:200] if os.path.exists(path) else ""


def play_song(fname, lang):
    """(display, audio): the creator's credit is announced first if there is one, thank-you after
    (skipped for spoken-story clips, where "thank you for singing" doesn't fit)."""
    wav = song_wav(fname)
    if not wav:
        return None
    title = os.path.splitext(fname)[0].replace("_", " ")
    credit = song_credit(fname)
    is_story = bool(re.search(r"story|tale|narration|kahani|कहानी", credit, re.I))
    audio = wav if is_story else song_with_thanks(wav, lang)
    if credit:
        intro = f"यह रहा {credit}!" if lang == "hi" else f"Here is {credit}!"
        try:
            audio = join_wavs(speak_cached(intro, lang), audio)
        except Exception as e:
            print("credit intro failed:", e, flush=True)
    thanks_line = "" if is_story else "\n" + skills.THANKS_SONG.get(lang, skills.THANKS_SONG["en"])
    shown = f"🎵 {title}" + (f"\nCredit: {credit}" if credit else "") + thanks_line
    return shown, audio


def song_with_thanks(wav, lang):
    try:
        return join_wavs(wav, speak_cached(skills.THANKS_SONG.get(lang, skills.THANKS_SONG["en"]), lang))
    except Exception as e:
        print("thank-you after song failed:", e, flush=True)
        return wav


def song_wav(fname):
    src = os.path.join(SONG_DIR, fname)
    cache = os.path.join(FILLER_DIR, "song-" + hashlib.sha1((src + str(os.path.getmtime(src))).encode()).hexdigest()[:16] + ".wav")
    if not os.path.exists(cache):
        os.makedirs(FILLER_DIR, exist_ok=True)
        out = subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", src, "-ac", "1", "-ar", "22050", cache],
                             capture_output=True, timeout=120)
        if out.returncode != 0:
            print("song convert failed", src, out.stderr[-200:], flush=True)
            return None
    return open(cache, "rb").read()


SPELLED = re.compile(r"(?<![a-z])([a-z])((?:[\s.\-]+[a-z](?![a-z]))+)")
HI_LETTERS = {"ए": "a", "बी": "b", "सी": "c", "डी": "d", "ई": "e", "एफ": "f", "जी": "g"}


def song_words(text):
    """Lower-case text with spelled-out letters joined: 'A B C D' / 'a.b.c.d' / 'ए बी सी डी' -> 'abcd'."""
    t = skills.nfc(text.lower())
    t = re.sub(r"(?:(?<=\s)|^)(" + "|".join(HI_LETTERS) + r")(?=\s|$)", lambda m: HI_LETTERS[m.group(1)], t)
    return SPELLED.sub(lambda m: m.group(1) + re.sub(r"[\s.\-]+", "", m.group(2)), t)


def find_song(text):
    """A parent-supplied audio file in songs/ whose name words all appear in what the child said,
    e.g. songs/abc.mp3 for 'play the abc song'. Returns (title, wav_bytes) or None."""
    if not os.path.isdir(SONG_DIR) or not SONG_ASK.search(text):
        return None
    low = song_words(text)
    best = None
    for f in sorted(os.listdir(SONG_DIR)):
        stem, ext = os.path.splitext(f)
        if ext.lower() not in (".mp3", ".wav", ".m4a", ".ogg", ".aac") or stem.startswith("."):
            continue
        words = [w for w in re.split(r"[\s_\-]+", skills.nfc(stem.lower())) if w]
        if words and all(re.search(rf"(?<![\w\u0900-\u097F]){re.escape(w)}(?![\w\u0900-\u097F])", low) for w in words):
            if not best or len(words) > best[1]:
                best = (f, len(words))
    if not best:
        return None
    return best[0]
last_filtered = {}              # toy_id -> original reply the safety filter replaced (shown to parents)


def answer_or_think(toy_id, heard, lang, status):
    """Order: bedtime → maths game → exact skills (skills.py) → LLM, whose reply then passes the
    parent's safety filter. Returns (reply_text, status, audio_or_None)."""
    if settings.get("bedtime_on") and skills.in_bedtime(skills.now_india(), settings["bedtime_start"], settings["bedtime_end"]):
        line = skills.bedtime_line(lang, settings.get("child_name", ""))
        return line, "bedtime", speak_cached(line, lang)

    if funquiz.active(toy_id):   # the fun quiz is running: this is an answer (or stop / again)
        reply = funquiz.turn(toy_id, heard, lang, rng)
        return reply, "funquiz", speak(reply, lang)

    prof = child_profile.handle(toy_id, heard, lang, skills.now_india().date())   # name / birthday, scripted
    if prof:
        sync_child()
        history[toy_id].append({"role": "user", "content": heard})
        history[toy_id].append({"role": "assistant", "content": prof[0]})
        return prof[0], "profile:" + prof[1], speak(prof[0], lang)

    offered = pending_offer.pop(toy_id, None)
    if offered == "__anthem__":
        if (YES.search(heard) or stories.STORY_YES_ANY.search(heard)) and not NO.search(heard) and os.path.exists(ANTHEM_FILE):
            display, audio = play_anthem(lang)
            return display, "anthem", audio
        offered = None
    if offered == "__count_again__":
        if YES.search(heard) and not NO.search(heard) and lang in ("en", "hi"):
            start = skills.count_along(lang)
            pending_offer[toy_id] = "__count_again__"
            history[toy_id].append({"role": "user", "content": heard})
            history[toy_id].append({"role": "assistant", "content": start.display})
            return start.display, "skill:count_along", speak_skill(start, lang)
        if NO.search(heard):
            line = "ठीक है, फिर कभी गिनेंगे!" if lang == "hi" else "Okay, we'll count again another time!"
            return line, "skill:offer-no", speak_cached(line, lang)
        offered = None
    if offered == "__state_capitals__":
        if YES.search(heard) and not NO.search(heard):
            ask = {"en": "all the state capitals", "hi": "सभी राज्यों की राजधानी बताओ",
                  "as": "সকলো ৰাজ্যৰ ৰাজধানী কোৱা", "mr": "सर्व राज्यांच्या राजधान्या सांग"}[lang]
            caps = india.answer(ask, lang)
            history[toy_id].append({"role": "user", "content": heard})
            history[toy_id].append({"role": "assistant", "content": caps[0]})
            return caps[0], "skill:india", speak_cached(caps[1], lang)
        if NO.search(heard):
            line = "ठीक है, फिर कभी!" if lang == "hi" else "Okay, maybe next time!"
            return line, "skill:offer-no", speak_cached(line, lang)
        offered = None
    if offered == "__playlist__":
        if YES.search(heard) and not NO.search(heard):
            remaining = playlists.get(toy_id) or []
            if not remaining:
                line = "यह रहे मेरे सारे गाने! फिर मिलते हैं।" if lang == "hi" else "That's all the songs I know! See you next time."
                return line, "skill:offer-no", speak_cached(line, lang)
            nxt = remaining.pop(0)
            played = play_song(nxt, lang)
            if remaining:
                pending_offer[toy_id] = "__playlist__"
                ask = " अगला गाना सुनोगे?" if lang == "hi" else " Want to hear the next song?"
            else:
                playlists.pop(toy_id, None)
                ask = " यह आख़िरी गाना था।" if lang == "hi" else " That was the last one!"
            history[toy_id].append({"role": "user", "content": heard})
            history[toy_id].append({"role": "assistant", "content": played[0] + ask})
            return played[0] + ask, "song", join_wavs(played[1], speak_cached(ask, lang))
        if NO.search(heard):
            playlists.pop(toy_id, None)
            line = "ठीक है, फिर कभी गाने सुनेंगे!" if lang == "hi" else "Okay, we'll listen to more songs another time!"
            return line, "skill:offer-no", speak_cached(line, lang)
        offered = None
    if offered:
        if YES.search(heard):
            played = play_song(offered, lang) if os.path.exists(os.path.join(SONG_DIR, offered)) else None
            if played:
                return played[0], "song", played[1]
        elif NO.search(heard):
            line = "ठीक है, फिर कभी!" if lang == "hi" else "Okay, maybe later!"
            return line, "skill:offer-no", speak_cached(line, lang)
        # anything else: the child moved on, handle it normally

    if not quizzes[toy_id].get("active"):   # during the maths game, "stop" ends the game instead
        stop = skills.stop_request(heard, lang)
        if stop:
            return stop.display, "skill:stop", speak_cached(stop.speech, lang)

    bye = skills.goodbye(heard, lang, settings.get("child_name", ""))
    if bye:
        quizzes[toy_id].clear()
        pending_offer.pop(toy_id, None)
        return bye.display, "skill:goodbye", speak_cached(bye.speech, lang)

    helper = skills.can_do(heard, lang)
    if helper:
        return helper.display, "skill:help", speak_cached(helper.speech, lang)

    if funquiz.START.search(heard) and not skills.QUIZ_START.search(skills.nfc(heard.lower())) and lang in funquiz.LANGS:
        reply = funquiz.start(toy_id, lang, rng)   # 10 fun questions, offline
        return reply, "funquiz", speak(reply, lang)

    if anthem_wanted(heard, lang) and os.path.exists(ANTHEM_FILE):
        display, audio = play_anthem(lang)
        return display, "anthem", audio

    fact = india.answer(heard, lang)   # India facts from a table: offline, no LLM
    if fact and fact[1] == skills.nfc(india.LINES["anthem"][lang]) and os.path.exists(ANTHEM_FILE):
        line = fact[1] + ANTHEM_OFFER[lang]
        pending_offer[toy_id] = "__anthem__"
        history[toy_id].append({"role": "user", "content": heard})
        history[toy_id].append({"role": "assistant", "content": line})
        return line, "skill:india", speak_cached(line, lang)
    if fact:
        if india.Q["all_states"].search(skills.nfc(heard.lower())):
            pending_offer[toy_id] = "__state_capitals__"
        history[toy_id].append({"role": "user", "content": heard})
        history[toy_id].append({"role": "assistant", "content": fact[1]})
        return fact[0], "skill:india", speak_cached(fact[1], lang)

    as_alpha = skills.assamese_alphabet(heard, lang)   # Assamese has no other offline skills yet
    if as_alpha:
        history[toy_id].append({"role": "user", "content": heard})
        history[toy_id].append({"role": "assistant", "content": as_alpha.display})
        return as_alpha.display, "skill:" + as_alpha.name, speak_skill(as_alpha, lang)

    if PLAY_ALL_SONGS.search(heard):
        all_songs = song_playlist()
        if all_songs:
            first, remaining = all_songs[0], all_songs[1:]
            played = play_song(first, lang)
            if played:
                if remaining:
                    playlists[toy_id] = remaining
                    pending_offer[toy_id] = "__playlist__"
                    ask = " अगला गाना सुनोगे?" if lang == "hi" else " Want to hear the next song?"
                else:
                    ask = ""
                history[toy_id].append({"role": "user", "content": heard})
                history[toy_id].append({"role": "assistant", "content": played[0] + ask})
                audio = join_wavs(played[1], speak_cached(ask, lang)) if ask else played[1]
                return played[0] + ask, "song", audio

    song = find_song(heard)
    played = play_song(song, lang) if song else None
    if played:
        return played[0], "song", played[1]

    if STORY_WORDS.search(heard) or story_accepted(toy_id, heard) or stories.by_title(heard):   # own stories, no LLM
        told_list = told[toy_id]
        st = stories.pick(heard, told_list, ready=lambda x: os.path.exists(story_path(x, lang)), rng=rng)
        display, _ = stories.telling(st, lang)
        told_list.append(st["id"])
        del told_list[:-20]
        history[toy_id].append({"role": "user", "content": heard})
        history[toy_id].append({"role": "assistant", "content": f"(told the story {st['title'][lang]})"})
        return display, "story:" + st["id"], story_audio(st, lang)

    sk = None
    if lang in ("en", "hi"):
        game = quizzes[toy_id]
        if game.get("active"):
            sk = skills.quiz_turn(game, heard, lang, rng)
        elif skills.QUIZ_START.search(skills.nfc(heard.lower())):
            sk = skills.quiz_start(game, lang, settings.get("child_age"), rng)
        elif skills.COUNT_ALONG_START.search(skills.nfc(heard.lower())):
            sk = skills.count_along(lang)
    sk = sk or skills.answer(heard, lang, rng=rng)
    if sk and sk.name == "phonics" and len(sk.display.splitlines()) > 1:
        abc = song_file(ABC_SONG_NAMES)
        if abc:
            pending_offer[toy_id] = abc
            sk = skills.Skill(sk.name, sk.display + "\n\nWould you like to hear the ABCD song?",
                              sk.speech + " Would you like to hear the A B C D song?", sk.speak_lang)
    if sk and sk.name == "count_along":
        pending_offer[toy_id] = "__count_again__"
    if sk:
        history[toy_id].append({"role": "user", "content": heard})
        history[toy_id].append({"role": "assistant", "content": sk.display})
        return sk.display, "skill:" + sk.name, speak_skill(sk, lang)

    if settings["llm"] == "local":
        line = LOCAL_LINE[lang]
        return line, "local", speak_cached(line, lang)
    try:
        reply = think(toy_id, heard, lang)
    except Exception as e:
        print("llm error (telling the child what still works offline):", e, flush=True)
        line = skills.offline_line(lang)
        return line, "offline", speak_cached(line, lang)
    hit = settings.get("safety_on") and skills.blocked_hit(reply, settings.get("blocked", ""))
    if hit:
        print(f"[{toy_id}] safety filter caught {hit!r}: {reply!r}", flush=True)
        last_filtered[toy_id] = reply
        history[toy_id][-1]["content"] = skills.SAFE_REDIRECT[lang]
        return skills.SAFE_REDIRECT[lang], f"filtered:{hit}", None
    return reply, status, None


told = defaultdict(list)   # toy_id -> story ids told, newest last
child_profile.open_db(os.path.join(HERE, "children.db"))   # the child's name + birthday, on this Mac only


def sync_child():
    """The brain gets the current child's first name and age (never the birthday itself)."""
    cur = child_profile.current()
    settings["child_name"] = child_profile.call_name(cur) or ""   # the pet name if there is one; never the school
    age = child_profile.age_of(cur["dob"], skills.now_india().date()) if cur and cur["dob"] else None
    if age:
        settings["child_age"] = max(2, min(14, age))
    json.dump(settings, open(SETTINGS, "w"), indent=1, ensure_ascii=False)


def with_name(reply, audio, lang):
    """Every reply uses the child's name: if the reply doesn't already say it, Dikkey says it first."""
    cur = child_profile.current()
    name = child_profile.call_name(cur)
    if not name or not audio:
        return reply, audio
    said = child_profile.name_in(name, lang)       # "Munu" -> "মুনু" for Assamese: same voice as the reply
    if name.lower() in reply.lower() or said in reply:
        return reply, audio
    try:
        clip = speak_cached(said + "!", lang)
        return f"{said}! {reply}", join_wavs(clip, audio, gap=0.2)
    except Exception as e:
        print("saying the name failed:", e, flush=True)
        return reply, audio


def with_birthday(reply, audio, lang):
    """On the child's birthday, the first reply of the day starts with happy birthday."""
    line = child_profile.birthday_line(lang, skills.now_india().date())
    if not line:
        return reply, audio
    try:
        return line + "\n\n" + reply, join_wavs(speak_cached(line, lang), audio, gap=0.5)
    except Exception as e:
        print("birthday greeting failed:", e, flush=True)
        return reply, audio

# ---- national anthem: official Government of India recording, played whole and unchanged, after a respect message
ANTHEM_FILE = os.path.join(HERE, "anthem", "jana_gana_mana.ogg")
ANTHEM_PLAY = re.compile(r"(?:play|sing|put\s+on|hear|listen\s+to)\b.{0,20}(?:national\s+anthem|jana\s*gana\s*mana)|"
                         r"(?:national\s+anthem|jana\s*gana\s*mana).{0,15}\b(?:play|sing|please)|"
                         r"(?:राष्ट्रगान|जन\s*गण\s*मन).{0,15}(?:सुनाओ|बजाओ|गाओ|चलाओ|लगाओ|ऐकव|लाव|वाजव|म्हण)|"
                         r"(?:राष्ट्रगीत).{0,15}(?:ऐकव|लाव|वाजव|म्हण)|"
                         r"(?:ৰাষ্ট্ৰীয়\s*সংগীত|জন\s*গণ\s*মন).{0,15}(?:শুনোৱা|বজোৱা|গোৱা|লগোৱা)", re.I)
# who made it and when (years in words: skills.spell_numbers would read Assamese/Marathi digits in English)
# Just naming the anthem plays it (any common spelling); a question about it ("who wrote...") gets the answer instead.
ANTHEM_WORD = re.compile(r"\bnation(?:al)?\s*(?:anth?[aeiou]+m|enth?[aeiou]+m|antham)\b|\bjana\s*gana\s*mana\b|राष्ट्रगान|जन\s*गण\s*मन|"
                         r"ৰাষ্ট্ৰীয়\s*সংগীত|জন\s*গণ\s*মন", re.I)
ANTHEM_QUESTION = re.compile(r"\b(?:what|who|which|when|why|how|wrote|written)\b|क्या|कौन|किसने|कब|लिखा|"
                             r"কি\b|কোন|কোনে|কেতিয়া|লিখিছিল|काय|कोण|कोणी|कधी|लिहिलं", re.I)


def anthem_wanted(text, lang):
    t = skills.nfc(text)
    if ANTHEM_PLAY.search(t):
        return True
    named = ANTHEM_WORD.search(t) or (lang == "mr" and "राष्ट्रगीत" in t)   # Marathi राष्ट्रगीत is the anthem
    return bool(named) and not ANTHEM_QUESTION.search(t)


ANTHEM_RESPECT = {
    "en": "This is our national anthem, Jana Gana Mana. Rabindranath Tagore wrote it and made its tune in nineteen eleven, "
          "and India adopted it as our national anthem on the twenty-fourth of January, nineteen fifty. "
          "Let us always respect our national anthem. Please stand up straight and listen with respect.",
    "hi": "यह हमारा राष्ट्रगान है, जन गण मन। इसे रवींद्रनाथ टैगोर ने उन्नीस सौ ग्यारह में लिखा और इसकी धुन बनाई। "
          "भारत ने इसे चौबीस जनवरी, उन्नीस सौ पचास को अपना राष्ट्रगान बनाया। "
          "हमें हमेशा अपने राष्ट्रगान का सम्मान करना चाहिए। कृपया सीधे खड़े हो जाओ और सम्मान से सुनो।",
    "as": "এইটো আমাৰ ৰাষ্ট্ৰীয় সংগীত, জন গণ মন। ৰবীন্দ্ৰনাথ ঠাকুৰে ইয়াক ঊনৈশ শ এঘাৰ চনত লিখিছিল আৰু সুৰ দিছিল। "
          "ভাৰতে ঊনৈশ শ পঞ্চাশ চনৰ চৌবিশ জানুৱাৰীত ইয়াক ৰাষ্ট্ৰীয় সংগীত হিচাপে গ্ৰহণ কৰে। "
          "আমি সদায় আমাৰ ৰাষ্ট্ৰীয় সংগীতক সন্মান কৰিব লাগে। অনুগ্ৰহ কৰি পোন হৈ থিয় হোৱা আৰু সন্মানেৰে শুনা।",
    "mr": "हे आपलं राष्ट्रगीत आहे, जन गण मन. रवींद्रनाथ टागोर यांनी ते एकोणीसशे अकरा साली लिहिलं आणि त्याला चाल दिली. "
          "भारताने चोवीस जानेवारी एकोणीसशे पन्नास रोजी ते आपलं राष्ट्रगीत म्हणून स्वीकारलं. "
          "आपण नेहमी आपल्या राष्ट्रगीताचा आदर केला पाहिजे. कृपया ताठ उभे राहा आणि आदराने ऐका.",
}
ANTHEM_OFFER = {"en": " Shall I play it for you? Please stand up when it plays.",
                "hi": " क्या मैं इसे बजाऊँ? जब यह बजे, तो खड़े हो जाना।",
                "as": " মই বজাই দিমনে? বাজোঁতে থিয় হৈ থাকিবা।",
                "mr": " मी ते लावू का? ते वाजताना उभे राहा."}
BHARAT_MAHAN = {"en": "Mera Bharat Mahan!", "hi": "मेरा भारत महान!", "as": "মোৰ ভাৰত মহান!", "mr": "माझा भारत महान!"}


def anthem_wav():
    """The official recording as mono 22 kHz WAV (cached); only the format changes, never speed or pitch."""
    cache = os.path.join(FILLER_DIR, "anthem-" + str(int(os.path.getmtime(ANTHEM_FILE))) + ".wav")
    if not os.path.exists(cache):
        os.makedirs(FILLER_DIR, exist_ok=True)
        out = subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", ANTHEM_FILE, "-ac", "1", "-ar", "22050", cache],
                             capture_output=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError("anthem convert failed: " + out.stderr.decode()[-200:])
    return open(cache, "rb").read()


def play_anthem(lang):
    """(display, audio): who made it + respect message, 3 s to stand up, the whole anthem, then Mera Bharat Mahan."""
    audio = join_wavs(join_wavs(speak_cached(ANTHEM_RESPECT[lang], lang), anthem_wav(), gap=3.0),
                      speak_cached(BHARAT_MAHAN[lang], lang), gap=1.0)
    display = (f"🇮🇳 {ANTHEM_RESPECT[lang]}\n\n🎵 Jana Gana Mana (official recording, Government of India)\n\n{BHARAT_MAHAN[lang]}")
    return display, audio


def story_voices(lang):
    return [STORY_VOICE[lang]] + ([STORY_OFFLINE[lang]] if lang in STORY_OFFLINE else [])


def story_file(st, lang, voice):
    spoken = stories.telling(st, lang)[1]
    key = json.dumps([voice, settings["speed"], settings["child_pitch"], spoken], ensure_ascii=False)
    return os.path.join(STORY_DIR, f"{st['id']}-{lang}-" + hashlib.sha1(key.encode()).hexdigest()[:12] + ".wav")


def story_path(st, lang):
    """The recording to play: the preferred voice's at today's settings if it exists, else the offline one's,
    else any earlier recording of this story (e.g. made before the speed was changed) - better than silence."""
    paths = [story_file(st, lang, v) for v in story_voices(lang)]
    found = next((p for p in paths if os.path.exists(p)), None)
    if found:
        return found
    older = sorted(glob.glob(os.path.join(STORY_DIR, f"{st['id']}-{lang}-*.wav")), key=os.path.getmtime, reverse=True)
    return older[0] if older else paths[0]


def story_audio(st, lang):
    path = story_path(st, lang)
    if os.path.exists(path):
        return open(path, "rb").read()
    spoken = stories.telling(st, lang)[1]
    for voice in story_voices(lang):
        try:
            if voice.startswith("eleven-"):   # no silent fallback here: the file name must match the voice
                audio = eleven_speak(spoken, lang, voice.split("-", 2)[2], settings["speed"])
            else:
                audio = speak(spoken, lang, voice)
        except Exception as e:
            print("story voice failed", voice, e, flush=True)
            continue
        path = story_file(st, lang, voice)
        os.makedirs(STORY_DIR, exist_ok=True)
        open(path + ".tmp", "wb").write(audio)
        os.replace(path + ".tmp", path)
        return audio
    raise RuntimeError(f"no voice could record {st['id']} in {lang}")


def record_stories():
    """Record every story once with the offline voices (English first: it is fastest)."""
    def run():
        done = 0
        for lang in ("en", "as", "hi", "mr"):
            for st in stories.STORIES:
                if os.path.exists(story_path(st, lang)):
                    continue
                try:
                    story_audio(st, lang)
                    done += 1
                    print(f"story recorded {st['id']} {lang}", flush=True)
                except Exception as e:
                    print("story recording failed", st["id"], lang, e, flush=True)
        print(f"stories ready ({done} newly recorded)", flush=True)
    threading.Thread(target=run, daemon=True).start()






def ask_deepseek(msgs, max_tokens):
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    body = json.dumps({"model": DEEPSEEK_MODEL, "messages": msgs, "max_tokens": max_tokens,
                       "temperature": 0.7, "stream": False}).encode()
    req = urllib.request.Request(DEEPSEEK_URL, body, {"Content-Type": "application/json",
                                                      "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=60, context=TLS) as r:
        return json.load(r)["choices"][0]["message"]["content"]
















def log(entry):
    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def to_rate(wav_bytes, rate):
    """Mono 16-bit WAV at `rate` Hz. The ESP32-S3-BOX-3 toy asks for 16000: its mic and speaker share one
    audio clock, so replies must come at the rate it records at (header X-Want-Rate)."""
    try:
        w = wave.open(io.BytesIO(wav_bytes))
        if w.getframerate() == rate and w.getnchannels() == 1 and w.getsampwidth() == 2:
            return wav_bytes
    except Exception:
        pass
    out = subprocess.run([FFMPEG, "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-ac", "1", "-ar", str(rate),
                          "-f", "s16le", "pipe:1"], input=wav_bytes, capture_output=True, timeout=120)
    if out.returncode != 0 or not out.stdout:
        return wav_bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(out.stdout)
    return buf.getvalue()


def wav_response(audio, **headers):
    want = request.headers.get("X-Want-Rate", "")
    if want.isdigit() and 8000 <= int(want) <= 48000:
        audio = to_rate(audio, int(want))
    resp = Response(audio, mimetype="audio/wav")
    for k, v in headers.items():
        resp.headers["X-" + k.replace("_", "-")] = urllib.parse.quote(str(v))
    return resp


@app.post("/talk")
def talk():
    wav = request.files["audio"].read() if "audio" in request.files else request.get_data()
    if not wav or len(wav) > MAX_UPLOAD:
        return jsonify(error="send a WAV under 4 MB as the body or as form field 'audio'"), 400
    toy_id = request.headers.get("X-Toy-Id", "toy")[:40]
    t0 = time.time()
    with heavy:
        heard, lang = transcribe(wav, request.headers.get("X-Lang"))
        t1 = time.time()
        status, audio = "ok", None
        if not heard:
            reply, status = SAY_AGAIN[lang], "empty"
        else:
            reply, status, audio = answer_or_think(toy_id, heard, lang, status)
        t2 = time.time()
        if audio is None:
            audio = speak(reply, lang)
        reply, audio = with_birthday(*with_name(reply, audio, lang), lang)
    t3 = time.time()
    timing = {"stt_ms": int((t1 - t0) * 1000), "llm_ms": int((t2 - t1) * 1000),
              "tts_ms": int((t3 - t2) * 1000), "total_ms": int((t3 - t0) * 1000)}
    log({"ts": time.time(), "toy": toy_id, "status": status, "lang": lang, "llm": settings["llm"],
         "heard": heard, "reply": reply, "audio_in_kb": len(wav) // 1024, **timing,
         **({"original": last_filtered.pop(toy_id, "")} if status.startswith("filtered") else {})})
    print(f"[{toy_id}] {status} {timing['total_ms']}ms heard={heard!r} reply={reply!r}", flush=True)
    return wav_response(audio, Heard=heard, Reply=reply, Status=status, Total_Ms=timing["total_ms"], Lang=lang)


@app.post("/chat")
def chat():
    """Typed instead of spoken: for testing from the dashboard before the toy exists."""
    heard = clean_for_speech(((request.get_json(silent=True) or {}).get("text") or "")[:500])
    if not heard:
        return jsonify(error="type something first"), 400
    toy_id = request.headers.get("X-Toy-Id", "dashboard")[:40]
    picked = request.get_json(silent=True).get("lang")
    lang = script_lang(heard, picked if picked in LANG_RULE else "en")
    t0 = time.time()
    with heavy:
        reply, status, audio = answer_or_think(toy_id, heard, lang, "typed")
        t1 = time.time()
        if audio is None:
            audio = speak(reply, lang)
        reply, audio = with_birthday(*with_name(reply, audio, lang), lang)
    t2 = time.time()
    timing = {"stt_ms": 0, "llm_ms": int((t1 - t0) * 1000), "tts_ms": int((t2 - t1) * 1000),
              "total_ms": int((t2 - t0) * 1000)}
    log({"ts": time.time(), "toy": toy_id, "status": status, "lang": lang, "llm": settings["llm"],
         "heard": heard, "reply": reply, "audio_in_kb": 0, **timing,
         **({"original": last_filtered.pop(toy_id, "")} if status.startswith("filtered") else {})})
    print(f"[{toy_id}] {status} {timing['total_ms']}ms typed={heard!r} reply={reply!r}", flush=True)
    return wav_response(audio, Heard=heard, Reply=reply, Status=status, Total_Ms=timing["total_ms"], Lang=lang)


@app.get("/say")
def say():
    text = clean_for_speech(request.args.get("text", ""))
    if not text:
        return jsonify(error="pass ?text=..."), 400
    with heavy:
        name = request.args.get("voice")
        if name and name not in {v["name"] for v in installed_voices()}:
            return jsonify(error="unknown voice"), 400
        return wav_response(speak(text, request.args.get("lang", "en"), name), Reply=text)


SAMPLES = {"mr": "नमस्कार मित्रा! मी डिक्की, तुझं बोलणारं खेळणं. चल, एक गोष्ट ऐकूया!",
           "as": "নমস্কাৰ বন্ধু! মই ডিক্কী, তোমাৰ কথা কোৱা খেলনা। আহা, এটা সাধু শুনো!",
           "en": "Hi friend! Why did the teddy bear skip dessert? Because it was already stuffed!",
           "hi": "नमस्ते दोस्त! मैं तुम्हारा बात करने वाला खिलौना हूँ। चलो एक कहानी सुनते हैं!"}


@app.get("/api/voices")
def list_voices():
    return jsonify(voices=installed_voices(), voice_en=settings["voice_en"], voice_hi=settings["voice_hi"],
                   voice_as=settings["voice_as"], voice_mr=settings["voice_mr"],
                   speed=settings["speed"], child_pitch=settings["child_pitch"], samples=SAMPLES)


@app.post("/api/voices")
def set_voice():
    body = request.get_json(silent=True) or {}
    names = {v["name"]: v["lang"] for v in installed_voices()}
    if "speed" in body:
        settings["speed"] = round(min(2.0, max(0.7, float(body["speed"]))), 2)
    if "child_pitch" in body:
        settings["child_pitch"] = round(min(1.6, max(1.05, float(body["child_pitch"]))), 2)
    for lang in ("en", "hi", "as", "mr"):
        name = body.get("voice_" + lang)
        if name:
            if names.get(name) != lang:
                return jsonify(error=f"{name} is not an installed {lang} voice"), 400
            with heavy:
                get_voice(name)
            settings["voice_" + lang] = name
    json.dump(settings, open(SETTINGS, "w"), indent=1)
    prewarm_fillers()
    return jsonify(ok=True, **settings)


@app.post("/reset")
def reset():
    history.pop(request.headers.get("X-Toy-Id", "toy")[:40], None)
    return jsonify(ok=True)


def llm_ok():
    if settings["llm"] == "local":
        return True
    if settings["llm"] == "eleven":
        return bool(os.environ.get("ELEVENLABS_API_KEY") and settings.get("eleven_agent_id"))
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def read_log(n=200):
    if not os.path.exists(LOG):
        return []
    with open(LOG) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    return rows[-n:]


@app.get("/health")
def health():
    return jsonify(ok=True, whisper=WHISPER_MODEL,
                   voice=" + ".join(settings["voice_" + l] for l in ("en", "hi", "as", "mr")),
                   speed=settings["speed"], llm=LLMS[settings["llm"]], llm_ready=llm_ok())


PARENT_KEYS = ("child_name", "child_age", "bedtime_on", "bedtime_start", "bedtime_end", "safety_on", "blocked")


@app.get("/api/parent")
def get_parent():
    now = skills.now_india()
    return jsonify(**{k: settings[k] for k in PARENT_KEYS}, default_blocked=skills.DEFAULT_BLOCKED,
                   bedtime_now=bool(settings["bedtime_on"] and skills.in_bedtime(now, settings["bedtime_start"], settings["bedtime_end"])),
                   now=now.strftime("%H:%M"))


@app.post("/api/parent")
def set_parent():
    body = request.get_json(silent=True) or {}
    try:
        if "child_name" in body:
            settings["child_name"] = re.sub(r"[^\w\s\u0900-\u097F\u0980-\u09FF.'-]", "", str(body["child_name"]))[:30].strip()
        if "child_age" in body:
            settings["child_age"] = max(2, min(14, int(body["child_age"])))
        for k in ("bedtime_on", "safety_on"):
            if k in body:
                settings[k] = bool(body[k])
        for k in ("bedtime_start", "bedtime_end"):
            if k in body:
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(body[k])):
                    return jsonify(error=f"{k} must look like 21:00"), 400
                settings[k] = body[k]
        if "blocked" in body:
            settings["blocked"] = str(body["blocked"])[:3000]
    except (TypeError, ValueError):
        return jsonify(error="age must be a number"), 400
    json.dump(settings, open(SETTINGS, "w"), indent=1, ensure_ascii=False)
    return get_parent()


@app.get("/api/llm")
def get_llm():
    return jsonify(current=settings["llm"], options=LLMS,
                   deepseek_key=bool(os.environ.get("DEEPSEEK_API_KEY")))


@app.post("/api/llm")
def set_llm():
    choice = (request.get_json(silent=True) or {}).get("llm")
    if choice not in LLMS:
        return jsonify(error="llm must be one of " + ", ".join(LLMS)), 400
    settings["llm"] = choice
    json.dump(settings, open(SETTINGS, "w"), indent=1)
    prewarm_fillers()   # Local swaps in the offline voices, which need their own clips
    return jsonify(ok=True, current=choice)


@app.get("/api/log")
def api_log():
    return jsonify(read_log(int(request.args.get("n", 200))))


@app.get("/dikkey")
def dikkey3d():
    """Dikkey himself in 3D (three.js, served from ./static so it works offline), live with the virtual board."""
    resp = Response(open(os.path.join(HERE, "dikkey3d.html")).read(), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/buddy")
def buddy_dash():
    """Greeting page: Dikkey flies in, asks for the mic, and speaks with the server voice."""
    resp = Response(open(os.path.join(HERE, "buddy.html")).read(), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/tv")
def tv():
    """Dikkey's retro TV: the virtual board (and its talk button) as an old CRT screen."""
    resp = Response(open(os.path.join(HERE, "tv.html")).read(), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def dashboard():
    resp = Response(open(os.path.join(HERE, "dashboard.html")).read(), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"   # always the latest dashboard, never an old copy
    return resp


# ---- "thinking" fillers: short lines played the moment the child stops talking ----
FILLERS = {
    "en": {"start": ["Let me think!", "Ooh, good question! Let me think.", "One moment, thinking!"],
           "wait": ["Almost there!", "Still thinking, just a moment!"]},
    "hi": {"start": ["मुझे सोचने दो!", "अरे वाह, अच्छा सवाल है! सोचता हूँ।", "एक मिनट, सोच रहा हूँ।"],
           "wait": ["बस थोड़ा सा और!", "अभी भी सोच रहा हूँ, एक पल!"]},
    "mr": {"start": ["मला विचार करू दे!", "अरे वा, छान प्रश्न! विचार करतो.", "एक मिनिट, विचार करतोय."],
           "wait": ["थोडंसं अजून!", "अजून विचार करतोय, एक क्षण!"]},
    "as": {"start": ["অনুগ্ৰহ কৰি অলপ ৰ'বা।"],   # Assamese: only "please wait a little" (user's choice)
           "wait": ["অনুগ্ৰহ কৰি অলপ ৰ'বা।"]},
}
_filler_lock = threading.Lock()






def prewarm_fillers():
    def run():
        if not _filler_lock.acquire(blocking=False):
            return
        try:
            os.makedirs(FILLER_DIR, exist_ok=True)
            for lang, kinds in FILLERS.items():
                for texts in kinds.values():
                    for text in texts:
                        path = filler_path(lang, text)
                        if not os.path.exists(path):
                            try:
                                audio = speak(text, lang)
                                open(path + ".tmp", "wb").write(audio)
                                os.replace(path + ".tmp", path)
                            except Exception as e:
                                print("filler failed", lang, text, e, flush=True)
            for lang in ("en", "hi", "as", "mr"):   # so "no internet" and "what can you do" play instantly
                for line in (skills.offline_line(lang), skills.nfc(skills.CAN_DO_LINE[lang])):
                    try:
                        speak_cached(line, lang)
                    except Exception as e:
                        print("prewarm failed", lang, e, flush=True)
            for text, lang in (("sing the abc", "en"), ("अंग्रेज़ी वर्णमाला सुनाओ", "hi"), ("हिंदी वर्णमाला सुनाओ", "hi"),
                               ("name the colors", "en"), ("रंग बताओ", "hi"),
                               ("how to read a clock", "en"), ("घड़ी कैसे देखें", "hi")):
                try:
                    speak_cached(skills.answer(text, lang).speech, lang)
                except Exception as e:
                    print("skill prewarm failed", text, e, flush=True)
            for lang in ("en", "hi", "as", "mr"):
                for line in (ANTHEM_RESPECT[lang], BHARAT_MAHAN[lang]):
                    try:
                        speak_cached(line, lang)
                    except Exception as e:
                        print("anthem prewarm failed", lang, e, flush=True)
            for lang in ("en", "hi"):   # count-along: cache every chunk so it plays instantly, no wifi needed
                try:
                    speak_skill(skills.count_along(lang), lang)
                except Exception as e:
                    print("count_along prewarm failed", lang, e, flush=True)
            for text, lang in (("what are the states of india", "en"), ("राज्यों के नाम बताओ", "hi"),
                               ("ৰাজ্যৰ নাম কোৱা", "as"), ("राज्यांची नावं सांग", "mr")):
                try:
                    speak_cached(india.answer(text, lang)[1], lang)
                except Exception as e:
                    print("india all_states prewarm failed", lang, e, flush=True)
            try:
                speak_skill(skills.assamese_alphabet("অসমীয়া বৰ্ণমালা", "as"), "as")
            except Exception as e:
                print("assamese alphabet prewarm failed", e, flush=True)
            print("fillers ready", flush=True)
        finally:
            _filler_lock.release()
    threading.Thread(target=run, daemon=True).start()


@app.get("/filler")
def filler():
    """Random ready-made clip for ?lang=en|hi|as|mr&kind=start|wait. 204 if none recorded yet (never blocks)."""
    lang = request.args.get("lang", "en")
    kind = request.args.get("kind", "start")
    texts = FILLERS.get(lang, FILLERS["en"]).get(kind, [])
    ready = [(t, filler_path(lang, t)) for t in texts if os.path.exists(filler_path(lang, t))]
    if not ready:
        return Response(status=204)
    text, path = random.choice(ready)
    return wav_response(open(path, "rb").read(), Reply=text)


@app.get("/api/children")
def api_children():
    today = skills.now_india().date()
    return jsonify([{"id": c["id"], "name": c["name"], "dob": c["dob"] or "", "school": c["school"] or "", "pet_name": c["pet_name"] or "",
                     "birthday": child_profile.show_date(c["dob"]) if c["dob"] else "",
                     "age": child_profile.age_of(c["dob"], today) if c["dob"] else None} for c in child_profile.all_children()])


@app.post("/api/children")
def api_children_save():
    """Parent adds or corrects a child: {id?, name, dob: 'YYYY-MM-DD' or ''}."""
    body = request.get_json(silent=True) or {}
    name = child_profile.clean_name(str(body.get("name", "")).strip().split(" ")[0])
    if not name:
        return jsonify(error="type a first name"), 400
    dob = str(body.get("dob") or "")
    if dob:
        try:
            born = datetime.date.fromisoformat(dob)
        except ValueError:
            return jsonify(error="birthday must be a date"), 400
        if not 0 <= skills.now_india().date().year - born.year <= 18:
            return jsonify(error="that birthday isn't a child's"), 400
    school = re.sub(r"[^\w\s.'&\u0900-\u09FF-]", "", str(body.get("school") or "")).strip()[:60]
    pet = child_profile.clean_name(str(body.get("pet_name") or "").strip().split(" ")[0]) if body.get("pet_name") else ""
    if body.get("id"):
        child_profile.save(int(body["id"]), name=name, dob=dob, school=school, pet_name=pet)
    else:
        child_profile.add(name, dob, school, pet)
    sync_child()
    return api_children()


@app.delete("/api/children/<int:child_id>")
def api_children_delete(child_id):
    child_profile.delete(child_id)
    sync_child()
    return api_children()


@app.get("/api/stories")
def api_stories():
    """For the dashboard's Local tab: every story, its message and which languages are recorded."""
    return jsonify([{"id": s["id"], "title": s["title"],
                     "message": {l: stories.split_message(s["text"][l])[1] for l in stories.LANGS},
                     "ready": {l: os.path.exists(story_path(s, l)) for l in stories.LANGS}} for s in stories.STORIES])


@app.get("/api/story_audio")
def api_story_audio():
    st, lang = stories.BY_ID.get(request.args.get("id", "")), request.args.get("lang", "en")
    if not st or lang not in stories.LANGS:
        return jsonify(error="unknown story or language"), 404
    path = story_path(st, lang)
    if not os.path.exists(path):
        return jsonify(error="not recorded yet"), 404
    return wav_response(open(path, "rb").read(), Reply=st["title"][lang])


if __name__ == "__main__":
    prewarm_fillers()
    if os.environ.get("TALKTOY_RECORD_STORIES") == "1":
        record_stories()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
