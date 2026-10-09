"""Run: .venv/bin/python -m pytest -q test_skills.py"""
import unicodedata

import pytest

from skills import answer, en_words, find_arithmetic, hi_words, spell_numbers


def ans(text, lang="en"):
    out = answer(text, lang)
    return out and (out.name, out.display)


# ---------------------------------------------------------------- arithmetic: must compute exactly
@pytest.mark.parametrize("text,lang,shown", [
    ("What is 5 plus 3?", "en", "5 + 3 = 8"),
    ("what's twelve times eleven", "en", "12 × 11 = 132"),
    ("How much is 100 divided by 4", "en", "100 ÷ 4 = 25"),
    ("7 minus 9", "en", "7 - 9 = -2"),
    ("subtract 3 from 10", "en", "10 - 3 = 7"),
    ("5 into 6", "en", "5 × 6 = 30"),
    ("10 by 4", "en", "10 ÷ 4 = 2.5"),
    ("what is 5 and 3", "en", "5 + 3 = 8"),
    ("twenty five plus seventeen", "en", "25 + 17 = 42"),
    ("2 + 3 * 4", "en", "2 + 3 × 4 = 14"),
    ("what is 1 divided by 3", "en", "1 ÷ 3 = 0.33"),
    ("पाँच और तीन कितने होते हैं", "hi", "5 + 3 = 8"),
    ("5 और 3 जोड़ दो", "hi", "5 + 3 = 8"),            # दो here is "give", not 2
    ("10 में से 3 घटाओ", "hi", "10 - 3 = 7"),
    ("सात गुणा आठ कितना होता है", "hi", "7 × 8 = 56"),
    ("१२ भाग ४", "hi", "12 ÷ 4 = 3"),
    ("बीस माइनस छह", "hi", "20 - 6 = 14"),
    ("नौ टाइम्स नौ", "hi", "9 × 9 = 81"),
])
def test_arithmetic(text, lang, shown):
    assert ans(text, lang) == ("math", shown)


def test_divide_by_zero_is_friendly():
    assert answer("what is 5 divided by 0", "en").name == "math"
    assert "zero" in answer("what is 5 divided by 0", "en").speech


def test_math_speech_uses_words_not_digits():
    s = answer("what is 7 times 9", "en").speech
    assert s == "seven times nine equals sixty three!"
    h = answer("सात गुणा नौ", "hi").speech
    assert h == "सात गुणा नौ बराबर तिरसठ!" and not any(c.isdigit() for c in h)


# ---------------------------------------------------------------- must NOT be treated as maths
@pytest.mark.parametrize("text,lang", [
    ("I am 5 years old and my sister is 3", "en"),
    ("tell me 3 stories", "en"),
    ("मुझे एक कहानी सुनाओ", "hi"),
    ("मुझे दो कहानियाँ सुनाओ", "hi"),
    ("मैं 7 साल का हूँ और मेरा भाई 4 का", "hi"),
    ("I have two dogs and one cat", "en"),
    ("what is your name", "en"),
    ("can you go into the garden", "en"),
    ("tell me a story after a nap", "en"),
])
def test_not_a_skill(text, lang):
    assert answer(text, lang) is None, answer(text, lang)


# ---------------------------------------------------------------- tables & counting
def test_table_en():
    out = answer("tell me the table of 7", "en")
    assert out.name == "table" and out.display.splitlines()[-1] == "7 × 10 = 70"
    assert "seven times ten is seventy" in out.speech


def test_table_hi_pahada_words():
    out = answer("पाँच का पहाड़ा सुनाओ", "hi")
    assert out.name == "table"
    assert "पाँच दूनी दस" in out.speech and "पाँच दहाई पचास" in out.speech


def test_table_hi_nukta_either_form():
    decomposed = unicodedata.normalize("NFD", "पाँच का पहाड़ा")
    assert answer(decomposed, "hi").name == "table"


@pytest.mark.parametrize("text,lang,shown", [
    ("count to 5", "en", "1, 2, 3, 4, 5"),
    ("count from 3 to 6", "en", "3, 4, 5, 6"),
    ("can you count till ten", "en", "1, 2, 3, 4, 5, 6, 7, 8, 9, 10"),
    ("1 से 5 तक गिनती सुनाओ", "hi", "1, 2, 3, 4, 5"),
    ("गिनती 3 तक", "hi", "1, 2, 3"),
])
def test_counting(text, lang, shown):
    assert ans(text, lang) == ("count", shown)


def test_counting_hi_speech():
    assert answer("गिनती 3 तक", "hi").speech == "एक, दो, तीन!"


# ---------------------------------------------------------------- alphabets
def test_english_alphabet():
    out = answer("can you sing the ABC", "en")
    assert out.name == "abc" and out.display == " ".join("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert out.speech.count(",") == 25 and "Double you" in out.speech


def test_english_alphabet_asked_in_hindi_is_spoken_in_devanagari():
    out = answer("अंग्रेज़ी वर्णमाला सुनाओ", "hi")
    assert out.name == "abc" and "डब्ल्यू" in out.speech


@pytest.mark.parametrize("text,shown", [
    ("what comes after c?", "After C comes D"),
    ("what letter comes before m", "Before M comes L"),
    ("what comes after z", "Z is the last letter!"),
])
def test_next_letter(text, shown):
    assert answer(text, "en").display == shown


@pytest.mark.parametrize("text,lang", [
    ("hindi alphabet please", "en"),
    ("हिंदी वर्णमाला सुनाओ", "hi"),
    ("क ख ग सुनाओ", "hi"),
    ("स्वर और व्यंजन बताओ", "hi"),
])
def test_hindi_alphabet(text, lang):
    out = answer(text, lang)
    assert out.name == "varnamala"
    assert "अ" in out.speech and "ज्ञ" in out.speech


def test_hindi_swar_only():
    out = answer("हिंदी के स्वर सुनाओ", "hi")
    assert "अः" in out.speech and "क्ष" not in out.speech


def test_assamese_is_left_to_llm():
    assert answer("৫ আৰু ৩ কিমান", "as") is None


# ---------------------------------------------------------------- number words
@pytest.mark.parametrize("n,en,hi", [
    (0, "zero", "शून्य"), (17, "seventeen", "सत्रह"), (99, "ninety nine", "निन्यानवे"),
    (100, "one hundred", "सौ"), (132, "one hundred and thirty two", "एक सौ बत्तीस"),
    (2025, "two thousand and twenty five", "दो हज़ार पच्चीस"), (150000, "one hundred and fifty thousand", "एक लाख पचास हज़ार"),
])
def test_number_words(n, en, hi):
    assert en_words(n) == en and hi_words(n) == unicodedata.normalize("NFC", hi)


def test_spell_numbers_in_llm_replies():
    assert spell_numbers("I have 7 friends and 9 toys.", "en") == "I have seven friends and nine toys."
    assert spell_numbers("मेरे पास 7 खिलौने हैं।", "hi") == unicodedata.normalize("NFC", "मेरे पास सात खिलौने हैं।")
    assert spell_numbers("It costs 2.5 coins", "en") == "It costs two point five coins"


# ================================================================== new skills
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import skills
from skills import (answer as A, blocked_hit, in_bedtime, quiz_start, quiz_turn, DEFAULT_BLOCKED,
                    count_along, COUNT_ALONG_START)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 27, 15, 45, tzinfo=IST)   # a Sunday


@pytest.mark.parametrize("text,lang,name,shown", [
    ("what time is it?", "en", "time", "3:45 PM"),
    ("कितने बजे हैं", "hi", "time", "3:45 PM"),
    ("what day is it today", "en", "date", "Sunday, 27 September 2026"),
    ("आज कौन सा दिन है", "hi", "date", "रविवार, 27 सितंबर 2026"),
    ("what's the date", "en", "date", "Sunday, 27 September 2026"),
])
def test_time_date(text, lang, name, shown):
    out = A(text, lang, now=NOW)
    assert (out.name, out.display) == (name, unicodedata.normalize("NFC", shown))


def test_time_speech():
    assert A("what time is it", "en", now=NOW).speech == "It's three forty five in the afternoon."
    assert A("what time is it", "en", now=NOW.replace(hour=9, minute=5)).speech == "It's nine oh five in the morning."
    assert A("कितने बजे हैं", "hi", now=NOW).speech == unicodedata.normalize("NFC", "अभी दोपहर के तीन बजकर पैंतालीस मिनट हुए हैं।")
    assert A("what's the date", "en", now=NOW).speech == "Today is Sunday, the twenty seventh of September, two thousand and twenty six."


def test_days_list_is_not_todays_day():
    out = A("tell me the days of the week", "en", now=NOW)
    assert out.name == "days" and out.display.startswith("Monday")
    assert A("हफ्ते के दिन बताओ", "hi").name == "days"
    assert A("months of the year", "en").display.endswith("December")
    assert A("महीनों के नाम सुनाओ", "hi").name == "months"


@pytest.mark.parametrize("text,first,last", [
    ("बारहखड़ी सुनाओ", "क", "कः"),
    ("ख की बारहखड़ी", "ख", "खः"),
    ("can you say the barakhadi", "क", "कः"),
    ("म की मात्रा", "म", "मः"),
])
def test_barakhadi(text, first, last):
    out = A(text, "hi")
    forms = out.display.split()
    assert out.name == "barakhadi" and forms[0] == first and forms[-1] == unicodedata.normalize("NFC", last) and len(forms) == 12


# ---------------------------------------------------------------- colors
@pytest.mark.parametrize("text,lang", [
    ("what colors do you know", "en"), ("name the colors", "en"), ("colours", "en"),
    ("रंग बताओ", "hi"), ("कौन से रंग", "hi"), ("रंग सुनाओ", "hi"),
])
def test_colors(text, lang):
    out = A(text, lang)
    assert out.name == "colors"
    words = skills.HI_COLORS if lang == "hi" else skills.EN_COLORS
    assert all(c in out.display for c in words) and all(c in out.speech for c in words)
    assert len(words) == 10


def test_colors_does_not_collide_with_alphabet():
    assert A("sing the alphabet", "en").name == "abc"
    assert A("name the colors", "en").name == "colors"
    assert A("हिंदी वर्णमाला सुनाओ", "hi").name == "varnamala"
    assert A("रंग बताओ", "hi").name == "colors"


# ---------------------------------------------------------------- clock lesson
@pytest.mark.parametrize("text,lang", [
    ("how to read a clock", "en"), ("how does a clock work", "en"), ("teach me the clock", "en"),
    ("clock lesson", "en"), ("how to tell time", "en"),
    ("घड़ी कैसे देखें", "hi"), ("घड़ी पढ़ना सिखाओ", "hi"), ("घड़ी के बारे में", "hi"),
])
def test_clock_lesson(text, lang):
    out = A(text, lang)
    assert out.name == "clock_lesson"
    steps = skills.CLOCK_STEPS_HI if lang == "hi" else skills.CLOCK_STEPS_EN
    assert all(s in out.speech for s in steps)
    assert out.display.count("\n") == len(steps) - 1   # one numbered line per step
    assert "1. " in out.display and f"{len(steps)}. " in out.display


def test_clock_lesson_does_not_collide_with_ask_time():
    assert A("what time is it", "en", now=NOW).name == "time"
    assert A("how to read a clock", "en").name == "clock_lesson"
    assert A("कितने बजे हैं", "hi", now=NOW).name == "time"
    assert A("घड़ी कैसे देखें", "hi").name == "clock_lesson"


# ---------------------------------------------------------------- Assamese alphabet
def test_assamese_alphabet_full_vowels_and_consonants():
    out = skills.assamese_alphabet("অসমীয়া বৰ্ণমালা", "as")
    assert out.name == "varnamala"
    assert all(v in out.display for v in skills.AS_SWAR)
    assert all(c in out.display for c in skills.AS_VYANJAN)
    assert len(skills.AS_SWAR) == 11 and len(skills.AS_VYANJAN) == 34


def test_assamese_alphabet_vowels_only_and_consonants_only():
    vowels = skills.assamese_alphabet("স্বৰবৰ্ণ", "as")
    consonants = skills.assamese_alphabet("ব্যঞ্জনবৰ্ণ", "as")
    assert "ব্যঞ্জন" not in vowels.display and "স্বৰবৰ্ণ" in vowels.display
    assert "স্বৰবৰ্ণ" not in consonants.display and "ব্যঞ্জন" in consonants.display


def test_assamese_alphabet_requires_assamese_lang():
    assert skills.assamese_alphabet("অসমীয়া বৰ্ণমালা", "hi") is None
    assert skills.assamese_alphabet("অসমীয়া বৰ্ণমালা", "en") is None


def test_assamese_alphabet_english_trigger_phrase_also_works():
    assert skills.ASSAMESE_ALPHA.search("assamese alphabet")
    assert skills.assamese_alphabet("tell me the assamese alphabet", "as") is not None


def test_assamese_not_included_in_the_general_skills_router():
    # answer() stays en/hi-only on purpose; Assamese alphabet is called separately by the server
    assert A("অসমীয়া বৰ্ণমালা", "as") is None


def test_rhymes():
    assert A("sing twinkle twinkle", "en").display.startswith("Twinkle Twinkle Little Star")
    assert A("मछली जल की रानी सुनाओ", "hi").display.startswith("मछली जल की रानी है")
    out = A("sing me a rhyme", "en", rng=random.Random(1))
    assert out.name == "rhyme" and "\n" not in out.speech
    assert A("कोई कविता सुनाओ", "hi", rng=random.Random(1)).name == "rhyme"


def test_story_and_chat_still_go_to_llm():
    for text, lang in [("tell me a story", "en"), ("कहानी सुनाओ", "hi"), ("what is your favourite colour", "en"),
                       ("do you like elephants", "en")]:
        assert A(text, lang, now=NOW) is None, text


# ---------------------------------------------------------------- quiz
def test_quiz_flow_correct_wrong_stop():
    rng, st = random.Random(7), {}
    start = quiz_start(st, "en", 6, rng)
    assert st["active"] and st["level"] == 2 and start.speech.startswith("Let's play")
    a, op, b, ans = st["q"]
    out = quiz_turn(st, f"it's {ans}", "en", rng)
    assert out.display.startswith("✓") and st["correct"] == 1 and st["asked"] == 2
    a, op, b, ans = st["q"]
    out = quiz_turn(st, str(ans + 1), "en", rng)
    assert out.display.startswith("✗") and "Good try!" in out.speech and st["correct"] == 1
    out = quiz_turn(st, "I don't know", "en", rng)
    assert out.display.startswith("✗")
    end = quiz_turn(st, "stop", "en", rng)
    assert not st["active"] and end.display == "Score: 1/3"


def test_quiz_hindi_answer_in_words_and_level_up():
    rng, st = random.Random(3), {}
    quiz_start(st, "hi", 5, rng)
    assert st["level"] == 1
    for _ in range(3):
        ans = st["q"][3]
        out = quiz_turn(st, skills.hi_words(ans), "hi", rng)
        assert out.display.startswith("✓")
    assert st["level"] == 2   # three right in a row → harder


def test_quiz_ends_after_ten_and_moves_on_when_child_changes_topic():
    rng, st = random.Random(5), {}
    quiz_start(st, "en", 8, rng)
    for _ in range(9):
        quiz_turn(st, str(st["q"][3]), "en", rng)
    last = quiz_turn(st, str(st["q"][3]), "en", rng)
    assert not st["active"] and "ten out of ten" in last.speech
    st2 = {}
    quiz_start(st2, "en", 8, rng)
    assert quiz_turn(st2, "tell me about dinosaurs", "en", rng) is None and not st2["active"]


def test_quiz_questions_are_valid():
    rng = random.Random(0)
    for level in (1, 2, 3, 4):
        for _ in range(300):
            a, op, b, ans = skills.quiz_question(level, rng)
            assert ans == skills.safe_eval(f"{a} {op} {b}") and ans >= 0


# ---------------------------------------------------------------- count along
def test_count_along_trigger_does_not_collide_with_one_shot_count():
    assert COUNT_ALONG_START.search("count with me")
    assert COUNT_ALONG_START.search(unicodedata.normalize("NFC", "चलो गिनती करते हैं"))
    assert not COUNT_ALONG_START.search("count to 100")
    assert not COUNT_ALONG_START.search(unicodedata.normalize("NFC", "सौ तक गिनती"))


def test_count_along_recites_one_to_hundred_continuously():
    out = count_along("en")
    assert out.name == "count_along" and out.speed == skills.COUNT_ALONG_SPEED
    assert out.display == ", ".join(str(n) for n in range(1, 101))
    assert "one" in out.speech and "one hundred" in out.speech and "Want me to count again" in out.speech
    # every number from 1 to 100 is actually spoken, in words, in order
    positions = [out.speech.index(skills.en_words(n)) for n in range(1, 101)]
    assert positions == sorted(positions)


def test_count_along_hindi_is_in_hindi_and_slow():
    out = count_along("hi")
    assert out.speed == skills.COUNT_ALONG_SPEED
    assert skills.hi_words(1) in out.speech and skills.hi_words(100) in out.speech
    assert "फिर से गिनूँ" in out.speech


def test_count_along_is_deterministic_so_it_is_cacheable():
    assert count_along("en") == count_along("en")
    assert count_along("hi") == count_along("hi")


# ---------------------------------------------------------------- parent controls
@pytest.mark.parametrize("reply,hit", [
    ("The dragon breathed fire and flew home.", None),
    ("Hello! How are you?", None),                      # 'hell' must not match 'hello'
    ("You should never play with a knife.", "knife"),
    ("Some people drink beer.", "beer"),
    ("उसने बंदूक उठाई", "बंदूक"),
    ("मछली बहुत सुंदर है", None),
])
def test_blocked_words(reply, hit):
    got = blocked_hit(reply, DEFAULT_BLOCKED)
    assert got == (unicodedata.normalize("NFC", hit) if hit else None)


@pytest.mark.parametrize("hh,mm,expect", [(20, 59, False), (21, 0, True), (23, 30, True), (3, 0, True), (6, 59, True), (7, 0, False), (12, 0, False)])
def test_bedtime_window_wraps_midnight(hh, mm, expect):
    assert in_bedtime(NOW.replace(hour=hh, minute=mm), "21:00", "07:00") is expect


def test_bedtime_daytime_window():
    assert in_bedtime(NOW.replace(hour=14, minute=0), "13:00", "15:00") is True
    assert in_bedtime(NOW.replace(hour=16, minute=0), "13:00", "15:00") is False


# ---------------------------------------------------------------- phonics (parent's list)
@pytest.mark.parametrize("text,lang,shown", [
    ("what is B for?", "en", "B for Ball or B for Bat"),
    ("A for?", "en", "A for Apple or A for Ant"),
    ("tell me z for", "en", "Z for Zebra"),
    ("x for", "en", "X: Axe, Box or Fox"),
    ("what is m for", "hi", "M for Monkey or M for Mouse"),
])
def test_phonics_one_letter(text, lang, shown):
    out = A(text, lang)
    assert (out.name, out.display, out.speak_lang) == ("phonics", shown, "en")


def test_phonics_full_list():
    out = A("say a for apple", "en")
    rows = out.display.splitlines()
    assert out.name == "phonics" and len(rows) == 26 and rows[0] == "A for Apple or A for Ant" and rows[-1] == "Z for Zebra"
    assert "Double you for Whale" in out.speech and out.speak_lang == "en"
    assert A("ए फॉर एप्पल सुनाओ", "hi").name == "phonics"


def test_phonics_does_not_steal_normal_sentences():
    for text in ("I am going for a walk", "thanks for playing", "what is it for", "is this for me"):
        assert A(text, "en") is None, text


# ---------------------------------------------------------------- goodbye / thank you
from skills import goodbye


@pytest.mark.parametrize("text,lang", [("bye", "en"), ("Okay bye bye!", "en"), ("goodbye Dikkey", "en"), ("see you tomorrow", "en"),
                                       ("I have to go", "en"), ("टाटा", "hi"), ("अच्छा बाय", "hi"), ("फिर मिलेंगे", "hi"), ("বিদায়", "as")])
def test_goodbye_says_thank_you(text, lang):
    out = goodbye(text, lang, "Aarav")
    assert out and out.name == "goodbye" and "Aarav" in out.speech


@pytest.mark.parametrize("text", ["maybe later", "can I see your toy", "I saw a byebye bird", "tell me about the taj mahal"])
def test_goodbye_not_triggered(text):
    assert goodbye(text, "en") is None


def test_goodbye_without_name():
    assert goodbye("bye", "en").speech == "Thank you for playing with me! I had so much fun. See you soon!"


# ---------------------------------------------------------------- stop
from skills import stop_request


@pytest.mark.parametrize("text,lang", [("stop", "en"), ("Stop!", "en"), ("please stop the song", "en"), ("be quiet", "en"),
                                       ("बस", "hi"), ("रुको", "hi"), ("चुप हो जाओ", "hi"), ("गाना बंद करो", "hi"), ("থমা", "as")])
def test_stop_request(text, lang):
    assert stop_request(text, lang).name == "stop"


@pytest.mark.parametrize("text", ["what is a bus stop", "don't stop the music", "can you stop by my house", "बस में कौन बैठा"])
def test_stop_not_triggered_mid_sentence(text):
    assert stop_request(text, "en") is None


# ---------------------------------------------------------------- offline / help
from skills import can_do, offline_line


@pytest.mark.parametrize("text,lang", [("what can you do?", "en"), ("help", "en"), ("what can we play", "en"),
                                       ("तुम क्या क्या कर सकते हो", "hi"), ("तुम क्या कर सकती हो", "hi"), ("তুমি কি কৰিব পাৰা", "as")])
def test_can_do(text, lang):
    assert can_do(text, lang).name == "help"


def test_can_do_not_triggered():
    for t in ("can you help me find my shoe", "what do you like to eat"):
        assert can_do(t, "en") is None, t


def test_offline_line_has_no_digits_and_mentions_songs():
    for lang in ("en", "hi", "as"):
        line = offline_line(lang)
        assert not any(c.isdigit() for c in line)
    assert "A B C D song" in offline_line("en") and "गाना" in offline_line("hi")
