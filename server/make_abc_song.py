#!/usr/bin/env python3
"""Make Dikkey's ABCD song entirely in code: no downloaded audio.

The traditional ABC song (tune: "Ah vous dirai-je, maman" / Twinkle Twinkle, 18th century)
is public domain. Each sung syllable is spoken by a Piper voice, then stretched to the note's
length and tuned to the note's pitch with ffmpeg; a soft code-generated piano plays the tune.

    .venv/bin/python make_abc_song.py            -> songs/abcd.wav
    .venv/bin/python make_abc_song.py --voice en_US-amy-medium --tempo 100
"""
import argparse, io, os, subprocess, wave

import numpy as np
from piper import PiperVoice, SynthesisConfig

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 22050
FFMPEG = os.environ.get("FFMPEG", "/usr/local/bin/ffmpeg")

# (sung syllable, note, beats). C major; one beat = one quarter note.
C4, D4, E4, F4, G4, A4 = 261.63, 293.66, 329.63, 349.23, 392.00, 440.00
SONG = [
    ("Ay", C4, 1), ("Bee", C4, 1), ("See", G4, 1), ("Dee", G4, 1), ("Ee", A4, 1), ("Eff", A4, 1), ("Jee", G4, 2),
    ("Aitch", F4, 1), ("Eye", F4, 1), ("Jay", E4, 1), ("Kay", E4, 1),
    ("Ell", D4, .5), ("Em", D4, .5), ("En", D4, .5), ("Oh", D4, .5), ("Pee", C4, 2),
    ("Cue", G4, 1), ("Arr", G4, 1), ("Ess", F4, 2), ("Tee", E4, 1), ("You", E4, 1), ("Vee", D4, 2),
    ("Dub", G4, .5), ("ble", G4, .5), ("you", G4, 1), ("Ex", F4, 2), ("Why", E4, 1), ("and", E4, 1), ("Zed", D4, 2),
    ("Now", C4, 1), ("I", C4, 1), ("know", G4, 1), ("my", G4, 1), ("Ay", A4, 1), ("Bee", A4, 1), ("Sees", G4, 2),
    ("Next", F4, 1), ("time", F4, 1), ("won't", E4, 1), ("you", E4, 1), ("sing", D4, 1), ("with", D4, 1), ("me!", C4, 2),
]


def speak(voice, text):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1.0))
    buf.seek(0)
    with wave.open(buf) as wf:
        sr = wf.getframerate()
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2").astype(np.float32) / 32768
    return x, sr


def trim(x, sr, floor=0.02):
    frame = int(sr * 0.01)
    rms = np.sqrt(np.convolve(x ** 2, np.ones(frame) / frame, mode="same"))
    idx = np.nonzero(rms > floor)[0]
    return x[idx[0]: idx[-1] + 1] if len(idx) else x


def pitch_of(x, sr):
    """Median f0 (Hz) of voiced frames by autocorrelation; 200 Hz if unsure."""
    n, hop = int(sr * 0.04), int(sr * 0.01)
    lo, hi = int(sr / 400), int(sr / 80)
    f0s = []
    for i in range(0, len(x) - n, hop):
        f = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt((f ** 2).mean()) < 0.03:
            continue
        ac = np.correlate(f, f, "full")[n - 1:]
        best = lo + int(np.argmax(ac[lo:hi]))
        if ac[best] <= 0.3 * ac[0]:
            continue
        f0s.append(sr / best)
    return float(np.median(f0s)) if f0s else 200.0


def core_pitch(x, sr):
    """Pitch of the loudest 0.2 s (the vowel you actually hear), by harmonic product spectrum."""
    n = min(len(x), int(sr * 0.2))
    e = np.convolve(x ** 2, np.ones(n), "valid")
    i = int(np.argmax(e))
    seg = x[i:i + n] * np.hanning(n)
    N = 16384
    spec = np.abs(np.fft.rfft(seg, N))
    hps = spec.copy()
    for h in (2, 3, 4):
        d = spec[::h]
        hps[:len(d)] *= d
    freqs = np.fft.rfftfreq(N, 1 / sr)
    band = (freqs > 80) & (freqs < 600)
    return float(freqs[band][np.argmax(hps[band])])


def tempo_chain(t):
    """ffmpeg atempo only takes 0.5..100 per stage, so chain stages for slow-downs."""
    parts = []
    while t < 0.5:
        parts.append("atempo=0.5")
        t /= 0.5
    parts.append(f"atempo={t:.5f}")
    return ",".join(parts)


def voice_pitch(voice):
    """The voice's natural pitch, measured once over a whole sentence (per-syllable guesses jump octaves)."""
    x, sr = speak(voice, "Hello there, my friend. Today is a lovely sunny day, and we are going to sing a song.")
    return pitch_of(x, sr)


def tune(x, sr, target_hz, target_sec, base_hz):
    """Shift pitch from the voice's base_hz to target_hz and fit the syllable into target_sec."""
    x = trim(x, sr)
    own = core_pitch(x, sr)               # pitch of this syllable's vowel (can slip an octave)
    while own > base_hz * 1.6:            # fold octave slips back toward the voice's normal range
        own /= 2
    while own < base_hz / 1.6:
        own *= 2
    f = target_hz / own
    length = len(x) / sr
    want = max(0.12, target_sec * 0.9)
    af = f"asetrate={int(sr * f)},aresample={SR}," + tempo_chain(length / f / want)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    out = subprocess.run([FFMPEG, "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                          "-af", af, "-f", "s16le", "-ar", str(SR), "-ac", "1", "pipe:1"],
                         input=pcm, capture_output=True, check=True)
    y = np.frombuffer(out.stdout, dtype="<i2").astype(np.float32) / 32768
    fade = min(len(y) // 4, int(SR * 0.02))
    if fade:
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
    return y


def piano(hz, sec):
    """Soft piano-ish note: a few harmonics with a fast attack and exponential decay."""
    t = np.arange(int(SR * sec)) / SR
    tone = sum(a * np.sin(2 * np.pi * hz * k * t) for k, a in ((1, 1.0), (2, 0.35), (3, 0.15), (4, 0.06)))
    env = np.minimum(1, t / 0.01) * np.exp(-3.0 * t)
    return (tone * env).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="en_US-amy-medium")
    ap.add_argument("--tempo", type=float, default=96, help="beats per minute")
    ap.add_argument("--out", default=os.path.join(HERE, "songs", "abcd.wav"))
    args = ap.parse_args()

    voice = PiperVoice.load(os.path.join(HERE, "voices", args.voice + ".onnx"))
    beat = 60.0 / args.tempo
    lead_in = 2 * beat   # two soft "count-in" notes before the singing starts
    total = lead_in + sum(b for _, _, b in SONG) * beat + 1.5
    vocals = np.zeros(int(SR * total), np.float32)
    music = np.zeros_like(vocals)

    for i, hz in enumerate((C4, G4)):   # count-in
        start = int(SR * i * beat)
        note = piano(hz, beat * 0.9)
        music[start:start + len(note)] += note

    base_hz = voice_pitch(voice)
    print(f"voice pitch {base_hz:.0f} Hz")
    t = lead_in
    cache = {}
    for word, hz, beats in SONG:
        dur = beats * beat
        start = int(SR * t)
        note = piano(hz, dur + 0.3)
        music[start:start + len(note)] += note[: len(music) - start]
        if word not in cache:
            cache[word] = speak(voice, word)
        sung = tune(*cache[word], hz, dur, base_hz)
        vocals[start:start + len(sung)] += sung[: len(vocals) - start]
        t += dur

    mix = 1.0 * vocals / (np.abs(vocals).max() or 1) + 0.35 * music / (np.abs(music).max() or 1)
    mix = mix / np.abs(mix).max() * 0.9
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with wave.open(args.out, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((mix * 32767).astype("<i2").tobytes())
    print(f"wrote {args.out}: {total:.1f}s, {len(SONG)} sung syllables, tempo {args.tempo:g} bpm")


if __name__ == "__main__":
    main()
