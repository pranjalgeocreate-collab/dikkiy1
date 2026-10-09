"""talktoy voice layer: turns text into a WAV clip, picking the right backend and caching it.

Backends, in the order speak() tries them for a given voice name:
  eleven-<lang>-<id>    ElevenLabs (online, needs ELEVENLABS_API_KEY)
  cartesia-<lang>       Cartesia Sonic (online, needs CARTESIA_API_KEY; no Assamese)
  indic-<pack>-<speaker> AI4Bharat Indic-TTS, served by indic_worker.py on INDIC_URL
  anything else          a local Piper voice (voices/<name>.onnx)
Any online backend that fails falls back to OFFLINE_VOICE[lang] automatically.

`settings` is set once by server.py right after it loads settings.json (voices.settings = settings),
so every function here sees the same live dict server.py mutates - no separate copy, no circular import.
"""
import hashlib, io, json, os, re, ssl, subprocess, urllib.request, wave

import certifi
from piper import PiperVoice, SynthesisConfig

import skills

HERE = os.path.dirname(os.path.abspath(__file__))
TLS = ssl.create_default_context(cafile=certifi.where())
FFMPEG = os.environ.get("FFMPEG", "/usr/local/bin/ffmpeg")
VOICE_DIR = os.path.join(HERE, "voices")
FILLER_DIR = os.path.join(HERE, "fillers")
RECORDED_DIR = os.path.join(HERE, "recorded")   # fixed lines recorded once (e.g. with ElevenLabs), played offline
CACHEABLE = {"abc", "varnamala", "barakhadi", "rhyme", "days", "months", "table", "count", "count_along", "colors",
            "clock_lesson", "letter", "phonics"}

settings = None   # set by server.py: voices.settings = settings, right after load_settings()

# ElevenLabs (online). Built-in voices, because this key may not list voices. v4 turbo is the fast model that knows Assamese and Marathi.
ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/"
ELEVEN_VOICES = {"cgSgspJ2msm6clMCkdW9": "Jessica · young, playful", "pFZP5JQG7iQjIQuC4Bku": "Lily · warm",
                 "FGY2WhTYpPnrIDTdsKH5": "Laura · bright", "XrExE9yKIg1WjnnlVkGX": "Matilda · friendly",
                 "TX3LPaxmHKxFdv7VOQHJ": "Liam · young boy-ish", "IKne3meq5aSn9XLyUdCD": "Charlie · cheerful"}
ELEVEN_MODEL = {"en": "eleven_flash_v2_5", "hi": "eleven_flash_v2_5", "as": "eleven_v4_turbo", "mr": "eleven_v4_turbo"}   # fastest per language (timed 09-30)
ELEVEN_LOCALE = {"en": "en", "hi": "hi_IN", "as": "as_IN", "mr": "mr_IN"}


def eleven_speak(text, lang, voice_id, speed):
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    # the dashboard speed is Piper's length scale (bigger = slower); ElevenLabs takes a rate between 0.7 and 1.2
    rate = round(min(1.2, max(0.7, 1 / speed)), 2)
    body = json.dumps({"text": text, "model_id": ELEVEN_MODEL.get(lang, "eleven_v3"),
                       "voice_settings": {"speed": rate, "stability": 0.5, "similarity_boost": 0.75}}).encode()
    req = urllib.request.Request(ELEVEN_URL + voice_id + "?output_format=pcm_22050", body,
                                 {"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=TLS) as r:
        pcm = r.read()
    if not pcm:
        raise RuntimeError("elevenlabs returned no audio")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
        wf.writeframes(pcm)
    return buf.getvalue()


# Cartesia (online). One multilingual voice; language is set per call. No Assamese as of this model.
CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_VOICE = "e3827ec5-697a-4b7c-9704-1a23041bbc51"   # "Dottie - Sweet Gal": very young, high-pitched, for kids
CARTESIA_MODEL = "sonic-3.6"   # sonic-2 was sunsetted 2026-10


def cartesia_speak(text, lang):
    key = os.environ.get("CARTESIA_API_KEY", "")
    if not key:
        raise RuntimeError("CARTESIA_API_KEY is not set")
    body = json.dumps({"model_id": CARTESIA_MODEL, "transcript": text,
                       "voice": {"mode": "id", "id": CARTESIA_VOICE},
                       "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 22050},
                       "language": lang}).encode()
    req = urllib.request.Request(CARTESIA_URL, body, {"X-API-Key": key, "Cartesia-Version": "2024-06-10",
                                                       "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=TLS) as r:
        audio = r.read()
    if not audio:
        raise RuntimeError("cartesia returned no audio")
    return audio


# AI4Bharat Indic-TTS runs in indic_worker.py (own venv, needs PyTorch).
INDIC_URL = os.environ.get("INDIC_URL", "http://127.0.0.1:8702")
# name -> (pack, speaker, lang, locale, label). en+hi names are fixed (saved in settings);
# other packs (e.g. "as") are added from whatever speakers the worker reports.
INDIC_FIXED = {"indic-female": ("en+hi", "female", "en", "en_IN", "Indian English · Female (AI4Bharat)"),
               "indic-male": ("en+hi", "male", "en", "en_IN", "Indian English · Male (AI4Bharat)"),
               "indic-hindifemale": ("en+hi", "hindifemale", "hi", "hi_IN", "हिंदी · Female (AI4Bharat)"),
               "indic-hindimale": ("en+hi", "hindimale", "hi", "hi_IN", "हिंदी · Male (AI4Bharat)")}
PACK_LANG = {"as": ("as", "as_IN", "অসমীয়া")}


def indic_catalog():
    try:
        with urllib.request.urlopen(INDIC_URL + "/", timeout=2) as r:
            packs = json.load(r).get("packs", {})
    except Exception:
        return {}
    cat = {k: v for k, v in INDIC_FIXED.items() if v[0] in packs}
    for pack, speakers in packs.items():
        if pack in PACK_LANG:
            lang, locale, title = PACK_LANG[pack]
            for spk in speakers:
                cat[f"indic-{pack}-{spk}"] = (pack, spk, lang, locale, f"{title} · {spk.title()} (AI4Bharat)")
    return cat


def indic_speak(text, pack, speaker, speed):
    req = urllib.request.Request(INDIC_URL + "/speak", json.dumps({"text": text, "pack": pack, "speaker": speaker,
                                                                   "speed": speed}).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=420) as r:  # one at a time; a story can queue behind another
        return r.read()


# if an online voice can't be reached (no internet, credit used up) these offline voices speak instead
OFFLINE_VOICE = {"en": "child-en", "hi": "child-indic-hi", "as": "indic-as-female", "mr": "hi_IN-priyamvada-medium"}
# Piper has no child voices, so these are a light adult voice pitched up with ffmpeg.
CHILD_VOICES = {"child-en": ("en_US-amy-medium", "en", "en_US", "Child (Amy, pitched up)"),
                "child-hi": ("hi_IN-priyamvada-medium", "hi", "hi_IN", "बच्चा · Child (Priyamvada, pitched up)"),
                "child-indic-en": ("indic-female", "en", "en_IN", "Child · Indian (AI4Bharat, pitched up)"),
                "child-indic-hi": ("indic-hindifemale", "hi", "hi_IN", "बच्चा · Indian (AI4Bharat, pitched up)"),
                "child-indic-as": ("indic-as-female", "as", "as_IN", "শিশু · Child (AI4Bharat, pitched up)")}

DEVANAGARI = re.compile(r"[ऀ-ॣ०-ॿ]")  # not the danda ।॥: Assamese/Bengali use it too
ASSAMESE = re.compile(r"[ঀ-৿]")  # Bengali-Assamese script block


def script_lang(text, default):
    # Marathi and Hindi share Devanagari, so the picked language decides between them
    return ("mr" if default == "mr" else "hi") if DEVANAGARI.search(text) else "as" if ASSAMESE.search(text) else default


_voice_cache = {}


def get_voice(name):
    name = CHILD_VOICES.get(name, (name,))[0]
    if name.startswith(("indic-", "eleven-", "cartesia-")):
        return None  # synthesized by indic_worker.py / ElevenLabs / Cartesia
    if name not in _voice_cache:
        print("loading piper voice", name, flush=True)
        _voice_cache[name] = PiperVoice.load(os.path.join(VOICE_DIR, name + ".onnx"))
    return _voice_cache[name]


def installed_voices():
    out = []
    for f in sorted(os.listdir(VOICE_DIR)):
        if f.endswith(".onnx") and os.path.exists(os.path.join(VOICE_DIR, f + ".json")):
            name = f[:-5]
            lang_code, speaker = name.split("-")[0], name.split("-")[1]
            out.append({"name": name, "lang": lang_code.split("_")[0], "locale": lang_code,
                        "speaker": speaker.replace("_", " ").title()})
    for name, (_, _, lang, locale, label) in indic_catalog().items():
        out.append({"name": name, "lang": lang, "locale": locale, "speaker": label, "indian": True})
    have = {v["name"] for v in out}
    for name, (base, lang, locale, label) in CHILD_VOICES.items():
        if base in have and os.path.exists(FFMPEG):
            out.insert(0, {"name": name, "lang": lang, "locale": locale, "speaker": label, "child": True})
    if os.environ.get("ELEVENLABS_API_KEY"):
        for lang, locale in ELEVEN_LOCALE.items():
            for vid, label in ELEVEN_VOICES.items():
                out.append({"name": f"eleven-{lang}-{vid}", "lang": lang, "locale": locale,
                            "speaker": label + " (ElevenLabs)", "eleven": True})
    return out


def pitch_up(wav_bytes, factor):
    """Raise pitch (and formants, which is what makes it sound young) without changing speed."""
    rate = wave.open(io.BytesIO(wav_bytes)).getframerate()
    af = f"asetrate={rate}*{factor},aresample={rate},atempo={1 / factor:.4f}"
    # Raw PCM out, then wrap it ourselves: ffmpeg can't seek a pipe, so its WAV header
    # would claim a ~37-hour length.
    out = subprocess.run([FFMPEG, "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-af", af,
                          "-f", "s16le", "-ac", "1", "-ar", str(rate), "pipe:1"],
                         input=wav_bytes, capture_output=True, timeout=30)
    if out.returncode != 0 or not out.stdout:
        return wav_bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(out.stdout)
    return buf.getvalue()


def join_wavs(first, second, gap=0.4):
    """first + a short pause + second, resampling second to first's rate if they differ."""
    a, b = wave.open(io.BytesIO(first)), wave.open(io.BytesIO(second))
    rate = a.getframerate()
    pcm_b = b.readframes(b.getnframes())
    if b.getframerate() != rate or b.getnchannels() != 1:
        out = subprocess.run([FFMPEG, "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-ac", "1", "-ar", str(rate),
                              "-f", "s16le", "pipe:1"], input=second, capture_output=True, timeout=60)
        pcm_b = out.stdout
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(a.readframes(a.getnframes()) + b"\x00\x00" * int(rate * gap) + pcm_b)
    return buf.getvalue()


def voice_in_use(lang):
    name = settings["voice_" + lang]
    return OFFLINE_VOICE[lang] if settings["llm"] == "local" and name.startswith("eleven-") else name


def filler_path(lang, text, speed=None):
    # keyed on everything that changes the sound, so a new voice/speed/pitch gets fresh clips.
    # CARTESIA_VOICE is a hardcoded constant, not a setting, but still changes the actual audio.
    key = json.dumps([voice_in_use(lang), CARTESIA_VOICE, speed if speed is not None else settings["speed"],
                      settings["child_pitch"], text], ensure_ascii=False)
    return os.path.join(FILLER_DIR, lang + "-" + hashlib.sha1(key.encode()).hexdigest()[:16] + ".wav")


def recorded_path(text, lang):
    return os.path.join(RECORDED_DIR, lang + "-" + hashlib.sha1(skills.nfc(text.strip()).encode()).hexdigest()[:16] + ".wav")


def speak(text, lang="en", voice_name=None, speed=None):
    if not voice_name and os.path.exists(recorded_path(text, lang)):   # a pre-recorded clip of this exact line
        return open(recorded_path(text, lang), "rb").read()
    lang = script_lang(text, lang)   # speak whatever script the reply came back in
    text = skills.spell_numbers(text, lang)
    name = voice_name or settings["voice_" + lang]
    if not voice_name:
        name = voice_in_use(lang)
    base = CHILD_VOICES.get(name, (name,))[0]
    if base.startswith("eleven-"):
        try:
            return eleven_speak(text, base.split("-")[1], base.split("-", 2)[2], speed or settings["speed"])
        except Exception as e:
            print("elevenlabs failed, using the offline voice:", e, flush=True)
            name = base = OFFLINE_VOICE[lang]
            base = CHILD_VOICES.get(name, (name,))[0]
    if base.startswith("cartesia-"):
        try:
            return cartesia_speak(text, base.split("-", 1)[1])
        except Exception as e:
            print("cartesia failed, using the offline voice:", e, flush=True)
            name = base = OFFLINE_VOICE[lang]
            base = CHILD_VOICES.get(name, (name,))[0]
    if base.startswith("indic-"):
        entry = indic_catalog().get(base)
        if not entry:
            raise RuntimeError(f"{base}: Indian voice worker is not running or lacks that pack")
        audio = indic_speak(text, entry[0], entry[1], speed or settings["speed"])
    else:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            get_voice(base).synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=speed or settings["speed"]))
        audio = buf.getvalue()
    return pitch_up(audio, settings["child_pitch"]) if name in CHILD_VOICES else audio


def speak_cached(text, lang, speed=None):
    """Skill answers never change, so keep their audio (keyed on voice/speed/pitch like fillers)."""
    path = filler_path(script_lang(text, lang), text, speed).replace(os.sep + "fillers" + os.sep, os.sep + "fillers" + os.sep + "skill-")
    if os.path.exists(path):
        return open(path, "rb").read()
    audio = speak(text, lang, speed=speed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path + ".tmp", "wb").write(audio)
    os.replace(path + ".tmp", path)
    return audio


def speak_skill(sk, lang):
    """Synthesize a Skill's audio: one clip normally, or several joined clips when .audio_parts is
    set (some offline voices cap input length, so a long recitation is split and stitched)."""
    voice_lang = sk.speak_lang or lang
    cacheable = sk.name in CACHEABLE
    if sk.audio_parts:
        audio = None
        for part in sk.audio_parts:
            clip = speak_cached(part, voice_lang, sk.speed) if cacheable else speak(part, voice_lang, speed=sk.speed)
            audio = clip if audio is None else join_wavs(audio, clip, gap=0.3)
        return audio
    return speak_cached(sk.speech, voice_lang, sk.speed) if cacheable else speak(sk.speech, voice_lang, speed=sk.speed)
