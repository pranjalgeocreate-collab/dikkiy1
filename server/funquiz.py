"""A fun 10-question quiz for kids, offline (no LLM), in en / hi / as / mr.

Each game picks 10 of the 118 questions (25 here + 93 in funquiz_more.py) (not the ones from the last game). Every question has three choices;
the child can say the answer in any of the four languages, or "one / two / three".
"again" repeats the question, "I don't know" reveals it, "stop" ends the game with the score so far."""
import random, re, unicodedata

import child_profile

LANGS = ("en", "hi", "as", "mr")
ROUND = 10

# (question en/hi/as/mr, [(choice en, hi, as, mr, *extra words)], index of the right choice)
BANK = [
    (("Which animal says moo?", "कौन सा जानवर मूँ बोलता है?", "কোনটো জন্তুৱে হাম্বা বুলি মাতে?", "कोणता प्राणी हंबा करतो?"),
     [("a cat", "बिल्ली", "মেকুৰী", "मांजर", "cat"), ("a cow", "गाय", "গৰু", "गाय", "cow"), ("a duck", "बत्तख", "হাঁহ", "बदक", "duck")], 1),
    (("What colour is a banana?", "केले का रंग क्या होता है?", "কলৰ ৰং কি?", "केळ्याचा रंग कोणता?"),
     [("blue", "नीला", "নীলা", "निळा"), ("yellow", "पीला", "হালধীয়া", "पिवळा"), ("pink", "गुलाबी", "গোলাপী", "गुलाबी")], 1),
    (("How many legs does a spider have?", "मकड़ी के कितने पैर होते हैं?", "মকৰাৰ কেইখন ভৰি থাকে?", "कोळ्याला किती पाय असतात?"),
     [("four", "चार", "চাৰি", "चार", "4"), ("six", "छह", "ছয়", "सहा", "6"), ("eight", "आठ", "আঠ", "आठ", "8")], 2),
    (("Which is the biggest animal on land?", "ज़मीन पर सबसे बड़ा जानवर कौन सा है?", "মাটিত আটাইতকৈ ডাঙৰ জন্তু কোনটো?", "जमिनीवरचा सगळ्यात मोठा प्राणी कोणता?"),
     [("an elephant", "हाथी", "হাতী", "हत्ती", "elephant"), ("a dog", "कुत्ता", "কুকুৰ", "कुत्रा", "dog"), ("a rabbit", "खरगोश", "শহাপহু", "ससा", "rabbit")], 0),
    (("What do bees make?", "मधुमक्खियाँ क्या बनाती हैं?", "মৌমাখিয়ে কি বনায়?", "मधमाश्या काय बनवतात?"),
     [("milk", "दूध", "গাখীৰ", "दूध"), ("honey", "शहद", "মৌ", "मध"), ("bread", "रोटी", "ৰুটি", "भाकरी")], 1),
    (("How many days are there in a week?", "एक हफ़्ते में कितने दिन होते हैं?", "এসপ্তাহত কেইদিন থাকে?", "एका आठवड्यात किती दिवस असतात?"),
     [("five", "पाँच", "পাঁচ", "पाच", "5"), ("seven", "सात", "সাত", "सात", "7"), ("ten", "दस", "দহ", "दहा", "10")], 1),
    (("Which fruit is called the king of fruits?", "किस फल को फलों का राजा कहते हैं?", "কোনবিধ ফলক ফলৰ ৰজা বোলা হয়?", "कोणत्या फळाला फळांचा राजा म्हणतात?"),
     [("mango", "आम", "আম", "आंबा"), ("apple", "सेब", "আপেল", "सफरचंद"), ("grapes", "अंगूर", "আঙুৰ", "द्राक्ष", "grape")], 0),
    (("What colour do you get when you mix blue and yellow?", "नीला और पीला मिलाने से कौन सा रंग बनता है?", "নীলা আৰু হালধীয়া মিহলালে কি ৰং হয়?", "निळा आणि पिवळा मिसळला की कोणता रंग होतो?"),
     [("green", "हरा", "সেউজীয়া", "हिरवा"), ("red", "लाल", "ৰঙা", "लाल"), ("purple", "बैंगनी", "বেঙুনীয়া", "जांभळा")], 0),
    (("Which is India's national bird?", "भारत का राष्ट्रीय पक्षी कौन सा है?", "ভাৰতৰ ৰাষ্ট্ৰীয় চৰাই কোনটো?", "भारताचा राष्ट्रीय पक्षी कोणता?"),
     [("the crow", "कौआ", "কাউৰী", "कावळा", "crow"), ("the peacock", "मोर", "ময়ূৰ", "मोर", "peacock"), ("the parrot", "तोता", "ভাটৌ", "पोपट", "parrot")], 1),
    (("What do we use to see?", "हम देखने के लिए किसका इस्तेमाल करते हैं?", "আমি কিহেৰে চাওঁ?", "आपण कशाने पाहतो?"),
     [("our ears", "कान", "কাণ", "कान", "ears", "ear"), ("our eyes", "आँखें", "চকু", "डोळे", "eyes", "eye", "आँख"), ("our nose", "नाक", "নাক", "नाक", "nose")], 1),
    (("Where does a fish live?", "मछली कहाँ रहती है?", "মাছ ক'ত থাকে?", "मासा कुठे राहतो?"),
     [("in water", "पानी में", "পানীত", "पाण्यात", "water", "पानी", "পানী", "पाणी"), ("in a tree", "पेड़ पर", "গছত", "झाडावर", "tree"),
      ("in the sky", "आसमान में", "আকাশত", "आकाशात", "sky")], 0),
    (("Which day comes after Monday?", "सोमवार के बाद कौन सा दिन आता है?", "সোমবাৰৰ পিছত কোনটো দিন আহে?", "सोमवारनंतर कोणता दिवस येतो?"),
     [("Sunday", "रविवार", "দেওবাৰ", "रविवार"), ("Tuesday", "मंगलवार", "মঙলবাৰ", "मंगळवार"), ("Friday", "शुक्रवार", "শুক্ৰবাৰ", "शुक्रवार")], 1),
    (("Which one can fly?", "इनमें से कौन उड़ सकता है?", "এইবোৰৰ ভিতৰত কোনে উৰিব পাৰে?", "यांपैकी कोण उडू शकतं?"),
     [("a butterfly", "तितली", "পখিলা", "फुलपाखरू", "butterfly"), ("a fish", "मछली", "মাছ", "मासा", "fish"), ("a cat", "बिल्ली", "মেকুৰী", "मांजर", "cat")], 0),
    (("How many wheels does a bicycle have?", "साइकिल में कितने पहिए होते हैं?", "চাইকেলত কেইখন চকা থাকে?", "सायकलला किती चाकं असतात?"),
     [("two", "दो", "দুই", "दोन", "2"), ("three", "तीन", "তিনি", "तीन", "3"), ("four", "चार", "চাৰি", "चार", "4")], 0),
    (("What shape is a ball?", "गेंद का आकार कैसा होता है?", "বলৰ আকৃতি কেনেকুৱা?", "चेंडूचा आकार कसा असतो?"),
     [("square", "चौकोर", "চাৰিকোণীয়া", "चौकोनी"), ("round", "गोल", "ঘূৰণীয়া", "गोल"), ("a triangle", "तिकोना", "ত্ৰিভুজ", "त्रिकोणी", "triangle")], 1),
    (("Which season is the coldest?", "सबसे ठंडा मौसम कौन सा है?", "আটাইতকৈ ঠাণ্ডা ঋতু কোনটো?", "सगळ्यात थंड ऋतू कोणता?"),
     [("summer", "गर्मी", "গৰমকাল", "उन्हाळा"), ("winter", "सर्दी", "জাৰকাল", "हिवाळा", "सर्दियाँ", "জাৰ"), ("the rainy season", "बरसात", "বাৰিষা", "पावसाळा", "rainy", "monsoon")], 1),
    (("What does a cow give us?", "गाय हमें क्या देती है?", "গৰুৱে আমাক কি দিয়ে?", "गाय आपल्याला काय देते?"),
     [("milk", "दूध", "গাখীৰ", "दूध"), ("eggs", "अंडे", "কণী", "अंडी", "egg"), ("honey", "शहद", "মৌ", "मध")], 0),
    (("Which is India's national animal?", "भारत का राष्ट्रीय पशु कौन सा है?", "ভাৰতৰ ৰাষ্ট্ৰীয় জন্তু কোনটো?", "भारताचा राष्ट्रीय प्राणी कोणता?"),
     [("the lion", "शेर", "সিংহ", "सिंह", "lion"), ("the tiger", "बाघ", "বাঘ", "वाघ", "tiger"), ("the elephant", "हाथी", "হাতী", "हत्ती", "elephant")], 1),
    (("What colour is grass?", "घास का रंग क्या होता है?", "ঘাঁহৰ ৰং কি?", "गवताचा रंग कोणता?"),
     [("green", "हरा", "সেউজীয়া", "हिरवा"), ("blue", "नीला", "নীলা", "निळा"), ("orange", "नारंगी", "কমলা", "नारिंगी")], 0),
    (("How many fingers are there on one hand?", "एक हाथ में कितनी उँगलियाँ होती हैं?", "এখন হাতত কেইটা আঙুলি থাকে?", "एका हाताला किती बोटं असतात?"),
     [("three", "तीन", "তিনি", "तीन", "3"), ("five", "पाँच", "পাঁচ", "पाच", "5"), ("ten", "दस", "দহ", "दहा", "10")], 1),
    (("Which planet do we live on?", "हम किस ग्रह पर रहते हैं?", "আমি কোনখন গ্ৰহত বাস কৰোঁ?", "आपण कोणत्या ग्रहावर राहतो?"),
     [("Mars", "मंगल", "মংগল", "मंगळ"), ("Earth", "पृथ्वी", "পৃথিৱী", "पृथ्वी", "धरती"), ("Jupiter", "बृहस्पति", "বৃহস্পতি", "गुरू")], 1),
    (("What does a hen lay?", "मुर्गी क्या देती है?", "কুকুৰাই কি পাৰে?", "कोंबडी काय देते?"),
     [("eggs", "अंडे", "কণী", "अंडी", "egg"), ("apples", "सेब", "আপেল", "सफरचंद", "apple"), ("stones", "पत्थर", "শিল", "दगड", "stone")], 0),
    (("Which one is sweet?", "इनमें से मीठा कौन सा है?", "এইবোৰৰ ভিতৰত মিঠা কোনটো?", "यांपैकी गोड काय आहे?"),
     [("sugar", "चीनी", "চেনি", "साखर", "शक्कर"), ("salt", "नमक", "নিমখ", "मीठ"), ("chilli", "मिर्च", "জলকীয়া", "मिरची", "chili")], 0),
    (("When can we see the stars?", "हम तारे कब देख सकते हैं?", "আমি তৰা কেতিয়া দেখিব পাৰোঁ?", "आपण तारे कधी पाहू शकतो?"),
     [("at night", "रात को", "ৰাতি", "रात्री", "night", "रात"), ("in the morning", "सुबह", "ৰাতিপুৱা", "सकाळी", "morning"),
      ("at lunch time", "दोपहर को", "দুপৰীয়া", "दुपारी", "lunch", "afternoon")], 0),
    (("What colour is the sky on a sunny day?", "धूप वाले दिन आसमान का रंग क्या होता है?", "ৰ'দালি দিনত আকাশৰ ৰং কি?", "उन्हाच्या दिवशी आकाशाचा रंग कोणता असतो?"),
     [("blue", "नीला", "নীলা", "निळा"), ("black", "काला", "ক'লা", "काळा"), ("pink", "गुलाबी", "গোলাপী", "गुलाबी")], 0),
]

from funquiz_more import MORE

BANK += MORE

L = {
    "start": {"en": "Yay, quiz time! I will ask you ten fun questions. Let's go!",
              "hi": "वाह, क्विज़ का समय! मैं तुमसे दस मज़ेदार सवाल पूछूँगा। चलो शुरू करें!",
              "as": "বাঃ, কুইজৰ সময়! মই তোমাক দহটা মজাৰ প্ৰশ্ন সুধিম। আহা আৰম্ভ কৰোঁ!",
              "mr": "वा, प्रश्नमंजुषेची वेळ! मी तुला दहा मजेदार प्रश्न विचारीन. चल सुरू करूया!"},
    "question": {"en": "Question {n}: {q} Is it {a}, {b}, or {c}?", "hi": "सवाल नंबर {n}: {q} {a}, {b}, या {c}?",
                 "as": "প্ৰশ্ন নম্বৰ {n}: {q} {a}, {b}, নে {c}?", "mr": "प्रश्न क्रमांक {n}: {q} {a}, {b}, की {c}?"},
    "again": {"en": "Which one? Is it {a}, {b}, or {c}?", "hi": "कौन सा? {a}, {b}, या {c}?",
              "as": "কোনটো? {a}, {b}, নে {c}?", "mr": "कोणतं? {a}, {b}, की {c}?"},
    "wrong": {"en": "Nice try! The answer is {ans}.", "hi": "अच्छी कोशिश! सही जवाब है {ans}।",
              "as": "ভাল চেষ্টা! শুদ্ধ উত্তৰ হ'ল {ans}।", "mr": "छान प्रयत्न! बरोबर उत्तर आहे {ans}."},
    "dont_know": {"en": "That's okay! The answer is {ans}.", "hi": "कोई बात नहीं! सही जवाब है {ans}।",
                  "as": "ঠিক আছে! শুদ্ধ উত্তৰ হ'ল {ans}।", "mr": "काही हरकत नाही! बरोबर उत्तर आहे {ans}."},
    "end": {"en": "That's the end of the quiz! You got {score} out of ten. {cheer}",
            "hi": "क्विज़ ख़त्म! तुम्हारे दस में से {score} जवाब सही हैं। {cheer}",
            "as": "কুইজ শেষ! তুমি দহটাৰ ভিতৰত {score}টা শুদ্ধ উত্তৰ দিলা। {cheer}",
            "mr": "प्रश्नमंजुषा संपली! तुझी दहापैकी {score} उत्तरं बरोबर आली. {cheer}"},
    "stop_kind": {"en": "Okay, we'll stop the quiz. Let's play again soon!", "hi": "ठीक है, क्विज़ रोकते हैं। फिर से खेलेंगे!",
                  "as": "ঠিক আছে, কুইজ বন্ধ কৰিলোঁ। আকৌ খেলিম!", "mr": "ठीक आहे, प्रश्नमंजुषा थांबवूया. पुन्हा खेळूया!"},
    "stop": {"en": "Okay, we'll stop the quiz. You got {score} right!", "hi": "ठीक है, क्विज़ रोकते हैं। तुम्हारे {score} जवाब सही थे!",
             "as": "ঠিক আছে, কুইজ বন্ধ কৰিলোঁ। তুমি {score}টা শুদ্ধ উত্তৰ দিলা!", "mr": "ठीक आहे, प्रश्नमंजुषा थांबवूया. तुझी {score} उत्तरं बरोबर होती!"},
}
RIGHT = {"en": ["Correct! Well done!", "Yes! You got it!", "Super! That's right!"],
         "hi": ["सही जवाब! शाबाश!", "हाँ! बिल्कुल सही!", "वाह! एकदम सही!"],
         "as": ["শুদ্ধ! বহুত ভাল!", "হয়! ঠিকেই কৈছা!", "বাঃ! একদম শুদ্ধ!"],
         "mr": ["बरोबर! शाब्बास!", "हो! अगदी बरोबर!", "वा! एकदम बरोबर!"]}
CHEER = {"en": ("You're a superstar!", "Great job!", "Good try! Let's play again soon!"),
         "hi": ("तुम तो सुपरस्टार हो!", "बहुत बढ़िया!", "अच्छी कोशिश! फिर से खेलेंगे!"),
         "as": ("তুমি এজন চুপাৰষ্টাৰ!", "বহুত ভাল!", "ভাল চেষ্টা! আকৌ খেলিম!"),
         "mr": ("तू तर सुपरस्टार आहेस!", "खूप छान!", "छान प्रयत्न! पुन्हा खेळूया!")}
ZERO = {"en": "zero", "hi": "शून्य", "as": "শূন্য", "mr": "शून्य"}
IDX = {"en": 0, "hi": 1, "as": 2, "mr": 3}

START = re.compile(r"\bquiz\b|quiz\s+time|ask\s+me\s+(?:fun\s+)?questions|क्विज़|क्विज|पहेली\s*खेल|কুইজ|প্ৰশ্নোত্তৰ|प्रश्नमंजुषा|क्विझ", re.I)
STOP = re.compile(r"^\W*(?:stop|quit|no\s+more|i'?m\s+done|enough|end\s+the\s+quiz)\b|बस\s*करो|रुको|बंद\s*करो|थांब|पुरे|বন্ধ\s*কৰা|থমা|ৰখা", re.I)
REPEAT = re.compile(r"\b(?:again|repeat|what\s+was\s+the\s+question)\b|फिर\s*से|दोबारा|पुन्हा|আকৌ|পুনৰ", re.I)
DONT_KNOW = re.compile(r"don'?t\s+know|no\s+idea|पता\s*नहीं|माहीत\s*नाही|মাহিত\s*নাই|নাজানো|জনা\s*নাই", re.I)
BY_NUMBER = [re.compile(r"^\W*(?:one|first|1|a|एक|पहला|পহিলা|এক|पहिला)\W*$", re.I),
             re.compile(r"^\W*(?:two|second|2|b|दो|दूसरा|দ্বিতীয়|দুই|दोन|दुसरा)\W*$", re.I),
             re.compile(r"^\W*(?:three|third|3|c|तीन|तीसरा|তৃতীয়|তিনি|तिसरा)\W*$", re.I)]

games = {}   # toy_id -> {"qs": [bank indexes], "n": 0, "score": 0, "tries": 0}
last_round = {}   # toy_id -> bank indexes used last game (so the next game has new questions first)


def nfc(s):
    return unicodedata.normalize("NFC", s)


def active(toy_id):
    return toy_id in games


def _choice_text(opt, lang):
    return opt[IDX[lang]]


def _ask(game, lang):
    q, opts, _ = BANK[game["qs"][game["n"]]]
    n = child_profile.num_word(game["n"] + 1, lang)
    a, b, c = (_choice_text(o, lang) for o in opts)
    return L["question"][lang].format(n=n, q=q[IDX[lang]], a=a, b=b, c=c)


def _words(opt):
    return [nfc(w.lower()) for w in opt]


def _has(word, text):
    if re.fullmatch(r"[a-z0-9 ]+", word):
        return re.search(rf"\b{re.escape(word)}\b", text) is not None
    return word in text


def pick(text, opts):
    """Index of the choice the child said, or None."""
    t = nfc(text.lower())
    found = []
    for i, opt in enumerate(opts):
        for w in _words(opt):
            for key in {w, re.sub(r"^(?:a|an|the|our|in|at)\s+", "", w)}:
                if key and _has(key, t):
                    found.append((t.find(key), -len(key), i))
    if found:
        # the choice said first; at the same spot the longest one wins ("ৰাতিপুৱা" is not "ৰাতি", "five hundred" is not "five")
        return min(found)[2]
    for i, p in enumerate(BY_NUMBER):   # "the first one" / "2" - only when no choice was named (some answers are numbers)
        if p.search(t):
            return i
    return None


def _score(n, lang):
    return child_profile.num_word(n, lang) if n else ZERO[lang]


def start(toy_id, lang, rng=random):
    fresh = [i for i in range(len(BANK)) if i not in last_round.get(toy_id, ())]
    qs = rng.sample(fresh, min(ROUND, len(fresh)))
    if len(qs) < ROUND:
        qs += rng.sample([i for i in range(len(BANK)) if i not in qs], ROUND - len(qs))
    games[toy_id] = {"qs": qs, "n": 0, "score": 0, "tries": 0}
    last_round[toy_id] = qs
    return nfc(L["start"][lang] + " " + _ask(games[toy_id], lang))


def turn(toy_id, text, lang, rng=random):
    """The child's answer -> Dikkey's reply (feedback + next question, or the final score)."""
    game = games[toy_id]
    t = nfc(text)
    if STOP.search(t):
        games.pop(toy_id)
        if not game["score"]:   # no "you got zero": just a kind goodbye
            return nfc(L["stop_kind"][lang])
        return nfc(L["stop"][lang].format(score=_score(game["score"], lang)))
    if REPEAT.search(t):
        return nfc(_ask(game, lang))
    q, opts, right = BANK[game["qs"][game["n"]]]
    answer = _choice_text(opts[right], lang)
    said = None if DONT_KNOW.search(t) else pick(t, opts)
    if said is None and not DONT_KNOW.search(t) and game["tries"] == 0:
        game["tries"] = 1
        a, b, c = (_choice_text(o, lang) for o in opts)
        return nfc(L["again"][lang].format(a=a, b=b, c=c))
    if said == right:
        game["score"] += 1
        feedback = rng.choice(RIGHT[lang])
    else:
        feedback = L["dont_know" if DONT_KNOW.search(t) else "wrong"][lang].format(ans=answer)
    game["n"] += 1
    game["tries"] = 0
    if game["n"] >= ROUND:
        games.pop(toy_id)
        s = game["score"]
        cheer = CHEER[lang][0 if s >= 8 else 1 if s >= 5 else 2]
        return nfc(feedback + " " + L["end"][lang].format(score=_score(s, lang), cheer=cheer))
    return nfc(feedback + " " + _ask(game, lang))
