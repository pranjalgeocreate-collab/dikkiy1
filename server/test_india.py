import pytest

import india


@pytest.mark.parametrize("q,lang,want", [
    ("what is the national song of india", "en", "Vande Mataram"),
    ("what is our national anthem", "en", "Jana Gana Mana"),
    ("भारत का राष्ट्रीय गीत क्या है", "hi", "वंदे मातरम्"),
    ("राष्ट्रगीत कौन सा है", "hi", "वंदे मातरम्"),
    ("आपलं राष्ट्रगीत कोणतं", "mr", "जन गण मन"),
    ("ভাৰতৰ ৰাষ্ট্ৰীয় গীত কি", "as", "বন্দে মাতৰম্"),
    ("who is the prime minister of india", "en", "Narendra Modi"),
    ("भारत के प्रधानमंत्री कौन हैं", "hi", "नरेंद्र मोदी"),
    ("भारताचे पंतप्रधान कोण आहेत", "mr", "नरेंद्र मोदी"),
    ("ভাৰতৰ প্ৰধানমন্ত্ৰী কোন", "as", "নৰেন্দ্ৰ মোদী"),
    ("how many states are there in india", "en", "twenty-eight states and eight union territories"),
    ("how many state in india", "en", "twenty-eight states"),
    ("भारत में कितने राज्य हैं", "hi", "अट्ठाईस"),
    ("भारतात किती राज्यं आहेत", "mr", "अठ्ठावीस"),
    ("ভাৰতত কিমানখন ৰাজ্য আছে", "as", "আঠাইশখন"),
    ("how many languages are there in india", "en", "twenty-two official languages"),
    ("भारत में कितनी भाषाएँ हैं", "hi", "बाईस"),
    ("what is the capital of india", "en", "New Delhi"),
    ("भारत की राजधानी क्या है", "hi", "नई दिल्ली"),
    ("ভাৰতৰ ৰাজধানী কি", "as", "নতুন দিল্লী"),
    ("what is the capital of assam", "en", "Dispur"),
    ("অসমৰ ৰাজধানী কি", "as", "দিছপুৰ"),
    ("महाराष्ट्राची राजधानी कोणती", "mr", "मुंबई"),
    ("उत्तर प्रदेश की राजधानी", "hi", "लखनऊ"),
    ("uttarakhand capital", "en", "Dehradun"),
    ("capital of west bengal", "en", "Kolkata"),
    ("capital of kashmir", "en", "Srinagar in summer and Jammu in winter"),
    ("capital of orissa", "en", "Bhubaneswar"),
])
def test_facts(q, lang, want):
    display, speech = india.answer(q, lang)
    assert want in speech and want in display


def test_all_state_capitals():
    display, speech = india.answer("tell me all the state capitals", "en")
    assert len(india.STATES) == 28 and len(india.TERRITORIES) == 8
    assert all(s[1][0] in speech for s in india.STATES)
    assert len(display.splitlines()) >= 28


@pytest.mark.parametrize("lang", ["hi", "as", "mr"])
def test_all_capitals_other_languages(lang):
    q = {"hi": "सभी राज्यों की राजधानी बताओ", "as": "সকলো ৰাজ্যৰ ৰাজধানী কোৱা", "mr": "सर्व राज्यांच्या राजधान्या सांग"}[lang]
    i = india.LANG_IDX[lang]
    assert all(s[1][i] in india.answer(q, lang)[1] for s in india.STATES)


@pytest.mark.parametrize("q,lang", [
    ("what are the states of india", "en"),
    ("name all the states", "en"),
    ("states of india", "en"),
    ("राज्यों के नाम बताओ", "hi"),
    ("ৰাজ্যৰ নাম কোৱা", "as"),
    ("राज्यांची नावं सांग", "mr"),
])
def test_all_state_names(q, lang):
    i = india.LANG_IDX[lang]
    speech = india.answer(q, lang)[1]
    assert all(s[0][i] in speech for s in india.STATES)
    assert not any(s[1][i] in speech for s in india.STATES)   # names only, no capitals mixed in


def test_all_state_names_does_not_collide_with_count_or_capitals():
    assert india.answer("how many states are there", "en")[1] == india.answer("how many state in india", "en")[1]
    assert "Amaravati" in india.answer("all the state capitals", "en")[1]
    assert "Amaravati" not in india.answer("what are the states", "en")[1]


@pytest.mark.parametrize("q,lang,offer_phrase", [
    ("what are the states", "en", "Do you want to hear their capitals too?"),
    ("राज्यों के नाम बताओ", "hi", "क्या तुम उनकी राजधानियाँ भी सुनना चाहोगे?"),
    ("ৰাজ্যৰ নাম কোৱা", "as", "তুমি সিহঁতৰ ৰাজধানীও শুনিব বিচৰা নেকি?"),
    ("राज्यांची नावं सांग", "mr", "तुला त्यांच्या राजधान्याही ऐकायच्या आहेत का?"),
])
def test_all_state_names_offers_capitals_afterwards(q, lang, offer_phrase):
    speech = india.answer(q, lang)[1]
    assert offer_phrase in speech
    # the all_capitals trigger itself must not also carry this follow-up question
    assert offer_phrase not in india.answer("all the state capitals", "en")[1]


@pytest.mark.parametrize("lang", ["hi", "as", "mr"])
def test_no_digits_spoken_in_indian_languages(lang):
    # skills.spell_numbers would read digits in English for Assamese and Marathi
    for q in ("how many states", "how many languages", "all state capitals", "prime minister"):
        assert not any(c.isdigit() for c in india.answer(q, lang)[1])


@pytest.mark.parametrize("q", ["why is the sky blue", "tell me a story", "what is 5 plus 3", "sing a song", "capital letters"])
def test_not_india(q):
    assert india.answer(q, "en") is None
