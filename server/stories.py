"""Dikkey's own 30 stories, told without the LLM and spoken with offline voices.

"tell me a story" -> a story the toy hasn't told recently; "a story about a lion" -> the lion story.
Each story is spoken as: opening line + story + "here is my little message for you" + the last sentence
(every story's last sentence is its message for the child)."""
import random, re, unicodedata

from story_classic import CLASSIC
from story_new import NEW

STORIES = CLASSIC + NEW
BY_ID = {s["id"]: s for s in STORIES}
LANGS = ("en", "hi", "as", "mr")

# more words that point at a story, on top of each story's own tags
EXTRA_TAGS = {
    "monkey-crocodile": ["monkey", "बंदर", "বান্দৰ", "माकड"],
    "cap-seller": ["monkey", "बंदर", "বান্দৰ", "माकड"],
    "ant-grasshopper": ["ant", "चींटी", "পৰুৱা", "मुंगी"],
    "dove-ant": ["ant", "चींटी", "পৰুৱা", "मुंगी"],
    "tortoise-hare": ["rabbit", "खरगोश", "শহা", "ससा"],
    "rabbit-lion-well": ["rabbit", "lion", "खरगोश", "शेर", "শহা", "সিংহ", "ससा", "सिंह"],
    "four-friends": ["crow", "mouse", "tortoise", "कौआ", "चूहा", "कछुआ", "কাউৰী", "নিগনি", "কাছ", "कावळा", "उंदीर", "कासव"],
    "lost-star": ["dikkey", "dikky", "डिक्की", "ডিক্কী"],
    "mimi-kitten": ["grandma", "दादी", "আইতা", "आजी"],
}

OPEN = {"en": "Here is a story called {title}.", "hi": "सुनो एक कहानी, {title}।",
        "as": "শুনা এটা সাধু, {title}।", "mr": "ऐक एक गोष्ट, {title}."}
MESSAGE = {"en": "Here is my little message for you: ", "hi": "मेरी तरफ़ से तुम्हारे लिए एक छोटी-सी बात: ",
           "as": "তোমাৰ বাবে মোৰ এটা সৰু কথা: ", "mr": "तुझ्यासाठी माझा छोटासा संदेश: "}
# "yes" words beyond server.YES (Marathi / Assamese), for offers like "shall I play it?"
STORY_YES_ANY = re.compile(r"^\W*(?:हो|होय|हो ना|লাগিব|হয়|বাৰু|ঠিক আছে|go|go on|play it)\b|^\W*(?:हो|होय|হয়|বাৰু)", re.I)
SENTENCE_END = re.compile(r"[.!?।]['’\"]?\s+")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def split_message(text):
    """(story, message): the message is the story's last sentence."""
    ends = list(SENTENCE_END.finditer(text))
    cut = ends[-1].end()
    return text[:cut].strip(), text[cut:].strip()


def tags_of(story):
    return [nfc(t.lower()) for t in story["tags"] + EXTRA_TAGS.get(story["id"], [])]


def _has(tag, heard):
    if re.fullmatch(r"[a-z ]+", tag):     # English: whole words, so "ant" doesn't match "want"
        return re.search(rf"\b{re.escape(tag)}s?\b", heard) is not None
    return tag in heard


def matching(heard):
    h = nfc(heard.lower())
    return [s for s in STORIES if any(_has(t, h) for t in tags_of(s))]


def _norm(t):
    t = re.sub(r"[^\w\s]", " ", nfc(t.lower()))
    return " ".join(w for w in t.split() if w not in ("the", "a"))


def by_title(heard):
    """The story whose title the child said, in any language ("The Lion and the Mouse", "प्यासा कौआ").
    Also catches a clipped start from the speech recogniser ("toise and the hare")."""
    h = _norm(heard)
    if len(h) < 6:
        return None
    for st in STORIES:
        for title in st["title"].values():
            t = _norm(title)
            if t and (t in h or (len(h) >= 10 and h in t)):
                return st
    return None


def pick(heard, told, ready=None, rng=random):
    """A story for what the child said. told: ids already told to this toy (newest last).
    ready(story) -> bool: prefer stories whose audio is already recorded (only for a random pick)."""
    titled = by_title(heard)
    if titled:
        return titled
    named = matching(heard)
    pool = named or STORIES
    fresh = [s for s in pool if s["id"] not in told] or [s for s in pool if not told or s["id"] != told[-1]] or pool
    if not named and ready:
        fresh = [s for s in fresh if ready(s)] or fresh
    return rng.choice(fresh)


def telling(story, lang):
    """(display text, spoken text) in this language."""
    body, message = split_message(story["text"][lang])
    title = story["title"][lang]
    spoken = OPEN[lang].format(title=title) + " " + body + " " + MESSAGE[lang] + message
    display = f"📖 {title}\n\n{body}\n\n💛 {message}"
    return display, nfc(spoken)
