"""Offline facts about India, answered from this table (no LLM, no internet), in en / hi / as / mr.

Numbers are written as words in the spoken text: skills.spell_numbers only knows English and Hindi words.
Facts as of 2026. PRIME_MINISTER is the one line likely to change; update it when it does."""
import re, unicodedata

PRIME_MINISTER = {"en": "Narendra Modi", "hi": "नरेंद्र मोदी", "as": "নৰেন্দ্ৰ মোদী", "mr": "नरेंद्र मोदी"}

# (names en/hi/as/mr, capital en/hi/as/mr, extra spellings to recognise)
STATES = [
    (("Andhra Pradesh", "आंध्र प्रदेश", "অন্ধ্ৰ প্ৰদেশ", "आंध्र प्रदेश"), ("Amaravati", "अमरावती", "অমৰাৱতী", "अमरावती"), ()),
    (("Arunachal Pradesh", "अरुणाचल प्रदेश", "অৰুণাচল প্ৰদেশ", "अरुणाचल प्रदेश"), ("Itanagar", "ईटानगर", "ইটানগৰ", "इटानगर"), ("arunachal", "अरुणाचल", "অৰুণাচল")),
    (("Assam", "असम", "অসম", "आसाम"), ("Dispur", "दिसपुर", "দিছপুৰ", "दिसपूर"), ("आसाम", "असम")),
    (("Bihar", "बिहार", "বিহাৰ", "बिहार"), ("Patna", "पटना", "পাটনা", "पाटणा"), ()),
    (("Chhattisgarh", "छत्तीसगढ़", "ছত্তীছগড়", "छत्तीसगड"), ("Raipur", "रायपुर", "ৰায়পুৰ", "रायपूर"), ("chattisgarh", "छत्तीसगढ")),
    (("Goa", "गोवा", "গোৱা", "गोवा"), ("Panaji", "पणजी", "পানাজী", "पणजी"), ()),
    (("Gujarat", "गुजरात", "গুজৰাট", "गुजरात"), ("Gandhinagar", "गांधीनगर", "গান্ধীনগৰ", "गांधीनगर"), ()),
    (("Haryana", "हरियाणा", "হাৰিয়ানা", "हरियाणा"), ("Chandigarh", "चंडीगढ़", "চণ্ডীগড়", "चंदीगड"), ("हरियाना",)),
    (("Himachal Pradesh", "हिमाचल प्रदेश", "হিমাচল প্ৰদেশ", "हिमाचल प्रदेश"), ("Shimla", "शिमला", "চিমলা", "शिमला"), ("himachal", "हिमाचल", "হিমাচল")),
    (("Jharkhand", "झारखंड", "ঝাৰখণ্ড", "झारखंड"), ("Ranchi", "रांची", "ৰাঁচী", "रांची"), ("झारखण्ड",)),
    (("Karnataka", "कर्नाटक", "কৰ্ণাটক", "कर्नाटक"), ("Bengaluru", "बेंगलुरु", "বেংগালুৰু", "बंगळूरु"), ()),
    (("Kerala", "केरल", "কেৰালা", "केरळ"), ("Thiruvananthapuram", "तिरुवनंतपुरम", "তিৰুৱনন্তপুৰম", "तिरुवनंतपुरम"), ("केरला",)),
    (("Madhya Pradesh", "मध्य प्रदेश", "মধ্য প্ৰদেশ", "मध्य प्रदेश"), ("Bhopal", "भोपाल", "ভোপাল", "भोपाळ"), ()),
    (("Maharashtra", "महाराष्ट्र", "মহাৰাষ্ট্ৰ", "महाराष्ट्र"), ("Mumbai", "मुंबई", "মুম্বাই", "मुंबई"), ()),
    (("Manipur", "मणिपुर", "মণিপুৰ", "मणिपूर"), ("Imphal", "इंफाल", "ইম্ফল", "इंफाळ"), ()),
    (("Meghalaya", "मेघालय", "মেঘালয়", "मेघालय"), ("Shillong", "शिलांग", "শ্বিলং", "शिलाँग"), ()),
    (("Mizoram", "मिज़ोरम", "মিজোৰাম", "मिझोराम"), ("Aizawl", "आइज़ोल", "আইজল", "ऐझॉल"), ("मिजोरम",)),
    (("Nagaland", "नागालैंड", "নাগালেণ্ড", "नागालँड"), ("Kohima", "कोहिमा", "কহিমা", "कोहिमा"), ()),
    (("Odisha", "ओडिशा", "ওড়িশা", "ओडिशा"), ("Bhubaneswar", "भुवनेश्वर", "ভুৱনেশ্বৰ", "भुवनेश्वर"), ("orissa", "उड़ीसा", "ওড়িশা")),
    (("Punjab", "पंजाब", "পঞ্জাৱ", "पंजाब"), ("Chandigarh", "चंडीगढ़", "চণ্ডীগড়", "चंदीगड"), ()),
    (("Rajasthan", "राजस्थान", "ৰাজস্থান", "राजस्थान"), ("Jaipur", "जयपुर", "জয়পুৰ", "जयपूर"), ()),
    (("Sikkim", "सिक्किम", "ছিক্কিম", "सिक्कीम"), ("Gangtok", "गंगटोक", "গেংটক", "गंगटोक"), ()),
    (("Tamil Nadu", "तमिलनाडु", "তামিলনাডু", "तमिळनाडू"), ("Chennai", "चेन्नई", "চেন্নাই", "चेन्नई"), ("tamilnadu", "तमिल नाडु")),
    (("Telangana", "तेलंगाना", "তেলেংগানা", "तेलंगणा"), ("Hyderabad", "हैदराबाद", "হায়দৰাবাদ", "हैदराबाद"), ()),
    (("Tripura", "त्रिपुरा", "ত্ৰিপুৰা", "त्रिपुरा"), ("Agartala", "अगरतला", "আগৰতলা", "आगरतळा"), ()),
    (("Uttar Pradesh", "उत्तर प्रदेश", "উত্তৰ প্ৰদেশ", "उत्तर प्रदेश"), ("Lucknow", "लखनऊ", "লক্ষ্ণৌ", "लखनौ"), ()),
    (("Uttarakhand", "उत्तराखंड", "উত্তৰাখণ্ড", "उत्तराखंड"), ("Dehradun", "देहरादून", "দেৰাদুন", "डेहराडून"), ("उत्तराखण्ड",)),
    (("West Bengal", "पश्चिम बंगाल", "পশ্চিমবংগ", "पश्चिम बंगाल"), ("Kolkata", "कोलकाता", "কলকাতা", "कोलकाता"), ("bengal", "बंगाल", "পশ্চিম বংগ")),
]
TERRITORIES = [
    (("Delhi", "दिल्ली", "দিল্লী", "दिल्ली"), ("New Delhi", "नई दिल्ली", "নতুন দিল্লী", "नवी दिल्ली"), ("দিল্লি",)),
    (("Jammu and Kashmir", "जम्मू और कश्मीर", "জম্মু আৰু কাশ্মীৰ", "जम्मू आणि काश्मीर"),
     ("Srinagar in summer and Jammu in winter", "गर्मियों में श्रीनगर और सर्दियों में जम्मू",
      "গৰমকালি শ্ৰীনগৰ আৰু জাৰকালি জম্মু", "उन्हाळ्यात श्रीनगर आणि हिवाळ्यात जम्मू"), ("kashmir", "कश्मीर", "কাশ্মীৰ", "काश्मीर")),
    (("Ladakh", "लद्दाख", "লাডাখ", "लडाख"), ("Leh", "लेह", "লেহ", "लेह"), ()),
    (("Puducherry", "पुडुचेरी", "পুডুচেৰী", "पुदुच्चेरी"), ("Puducherry", "पुडुचेरी", "পুডুচেৰী", "पुदुच्चेरी"), ("pondicherry",)),
    (("Chandigarh", "चंडीगढ़", "চণ্ডীগড়", "चंदीगड"), ("Chandigarh", "चंडीगढ़", "চণ্ডীগড়", "चंदीगड"), ()),
    (("Lakshadweep", "लक्षद्वीप", "লাক্ষাদ্বীপ", "लक्षद्वीप"), ("Kavaratti", "कवरत्ती", "কাৱাৰত্তি", "कवरत्ती"), ()),
    (("Andaman and Nicobar Islands", "अंडमान और निकोबार द्वीपसमूह", "আন্দামান আৰু নিকোবৰ দ্বীপপুঞ্জ", "अंदमान आणि निकोबार बेटे"),
     ("Sri Vijaya Puram, earlier called Port Blair", "श्री विजयपुरम, जिसे पहले पोर्ट ब्लेयर कहते थे",
      "শ্ৰী বিজয়পুৰম, আগতে পৰ্ট ব্লেয়াৰ বুলি কোৱা হৈছিল", "श्री विजयपुरम, पूर्वीचं पोर्ट ब्लेअर"), ("andaman", "अंडमान", "আন্দামান", "अंदमान")),
    (("Dadra and Nagar Haveli and Daman and Diu", "दादरा और नगर हवेली और दमन और दीव", "দাদৰা আৰু নগৰ হাভেলী আৰু দমন আৰু দিউ",
      "दादरा आणि नगर हवेली आणि दमण आणि दीव"), ("Daman", "दमन", "দমন", "दमण"), ("daman", "दमन", "दमण", "dadra", "दादरा")),
]
LANG_IDX = {"en": 0, "hi": 1, "as": 2, "mr": 3}

LANGUAGES_22 = {
    "en": "Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, "
          "Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu and Urdu",
    "hi": "असमिया, बांग्ला, बोडो, डोगरी, गुजराती, हिंदी, कन्नड़, कश्मीरी, कोंकणी, मैथिली, मलयालम, मणिपुरी, मराठी, नेपाली, "
          "ओड़िया, पंजाबी, संस्कृत, संथाली, सिंधी, तमिल, तेलुगु और उर्दू",
    "as": "অসমীয়া, বাংলা, বড়ো, ডোগ্ৰী, গুজৰাটী, হিন্দী, কানাড়া, কাশ্মীৰী, কোংকণী, মৈথিলী, মালয়ালম, মণিপুৰী, মাৰাঠী, নেপালী, "
          "ওড়িয়া, পঞ্জাবী, সংস্কৃত, সাঁওতালী, সিন্ধী, তামিল, তেলুগু আৰু উৰ্দু",
    "mr": "आसामी, बंगाली, बोडो, डोगरी, गुजराती, हिंदी, कन्नड, काश्मिरी, कोंकणी, मैथिली, मल्याळम, मणिपुरी, मराठी, नेपाळी, "
          "ओडिया, पंजाबी, संस्कृत, संथाली, सिंधी, तमिळ, तेलुगू आणि उर्दू",
}

LINES = {
    "song": {"en": "India's national song is Vande Mataram. It was written by Bankim Chandra Chatterjee.",
             "hi": "भारत का राष्ट्रीय गीत है वंदे मातरम्। इसे बंकिम चंद्र चट्टोपाध्याय ने लिखा था।",
             "as": "ভাৰতৰ ৰাষ্ট্ৰীয় গীত হ'ল বন্দে মাতৰম্। এইটো বংকিমচন্দ্ৰ চট্টোপাধ্যায়ে লিখিছিল।",
             "mr": "भारताचं राष्ट्रीय गीत आहे वंदे मातरम्. ते बंकिमचंद्र चट्टोपाध्याय यांनी लिहिलं."},
    "anthem": {"en": "India's national anthem is Jana Gana Mana. Rabindranath Tagore wrote it in nineteen eleven, and India adopted it on the twenty-fourth of January, nineteen fifty.",
               "hi": "भारत का राष्ट्रगान है जन गण मन। इसे रवींद्रनाथ टैगोर ने उन्नीस सौ ग्यारह में लिखा, और भारत ने इसे चौबीस जनवरी, उन्नीस सौ पचास को अपनाया।",
               "as": "ভাৰতৰ ৰাষ্ট্ৰীয় সংগীত হ'ল জন গণ মন। ৰবীন্দ্ৰনাথ ঠাকুৰে ইয়াক ঊনৈশ শ এঘাৰ চনত লিখিছিল, আৰু ভাৰতে ঊনৈশ শ পঞ্চাশ চনৰ চৌবিশ জানুৱাৰীত গ্ৰহণ কৰে।",
               "mr": "भारताचं राष्ट्रगीत आहे जन गण मन. रवींद्रनाथ टागोर यांनी ते एकोणीसशे अकरा साली लिहिलं, आणि भारताने चोवीस जानेवारी एकोणीसशे पन्नास रोजी ते स्वीकारलं."},
    "pm": {"en": "The Prime Minister of India is {pm}.", "hi": "भारत के प्रधानमंत्री {pm} हैं।",
           "as": "ভাৰতৰ প্ৰধানমন্ত্ৰী হ'ল {pm}।", "mr": "भारताचे पंतप्रधान {pm} आहेत."},
    "states": {"en": "India has twenty-eight states and eight union territories.",
               "hi": "भारत में अट्ठाईस राज्य और आठ केंद्र शासित प्रदेश हैं।",
               "as": "ভাৰতত আঠাইশখন ৰাজ্য আৰু আঠখন কেন্দ্ৰীয় শাসিত অঞ্চল আছে।",
               "mr": "भारतात अठ्ठावीस राज्यं आणि आठ केंद्रशासित प्रदेश आहेत."},
    "languages": {"en": "India's constitution has twenty-two official languages, and hundreds of languages are spoken across the country. They are: {list}.",
                  "hi": "भारत के संविधान में बाईस आधिकारिक भाषाएँ हैं, और पूरे देश में सैकड़ों भाषाएँ बोली जाती हैं। वे हैं: {list}।",
                  "as": "ভাৰতৰ সংবিধানত বাইশটা চৰকাৰী ভাষা আছে, আৰু গোটেই দেশত শ শ ভাষা কোৱা হয়। সেইবোৰ হ'ল: {list}।",
                  "mr": "भारताच्या संविधानात बावीस अधिकृत भाषा आहेत, आणि देशात शेकडो भाषा बोलल्या जातात. त्या आहेत: {list}."},
    "india_capital": {"en": "The capital of India is New Delhi.", "hi": "भारत की राजधानी नई दिल्ली है।",
                      "as": "ভাৰতৰ ৰাজধানী নতুন দিল্লী।", "mr": "भारताची राजधानी नवी दिल्ली आहे."},
    "state_capital": {"en": "The capital of {name} is {cap}.", "hi": "{name} की राजधानी {cap} है।",
                      "as": "{name}ৰ ৰাজধানী {cap}।", "mr": "{name} राज्याची राजधानी {cap} आहे."},
    "ut_capital": {"en": "{name} is a union territory. Its capital is {cap}.",
                   "hi": "{name} एक केंद्र शासित प्रदेश है। इसकी राजधानी {cap} है।",
                   "as": "{name} এখন কেন্দ্ৰীয় শাসিত অঞ্চল। ইয়াৰ ৰাজধানী {cap}।",
                   "mr": "{name} हा केंद्रशासित प्रदेश आहे. त्याची राजधानी {cap} आहे."},
    "all_capitals": {"en": "Here are the capitals of India's twenty-eight states. {list}.",
                     "hi": "भारत के अट्ठाईस राज्यों की राजधानियाँ ये हैं। {list}।",
                     "as": "ভাৰতৰ আঠাইশখন ৰাজ্যৰ ৰাজধানী এইবোৰ। {list}।",
                     "mr": "भारताच्या अठ्ठावीस राज्यांच्या राजधान्या या आहेत. {list}."},
    "all_states": {"en": "India's twenty-eight states are: {list}. Do you want to hear their capitals too?",
                   "hi": "भारत के अट्ठाईस राज्य हैं: {list}। क्या तुम उनकी राजधानियाँ भी सुनना चाहोगे?",
                   "as": "ভাৰতৰ আঠাইশখন ৰাজ্য হ'ল: {list}। তুমি সিহঁতৰ ৰাজধানীও শুনিব বিচৰা নেকি?",
                   "mr": "भारताची अठ्ठावीस राज्यं आहेत: {list}. तुला त्यांच्या राजधान्याही ऐकायच्या आहेत का?"},
}
PAIR = {"en": "{name}, {cap}", "hi": "{name}, {cap}", "as": "{name}, {cap}", "mr": "{name}, {cap}"}
SEP = {"en": ". ", "hi": "। ", "as": "। ", "mr": ". "}

# what the child asks (all languages at once: a Hindi speaker may use an English word)
Q = {
    "anthem": r"national\s+anthem|jana\s+gana\s+mana|राष्ट्रगान|राष्ट्रीय\s*गान|ৰাষ্ট্ৰীয়\s*সংগীত",
    "song": r"national\s+song|vande\s+mataram|राष्ट्रीय\s*गीत|ৰাষ্ট্ৰীয়\s*গীত",
    "pm": r"prime\s+minister|\bpm\s+of\s+india|प्रधान\s*मंत्री|पंतप्रधान|প্ৰধান\s*মন্ত্ৰী",
    "states": r"how\s+many\s+states?\b|number\s+of\s+states?\b|total\s+(?:number\s+of\s+)?states?\b|कितने\s*राज्य|राज्य\s*कितने|"
              r"किती\s*राज्य|राज्यं?\s*किती|কিমান(?:খন)?\s*ৰাজ্য|ৰাজ্য\s*কিমান|কেইখন\s*ৰাজ্য|union\s+territor",
    "languages": r"how\s+many\s+languages|languages\s+(?:of|in)\s+india|total\s+languages|official\s+languages|कितनी\s*भाषा|"
                 r"भाषाएँ\s*कितनी|किती\s*भाषा|কিমান\s*ভাষা|কেইটা\s*ভাষা",
    "all_capitals": r"all\s+(?:the\s+)?(?:state\s+)?capitals|capitals\s+of\s+(?:all\s+)?(?:the\s+)?states|state\s+capitals|"
                    r"सभी\s*राज्यों\s*की\s*राजधानी|सारी\s*राजधानियाँ|सब\s*राजधानी|सभी\s*राजधानी|"
                    r"सर्व\s*राज्यांच्या\s*राजधान्या|सगळ्या\s*राजधान्या|सर्व\s*राजधान्या|সকলো\s*ৰাজ্যৰ\s*ৰাজধানী|সকলো\s*ৰাজধানী",
    "all_states": r"(?:name|list)\s+(?:all\s+)?(?:the\s+)?states|what\s+are\s+the\s+states|states\s+of\s+india|"
                  r"all\s+(?:the\s+)?states(?:'?\s+names?)?|राज्यों\s*के\s*नाम|सारे\s*राज्य\s*कौन|कौन\s*(?:से|सी)\s*राज्य|"
                  r"राज्यांची\s*नावं?|सगळी\s*राज्यं\s*कोणती|ৰাজ্যৰ\s*নাম|সকলো\s*ৰাজ্যৰ\s*নাম",
}
Q = {k: re.compile(v, re.I) for k, v in Q.items()}
CAPITAL = re.compile(r"capital|राजधानी|ৰাজধানী", re.I)
INDIA = re.compile(r"\bindia\b|भारत|ভাৰত|हिंदुस्तान", re.I)
# In Marathi "राष्ट्रगीत" is the anthem; in Hindi it is the national song.
RASHTRAGEET = re.compile(r"राष्ट्रगीत")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def _find_place(text):
    """(entry, is_territory) for the state or territory named in text, longest name first."""
    low = nfc(text.lower())
    names = []
    for group, terr in ((STATES, False), (TERRITORIES, True)):
        for entry in group:
            for n in entry[0] + entry[2]:
                names.append((nfc(n.lower()), entry, terr))
    for n, entry, terr in sorted(names, key=lambda x: -len(x[0])):
        if re.fullmatch(r"[a-z .]+", n):
            if re.search(rf"\b{re.escape(n)}\b", low):
                return entry, terr
        elif n in low:
            return entry, terr
    return None


def answer(text, lang):
    """(display, speech) or None."""
    if lang not in LANG_IDX:
        return None
    t = nfc(text)
    i = LANG_IDX[lang]
    kind = next((k for k in ("anthem", "song", "pm", "languages", "all_capitals", "all_states", "states")
                 if Q[k].search(t)), None)
    if not kind and RASHTRAGEET.search(t):
        kind = "anthem" if lang == "mr" else "song"
    if kind == "pm":
        line = LINES["pm"][lang].format(pm=PRIME_MINISTER[lang])
    elif kind == "languages":
        line = LINES["languages"][lang].format(list=LANGUAGES_22[lang])
    elif kind == "all_capitals":
        pairs = [PAIR[lang].format(name=s[0][i], cap=s[1][i]) for s in STATES]
        line = LINES["all_capitals"][lang].format(list=SEP[lang].join(pairs))
    elif kind == "all_states":
        names = [s[0][i] for s in STATES]
        line = LINES["all_states"][lang].format(list=", ".join(names))
    elif kind:
        line = LINES[kind][lang]
    elif CAPITAL.search(t):
        place = _find_place(t)
        if place:
            entry, terr = place
            line = LINES["ut_capital" if terr else "state_capital"][lang].format(name=entry[0][i], cap=entry[1][i])
        elif INDIA.search(t):
            line = LINES["india_capital"][lang]
        else:
            return None
    else:
        return None
    line = nfc(line)
    display = line.replace(SEP[lang].join([""] * 2), "\n") if kind == "all_capitals" else line
    return display, line
