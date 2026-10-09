#!/usr/bin/env python3
"""Dikkey's song maker: sings traditional (public-domain) songs in a Piper voice, in code.

Each song is a list of (word-or-syllable, note, beats); None as the word is a rest.
Every sung piece is spoken by Piper, tuned to its note and fitted to its length
(see make_abc_song.tune), over a soft code-generated piano.

    .venv/bin/python make_song.py all
    .venv/bin/python make_song.py black_sheep --tempo 100
    .venv/bin/python make_song.py --list

The output file name is what the child has to say (plus "sing"/"play"/"song"/"गाना"/"सुनाओ"):
songs/black_sheep.wav -> "sing baa baa black sheep"; songs/मोटा_हाथी.wav -> "मोटा हाथी गाना सुनाओ".
"""
import argparse, os, wave

import numpy as np
from piper import PiperVoice

from make_abc_song import SR, piano, pitch_of, speak, tune, C4, D4, E4, F4, G4, A4

HERE = os.path.dirname(os.path.abspath(__file__))
G3, B3, C5 = 196.00, 246.94, 523.25
PITCH_SENTENCE = {"en": "Hello there, my friend. Today is a lovely sunny day, and we are going to sing a song.",
                  "hi": "नमस्ते दोस्त! आज बहुत अच्छा दिन है, और हम सब मिलकर एक गाना गाएँगे।"}

# ------------------------------------------------------------------ Baa Baa Black Sheep (tune: Twinkle / ABC)
BAA_BAA = [
    ("Baa", C4, 1), ("baa", C4, 1), ("black", G4, 1), ("sheep", G4, 1),
    ("have", A4, .5), ("you", A4, .5), ("a", A4, .5), ("ny", A4, .5), ("wool?", G4, 2),
    ("Yes", F4, 1), ("sir,", F4, 1), ("yes", E4, 1), ("sir,", E4, 1), ("three", D4, 1), ("bags", D4, 1), ("full!", C4, 2),
    ("One", G4, 1), ("for", G4, .5), ("the", G4, .5), ("mas", F4, 1), ("ter,", F4, 1),
    ("one", E4, 1), ("for", E4, .5), ("the", E4, .5), ("dame,", D4, 2),
    ("And", G4, .5), ("one", G4, .5), ("for", G4, .5), ("the", G4, .5), ("lit", F4, .5), ("tle", F4, .5), ("boy", F4, 1),
    ("who", E4, .5), ("lives", E4, .5), ("down", E4, .5), ("the", E4, .5), ("lane.", D4, 2),
    ("Baa", C4, 1), ("baa", C4, 1), ("black", G4, 1), ("sheep", G4, 1),
    ("have", A4, .5), ("you", A4, .5), ("a", A4, .5), ("ny", A4, .5), ("wool?", G4, 2),
    ("Yes", F4, 1), ("sir,", F4, 1), ("yes", E4, 1), ("sir,", E4, 1), ("three", D4, 1), ("bags", D4, 1), ("full!", C4, 2),
]


# ------------------------------------------------------------------ Old MacDonald (safari), traditional tune
def macdonald_verse(animal, sound):
    """One verse; `animal` is a list of syllables sung on the last notes of line 2."""
    a1, a2 = (animal + [None])[:2]
    line2 = [("And", C4, .5), ("on", C4, .5), ("his", C4, 1), ("farm", C4, 1), ("he", G3, 1), ("had", A4 / 2, 1)]
    line2 += [("a", A4 / 2, .5)] + ([(a1, G3, .5), (a2, G3, 1)] if a2 else [(a1, G3, 1.5)])
    return [
        ("Old", C4, 1), ("Mac", C4, 1), ("Don", C4, 1), ("ald", G3, 1), ("had", A4 / 2, 1), ("a", A4 / 2, 1), ("farm,", G3, 2),
        ("Ee", E4, 1), ("eye", E4, 1), ("ee", D4, 1), ("eye", D4, 1), ("oh!", C4, 2), (None, C4, 1),
        *line2,
        ("Ee", E4, 1), ("eye", E4, 1), ("ee", D4, 1), ("eye", D4, 1), ("oh!", C4, 2), (None, C4, .5),
        ("With", G3, .5), ("a", G3, .5), (sound, C4, .5), (sound, C4, .5), ("here,", C4, 1), (None, C4, .5),
        ("and", G3, .5), ("a", G3, .5), (sound, C4, .5), (sound, C4, .5), ("there,", C4, 1), (None, C4, .5),
        ("Here", C4, .5), ("a", C4, .5), (sound, C4, 1), ("there", C4, .5), ("a", C4, .5), (sound, C4, 1),
        ("ev", C4, .5), ("ry", C4, .5), ("where", C4, .5), ("a", C4, .5), (sound, C4, .5), (sound, C4, .5), (None, C4, 1),
        ("Old", C4, 1), ("Mac", C4, 1), ("Don", C4, 1), ("ald", G3, 1), ("had", A4 / 2, 1), ("a", A4 / 2, 1), ("farm,", G3, 2),
        ("Ee", E4, 1), ("eye", E4, 1), ("ee", D4, 1), ("eye", D4, 1), ("oh!", C4, 2), (None, C4, 2),
    ]


MACDONALD = (macdonald_verse(["li", "on"], "roar") + macdonald_verse(["el", "ephant"], "toot")
             + macdonald_verse(["mon", "key"], "ooh") + macdonald_verse(["snake"], "hiss"))

# ------------------------------------------------------------------ एक मोटा हाथी (counting rhyme, original simple tune)
def hathi_verse(count_word, plural):
    hathi = "हाथी"
    line1 = [(count_word, C4, 1), ("मोटे" if plural else "मोटा", E4, 1), (hathi, G4, 2),
             ("झूम", G4, 1), ("के", A4, 1), ("चले" if plural else "चला", G4, 2)]
    line2 = [("मकड़ी", F4, 1), ("के", F4, 1), ("जाले", E4, 1), ("में", E4, 1),
             ("जाकर", D4, 1), ("फँसे" if plural else "फँसा", D4, 1), (None, C4, 2)]
    return line1 + line2


MOTA_HATHI = (hathi_verse("एक", False) +
              [("उसको", G4, 1), ("फँसा", G4, 1), ("देखकर", F4, 2), ("दूसरा", E4, 1), ("आया", D4, 1), (None, C4, 2)] +
              hathi_verse("दो", True) +
              [("उनको", G4, 1), ("फँसा", G4, 1), ("देखकर", F4, 2), ("तीसरा", E4, 1), ("आया", D4, 1), (None, C4, 2)] +
              hathi_verse("तीन", True) +
              [("सबने", G4, 1), ("मिलकर", G4, 1), ("ज़ोर", F4, 1), ("लगाया", F4, 1), ("जाला", E4, 1), ("टूटा", D4, 1),
               ("सब", E4, 1), ("भाग", D4, 1), ("गए!", C4, 2)])

SONGS = {
    "black_sheep": dict(title="Baa Baa Black Sheep", notes=BAA_BAA, voice="en_US-amy-medium", lang="en", tempo=100),
    "old_macdonald": dict(title="Old MacDonald (safari)", notes=MACDONALD, voice="en_US-amy-medium", lang="en", tempo=126),
    "मोटा_हाथी": dict(title="एक मोटा हाथी", notes=MOTA_HATHI, voice="hi_IN-priyamvada-medium", lang="hi", tempo=96),
}


def base_pitch(voice, lang):
    x, sr = speak(voice, PITCH_SENTENCE[lang])
    return pitch_of(x, sr)


def make(name, tempo=None):
    spec = SONGS[name]
    voice = PiperVoice.load(os.path.join(HERE, "voices", spec["voice"] + ".onnx"))
    beat = 60.0 / (tempo or spec["tempo"])
    base = base_pitch(voice, spec["lang"])
    notes = spec["notes"]
    total = 2 * beat + sum(b for _, _, b in notes) * beat + 1.5
    vocals = np.zeros(int(SR * total), np.float32)
    music = np.zeros_like(vocals)
    for i, hz in enumerate((C4, G4)):  # count-in
        note = piano(hz, beat * 0.9)
        start = int(SR * i * beat)
        music[start:start + len(note)] += note
    t, cache = 2 * beat, {}
    for word, hz, beats in notes:
        dur = beats * beat
        start = int(SR * t)
        t += dur
        if word is None:
            continue
        note = piano(hz, dur + 0.3)
        music[start:start + len(note)] += note[: len(music) - start]
        if word not in cache:
            cache[word] = speak(voice, word)
        sung = tune(*cache[word], hz, dur, base)
        vocals[start:start + len(sung)] += sung[: len(vocals) - start]
    mix = vocals / (np.abs(vocals).max() or 1) + 0.35 * music / (np.abs(music).max() or 1)
    mix = mix / np.abs(mix).max() * 0.9
    out = os.path.join(HERE, "songs", name + ".wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((mix * 32767).astype("<i2").tobytes())
    print(f"{spec['title']}: {out} ({total:.0f}s)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", default="all")
    ap.add_argument("--tempo", type=float)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, v in SONGS.items():
            print(f"{k:16} {v['title']}")
        return
    for name in (SONGS if a.name == "all" else [a.name]):
        make(name, a.tempo)


if __name__ == "__main__":
    main()
