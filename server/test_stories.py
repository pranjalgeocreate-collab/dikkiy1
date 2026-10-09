import random

import pytest

import stories as S


def test_thirty_stories_in_four_languages():
    assert len(S.STORIES) == 30 and len(S.BY_ID) == 30
    for s in S.STORIES:
        for lang in S.LANGS:
            assert s["title"][lang] and s["text"][lang]


@pytest.mark.parametrize("lang", S.LANGS)
def test_every_story_ends_with_a_message(lang):
    for s in S.STORIES:
        body, message = S.split_message(s["text"][lang])
        assert len(body) > 150 and 15 <= len(message) <= 180, (s["id"], message)
        display, spoken = S.telling(s, lang)
        assert spoken.endswith(message) and S.MESSAGE[lang] in spoken and message in display


@pytest.mark.parametrize("heard,ids", [
    ("tell me a story about a lion", {"lion-mouse", "rabbit-lion-well"}),
    ("हाथी की कहानी सुनाओ", {"elephant-friend"}),
    ("माकडाची गोष्ट सांग", {"monkey-crocodile", "cap-seller"}),
    ("I want a story about a dog", {"bholu-puppy"}),
    ("কাউৰীৰ সাধু কোৱা", {"thirsty-crow", "four-friends"}),
])
def test_named_story(heard, ids):
    assert S.pick(heard, [], rng=random.Random(1))["id"] in ids


def test_want_does_not_mean_ant():
    assert S.matching("I want a story") == []


def test_no_repeats_until_all_told():
    told, rng = [], random.Random(3)
    for _ in range(30):
        told.append(S.pick("tell me a story", told, rng=rng)["id"])
    assert len(set(told)) == 30


def test_random_pick_prefers_recorded_audio():
    ready = {"firefly"}
    assert S.pick("tell me a story", [], ready=lambda s: s["id"] in ready)["id"] == "firefly"


@pytest.mark.parametrize("heard,sid", [
    ("The Lion and the Mouse", "lion-mouse"),
    ("toise and the Hare", "tortoise-hare"),
    ("प्यासा कौआ", "thirsty-crow"),
    ("পিয়াহী কাউৰী", "thirsty-crow"),
    ("সৰু জোনাকী", "firefly"),
    ("ससा आणि कासव", "tortoise-hare"),
])
def test_story_by_title(heard, sid):
    assert S.by_title(heard)["id"] == sid and S.pick(heard, [sid])["id"] == sid


@pytest.mark.parametrize("heard", ["why is the sky blue", "hello", "what is two plus two", "হয়", "ha"])
def test_ordinary_talk_is_not_a_title(heard):
    assert S.by_title(heard) is None
