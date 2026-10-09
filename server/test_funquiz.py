import random

import pytest

import funquiz as F


@pytest.fixture(autouse=True)
def clean():
    F.games.clear(); F.last_round.clear()


def test_bank_complete():
    assert len(F.BANK) >= 100
    assert len({q[0] for q, _, _ in F.BANK}) == len(F.BANK)          # no question twice
    for q, opts, right in F.BANK:
        assert len(q) == 4 and all(q) and len(opts) == 3 and 0 <= right < 3
        assert all(len(o) >= 4 and all(o[:4]) for o in opts)


@pytest.mark.parametrize("lang", F.LANGS)
def test_every_right_answer_is_recognised_in_its_own_language(lang):
    for q, opts, right in F.BANK:
        assert F.pick(opts[right][F.IDX[lang]], opts) == right, (q[0], lang)


@pytest.mark.parametrize("said,qi,want", [
    ("two", 13, 0), ("it has two wheels", 13, 0), ("eight", 2, 2), ("cow", 0, 1), ("गाय", 0, 1), ("গৰু", 0, 1),
    ("the first one", 0, None), ("1", 3, 0), ("मोर", 8, 1), ("ময়ূৰ", 8, 1), ("वाघ", 17, 1),
])
def test_pick(said, qi, want):
    assert F.pick(said, F.BANK[qi][1]) == want


def play(lang, answers):
    rng = random.Random(1)
    first = F.start("t", lang, rng)
    replies = [first]
    for a in answers(lambda: F.BANK[F.games["t"]["qs"][F.games["t"]["n"]]]):
        replies.append(F.turn("t", a, lang, rng))
    return replies


@pytest.mark.parametrize("lang", F.LANGS)
def test_perfect_game(lang):
    i = F.IDX[lang]
    def answers(cur):
        for _ in range(10):
            _, opts, right = cur()
            yield opts[right][i]
    replies = play(lang, answers)
    assert not F.active("t")
    last = replies[-1]
    assert F.child_profile.num_word(10, lang) in last and F.CHEER[lang][0] in last
    assert not any(c.isdigit() for r in replies for c in r)   # numbers are spoken as words


def test_wrong_unclear_dont_know_and_stop():
    F.start("t", "en", random.Random(2))
    q, opts, right = F.BANK[F.games["t"]["qs"][0]]
    assert F.turn("t", "banana boat", "en").startswith("Which one?")        # unclear: asked once more
    wrong = (right + 1) % 3
    assert F.turn("t", opts[wrong][0], "en").startswith("Nice try! The answer is " + opts[right][0])
    assert F.turn("t", "I don't know", "en").startswith("That's okay! The answer is")
    assert "Question three" in F.turn("t", "again", "en")
    assert F.turn("t", "stop", "en") == "Okay, we'll stop the quiz. Let's play again soon!"
    assert not F.active("t")


def test_next_game_uses_new_questions():
    F.start("t", "en", random.Random(3)); first = set(F.games["t"]["qs"])
    F.games.clear()
    F.start("t", "en", random.Random(4)); second = set(F.games["t"]["qs"])
    assert not first & second


@pytest.mark.parametrize("q", ["let's play a quiz", "quiz time", "क्विज़ खेलें", "কুইজ খেলোঁ", "प्रश्नमंजुषा खेळूया"])
def test_start_phrases(q):
    assert F.START.search(q)


@pytest.mark.parametrize("lang", F.LANGS)
def test_every_choice_is_heard_as_itself(lang):
    """Saying any choice picks that choice, never another one (e.g. ৰাতিপুৱা is not ৰাতি)."""
    for q, opts, _ in F.BANK:
        for i, o in enumerate(opts):
            assert F.pick(o[F.IDX[lang]], opts) == i, (q[0], lang, o[F.IDX[lang]])
