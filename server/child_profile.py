"""Dikkey asks the child's name and birthday and remembers them (children.db, on this Mac only).

Scripted, not the LLM: the cloud brain never sees the date of birth, only the first name and age (as before).
Only the first name is kept. Flow: a greeting from a child Dikkey doesn't know -> "What's your name?" ->
birthday -> school -> pet name (each can be skipped); Dikkey then calls the child by the pet name.
The school name stays on this Mac: it is never sent to the brain. Also: "my name is X", "what's my name?",
"what's my school?", "when is my birthday?", "how old am I?", and a happy-birthday greeting on the day."""
import datetime, re, sqlite3, threading, unicodedata

import skills

LANGS = ("en", "hi", "as", "mr")
_lock = threading.Lock()
DB = None


def nfc(s):
    return unicodedata.normalize("NFC", s)


def open_db(path):
    global DB
    DB = sqlite3.connect(path, check_same_thread=False)
    DB.row_factory = sqlite3.Row
    DB.execute("""CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, dob TEXT, created REAL, last_seen REAL, greeted_on TEXT)""")
    have = {r[1] for r in DB.execute("PRAGMA table_info(children)")}
    for col in ("school", "pet_name"):   # added 09-30; older databases get the columns
        if col not in have:
            DB.execute(f"ALTER TABLE children ADD COLUMN {col} TEXT")
    DB.commit()


LATIN = re.compile(r"^[A-Za-z' -]+$")
DEVA = re.compile(r"[\u0900-\u097F]")
BENG = re.compile(r"[\u0980-\u09FF]")


def _to_latin(name):
    """Indian script -> plain English letters, for the English voice ("মুনু" -> "Munu")."""
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    dev = _beng_to_deva(name) if BENG.search(name) else name
    out = unicodedata.normalize("NFKD", transliterate(dev, sanscript.DEVANAGARI, sanscript.IAST))
    out = "".join(c for c in out if not unicodedata.combining(c))
    return out[:1].upper() + out[1:]


def _latin_to_deva(name):
    """"Munu" -> "मुनु", "Riya" -> "रिया", "Aarav" -> "आरव" (names ending in -a get a long a)."""
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    n = name.lower().replace("w", "v")
    if len(n) > 2 and n.endswith("a") and n[-2] not in "aeiou":
        n += "a"
    return transliterate(n, sanscript.ITRANS, sanscript.DEVANAGARI).rstrip("\u094d")   # no dangling halant


def _deva_to_assamese(t):
    """Devanagari -> Assamese letters: same layout shifted by 0x80, with Assamese ৰ (ra) and ৱ (wa)."""
    out = []
    for c in t:
        o = ord(c)
        if c == "\u0930":
            out.append("\u09f0")          # र -> ৰ
        elif c == "\u0935":
            out.append("\u09f1")          # व -> ৱ
        elif c == "\u092f" and (not out or out[-1] != "\u09cd"):
            out.append("\u09df")          # य -> য় (plain য reads "z"; after ্ it stays য as in জ্যোতি)
        elif 0x0900 <= o <= 0x097F:
            out.append(chr(o + 0x80))
        else:
            out.append(c)
    return "".join(out)


def _beng_to_deva(t):
    out = []
    for c in t:
        o = ord(c)
        if c in "\u09f0\u09b0":
            out.append("\u0930")
        elif c == "\u09f1":
            out.append("\u0935")
        elif 0x0980 <= o <= 0x09FF:
            out.append(chr(o - 0x80))
        else:
            out.append(c)
    return "".join(out)


def name_in(name, lang):
    """The child's name written so that this language's voice can say it (the same voice as the reply)."""
    if not name:
        return name
    try:
        if lang == "en":
            return name if LATIN.match(name) else _to_latin(name)
        if lang in ("hi", "mr"):
            if DEVA.search(name):
                return name
            return nfc(_beng_to_deva(name) if BENG.search(name) else _latin_to_deva(name))
        if lang == "as":
            if BENG.search(name):
                return name
            return nfc(_deva_to_assamese(name if DEVA.search(name) else _latin_to_deva(name)))
    except Exception:
        pass
    return name


def call_name(row):
    """What Dikkey calls the child: the pet name if there is one."""
    return (row["pet_name"] or row["name"]) if row else None


def _now():
    return datetime.datetime.now().timestamp()


def current():
    """The child Dikkey is talking to: the one seen most recently."""
    with _lock:
        return DB.execute("SELECT * FROM children ORDER BY last_seen DESC LIMIT 1").fetchone()


def all_children():
    with _lock:
        return [dict(r) for r in DB.execute("SELECT * FROM children ORDER BY last_seen DESC")]


def remember_name(name):
    """Existing child with that name becomes current; otherwise a new child. Returns the row."""
    with _lock:
        row = DB.execute("SELECT * FROM children WHERE lower(name) = lower(?)", (name,)).fetchone()
        if row:
            DB.execute("UPDATE children SET last_seen = ? WHERE id = ?", (_now(), row["id"]))
        else:
            DB.execute("INSERT INTO children (name, created, last_seen) VALUES (?, ?, ?)", (name, _now(), _now()))
        DB.commit()
        return DB.execute("SELECT * FROM children WHERE lower(name) = lower(?)", (name,)).fetchone()


def save(child_id, name=None, dob=None, school=None, pet_name=None):
    with _lock:
        if school is not None:
            DB.execute("UPDATE children SET school = ? WHERE id = ?", (school or None, child_id))
        if pet_name is not None:
            DB.execute("UPDATE children SET pet_name = ? WHERE id = ?", (pet_name or None, child_id))
        if name is not None:
            DB.execute("UPDATE children SET name = ? WHERE id = ?", (name, child_id))
        if dob is not None:
            DB.execute("UPDATE children SET dob = ? WHERE id = ?", (dob or None, child_id))
        DB.execute("UPDATE children SET last_seen = ? WHERE id = ?", (_now(), child_id))
        DB.commit()


def add(name, dob=None, school=None, pet_name=None):
    with _lock:
        DB.execute("INSERT INTO children (name, dob, school, pet_name, created, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                   (name, dob or None, school or None, pet_name or None, _now(), _now()))
        DB.commit()


def delete(child_id):
    with _lock:
        DB.execute("DELETE FROM children WHERE id = ?", (child_id,))
        DB.commit()


def mark_greeted(child_id, day):
    with _lock:
        DB.execute("UPDATE children SET greeted_on = ? WHERE id = ?", (day, child_id))
        DB.commit()


# ------------------------------------------------------------------ dates
def split_dob(dob):
    """'2019-03-05' -> (2019, 3, 5); '--03-05' (no year) -> (None, 3, 5)."""
    y, m, d = dob.split("-")[-3:] if not dob.startswith("--") else (None, *dob[2:].split("-"))
    return (int(y) if y else None), int(m), int(d)


def age_of(dob, today):
    y, m, d = split_dob(dob)
    if not y:
        return None
    return today.year - y - ((today.month, today.day) < (m, d))


MONTHS = {
    "en": "January February March April May June July August September October November December".split(),
    "hi": "जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर".split(),
    "as": "জানুৱাৰী ফেব্ৰুৱাৰী মাৰ্চ এপ্ৰিল মে' জুন জুলাই আগষ্ট ছেপ্টেম্বৰ অক্টোবৰ নৱেম্বৰ ডিচেম্বৰ".split(),
    "mr": "जानेवारी फेब्रुवारी मार्च एप्रिल मे जून जुलै ऑगस्ट सप्टेंबर ऑक्टोबर नोव्हेंबर डिसेंबर".split(),
}
MONTH_ALIASES = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
                 "nov": 11, "dec": 12, "फरवरी": 2, "सितम्बर": 9, "नवम्बर": 11, "दिसम्बर": 12, "अगस्त": 8,
                 "মে": 5, "আগষ্ট": 8, "আগস্ট": 8, "চেপ্টেম্বৰ": 9, "ছেপ্তেম্বৰ": 9, "নভেম্বৰ": 11, "ডিচেম্বাৰ": 12,
                 "सप्टेम्बर": 9, "नोव्हेम्बर": 11, "डिसेम्बर": 12, "ओगस्ट": 8}
NUM = {  # 1..31 as words, for speaking and for reading what the child said
    "hi": "एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस "
          "तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस".split(),
    "as": "এক দুই তিনি চাৰি পাঁচ ছয় সাত আঠ ন দহ এঘাৰ বাৰ তেৰ চৈধ্য পোন্ধৰ ষোল্ল সোতৰ ওঠৰ ঊনৈশ বিশ একৈশ বাইশ "
          "তেইশ চৌবিশ পঁচিশ ছাব্বিশ সাতাইশ আঠাইশ ঊনত্ৰিশ ত্ৰিশ একত্ৰিশ".split(),
    "mr": "एक दोन तीन चार पाच सहा सात आठ नऊ दहा अकरा बारा तेरा चौदा पंधरा सोळा सतरा अठरा एकोणीस वीस एकवीस बावीस "
          "तेवीस चोवीस पंचवीस सव्वीस सत्तावीस अठ्ठावीस एकोणतीस तीस एकतीस".split(),
}
NUM_EXTRA = {"ঊনৈছ": 19, "বিছ": 20, "একৈছ": 21, "বাইছ": 22, "তেইছ": 23, "চৌবিছ": 24, "পঁচিছ": 25, "ছয়": 6,
             "छः": 6, "पांच": 5, "नव": 9}
THOUSAND = r"thousand|हज़ार|हजार|হাজাৰ"
BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
EN_ORD = {skills.en_ordinal(n).lower(): n for n in range(1, 32)} if hasattr(skills, "en_ordinal") else {}


def num_word(n, lang):
    return skills.en_words(n) if lang == "en" else NUM[lang][n - 1] if 1 <= n <= 31 else str(n)


def say_date(m, d, lang):
    if lang == "en":
        return f"the {skills.en_ordinal(d) if hasattr(skills, 'en_ordinal') else d} of {MONTHS['en'][m - 1]}"
    return f"{num_word(d, lang)} {MONTHS[lang][m - 1]}"


def show_date(dob):
    y, m, d = split_dob(dob)
    return f"{d} {MONTHS['en'][m - 1]}" + (f" {y}" if y else "")


def _to_digits(text):
    t = nfc(text.lower()).translate(BENGALI_DIGITS)
    t = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", t)
    for w, n in sorted(EN_ORD.items(), key=lambda x: -len(x[0])):
        t = re.sub(rf"\b{re.escape(w)}\b", str(n), t)
    t = skills.words_to_digits(t)                           # English + Hindi number words
    words = {w: i + 1 for lang in ("as", "mr") for i, w in enumerate(NUM[lang])}
    words.update(NUM_EXTRA)
    for w in sorted(words, key=len, reverse=True):
        t = re.sub(rf"(?<![ऀ-৿]){re.escape(w)}(?![ऀ-৿])", str(words[w]), t)
    t = re.sub(rf"(\d+)\s*(?:{THOUSAND})\s*(?:and\s*)?(\d+)?", lambda m: str(int(m.group(1)) * 1000 + int(m.group(2) or 0)), t)
    t = re.sub(r"\b(19|20)\s+(\d{2})\b", r"\1\2", t)       # "twenty nineteen" -> 20 19 -> 2019
    return t


def parse_dob(text, today):
    """'5 March 2019', 'march 5th 2019', '5/3/2019', 'पाँच मार्च दो हज़ार उन्नीस', 'পাঁচ মাৰ্চ' ... -> 'YYYY-MM-DD' or '--MM-DD'."""
    t = _to_digits(text)
    m = y = d = None
    num = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", t)     # Indian order: day/month/year
    if num:
        d, m, y = int(num.group(1)), int(num.group(2)), int(num.group(3))
        y = y + 2000 if y < 100 else y
    else:
        low = nfc(text.lower())
        names = [(nfc(n.lower()), i + 1) for lang in MONTHS for i, n in enumerate(MONTHS[lang])]
        names += [(nfc(k), v) for k, v in MONTH_ALIASES.items()]
        for n, i in sorted(names, key=lambda x: -len(x[0])):
            if (re.search(rf"\b{re.escape(n)}\b", low) if re.fullmatch(r"[a-z]+", n) else n in low):
                m = i
                break
        if not m:
            return None
        nums = [int(x) for x in re.findall(r"\d+", t)]
        years = [n for n in nums if n >= 1000]
        days = [n for n in nums if 1 <= n <= 31]
        if not days:
            return None
        if years and not today.year - 18 <= years[0] <= today.year:   # a year was said, but not a child's
            return None
        d, y = days[0], (years[0] if years else None)
    try:
        born = datetime.date(y or 2000, m, d)
    except ValueError:
        return None
    if y and not (0 <= today.year - y <= 18 and born <= today):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}" if y else f"--{m:02d}-{d:02d}"


# ------------------------------------------------------------------ names
NAME_SAID = [
    re.compile(r"(?:my name is|my name's|call me|i am called|i'm called)\s+([a-z][a-z'-]*)", re.I),
    re.compile(r"(?:मेरा नाम|मेरा नाम है)\s+([ऀ-ॿ]+)"),
    re.compile(r"(?:माझं नाव|माझे नाव|माझ नाव|माझं नाव आहे)\s+([ऀ-ॿ]+)"),
    re.compile(r"(?:মোৰ নাম)\s+([ঀ-৿]+)"),
]
NOT_NAMES = {"is", "hai", "है", "हैं", "आहे", "হয়", "what", "yes", "no", "hi", "hello", "dikkey", "dikky", "क्या", "काय", "কি",
             "नहीं", "नाही", "নাই", "okay", "ok", "the", "a"}


def said_name(text):
    """Only an explicit 'my name is X' (used any time)."""
    for p in NAME_SAID:
        m = p.search(nfc(text))
        if m and m.group(1).lower() not in NOT_NAMES:
            return clean_name(m.group(1))
    return None


def answer_name(text):
    """Reply to 'what's your name?': 'my name is Aarav', 'I'm Aarav', or just 'Aarav'."""
    n = said_name(text)
    if n:
        return n
    t = nfc(text).strip()
    m = re.match(r"(?:i am|i'm|its|it's|मैं|मी|মই)\s+(\S+)", t, re.I)
    if m and m.group(1).lower() not in NOT_NAMES:
        return clean_name(m.group(1))
    words = re.sub(r"[^\w\s'ऀ-৿-]", " ", t).split()
    words = [w for w in words if w.lower() not in NOT_NAMES]
    if 1 <= len(words) <= 2:
        return clean_name(words[0])
    return None


SCHOOL_LEAD = re.compile(r"^\W*(?:my\s+school(?:'s)?(?:\s+name)?\s+is|i\s+go\s+to|i\s+study\s+(?:at|in)|it'?s|the\s+school\s+is|"
                         r"मेरे\s*स्कूल\s*का\s*नाम|मेरा\s*स्कूल|मैं|माझ्या\s*शाळेचं\s*नाव|माझ्या\s*शाळेचे\s*नाव|माझी\s*शाळा|मी|"
                         r"মোৰ\s*স্কুলৰ\s*নাম|মোৰ\s*বিদ্যালয়ৰ\s*নাম|মোৰ\s*স্কুল|মই)\s*", re.I)
SCHOOL_TAIL = re.compile(r"\s*(?:है|हैं|में\s*पढ़ता\s*हूँ|में\s*पढ़ती\s*हूँ|आहे|मध्ये\s*शिकतो|मध्ये\s*शिकते|হয়|ত\s*পঢ়োঁ)?\W*$")
PET_LEAD = re.compile(r"^\W*(?:(?:you\s+can\s+)?call\s+me|my\s+(?:pet\s+name|nickname|home\s+name)\s+is|they\s+call\s+me|everyone\s+calls\s+me|it'?s|"
                      r"मुझे|मेरा\s*(?:निकनेम|प्यार\s*का\s*नाम|घर\s*का\s*नाम)|मला|माझं\s*(?:टोपणनाव|लाडकं\s*नाव)|"
                      r"মোক|মোৰ\s*(?:মৰমৰ|ঘৰুৱা|আদৰৰ)\s*নাম)\s*", re.I)
PET_TAIL = re.compile(r"\s*(?:बुलाते\s*हैं|कहते\s*हैं|बुलाओ|कहो|है|म्हणतात|म्हण|आहे|বুলি\s*মাতে|বুলি\s*মাতিবা|বুলি|হয়)?\W*$")
NO_PET = re.compile(r"^\W*(?:no|none|nothing|no\s+pet\s+name|just\s+my\s+name|कोई\s*नहीं|नहीं|नाही|काही\s*नाही|নাই|নাই\s*দিয়া)\b", re.I)


def answer_school(text):
    t = SCHOOL_TAIL.sub("", SCHOOL_LEAD.sub("", nfc(text).strip()))
    t = re.sub(r"[^\w\s.'&\u0900-\u09FF-]", "", t).strip()
    return t[:60] if len(t) >= 2 and t.lower() not in NOT_NAMES else None


def answer_pet(text):
    t = PET_TAIL.sub("", PET_LEAD.sub("", nfc(text).strip()))
    words = [w for w in re.sub(r"[^\w\s'\u0900-\u09FF-]", " ", t).split() if w.lower() not in NOT_NAMES]
    return clean_name(words[0]) if 1 <= len(words) <= 2 else None


def clean_name(w):
    w = re.sub(r"[^\w'ऀ-৿-]", "", w)[:20]
    if not w or any(c.isdigit() for c in w):
        return None
    return w[:1].upper() + w[1:] if re.fullmatch(r"[a-zA-Z'-]+", w) else w


# ------------------------------------------------------------------ what Dikkey says
L = {
    "ask_name": {"en": "Hi! I'm Dikkey. What's your name?", "hi": "नमस्ते! मैं डिक्की हूँ। तुम्हारा नाम क्या है?",
                 "as": "নমস্কাৰ! মই ডিক্কী। তোমাৰ নাম কি?", "mr": "नमस्कार! मी डिक्की. तुझं नाव काय?"},
    "name_again": {"en": "Sorry, I didn't catch it. What's your name?", "hi": "माफ़ करना, मैंने सुना नहीं। तुम्हारा नाम क्या है?",
                   "as": "দুঃখিত, মই শুনা নাপালোঁ। তোমাৰ নাম কি?", "mr": "सॉरी, मला ऐकू आलं नाही. तुझं नाव काय?"},
    "ask_dob": {"en": "Nice to meet you, {name}! When is your birthday? Tell me the day, the month and the year you were born.",
                "hi": "तुमसे मिलकर अच्छा लगा, {name}! तुम्हारा जन्मदिन कब है? दिन, महीना और साल बताओ।",
                "as": "তোমাক লগ পাই ভাল লাগিল, {name}! তোমাৰ জন্মদিন কেতিয়া? দিন, মাহ আৰু বছৰ কোৱা।",
                "mr": "तुला भेटून छान वाटलं, {name}! तुझा वाढदिवस कधी असतो? दिवस, महिना आणि वर्ष सांग."},
    "dob_again": {"en": "Sorry, I didn't understand. Say it like this: fifth of March, twenty nineteen.",
                  "hi": "मैं समझ नहीं पाया। ऐसे बताओ: पाँच मार्च, दो हज़ार उन्नीस।",
                  "as": "মই বুজি নাপালোঁ। এনেকৈ কোৱা: পাঁচ মাৰ্চ, দুই হাজাৰ ঊনৈশ।",
                  "mr": "मला कळलं नाही. असं सांग: पाच मार्च, दोन हजार एकोणीस."},
    "dob_skip": {"en": "That's okay! A grown-up can tell me later.", "hi": "कोई बात नहीं! कोई बड़ा बाद में बता देगा।",
                 "as": "ঠিক আছে! পিছত কোনো ডাঙৰ মানুহে মোক ক'ব পাৰিব।", "mr": "काही हरकत नाही! मोठं कोणीतरी नंतर सांगेल."},
    "saved": {"en": "Thank you, {name}! I will remember that your birthday is {date}.",
              "hi": "धन्यवाद, {name}! मुझे याद रहेगा कि तुम्हारा जन्मदिन {date} को है।",
              "as": "ধন্যবাদ, {name}! মই মনত ৰাখিম যে তোমাৰ জন্মদিন {date}।",
              "mr": "धन्यवाद, {name}! तुझा वाढदिवस {date} ला असतो, हे मी लक्षात ठेवीन."},
    "ask_school": {"en": "And what is the name of your school?", "hi": "और तुम्हारे स्कूल का नाम क्या है?",
                   "as": "আৰু তোমাৰ স্কুলৰ নাম কি?", "mr": "आणि तुझ्या शाळेचं नाव काय?"},
    "ask_pet": {"en": "Lovely! What does your family call you at home? I will call you by your pet name.",
                "hi": "बहुत बढ़िया! घर पर सब तुम्हें प्यार से क्या बुलाते हैं? मैं भी तुम्हें उसी प्यार के नाम से बुलाऊँगा।",
                "as": "বৰ ভাল! ঘৰত সকলোৱে তোমাক মৰমেৰে কি বুলি মাতে? মইও তোমাক সেই মৰমৰ নামেৰে মাতিম।",
                "mr": "छान! घरी सगळे तुला लाडाने काय म्हणतात? मीही तुला त्याच लाडक्या नावाने हाक मारेन."},
    "pet_saved": {"en": "Okay, {pet}! From now on I'll call you {pet}.", "hi": "ठीक है, {pet}! अब से मैं तुम्हें {pet} बुलाऊँगा।",
                  "as": "ঠিক আছে, {pet}! এতিয়াৰ পৰা মই তোমাক {pet} বুলি মাতিম।", "mr": "ठीक आहे, {pet}! आतापासून मी तुला {pet} म्हणेन."},
    "no_pet": {"en": "Okay, I'll call you {name}!", "hi": "ठीक है, मैं तुम्हें {name} बुलाऊँगा!", "as": "ঠিক আছে, মই তোমাক {name} বুলি মাতিম!",
               "mr": "ठीक आहे, मी तुला {name} म्हणेन!"},
    "your_school": {"en": "Your school is {school}.", "hi": "तुम्हारा स्कूल {school} है।", "as": "তোমাৰ স্কুল {school}।",
                    "mr": "तुझी शाळा {school} आहे."},
    "no_school": {"en": "You haven't told me your school yet! What is its name?", "hi": "तुमने अभी तक अपने स्कूल का नाम नहीं बताया! क्या है?",
                  "as": "তুমি এতিয়াও তোমাৰ স্কুলৰ নাম কোৱা নাই! কি?", "mr": "तू अजून तुझ्या शाळेचं नाव सांगितलं नाहीस! काय आहे?"},
    "hello_name": {"en": "Hello, {name}!", "hi": "नमस्ते, {name}!", "as": "নমস্কাৰ, {name}!", "mr": "नमस्कार, {name}!"},
    "hello_again": {"en": "Hello again, {name}! I remember you.", "hi": "फिर से नमस्ते, {name}! मुझे तुम याद हो।",
                    "as": "আকৌ নমস্কাৰ, {name}! মোৰ তোমাক মনত আছে।", "mr": "पुन्हा नमस्कार, {name}! तू मला आठवतोस."},
    "your_name": {"en": "Your name is {name}!", "hi": "तुम्हारा नाम {name} है!", "as": "তোমাৰ নাম {name}!", "mr": "तुझं नाव {name} आहे!"},
    "your_bday": {"en": "Your birthday is {date}!", "hi": "तुम्हारा जन्मदिन {date} को है!", "as": "তোমাৰ জন্মদিন {date}!",
                  "mr": "तुझा वाढदिवस {date} ला असतो!"},
    "your_age": {"en": "You are {age} years old!", "hi": "तुम्हारी उम्र {age} साल है!", "as": "তোমাৰ বয়স {age} বছৰ!",
                 "mr": "तुझं वय {age} वर्षं आहे!"},
    "dont_know": {"en": "I don't know yet! What's your name?", "hi": "मुझे अभी पता नहीं! तुम्हारा नाम क्या है?",
                  "as": "মই এতিয়াও নাজানো! তোমাৰ নাম কি?", "mr": "मला अजून माहीत नाही! तुझं नाव काय?"},
    "no_bday": {"en": "You haven't told me your birthday yet! When is it?", "hi": "तुमने अभी तक अपना जन्मदिन नहीं बताया! कब है?",
                "as": "তুমি এতিয়াও তোমাৰ জন্মদিন কোৱা নাই! কেতিয়া?", "mr": "तू अजून तुझा वाढदिवस सांगितला नाहीस! कधी असतो?"},
    "birthday": {"en": "Happy birthday, {name}! Today is your special day!", "hi": "जन्मदिन की बहुत-बहुत बधाई, {name}! आज तुम्हारा ख़ास दिन है!",
                 "as": "জন্মদিনৰ শুভেচ্ছা, {name}! আজি তোমাৰ বিশেষ দিন!", "mr": "वाढदिवसाच्या खूप खूप शुभेच्छा, {name}! आज तुझा खास दिवस आहे!"},
}
Q = {
    "greet": re.compile(r"^\W*(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))\b|^\W*(?:नमस्ते|नमस्कार|हेलो|हैलो|হেলো|নমস্কাৰ)", re.I),
    "what_name": re.compile(r"what(?:'s| is) my name|do you know my name|who am i\b|मेरा नाम क्या|माझं नाव काय|माझे नाव काय|মোৰ নাম কি", re.I),
    "when_bday": re.compile(r"when(?:'s| is) my birthday|मेरा जन्मदिन कब|माझा वाढदिवस कधी|মোৰ জন্মদিন কেতিয়া", re.I),
    "how_old": re.compile(r"how old am i|मेरी उम्र|मैं कितने साल|माझं वय किती|मी किती वर्ष|মোৰ বয়স কিমান", re.I),
    "my_school": re.compile(r"(?:what(?:'s| is) (?:the name of )?my school|which school do i go|मेरा स्कूल कौन|मेरे स्कूल का नाम क्या|"
                            r"माझी शाळा कोणती|माझ्या शाळेचं नाव काय|মোৰ স্কুলৰ নাম কি|মোৰ স্কুল কোনখন)", re.I),
    "skip": re.compile(r"^\W*(?:no|skip|later|i don'?t know|नहीं|पता नहीं|नाही|माहीत नाही|নাই|নাজানো|নহয়)\b", re.I),
}

flow = {}   # toy_id -> {"step": "name" | "dob", "id": child id, "tries": n}; in memory, a restart just starts over
asked = set()   # toy ids asked for a name since the server started (asked once, not on every hello)


def line(key, lang, **kw):
    return nfc(L[key][lang].format(**kw))


def _row(child_id):
    with _lock:
        return DB.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()


def _next(toy_id, row, lang, lead=""):
    """Ask for whatever this child hasn't told Dikkey yet: birthday, then school, then pet name."""
    for step, key, have in (("dob", "ask_dob", row["dob"]), ("school", "ask_school", row["school"]),
                            ("pet", "ask_pet", row["pet_name"])):
        if not have and step not in flow.get(toy_id, {}).get("skipped", ()):
            skipped = flow.get(toy_id, {}).get("skipped", ())
            flow[toy_id] = {"step": step, "id": row["id"], "tries": 0, "skipped": skipped}
            ask = line(key, lang, name=row["name"])
            return (lead + " " + ask).strip()
    flow.pop(toy_id, None)
    return lead or line("hello_again", lang, name=call_name(row))


def _skip(toy_id, step):
    st = flow.get(toy_id, {})
    st["skipped"] = tuple(st.get("skipped", ())) + (step,)


def handle(toy_id, heard, lang, today):
    """(reply, status) when this is about the child's name, birthday, school or pet name, else None."""
    if lang not in LANGS:
        return None
    text = nfc(heard.strip())
    st = flow.get(toy_id)
    if st and st["step"] == "name":
        name = answer_name(text)
        if name:
            row = remember_name(name)
            if row["dob"] and row["school"] and row["pet_name"]:
                flow.pop(toy_id, None)
                return line("hello_again", lang, name=call_name(row)), "name"
            flow[toy_id] = {"step": None, "id": row["id"]}
            return _next(toy_id, row, lang), "name"
        if Q["skip"].search(text) or st["tries"] >= 1:
            flow.pop(toy_id, None)
            return None
        st["tries"] += 1
        return line("name_again", lang), "name-again"
    if st and st["step"] == "dob":
        row = _row(st["id"])
        dob = parse_dob(text, today)
        if dob:
            save(st["id"], dob=dob)
            _, m, d = split_dob(dob)
            return _next(toy_id, _row(st["id"]), lang, line("saved", lang, name=row["name"], date=say_date(m, d, lang))), "dob"
        if Q["skip"].search(text) or st["tries"] >= 1:
            _skip(toy_id, "dob")
            return _next(toy_id, row, lang, line("dob_skip", lang)), "dob-skip"
        st["tries"] += 1
        return line("dob_again", lang), "dob-again"
    if st and st["step"] == "school":
        row = _row(st["id"])
        school = None if Q["skip"].search(text) else answer_school(text)
        if school:
            save(st["id"], school=school)
        else:
            _skip(toy_id, "school")
        return _next(toy_id, _row(st["id"]), lang), "school" if school else "school-skip"
    if st and st["step"] == "pet":
        row = _row(st["id"])
        pet = None if NO_PET.search(text) else answer_pet(text)
        flow.pop(toy_id, None)
        if pet and pet.lower() != row["name"].lower():
            save(st["id"], pet_name=pet)
            return line("pet_saved", lang, pet=pet), "pet"
        save(st["id"], pet_name=row["name"])   # no pet name: the name is what Dikkey calls them
        return line("no_pet", lang, name=row["name"]), "pet-none"

    name = said_name(text)
    if name:
        row = remember_name(name)
        return _next(toy_id, row, lang, line("hello_name", lang, name=call_name(row))), "name"

    cur = current()
    if Q["what_name"].search(text):
        if cur:
            return line("your_name", lang, name=call_name(cur)), "ask"
        flow[toy_id] = {"step": "name", "tries": 0}
        return line("dont_know", lang), "ask"
    if Q["my_school"].search(text):
        if not cur:
            flow[toy_id] = {"step": "name", "tries": 0}
            return line("dont_know", lang), "ask"
        if not cur["school"]:
            flow[toy_id] = {"step": "school", "id": cur["id"], "tries": 0}
            return line("no_school", lang), "ask"
        return line("your_school", lang, school=cur["school"]), "ask"
    if Q["when_bday"].search(text) or Q["how_old"].search(text):
        if not cur:
            flow[toy_id] = {"step": "name", "tries": 0}
            return line("dont_know", lang), "ask"
        if not cur["dob"]:
            flow[toy_id] = {"step": "dob", "id": cur["id"], "tries": 0}
            return line("no_bday", lang), "ask"
        y, m, d = split_dob(cur["dob"])
        age = age_of(cur["dob"], today)
        if Q["how_old"].search(text) and age is not None:
            return line("your_age", lang, age=num_word(age, lang)), "ask"
        return line("your_bday", lang, date=say_date(m, d, lang)), "ask"
    if Q["greet"].search(text) and toy_id not in asked:
        asked.add(toy_id)
        if not cur:
            flow[toy_id] = {"step": "name", "tries": 0}
            return line("ask_name", lang), "ask-name"
        if not (cur["dob"] and cur["school"] and cur["pet_name"]):   # a known child with something still to ask
            return _next(toy_id, cur, lang, line("hello_name", lang, name=call_name(cur))), "ask-more"
    return None


def birthday_line(lang, today):
    """Happy birthday, once on the day, for the current child."""
    cur = current()
    if not cur or not cur["dob"] or lang not in LANGS:
        return None
    _, m, d = split_dob(cur["dob"])
    day = today.isoformat()
    if (m, d) != (today.month, today.day) or cur["greeted_on"] == day:
        return None
    mark_greeted(cur["id"], day)
    return line("birthday", lang, name=call_name(cur))
