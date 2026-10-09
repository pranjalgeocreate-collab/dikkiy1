import datetime

import pytest

import child_profile as P

TODAY = datetime.date(2026, 9, 30)


@pytest.fixture(autouse=True)
def db(tmp_path):
    P.open_db(str(tmp_path / "c.db"))
    P.flow.clear(); P.asked.clear()


@pytest.mark.parametrize("said,dob", [
    ("5 March 2019", "2019-03-05"),
    ("march 5th 2019", "2019-03-05"),
    ("the fifth of march twenty nineteen", "2019-03-05"),
    ("5/3/2019", "2019-03-05"),
    ("12-11-18", "2018-11-12"),
    ("पाँच मार्च दो हज़ार उन्नीस", "2019-03-05"),
    ("5 मार्च 2019", "2019-03-05"),
    ("पाच मार्च दोन हजार एकोणीस", "2019-03-05"),
    ("१२ नोव्हेंबर २०१८", "2018-11-12"),
    ("পাঁচ মাৰ্চ দুই হাজাৰ ঊনৈশ", "2019-03-05"),
    ("৫ মাৰ্চ ২০১৯", "2019-03-05"),
    ("25 December", "--12-25"),
])
def test_parse_dob(said, dob):
    assert P.parse_dob(said, TODAY) == dob


@pytest.mark.parametrize("said", ["I don't know", "31 February 2019", "5 March 1950", "banana", "5 March 2030"])
def test_bad_dob(said):
    assert P.parse_dob(said, TODAY) is None


@pytest.mark.parametrize("said,name", [
    ("my name is aarav", "Aarav"), ("Aarav", "Aarav"), ("I'm Riya", "Riya"), ("मेरा नाम अनु है", "अनु"),
    ("माझं नाव ओम आहे", "ओम"), ("মোৰ নাম জ্যোতি", "জ্যোতি"), ("মই জ্যোতি", "জ্যোতি"),
])
def test_names(said, name):
    assert P.answer_name(said) == name


def test_full_conversation_english():
    assert P.handle("toy", "hello", "en", TODAY)[0] == "Hi! I'm Dikkey. What's your name?"
    r, _ = P.handle("toy", "my name is aarav sharma", "en", TODAY)
    assert "Aarav" in r and "birthday" in r and "Sharma" not in r        # first name only
    r, _ = P.handle("toy", "5 march 2019", "en", TODAY)
    assert r == "Thank you, Aarav! I will remember that your birthday is the fifth of March. And what is the name of your school?"
    r, _ = P.handle("toy", "my school is Little Flowers Public School", "en", TODAY)
    assert "pet name" in r
    assert P.handle("toy", "call me Chintu", "en", TODAY)[0] == "Okay, Chintu! From now on I'll call you Chintu."
    c = P.current()
    assert (c["name"], c["dob"], c["school"], c["pet_name"]) == ("Aarav", "2019-03-05", "Little Flowers Public School", "Chintu")
    assert P.handle("toy", "what's my name", "en", TODAY)[0] == "Your name is Chintu!"
    assert P.handle("toy", "what is my school", "en", TODAY)[0] == "Your school is Little Flowers Public School."
    assert P.handle("toy", "how old am i", "en", TODAY)[0] == "You are seven years old!"
    assert P.handle("toy", "when is my birthday", "en", TODAY)[0] == "Your birthday is the fifth of March!"
    assert P.handle("toy", "hello", "en", TODAY) is None                  # known child: no asking again
    assert P.handle("toy", "why is the sky blue", "en", TODAY) is None


def test_assamese_conversation_speaks_words_not_digits():
    P.handle("toy", "নমস্কাৰ", "as", TODAY)
    P.handle("toy", "মোৰ নাম জ্যোতি", "as", TODAY)
    r, _ = P.handle("toy", "পাঁচ মাৰ্চ দুই হাজাৰ ঊনৈশ", "as", TODAY)
    assert "জ্যোতি" in r and "পাঁচ মাৰ্চ" in r and "স্কুলৰ নাম" in r and not any(c.isdigit() for c in r)
    assert "মৰমৰ" in P.handle("toy", "মোৰ স্কুলৰ নাম ডন বস্কো স্কুল", "as", TODAY)[0]
    assert P.handle("toy", "মোক জুনু বুলি মাতে", "as", TODAY)[0] == "ঠিক আছে, জুনু! এতিয়াৰ পৰা মই তোমাক জুনু বুলি মাতিম।"
    assert P.current()["school"] == "ডন বস্কো স্কুল"
    assert P.handle("toy", "মোৰ বয়স কিমান", "as", TODAY)[0] == "তোমাৰ বয়স সাত বছৰ!"


@pytest.mark.parametrize("lang,school_said,school,pet_said,pet", [
    ("hi", "मेरे स्कूल का नाम केंद्रीय विद्यालय है", "केंद्रीय विद्यालय", "मुझे गुड्डू बुलाते हैं", "गुड्डू"),
    ("mr", "माझ्या शाळेचं नाव ज्ञानप्रबोधिनी आहे", "ज्ञानप्रबोधिनी", "मला बंटी म्हणतात", "बंटी"),
])
def test_school_and_pet_name_hindi_marathi(lang, school_said, school, pet_said, pet):
    P.add("X", "2019-01-01")
    P.flow["toy"] = {"step": "school", "id": P.current()["id"], "tries": 0}
    P.handle("toy", school_said, lang, TODAY)
    P.handle("toy", pet_said, lang, TODAY)
    assert (P.current()["school"], P.current()["pet_name"]) == (school, pet)


def test_skip_everything():
    P.handle("toy", "hi", "en", TODAY); P.handle("toy", "Riya", "en", TODAY)
    assert "didn't understand" in P.handle("toy", "blue", "en", TODAY)[0]
    r = P.handle("toy", "no", "en", TODAY)[0]
    assert "grown-up" in r and "school" in r
    assert "pet name" in P.handle("toy", "I don't know", "en", TODAY)[0]
    assert P.handle("toy", "no", "en", TODAY)[0] == "Okay, I'll call you Riya!"
    c = P.current()
    assert (c["name"], c["dob"], c["school"], c["pet_name"]) == ("Riya", None, None, "Riya")
    assert "haven't told me" in P.handle("toy", "when is my birthday", "en", TODAY)[0]


def test_known_child_is_asked_what_is_missing_once():
    P.add("Munu", "2021-03-15")
    r = P.handle("toy", "hello", "en", TODAY)[0]
    assert r == "Hello, Munu! And what is the name of your school?"
    P.handle("toy", "Sunshine Kids", "en", TODAY)
    P.handle("toy", "they call me Mimi", "en", TODAY)
    assert P.call_name(P.current()) == "Mimi"
    assert P.handle("toy", "hello", "en", TODAY) is None


def test_birthday_greeting_once():
    P.add("Om", "2020-09-30")
    assert P.birthday_line("mr", TODAY) == "वाढदिवसाच्या खूप खूप शुभेच्छा, Om! आज तुझा खास दिवस आहे!"
    P.save(P.current()["id"], pet_name="Omu")
    P.mark_greeted(P.current()["id"], "")
    assert "Omu" in P.birthday_line("en", TODAY)
    assert P.birthday_line("mr", TODAY) is None


@pytest.mark.parametrize("name,lang,want", [
    ("Munu", "as", "মুনু"), ("Munu", "hi", "मुनु"), ("Munu", "mr", "मुनु"), ("Munu", "en", "Munu"),
    ("Riya", "as", "ৰিয়া"), ("Riya", "hi", "रिया"), ("Aarav", "hi", "आरव"), ("Aarav", "as", "আৰৱ"),
    ("Jyoti", "as", "জ্যোতি"), ("Om", "hi", "ओम"), ("मुनु", "en", "Munu"), ("জ্যোতি", "hi", "ज्योति"),
])
def test_name_in_each_language(name, lang, want):
    """The name is said by the same voice as the reply, so it must be in that language's script."""
    assert P.name_in(name, lang) == want
