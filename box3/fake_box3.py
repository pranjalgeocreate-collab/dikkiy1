#!/usr/bin/env python3
"""Pretends to be the ESP32-S3-BOX-3B: sends exactly what the toy firmware sends and checks the replies.
Run on the Mac with the server up:  python3 fake_box3.py [http://127.0.0.1:8700]
1) /filler?lang=en&kind=start with X-Want-Rate: 16000   (the "Hmm, let me think!" line)
2) /talk: a 16 kHz mono WAV of a child's question, headers X-Toy-Id / X-Want-Rate (no X-Lang: the server detects)
Each reply must be a 16 kHz, mono, 16-bit WAV, because the BOX-3 plays at the rate it records at."""
import io, sys, time, urllib.parse, urllib.request, wave

BRAIN = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8700").rstrip("/")
RATE = 16000


def check_wav(data, what):
    w = wave.open(io.BytesIO(data))
    ok = (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2)
    secs = w.getnframes() / w.getframerate()
    print(f"  {what}: {w.getframerate()} Hz, {w.getnchannels()} ch, {8 * w.getsampwidth()}-bit, {secs:.1f}s -> {'OK' if ok else 'WRONG FORMAT'}")
    return ok


def get(path, headers):
    req = urllib.request.Request(BRAIN + path, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status, dict(r.headers), r.read()


def child_says(text):
    """A spoken question, made with Dikkey's own English voice, then turned into what the BOX mic records."""
    _, _, wav = get("/say?" + urllib.parse.urlencode({"text": text, "lang": "en"}), {"X-Want-Rate": str(RATE)})
    return wav


ok = True
print("filler:")
status, h, body = get("/filler?lang=en&kind=start", {"X-Want-Rate": str(RATE)})
if status == 204:
    print("  (no filler recorded yet: the toy just waits quietly)")
else:
    ok &= check_wav(body, "filler")

for q in ["tell me a story", "what is two plus two", "let's play a quiz"]:
    print(f"talk: {q!r}")
    question = child_says(q)
    t = time.time()
    req = urllib.request.Request(BRAIN + "/talk", data=question, method="POST",
                                 headers={"Content-Type": "audio/wav", "X-Toy-Id": "box3-test", "X-Want-Rate": str(RATE)})
    with urllib.request.urlopen(req, timeout=300) as r:
        reply, heard = r.read(), urllib.parse.unquote(r.headers.get("X-Heard", ""))
        said, status = urllib.parse.unquote(r.headers.get("X-Reply", "")), r.headers.get("X-Status", "")
    print(f"  heard {heard!r} -> {status} in {time.time() - t:.1f}s: {said[:70]!r}")
    ok &= check_wav(reply, "reply")
# leave no quiz running for the test toy
urllib.request.urlopen(urllib.request.Request(BRAIN + "/chat", data=b'{"text":"stop","lang":"en"}', method="POST",
                       headers={"Content-Type": "application/json", "X-Toy-Id": "box3-test"}), timeout=60).read()
print("ALL OK" if ok else "SOMETHING IS WRONG")
sys.exit(0 if ok else 1)
