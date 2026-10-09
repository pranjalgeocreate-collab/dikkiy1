"""Deterministic answers that must never come from the LLM: alphabets, arithmetic,
multiplication tables and counting. Pure Python, no I/O, so it is unit-tested in
test_skills.py.

    answer(text, lang) -> Skill(display, speech) or None

`display` is what the dashboard shows; `speech` is what gets spoken (letters are
spelled the way they sound, numbers become words so every voice can say them).
"""
import ast
import operator
import re
import unicodedata
from dataclasses import dataclass


def nfc(s):
    # ड़/ढ़/य़ can arrive precomposed or as letter+nukta; NFC makes both the same
    return unicodedata.normalize("NFC", s)


def rx(pattern):
    return re.compile(nfc(pattern))


@dataclass
class Skill:
    name: str
    display: str
    speech: str
    speak_lang: str = None   # force a voice language (e.g. English phonics asked in Hindi mode)
    speed: float = None      # force a TTS speed (e.g. slower for counting, so each number is clear)
    audio_parts: tuple = None   # synthesize+join these instead of .speech (offline TTS has a length limit)


# ------------------------------------------------------------------ numbers → words
EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
           "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

HI_0_100 = nfc("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
            "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस "
            "पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस "
            "सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ "
            "इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर "
            "पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी "
            "सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे "
            "निन्यानवे सौ").split()
assert len(HI_0_100) == 101


def en_words(n):
    if n < 0:
        return "minus " + en_words(-n)
    if n < 20:
        return EN_ONES[n]
    if n < 100:
        return EN_TENS[n // 10] + ("" if n % 10 == 0 else " " + EN_ONES[n % 10])
    for size, word in ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            head, rest = divmod(n, size)
            out = en_words(head) + " " + word
            if rest:
                out += (" and " if rest < 100 else " ") + en_words(rest)
            return out
    raise ValueError(n)


def hi_words(n):
    if n < 0:
        return "माइनस " + hi_words(-n)
    if n <= 100:
        return HI_0_100[n]
    for size, word in ((10**7, "करोड़"), (10**5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= size:
            head, rest = divmod(n, size)
            return hi_words(head) + " " + word + ("" if rest == 0 else " " + hi_words(rest))
    raise ValueError(n)


def num_words(x, lang):
    """Int or float → words. Floats are said digit by digit after the point."""
    words = hi_words if lang == "hi" else en_words
    if isinstance(x, float) and not x.is_integer():
        whole, frac = f"{abs(x):.2f}".rstrip("0").split(".")
        point = " दशमलव " if lang == "hi" else " point "
        sign = ("माइनस " if lang == "hi" else "minus ") if x < 0 else ""
        return sign + words(int(whole)) + point + " ".join(words(int(d)) for d in frac)
    return words(int(x))


def fmt(x):
    """Number as shown on screen."""
    if isinstance(x, float) and not x.is_integer():
        return f"{x:.2f}".rstrip("0").rstrip(".")
    return str(int(x))


DIGIT_RUN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")


def spell_numbers(text, lang):
    """Replace digit runs in any reply with words, so voices that lack some digits still say them."""
    if lang not in ("en", "hi"):
        return text
    text = text.translate(DIGIT_MAP)

    def rep(m):
        s = m.group(0)
        v = float(s) if "." in s else int(s)
        if isinstance(v, int) and abs(v) >= 10**9:
            return s
        return num_words(v, lang)
    return DIGIT_RUN.sub(rep, text)


# ------------------------------------------------------------------ words → numbers
DIGIT_MAP = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯", "01234567890123456789")
EN_WORD_VALUE = {w: i for i, w in enumerate(EN_ONES)}
EN_WORD_VALUE.update({w: i * 10 for i, w in enumerate(EN_TENS) if w})
HI_WORD_VALUE = {w: i for i, w in enumerate(HI_0_100)}
HI_WORD_VALUE.update({"पांच": 5, "छः": 6, "एक सौ": 100, "सौ": 100, "शुन्य": 0,
                      "पन्द्रह": 15, "सत्तरह": 17, "अठाईस": 28, "चालिस": 40})
HI_WORD_VALUE = {nfc(k): v for k, v in HI_WORD_VALUE.items()}
# "दो" is also "give" (जोड़ दो, बता दो): drop it after a verb before reading numbers
GIVE = rx(r"(जोड़|घटा|बता|गिन|सुना|कर|दे|निकाल|बोल|समझा|लिख|सिखा)\s+दो(?![\u0900-\u097F])")


def words_to_digits(text):
    """'five plus twenty three' → '5 plus 23'; 'पाँच और तीन' → '5 और 3'."""
    text = GIVE.sub(r"\1", nfc(text).translate(DIGIT_MAP))
    # English: tens + ones pairs first, then single words, then "N hundred"
    tens = "|".join(w for w in EN_TENS if w)
    ones = "|".join(EN_ONES[1:10])
    text = re.sub(rf"\b({tens})[\s-]+({ones})\b", lambda m: str(EN_WORD_VALUE[m.group(1)] + EN_WORD_VALUE[m.group(2)]), text)
    text = re.sub(r"\b(" + "|".join(sorted(EN_WORD_VALUE, key=len, reverse=True)) + r")\b",
                  lambda m: str(EN_WORD_VALUE[m.group(1)]), text)
    text = re.sub(r"\b(\d+)\s+hundred(?:\s+(?:and\s+)?(\d+))?\b",
                  lambda m: str(int(m.group(1)) * 100 + int(m.group(2) or 0)), text)
    text = re.sub(r"\b(?:a|one)\s+hundred\b", "100", text)
    # Hindi: longest words first; Devanagari has no \b, so match on spaces/punctuation
    for w in sorted(HI_WORD_VALUE, key=len, reverse=True):
        text = re.sub(rf"(?<![ऀ-ॿ]){re.escape(w)}(?![ऀ-ॿ])", str(HI_WORD_VALUE[w]), text)
    text = re.sub(r"(\d+)\s*सौ", lambda m: str(int(m.group(1)) * 100), text)
    return text


# ------------------------------------------------------------------ arithmetic
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def safe_eval(expr):
    """Evaluate + - * / and brackets on numbers only. Anything else raises."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.left), ev(node.right))
        raise ValueError("not arithmetic")
    return ev(ast.parse(expr, mode="eval"))


# Reordering phrases first (the numbers swap), then plain operator words.
REORDER = [
    (re.compile(r"(?:subtract|take away|minus)\s+(\d+(?:\.\d+)?)\s+from\s+(\d+(?:\.\d+)?)"), r"\2 - \1"),
    (rx(r"(\d+(?:\.\d+)?)\s*में\s*से\s*(\d+(?:\.\d+)?)\s*(?:घटा[\u0900-\u097F]*|कम\s*कर[\u0900-\u097F]*|निकाल[\u0900-\u097F]*|माइनस)?"), r"\1 - \2"),
    (re.compile(r"(?:divide)\s+(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)"), r"\1 / \2"),
    (re.compile(r"(?:multiply)\s+(\d+(?:\.\d+)?)\s+(?:by|and|with)\s+(\d+(?:\.\d+)?)"), r"\1 * \2"),
    (re.compile(r"(?:add)\s+(\d+(?:\.\d+)?)\s+(?:and|to|with|plus)\s+(\d+(?:\.\d+)?)"), r"\1 + \2"),
]
OP_WORDS = [
    (r"multiplied\s+by|times|into|गुणा(?:\s*करो)?|गुना|टाइम्स|इंटू|×|\*|\bx\b", " * "),
    (r"divided\s+by|divide\s+by|over|भाग(?:\s*देने\s*पर)?|बटा|डिवाइडेड\s*बाय|÷|/|\bby\b", " / "),
    (r"plus|added\s+to|जोड़(?:ो|ने\s*पर)?|प्लस|\+", " + "),
    (r"minus|less|take\s+away|घटा(?:ओ|ने\s*पर)?|माइनस|कम|−|–|(?<=\d)\s*-\s*(?=\d)", " - "),
]
MATH_CUE = rx(r"how much|what is|what's|whats|equals?|total|answer|solve|calculate|sum|"
                      r"कितना|कितने|कितनी|क्या होता|बराबर|जोड़|उत्तर|हल")
AND_WORD = rx(r"\s(?:and|और|व)\s")


def find_arithmetic(text):
    """Return a clean expression like '5 + 3' if the text asks for a calculation, else None."""
    t = words_to_digits(text.lower())
    for pat, rep in REORDER:
        t = pat.sub(rep, t)
    for pat, sym in OP_WORDS:
        t = re.sub(nfc(pat), sym, t)
    # "5 and 3" / "5 और 3" means plus only when the child is clearly asking a sum
    if MATH_CUE.search(text.lower()) and not re.search(r"\d\s*[-+*/]\s*\d", t):
        t = AND_WORD.sub(" + ", t)
    m = re.search(r"\(?\s*-?\d+(?:\.\d+)?(?:\s*[-+*/]\s*\(?\s*-?\d+(?:\.\d+)?\s*\)?)+", t)
    if not m:
        return None
    expr = re.sub(r"\s+", " ", m.group(0)).strip()
    if expr.count("(") != expr.count(")"):
        expr = expr.replace("(", "").replace(")", "")
    return expr


SAY_OP = {"en": {"+": "plus", "-": "minus", "*": "times", "/": "divided by"},
          "hi": {"+": "जोड़", "-": "घटा", "*": "गुणा", "/": "भाग"}}


def arithmetic(text, lang):
    expr = find_arithmetic(text)
    if not expr:
        return None
    try:
        value = safe_eval(expr)
    except ZeroDivisionError:
        if lang == "hi":
            return Skill("math", "किसी संख्या को शून्य से भाग नहीं दे सकते!",
                         "किसी संख्या को शून्य से भाग नहीं दे सकते! यह एक पहेली है जिसका कोई उत्तर नहीं।")
        return Skill("math", "You can't divide by zero!",
                     "Ooh, tricky! You can't divide a number by zero. Nobody can!")
    except Exception:
        return None
    if isinstance(value, float):
        value = round(value, 2)
    shown = expr.replace("*", "×").replace("/", "÷") + " = " + fmt(value)
    tokens = re.findall(r"-?\d+(?:\.\d+)?|[-+*/()]", expr)
    say_op = SAY_OP.get(lang, SAY_OP["en"])
    said = " ".join(say_op[tok] if tok in say_op else num_words(float(tok) if "." in tok else int(tok), lang)
                    for tok in tokens if tok not in "()")
    if lang == "hi":
        return Skill("math", shown, f"{said} बराबर {num_words(value, lang)}!")
    return Skill("math", shown, f"{said} equals {num_words(value, lang)}!")


# ------------------------------------------------------------------ tables & counting
HI_TABLE_WORD = [nfc(w) for w in ["", "एकम", "दूनी", "तिया", "चौके", "पंजे", "छक्के", "सत्ते", "अट्ठे", "नवां", "दहाई"]]
TABLE = rx(r"(?:table\s+of\s+(\d+))"
           r"|(?:(\d+)\s*(?:times\s+table|ka\s+table|का\s*(?:पहाड़ा|टेबल|table)))"
           r"|(?:पहाड़ा\s*(\d+))"
           r"|(?:(\d+)\s*(?:की|का)\s*तालिका)")


def table(text, lang):
    m = TABLE.search(words_to_digits(text.lower()))
    if not m:
        return None
    n = int(next(g for g in m.groups() if g))
    if not 1 <= n <= 100:
        return None
    shown = "\n".join(f"{n} × {i} = {n * i}" for i in range(1, 11))
    if lang == "hi":
        speech = f"{hi_words(n)} का पहाड़ा: " + ", ".join(
            f"{hi_words(n)} {HI_TABLE_WORD[i]} {hi_words(n * i)}" for i in range(1, 11)) + "।"
    else:
        speech = f"The table of {en_words(n)}: " + ". ".join(
            f"{en_words(n)} times {en_words(i)} is {en_words(n * i)}" for i in range(1, 11)) + "."
    return Skill("table", shown, speech)


COUNT = rx(r"(?:count\s+(?:from\s+(\d+)\s+)?(?:to|till|until|up\s*to)\s+(\d+))|"
                   r"(?:(?:(\d+)\s*से\s*)?(\d+)\s*तक\s*(?:गिन|गिनती|काउंट))|(?:गिनती\s*(\d+)\s*तक)")


def counting(text, lang):
    m = COUNT.search(words_to_digits(text.lower()))
    if not m:
        return None
    g = m.groups()
    start, end = (g[0], g[1]) if g[1] else (g[2], g[3]) if g[3] else (None, g[4])
    start, end = int(start or 1), int(end)
    if not (0 <= start <= end <= 100):
        return None
    nums = range(start, end + 1)
    words = hi_words if lang == "hi" else en_words
    return Skill("count", ", ".join(map(str, nums)), ", ".join(words(i) for i in nums) + "!")


# ------------------------------------------------------------------ alphabets
EN_LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
EN_SAY = ["Ay", "Bee", "See", "Dee", "Ee", "Eff", "Jee", "Aitch", "Eye", "Jay", "Kay", "Ell", "Em", "En", "Oh",
          "Pee", "Cue", "Arr", "Ess", "Tee", "You", "Vee", "Double you", "Ex", "Why", "Zed"]
EN_SAY_HI = ["ए", "बी", "सी", "डी", "ई", "एफ़", "जी", "एच", "आई", "जे", "के", "एल", "एम", "एन", "ओ",
             "पी", "क्यू", "आर", "एस", "टी", "यू", "वी", "डब्ल्यू", "एक्स", "वाई", "ज़ेड"]
HI_SWAR = ["अ", "आ", "इ", "ई", "उ", "ऊ", "ऋ", "ए", "ऐ", "ओ", "औ", "अं", "अः"]
HI_VYANJAN = ["क", "ख", "ग", "घ", "ङ", "च", "छ", "ज", "झ", "ञ", "ट", "ठ", "ड", "ढ", "ण",
              "त", "थ", "द", "ध", "न", "प", "फ", "ब", "भ", "म", "य", "र", "ल", "व",
              "श", "ष", "स", "ह", "क्ष", "त्र", "ज्ञ"]

HINDI_ALPHA = rx(r"hindi\s+(?:alphabets?|letters|varnamala)|varnamala|varnmala|वर्णमाला|स्वर\s*(?:और|व)\s*व्यंजन|"
                         r"हिंदी\s*(?:के\s*)?(?:अक्षर|स्वर|व्यंजन|alphabet)|व्यंजन\s*(?:सुनाओ|बताओ|बोलो)|"
                         r"स्वर\s*(?:सुनाओ|बताओ|बोलो)|क\s*ख\s*ग|अ\s*आ\s*इ|ka\s*kha\s*ga")
ENGLISH_ALPHA = rx(r"\babc\b|\babcd\b|\ba\s*b\s*c\s*d\b|alphabets?|english\s+letters|abc\s*song|"
                           r"(?:अंग्रेज़ी|अंग्रेजी|इंग्लिश)\s*(?:की\s*)?(?:वर्णमाला|अक्षर|alphabet)|ए\s*बी\s*सी\s*डी|एबीसीडी")
NEXT_LETTER = re.compile(r"(after|before)\s+(?:the\s+letter\s+)?['\"]?([a-z])['\"]?\s*(?:[?.!,]|$)")


def english_alphabet(text, lang):
    low = text.lower()
    m = NEXT_LETTER.search(low)
    if m and re.search(r"letter|comes|alphabet|abc", low):
        i = ord(m.group(2)) - ord("a")
        j = i + (1 if m.group(1) == "after" else -1)
        L = m.group(2).upper()
        if not 0 <= j < 26:
            edge = "Z is the last letter!" if j > 25 else "A is the very first letter!"
            return Skill("letter", edge, edge.replace("Z ", "Zed ").replace("A ", "Ay "))
        R = EN_LETTERS[j]
        return Skill("letter", f"{m.group(1).title()} {L} comes {R}",
                     f"{m.group(1).title()} {EN_SAY[i]} comes {EN_SAY[j]}!")
    if not ENGLISH_ALPHA.search(low) or (HINDI_ALPHA.search(low) and not ENGLISH_CUE.search(low)):
        return None
    shown = " ".join(EN_LETTERS)
    if lang == "hi":
        return Skill("abc", shown, "चलो अंग्रेज़ी वर्णमाला बोलते हैं! " + ", ".join(EN_SAY_HI) + "। शाबाश!")
    return Skill("abc", shown, "Let's sing the alphabet! " + ", ".join(EN_SAY) + ". Well done!")


ENGLISH_CUE = rx(r"अंग्रेज़ी|अंग्रेजी|इंग्लिश|english|\babc")


def hindi_alphabet(text, lang):
    if not HINDI_ALPHA.search(text.lower()) or ENGLISH_CUE.search(text.lower()):
        return None
    only_swar = re.search(r"स्वर|swar|vowel", text.lower()) and not re.search(r"व्यंजन|vyanjan|consonant|वर्णमाला|varnamala|alphabet", text.lower())
    only_vyanjan = re.search(r"व्यंजन|vyanjan|consonant", text.lower()) and not re.search(r"स्वर|swar|vowel|वर्णमाला|varnamala|alphabet", text.lower())
    parts_shown, parts_said = [], []
    if not only_vyanjan:
        parts_shown.append("स्वर: " + " ".join(HI_SWAR))
        parts_said.append("पहले स्वर: " + ", ".join(HI_SWAR))
    if not only_swar:
        parts_shown.append("व्यंजन: " + " ".join(HI_VYANJAN))
        parts_said.append(("अब " if parts_said else "") + "व्यंजन: " + ", ".join(HI_VYANJAN))
    return Skill("varnamala", "\n".join(parts_shown), "चलो हिंदी वर्णमाला सीखें! " + "। ".join(parts_said) + "। शाबाश!")


# ------------------------------------------------------------------ colors
EN_COLORS = ["red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "black", "white"]
HI_COLORS = [nfc(c) for c in ["लाल", "नारंगी", "पीला", "हरा", "नीला", "बैंगनी", "गुलाबी", "भूरा", "काला", "सफ़ेद"]]

COLORS = rx(r"what colou?rs? do you know|name (?:the|some) colou?rs?|list (?:the|some) colou?rs?|"
            r"say (?:the|some) colou?rs?|tell me (?:the|some) colou?rs?|colou?rs? song|^\W*colou?rs?\W*$|"
            r"रंग\s*(?:बताओ|सुनाओ|कौन\s*(?:से|सी)|के\s*नाम)|कौन\s*(?:से|सी)\s*रंग")


def colors(text, lang):
    if not COLORS.search(text.lower()):
        return None
    if lang == "hi":
        return Skill("colors", " ".join(HI_COLORS), "चलो रंग सीखें! " + ", ".join(HI_COLORS) + "। शाबाश!")
    return Skill("colors", " ".join(EN_COLORS), "Let's learn colors! " + ", ".join(EN_COLORS) + ". Well done!")


# ------------------------------------------------------------------ Assamese alphabet
# Not part of answer()'s en/hi-gated router: Assamese has no offline skills yet, and
# broadening that gate would make every other skill (table, counting, arithmetic...)
# fire in Assamese too while still only knowing how to speak English or Hindi. This is
# called directly by the server for lang == "as", kept separate and self-contained.
AS_SWAR = [nfc(v) for v in ["অ", "আ", "ই", "ঈ", "উ", "ঊ", "ঋ", "এ", "ঐ", "ও", "ঔ"]]
AS_VYANJAN = [nfc(c) for c in
              ["ক", "খ", "গ", "ঘ", "ঙ", "চ", "ছ", "জ", "ঝ", "ঞ", "ট", "ঠ", "ড", "ঢ", "ণ",
               "ত", "থ", "দ", "ধ", "ন", "প", "ফ", "ব", "ভ", "ম", "য", "ৰ", "ল", "ৱ",
               "স", "শ", "ষ", "হ", "ক্ষ"]]

ASSAMESE_ALPHA = rx(r"assamese\s+(?:alphabets?|letters)|অসমীয়া\s*(?:বৰ্ণমালা|অক্ষৰ)|বৰ্ণমালা|"
                    r"স্বৰবৰ্ণ|ব্যঞ্জনবৰ্ণ|স্বৰ\s*(?:আৰু|আৰো)\s*ব্যঞ্জন")


def assamese_alphabet(text, lang):
    if lang != "as" or not ASSAMESE_ALPHA.search(nfc(text.lower())):
        return None
    t = nfc(text.lower())
    only_swar = re.search(r"স্বৰবৰ্ণ|স্বৰ\b", t) and "ব্যঞ্জন" not in t
    only_vyanjan = re.search(r"ব্যঞ্জনবৰ্ণ|ব্যঞ্জন\b", t) and "স্বৰ" not in t
    parts_shown, parts_said = [], []
    if not only_vyanjan:
        parts_shown.append("স্বৰবৰ্ণ: " + " ".join(AS_SWAR))
        parts_said.append("প্ৰথমে স্বৰবৰ্ণ: " + ", ".join(AS_SWAR))
    if not only_swar:
        parts_shown.append("ব্যঞ্জনবৰ্ণ: " + " ".join(AS_VYANJAN))
        parts_said.append(("এতিয়া " if parts_said else "") + "ব্যঞ্জনবৰ্ণ: " + ", ".join(AS_VYANJAN))
    return Skill("varnamala", "\n".join(parts_shown), nfc("আহা অসমীয়া বৰ্ণমালা শিকোঁ! ") + "। ".join(parts_said) + nfc("। বাঃ, বহুত ভাল!"))


# ------------------------------------------------------------------ router



# ================================================================== time, day, date (India time)
EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
HI_DAYS = [nfc(d) for d in ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]
HI_MONTHS = [nfc(m) for m in ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर",
                              "अक्टूबर", "नवंबर", "दिसंबर"]]
EN_ORD = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth",
          20: "twentieth", 30: "thirtieth"}


def en_ordinal(n):
    if n in EN_ORD:
        return EN_ORD[n]
    if n > 20 and n % 10:
        return EN_TENS[n // 10] + " " + en_ordinal(n % 10)
    return en_words(n) + "th"


def now_india():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Kolkata"))


ASK_TIME = rx(r"what\s*(?:'s|is)?\s*the\s+time|what\s+time|time\s+is\s+it|tell\s+me\s+the\s+time|"
              r"कितने\s*बजे|कितना\s*बजा|क्या\s*(?:टाइम|समय)|(?:टाइम|समय)\s*क्या|(?:टाइम|समय)\s*बताओ")
ASK_DATE = rx(r"what\s+day|which\s+day|what\s*(?:'s|is)?\s*(?:the\s+|today'?s\s+)?date|today'?s\s+date|what\s+month|"
              r"which\s+month|what\s+year|which\s+year|day\s+is\s+(?:it\s+)?today|"
              r"कौन\s*सा\s*दिन|क्या\s*दिन|कौनसा\s*दिन|तारीख|तिथि|कौन\s*सा\s*महीना|कौन\s*सा\s*साल|आज\s*क्या\s*है")


def time_of_day(h, lang):
    if lang == "hi":
        return "सुबह" if 4 <= h < 12 else "दोपहर" if h < 16 else "शाम" if h < 20 else "रात"
    return "in the morning" if 4 <= h < 12 else "in the afternoon" if h < 17 else "in the evening" if h < 21 else "at night"


def time_date(text, lang, now=None):
    low = text.lower()
    wants_time, wants_date = ASK_TIME.search(low), ASK_DATE.search(low)
    if not (wants_time or wants_date):
        return None
    now = now or now_india()
    if wants_time:
        h12 = now.hour % 12 or 12
        shown = now.strftime("%I:%M %p").lstrip("0")
        if lang == "hi":
            part = time_of_day(now.hour, "hi")
            if now.minute == 0:
                return Skill("time", shown, nfc(f"अभी {part} के {hi_words(h12)} बजे हैं।"))
            return Skill("time", shown, nfc(f"अभी {part} के {hi_words(h12)} बजकर {hi_words(now.minute)} मिनट हुए हैं।"))
        mins = "o'clock" if now.minute == 0 else ("oh " + en_words(now.minute)) if now.minute < 10 else en_words(now.minute)
        return Skill("time", shown, f"It's {en_words(h12)} {mins} {time_of_day(now.hour, 'en')}.")
    d, m, y, wd = now.day, now.month, now.year, now.weekday()
    if lang == "hi":
        return Skill("date", f"{HI_DAYS[wd]}, {d} {HI_MONTHS[m - 1]} {y}",
                     nfc(f"आज {HI_DAYS[wd]} है, {hi_words(d)} {HI_MONTHS[m - 1]}, {hi_words(y)}।"))
    return Skill("date", f"{EN_DAYS[wd]}, {d} {EN_MONTHS[m - 1]} {y}",
                 f"Today is {EN_DAYS[wd]}, the {en_ordinal(d)} of {EN_MONTHS[m - 1]}, {en_words(y)}.")


# ------------------------------------------------------------------ how to read a clock
CLOCK_LESSON = rx(r"how (?:to|do you) read a clock|how (?:does|do) a clock work|teach me the clock|"
                  r"clock lesson|learn (?:the|about the) clock|how to tell time|"
                  r"घड़ी\s*(?:कैसे\s*(?:देखें|देखते|पढ़ें|पढ़ते)|पढ़ना\s*सिखाओ|सिखाओ|के\s*बारे\s*में)")

CLOCK_STEPS_EN = [
    "A clock has two hands, and they are not the same size.",
    "The short, fat hand is the hour hand. It tells you which hour it is.",
    "The long, thin hand is the minute hand. It tells you how many minutes have passed.",
    "The numbers one to twelve go all the way around the clock, like a circle.",
    "When the long hand points straight up at the twelve, that means it is exactly o'clock.",
    "So if the short hand is on the three and the long hand is on the twelve, it is three o'clock!",
]
CLOCK_STEPS_HI = [nfc(s) for s in [
    "घड़ी में दो कांटे होते हैं, और वे एक जैसे नहीं होते।",
    "छोटा, मोटा कांटा घंटे का कांटा है। यह बताता है कि कौन सा घंटा हो रहा है।",
    "लंबा, पतला कांटा मिनट का कांटा है। यह बताता है कि कितने मिनट बीत चुके हैं।",
    "एक से बारह तक के अंक घड़ी के चारों ओर, एक गोले की तरह लगे होते हैं।",
    "जब लंबा कांटा सीधा ऊपर बारह की तरफ़ होता है, तो इसका मतलब है पूरे बजे।",
    "तो अगर छोटा कांटा तीन पर है और लंबा कांटा बारह पर है, तो तीन बजे हैं!",
]]


def clock_lesson(text, lang):
    if not CLOCK_LESSON.search(text.lower()):
        return None
    steps = CLOCK_STEPS_HI if lang == "hi" else CLOCK_STEPS_EN
    numbered = [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    if lang == "hi":
        return Skill("clock_lesson", "\n".join(numbered), "चलो घड़ी पढ़ना सीखें! " + " ".join(steps))
    return Skill("clock_lesson", "\n".join(numbered), "Let's learn how to read a clock! " + " ".join(steps))


# ================================================================== बारहखड़ी
MATRAS = ["", "ा", "ि", "ी", "ु", "ू", "े", "ै", "ो", "ौ", "ं", "ः"]
BARAKHADI = rx(r"बारहखड़ी|बारहखडी|बाराखड़ी|बारखड़ी|barakhadi|barahkhadi|barakhdi|मात्रा|matra")
BARAKHADI_LETTER = rx(r"(?<![ऀ-ॿ])([क-ह](?:्[क-ह])?)(?![ऀ-ॿ])")


def barakhadi(text, lang):
    t = nfc(text)
    if not BARAKHADI.search(t.lower()):
        return None
    letters = [x for x in BARAKHADI_LETTER.findall(t) if x not in HI_VYANJAN_SKIP]
    base = letters[0] if letters else "क"
    forms = [nfc(base + m) for m in MATRAS]
    return Skill("barakhadi", " ".join(forms), nfc(f"{base} की बारहखड़ी: ") + ", ".join(forms) + "। शाबाश!")


HI_VYANJAN_SKIP = set()  # letters that are also words and must not be read as the chosen letter


# ================================================================== rhymes & lists (traditional, public domain)
RHYMES = {
    "en": {
        "twinkle": ("Twinkle Twinkle Little Star",
                    "Twinkle, twinkle, little star,\nHow I wonder what you are!\nUp above the world so high,\n"
                    "Like a diamond in the sky.\nTwinkle, twinkle, little star,\nHow I wonder what you are!"),
        "humpty": ("Humpty Dumpty",
                   "Humpty Dumpty sat on a wall,\nHumpty Dumpty had a great fall.\n"
                   "All the king's horses and all the king's men\nCouldn't put Humpty together again."),
        "baa baa|black sheep": ("Baa Baa Black Sheep",
                                "Baa, baa, black sheep, have you any wool?\nYes sir, yes sir, three bags full!\n"
                                "One for the master, one for the dame,\nAnd one for the little boy who lives down the lane."),
        "hickory": ("Hickory Dickory Dock",
                    "Hickory, dickory, dock,\nThe mouse ran up the clock.\nThe clock struck one,\n"
                    "The mouse ran down,\nHickory, dickory, dock."),
    },
    "hi": {
        "मछली": ("मछली जल की रानी है",
                 "मछली जल की रानी है,\nजीवन उसका पानी है।\nहाथ लगाओ डर जाएगी,\nबाहर निकालो मर जाएगी।"),
        "आलू|कचालू": ("आलू कचालू",
                      "आलू कचालू बेटा कहाँ गए थे,\nबैंगन की टोकरी में सो रहे थे।\n"
                      "बैंगन ने लात मारी रो रहे थे,\nमम्मी ने प्यार किया हँस रहे थे।"),
        "हाथी": ("हाथी राजा",
                 "हाथी राजा कहाँ चले,\nसूँड़ हिलाकर कहाँ चले।\nमेरे घर भी आओ ना,\nहलवा पूरी खाओ ना।"),
    },
}
RHYME_ASK = rx(r"rhyme|poem|nursery|sing\s+(?:me\s+)?a\s+song|sing\s+something|a\s+song|"
               r"कविता|राइम|बालगीत|बाल\s*गीत|गाना\s*सुनाओ|गीत\s*सुनाओ|पोएम|गाना\s*गाओ")


def rhyme(text, lang, rng=None):
    import random
    low = nfc(text.lower())
    for rl, book in RHYMES.items():
        for key, (title, body) in book.items():
            if re.search(nfc(key), low):
                return Skill("rhyme", f"{title}\n{nfc(body)}", nfc(body.replace("\n", " ")))
    if not RHYME_ASK.search(low) or lang not in RHYMES:
        return None
    title, body = (rng or random).choice(sorted(RHYMES[lang].values()))
    intro = "यह रही एक कविता: " if lang == "hi" else "Here's a rhyme! "
    return Skill("rhyme", f"{title}\n{nfc(body)}", nfc(intro + title + "। " if lang == "hi" else intro + title + ". ")
                 + nfc(body.replace("\n", " ")))


LIST_DAYS = rx(r"days\s+of\s+(?:the\s+)?week|name\s+the\s+days|week\s*days|seven\s+days|"
               r"(?:हफ्ते|हफ़्ते|सप्ताह)\s*के\s*(?:दिन|सात\s*दिन)|दिनों\s*के\s*नाम|वारों\s*के\s*नाम")
LIST_MONTHS = rx(r"months\s+of\s+(?:the\s+)?year|name\s+the\s+months|all\s+the\s+months|twelve\s+months|"
                 r"महीनों\s*के\s*नाम|साल\s*के\s*(?:महीने|बारह\s*महीने)|बारह\s*महीने")


def lists(text, lang):
    low = nfc(text.lower())
    if LIST_DAYS.search(low):
        days = HI_DAYS if lang == "hi" else EN_DAYS
        intro = "हफ्ते के सात दिन: " if lang == "hi" else "The seven days of the week are: "
        return Skill("days", " ".join(days), nfc(intro) + ", ".join(days) + ("।" if lang == "hi" else "."))
    if LIST_MONTHS.search(low):
        months = HI_MONTHS if lang == "hi" else EN_MONTHS
        intro = "साल के बारह महीने: " if lang == "hi" else "The twelve months of the year are: "
        return Skill("months", " ".join(months), nfc(intro) + ", ".join(months) + ("।" if lang == "hi" else "."))
    return None


# ================================================================== maths quiz (state lives in the server, per toy)
QUIZ_START = rx(r"maths?\s+(?:quiz|game)|quiz\s+me|number\s+game|play\s+(?:a\s+)?(?:maths?|number)|ask\s+me\s+(?:a\s+)?(?:maths?|sum)|"
                r"गणित\s*(?:का|की)?\s*(?:खेल|क्विज़|क्विज|गेम)|मैथ्स?\s*(?:का)?\s*(?:क्विज़|क्विज|गेम|खेल)|"
                r"सवाल\s*पूछो|सवाल\s*करो|मुझसे\s*(?:सवाल|सवाल)\s*पूछो")
QUIZ_STOP = rx(r"\bstop\b|enough|no\s+more|finish|\bquit\b|i\s+am\s+done|i'm\s+done|"
               r"(?<![ऀ-ॿ])बस(?![ऀ-ॿ])|रुको|बंद\s*करो|ख़त्म|खत्म|नहीं\s*खेलना|अब\s*नहीं")
DONT_KNOW = rx(r"don'?t\s+know|dunno|no\s+idea|not\s+sure|पता\s*नहीं|नहीं\s*पता|मालूम\s*नहीं|नहीं\s*आता")
QUIZ_LEN = 10
PRAISE = {"en": ["Yes! Well done!", "Correct! Super!", "Right! You're so clever!", "Yes! Brilliant!"],
          "hi": ["हाँ! बहुत बढ़िया!", "सही जवाब! शाबाश!", "बिल्कुल सही! तुम तो बहुत होशियार हो!", "सही! कमाल कर दिया!"]}


def age_level(age):
    try:
        age = int(age)
    except (TypeError, ValueError):
        return 2
    return 1 if age <= 5 else 2 if age <= 7 else 3


def quiz_question(level, rng):
    """(a, op, b, answer) sized for the level: 1 = add within 10, 2 = +/- within 20,
    3 = +/- within 50 and tables to 10, 4 = +/- within 100 and tables to 12."""
    if level <= 1:
        a, b = rng.randint(1, 5), rng.randint(1, 5)
        return a, "+", b, a + b
    op = rng.choice(["+", "-"] if level == 2 else ["+", "-", "*"])
    top = {2: 20, 3: 50}.get(level, 100)
    if op == "*":
        a, b = rng.randint(2, 10 if level == 3 else 12), rng.randint(1, 10)
        return a, op, b, a * b
    if op == "-":
        a = rng.randint(2, top)
        b = rng.randint(1, a)
        return a, op, b, a - b
    a = rng.randint(1, top // 2)
    b = rng.randint(1, top // 2)
    return a, op, b, a + b


def say_question(q, lang):
    a, op, b, _ = q
    if lang == "hi":
        return nfc(f"{hi_words(a)} {SAY_OP['hi'][op]} {hi_words(b)} कितने होते हैं?")
    return f"What is {en_words(a)} {SAY_OP['en'][op]} {en_words(b)}?"


def show_q(q):
    a, op, b, ans = q
    return f"{a} {op.replace('*', '×').replace('-', '−')} {b}"


def quiz_start(state, lang, age, rng):
    state.clear()
    state.update(active=True, level=age_level(age), streak=0, misses=0, asked=1, correct=0)
    state["q"] = quiz_question(state["level"], rng)
    if lang == "hi":
        intro = "चलो गणित का खेल खेलते हैं! मैं सवाल पूछूँगा, तुम जवाब दो। रुकना हो तो बस बोलो। पहला सवाल: "
    else:
        intro = "Let's play a maths game! I ask, you answer. Say stop any time. First question: "
    return Skill("quiz", f"Maths game! Q1: {show_q(state['q'])} = ?", nfc(intro) + say_question(state["q"], lang))


def quiz_turn(state, text, lang, rng):
    """Handle the child's reply while a quiz is running. Returns a Skill, or None when the
    child has clearly moved on (the quiz ends and the text goes to normal handling)."""
    if not state.get("active"):
        return None
    t = nfc(text.lower())
    a, op, b, ans = state["q"]
    if QUIZ_STOP.search(t):
        return quiz_end(state, lang, early=True)
    nums = re.findall(r"-?\d+", words_to_digits(t))
    if not nums and not DONT_KNOW.search(t):
        state["active"] = False
        return None
    said_ans = num_words(ans, lang)
    if nums and int(nums[-1]) == ans:
        state["correct"] += 1
        state["streak"] += 1
        state["misses"] = 0
        head = rng.choice(PRAISE.get(lang, PRAISE["en"]))
        if state["streak"] in (3, 5, 8):
            head += nfc(f" लगातार {hi_words(state['streak'])} सही!") if lang == "hi" else f" That's {en_words(state['streak'])} in a row!"
        if state["streak"] >= 3 and state["level"] < 4:
            state["level"] += 1
            state["streak"] = 0
        mark = "✓"
    else:
        state["streak"] = 0
        state["misses"] += 1
        if state["misses"] >= 2 and state["level"] > 1:
            state["level"] -= 1
            state["misses"] = 0
        q_words = say_question(state["q"], lang).rstrip("?").replace("What is ", "").replace(" कितने होते हैं", "")
        head = nfc(f"कोई बात नहीं! {q_words} होते हैं {said_ans}।") if lang == "hi" else \
            f"Good try! {q_words[0].upper() + q_words[1:]} is {said_ans}."
        mark = "✗"
    shown_prev = f"{mark} {show_q(state['q'])} = {ans}"
    if state["asked"] >= QUIZ_LEN:
        end = quiz_end(state, lang)
        return Skill("quiz", shown_prev + "\n" + end.display, nfc(head) + " " + end.speech)
    state["asked"] += 1
    state["q"] = quiz_question(state["level"], rng)
    nxt = nfc(" अगला सवाल: ") if lang == "hi" else " Next question: "
    return Skill("quiz", f"{shown_prev}\nQ{state['asked']}: {show_q(state['q'])} = ?",
                 nfc(head) + nxt + say_question(state["q"], lang))


def quiz_end(state, lang, early=False):
    state["active"] = False
    got, out_of = state.get("correct", 0), state.get("asked", 0) - (1 if early else 0)
    if out_of <= 0:
        msg = "ठीक है, फिर कभी खेलेंगे!" if lang == "hi" else "Okay, let's play another time!"
        return Skill("quiz", "Game stopped", nfc(msg))
    if lang == "hi":
        msg = f"बहुत बढ़िया खेल! तुमने {hi_words(out_of)} में से {hi_words(got)} सही किए!"
    else:
        msg = f"Great game! You got {en_words(got)} out of {en_words(out_of)}!"
    return Skill("quiz", f"Score: {got}/{out_of}", nfc(msg))


# ================================================================== count along
# Dikkey recites 1 to 100 continuously, slowly enough for the child to chant along, then
# asks to repeat. One continuous reply, not a turn-by-turn game (see skill "count" for that).
COUNT_ALONG_START = rx(r"count\s+(?:with\s+me|together|along)|let'?s\s+count|count\s+to\s*(?:a\s*)?hundred|"
                        r"साथ\s*(?:में\s*)?गिन(?:ती)?|गिनती\s*साथ|चलो\s*गिनती\s*(?:करें|करते\s*हैं|करो)|"
                        r"मिलकर\s*गिनती")
COUNT_ALONG_TOP = 100
COUNT_ALONG_SPEED = 0.9   # slower than the normal chat pace, so a young child can chant along
COUNT_ALONG_CHUNK = 20    # numbers per TTS call: the offline voice model caps input length,
                          # so one 1-to-100 utterance is synthesized as several clips and joined


def count_along(lang):
    nums = list(range(1, COUNT_ALONG_TOP + 1))
    words = hi_words if lang == "hi" else en_words
    shown = ", ".join(map(str, nums))
    if lang == "hi":
        intro, outro = "चलो साथ में गिनती करें! मेरे साथ गिनो: ", " हमने सौ तक गिन लिया! बहुत बढ़िया! फिर से गिनूँ?"
    else:
        intro, outro = "Let's count together! Count along with me: ", " We counted all the way to one hundred! Want me to count again?"
    chunks = [nums[i:i + COUNT_ALONG_CHUNK] for i in range(0, len(nums), COUNT_ALONG_CHUNK)]
    parts = []
    for i, chunk in enumerate(chunks):
        text = ", ".join(words(n) for n in chunk)
        if i == 0:
            text = nfc(intro) + text
        if i == len(chunks) - 1:
            text = text + "!" + nfc(outro)
        parts.append(nfc(text))
    full_speech = nfc(intro) + ", ".join(words(n) for n in nums) + "!" + nfc(outro)
    return Skill("count_along", shown, full_speech, speed=COUNT_ALONG_SPEED, audio_parts=tuple(parts))


# ================================================================== parent controls
DEFAULT_BLOCKED = ("kill, killing, murder, gun, guns, knife, knives, blood, bloody, weapon, weapons, bomb, shoot, "
                   "shooting, suicide, die, dies, dying, dead, death, sex, sexy, naked, porn, drug, drugs, alcohol, "
                   "beer, wine, vodka, whisky, whiskey, cigarette, cigarettes, vape, hate, stupid, idiot, damn, hell, "
                   "मारना, मार डालो, हत्या, बंदूक, चाकू, खून, बम, आत्महत्या, मौत, मरना, शराब, बीयर, सिगरेट, नशा, "
                   "बेवकूफ, गाली")


def blocked_hit(reply, blocked):
    """First blocked word/phrase found in an LLM reply (case-insensitive, whole words), else None."""
    low = nfc(reply.lower())
    for w in [nfc(x.strip().lower()) for x in blocked.split(",") if x.strip()]:
        if re.search(rf"(?<![\wऀ-ॿ]){re.escape(w)}(?![\wऀ-ॿ])", low):
            return w
    return None


SAFE_REDIRECT = {"en": "Let's talk about something fun instead! What's your favourite animal?",
                 "hi": "चलो, कुछ मज़ेदार बात करते हैं! तुम्हारा पसंदीदा जानवर कौन सा है?",
                 "as": "আহা, কিবা মজাৰ কথা পাতোঁ! তোমাৰ প্ৰিয় জন্তুটো কি?",
                 "mr": "चल, काहीतरी मजेशीर बोलूया! तुझा आवडता प्राणी कोणता?"}


def in_bedtime(now, start, end):
    """True if now's HH:MM falls in [start, end), where the window may wrap past midnight."""
    def mins(s):
        h, m = (int(x) for x in s.split(":"))
        return h * 60 + m
    t, a, b = now.hour * 60 + now.minute, mins(start), mins(end)
    return a <= t < b if a < b else t >= a or t < b


def bedtime_line(lang, name=""):
    name = name.strip()
    if lang == "hi":
        return nfc(f"सोने का समय हो गया{', ' + name if name else ''}! आँखें बंद करो और मीठे सपने देखो। कल बात करेंगे!")
    if lang == "mr":
        return nfc(f"झोपायची वेळ झाली{', ' + name if name else ''}! डोळे मिट आणि गोड स्वप्नं बघ. उद्या बोलूया!")
    if lang == "as":
        return nfc(f"শুবৰ সময় হ'ল{', ' + name if name else ''}! চকু মুদা আৰু ধুনীয়া সপোন দেখা। কাইলৈ কথা পাতিম!")
    return f"It's sleep time{', ' + name if name else ''}! Close your eyes and have sweet dreams. Let's talk tomorrow!"


# ================================================================== phonics: "A for Apple" (the parent's own list)
PHONICS = {
    "A": ["Apple", "Ant"], "B": ["Ball", "Bat"], "C": ["Carrot", "Car"], "D": ["Duck", "Door"],
    "E": ["Elevator", "Egg"], "F": ["Fish", "Flag"], "G": ["Guitar", "Glass"], "H": ["Hammer", "Hat"],
    "I": ["Indian", "Igloo"], "J": ["Jam", "Juice"], "K": ["Kangaroo", "Key"], "L": ["Ladder", "Leaf"],
    "M": ["Monkey", "Mouse"], "N": ["Nail", "Nose"], "O": ["Octopus", "Orange"], "P": ["Paint", "Popcorn"],
    "Q": ["Question", "Queen"], "R": ["Radio", "Rake"], "S": ["Saw", "Snake"], "T": ["Tree", "Train"],
    "U": ["Umbrella", "Unicorn"], "V": ["Vacuum", "Violin"], "W": ["Whale", "Watch"], "X": ["Axe", "Box", "Fox"],
    "Y": ["Yo yo", "Yacht"], "Z": ["Zebra"],
}
PHONICS_ALL = rx(r"a\s+for\s+apple|phonics|letter\s+sounds|abc\s+words|alphabet\s+words|words\s+for\s+(?:each|every)\s+letter|"
                 r"ए\s*फ(?:ॉ|ो)र\s*एप्पल|फोनिक्स")
PHONICS_ONE = re.compile(r"(?:^|\bwhat\s+is\s+|\bwhat's\s+|\bsay\s+|\btell\s+me\s+)['\"]?([a-z])['\"]?\s+for\b(?!\s+\w+\s+for)")


def phonics_line(L, say):
    words = PHONICS[L]
    name = EN_SAY[ord(L) - ord("A")]
    def either(items):   # "a or b", "a, b or c"
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]
    if L == "X":   # X lives at the end of words
        return (f"X: {either(words)}", f"{name}! {either(words)}.")
    return (either([f"{L} for {w}" for w in words]), either([f"{name} for {w}" for w in words]) + ".")


def phonics(text, lang):
    low = text.lower().strip()
    one = PHONICS_ONE.search(low)
    if one and not PHONICS_ALL.search(low):
        L = one.group(1).upper()
        shown, said = phonics_line(L, True)
        return Skill("phonics", shown, said, speak_lang="en")
    if not PHONICS_ALL.search(low):
        return None
    lines = [phonics_line(L, True) for L in PHONICS]
    return Skill("phonics", "\n".join(x[0] for x in lines), "Let's learn A for Apple! " + " ".join(x[1] for x in lines),
                 speak_lang="en")


# ================================================================== router
def answer(text, lang, now=None, rng=None):
    """First skill that matches wins. Order matters: lists before date ("days of the week" is not
    "what day is it"), barakhadi before the Hindi alphabet, Hindi alphabet before English."""
    if lang not in ("en", "hi"):
        return None
    text = nfc(text)
    for skill in (phonics, lists, clock_lesson, lambda t, l: time_date(t, l, now), barakhadi, lambda t, l: rhyme(t, l, rng),
                  hindi_alphabet, english_alphabet, colors, table, counting, arithmetic):
        out = skill(text, lang)
        if out:
            return out
    return None


# ================================================================== goodbye / thank you (all languages)
GOODBYE = rx(r"^\W*(?:ok(?:ay)?\s+)?(?:bye(?:\s*bye)?|good\s*bye|goodbye|see\s+you(?:\s+(?:later|soon|tomorrow))?|ta\s*ta|"
             r"tata|gotta\s+go|i\s+have\s+to\s+go|i'?m\s+going\s+now)\b|"
             r"(?<![ऀ-ॿ])(?:बाय|टाटा|अलविदा|फिर\s*मिलेंगे|चलता\s*हूँ|चलती\s*हूँ|अब\s*जाना\s*है|पुन्हा\s*भेटू|निघतो|निघते)|"
             r"বিদায়|বাই|পিছত\s*লগ\s*পাম")
THANKS_BYE = {
    "en": "Thank you for playing with me{name}! I had so much fun. See you soon!",
    "hi": "मेरे साथ खेलने के लिए धन्यवाद{name}! मुझे बहुत मज़ा आया। फिर मिलेंगे!",
    "as": "মোৰ লগত খেলাৰ বাবে ধন্যবাদ{name}! মোৰ বহুত ভাল লাগিল। পিছত লগ পাম!",
    "mr": "माझ्याबरोबर खेळल्याबद्दल धन्यवाद{name}! मला खूप मजा आली. पुन्हा भेटू!",
}
THANKS_SONG = {"en": "Thank you for singing with me!", "hi": "मेरे साथ गाने के लिए धन्यवाद!",
               "as": "মোৰ লগত গীত গোৱাৰ বাবে ধন্যবাদ!", "mr": "माझ्याबरोबर गाणं गायल्याबद्दल धन्यवाद!"}


def goodbye(text, lang, name=""):
    if not GOODBYE.search(nfc(text.lower().strip())):
        return None
    line = nfc(THANKS_BYE.get(lang, THANKS_BYE["en"]).format(name=", " + name.strip() if name.strip() else ""))
    return Skill("goodbye", line, line)


# ================================================================== "stop" (the child wants Dikkey to be quiet)
STOP_TALK = rx(r"^\W*(?:please\s+)?(?:stop(?:\s+it|\s+talking|\s+singing|\s+the\s+song|\s+playing)?|be\s+quiet|quiet|shush|shh+|"
               r"that'?s\s+enough|enough|no\s+more|pause)\W*$|"
               r"^\W*(?:बस|बस\s*करो|रुको|रुक\s*जाओ|चुप|चुप\s*हो\s*जाओ|बंद\s*करो|गाना\s*बंद\s*करो|अब\s*बस)\W*$|"
               r"^\W*(?:থমা|ৰখা|মনে\s*মনে\s*থকা|বন্ধ\s*কৰা)\W*$|"
               r"^\W*(?:थांब|थांबा|गप्प\s*बस|पुरे|बंद\s*कर)\W*$")
STOP_LINE = {"en": "Okay, I stopped!", "hi": "ठीक है, रुक गया!", "as": "ঠিক আছে, ৰখিলোঁ!", "mr": "ठीक आहे, थांबलो!"}


def stop_request(text, lang):
    if not STOP_TALK.search(nfc(text.lower().strip())):
        return None
    line = nfc(STOP_LINE.get(lang, STOP_LINE["en"]))
    return Skill("stop", line, line)


# ================================================================== offline & "what can you do?"
OFFLINE_LINE = {
    "en": ("I can't reach the internet right now, but I can still do lots with you! I can play the A B C D song and more "
           "songs, do maths, say the alphabet, and play learning games. Try saying: play the A B C D song, "
           "what is five plus three, say A for Apple, or let's play a maths game!"),
    "hi": ("अभी इंटरनेट नहीं है, पर मैं फिर भी तुम्हारे साथ बहुत कुछ कर सकता हूँ! मैं ए बी सी डी गाना और दूसरे गाने सुना "
           "सकता हूँ, गणित के सवाल हल कर सकता हूँ, वर्णमाला और बारहखड़ी सिखा सकता हूँ, और खेल खेल सकता हूँ। बोलो: "
           "एक मोटा हाथी गाना सुनाओ, पाँच और तीन कितने होते हैं, हिंदी वर्णमाला सुनाओ, या गणित का खेल खेलें!"),
    "as": ("এতিয়া ইণ্টাৰনেট নাই, কিন্তু মই তোমাক গান শুনাব পাৰোঁ! ইংৰাজী বা হিন্দীত কোৱা, মই অংক, বৰ্ণমালা "
           "আৰু খেলো খেলিব পাৰোঁ।"),
    "mr": ("आत्ता इंटरनेट नाही, पण मी तुला गाणी ऐकवू शकतो! इंग्रजी किंवा हिंदीत बोल, मग मी गणित, मुळाक्षरं "
           "आणि खेळ खेळू शकतो."),
}
CAN_DO_LINE = {
    "en": ("I can chat and tell stories, and I can also play songs like the A B C D song and Old MacDonald, "
           "do maths, say A for Apple, sing the alphabet, name the colors, teach you how to read a clock, tell the time, "
           "count, say times tables, count together with you, and play a maths game. What would you like to do?"),
    "hi": ("मैं बातें कर सकता हूँ और कहानियाँ सुना सकता हूँ। मैं गाने सुना सकता हूँ, गणित के सवाल हल कर सकता हूँ, "
           "हिंदी वर्णमाला, बारहखड़ी, रंग, पहाड़े और घड़ी पढ़ना सिखा सकता हूँ, समय बता सकता हूँ, साथ में गिनती कर सकता हूँ, और गणित का खेल खेल सकता हूँ। "
           "बोलो, क्या करें?"),
    "as": "মই কথা পাতিব পাৰোঁ, সাধু কব পাৰোঁ, আৰু গান শুনাব পাৰোঁ। কি কৰিবা কোৱা?",
    "mr": "मी गप्पा मारू शकतो, गोष्टी सांगू शकतो आणि गाणी ऐकवू शकतो. बोल, काय करूया?",
}
CAN_DO = rx(r"what\s+can\s+you\s+do|what\s+do\s+you\s+do|what\s+can\s+we\s+(?:do|play)|^\W*help\W*$|help\s+me\s+learn|"
            r"what\s+games|तुम\s*क्या\s*(?:क्या\s*)?कर\s*सकत|क्या\s*क्या\s*कर\s*सकत|क्या\s*खेलें|मदद|"
            r"তুমি\s*কি\s*কৰিব\s*পাৰা|तू\s*काय\s*(?:काय\s*)?करू\s*शकत")


def offline_line(lang):
    return nfc(OFFLINE_LINE.get(lang, OFFLINE_LINE["en"]))


def can_do(text, lang):
    if not CAN_DO.search(nfc(text.lower())):
        return None
    line = nfc(CAN_DO_LINE.get(lang, CAN_DO_LINE["en"]))
    return Skill("help", line, line)
