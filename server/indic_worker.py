#!/usr/bin/env python3
"""Indian voices worker: AI4Bharat Indic-TTS (FastPitch + HiFi-GAN), one model per language pack.

Runs in its own venv (.venv-indic: PyTorch 2.2.2 + coqui-tts 0.25.3, the last
versions that run on an Intel Mac). The brain server calls it on 127.0.0.1:8702.
  GET  /  -> {"ok": true, "packs": {"en+hi": ["female", "hindifemale", ...], "as": [...]}}
  POST /speak {"text": "...", "pack": "en+hi", "speaker": "hindifemale", "speed": 1.4}  -> audio/wav
Packs live in indic/<pack>/ (fastpitch/ + hifigan/ with model_slim.pth); each loads on first use.
"""
import io, json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import torch
from TTS.utils.synthesizer import Synthesizer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "indic")
PORT = int(os.environ.get("INDIC_PORT", 8702))

torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
lock = threading.Lock()
_loaded = {}


def packs():
    return sorted(d for d in os.listdir(ROOT)
                  if os.path.exists(os.path.join(ROOT, d, "fastpitch", "model_slim.pth"))
                  and os.path.exists(os.path.join(ROOT, d, "hifigan", "model_slim.pth")))


def speakers_of(pack):
    import json as _j
    c = _j.load(open(os.path.join(ROOT, pack, "fastpitch", "config.json")))
    return sorted(torch.load(c["speakers_file"], map_location="cpu")) if c.get("speakers_file") else ["default"]


def get(pack):
    if pack not in _loaded:
        M = os.path.join(ROOT, pack)
        print("loading pack", pack, flush=True)
        _loaded[pack] = Synthesizer(tts_checkpoint=os.path.join(M, "fastpitch", "model_slim.pth"),
                                    tts_config_path=os.path.join(M, "fastpitch", "config.json"),
                                    vocoder_checkpoint=os.path.join(M, "hifigan", "model_slim.pth"),
                                    vocoder_config=os.path.join(M, "hifigan", "config.json"), use_cuda=False)
    return _loaded[pack]


def clean(text):
    # The model's alphabet has no danda or curly quotes; a full stop gives the same pause.
    return text.replace("।", ".").replace("॥", ".").replace("’", "'").replace("‘", "'").replace("“", "").replace("”", "")


MAX_GAP = float(os.environ.get("INDIC_MAX_GAP", 0.4))  # seconds; the as model pauses ~1.4 s at every ।!?


def squeeze_silence(audio, sr, max_gap=MAX_GAP, edge=0.15, frame=0.02, floor=0.01):
    """Shorten every quiet stretch longer than max_gap to max_gap, and trim the ends to `edge`."""
    n = int(sr * frame)
    if len(audio) < n * 3:
        return audio
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    loud = np.sqrt((frames ** 2).mean(1)) > floor
    if not loud.any():
        return audio
    keep, run = [], []
    for i, is_loud in enumerate(loud):
        if is_loud:
            keep.extend(run[: int(max_gap / frame)] if keep else run[-int(edge / frame):])
            run = []
            keep.append(i)
        else:
            run.append(i)
    keep.extend(run[: int(edge / frame)])
    return frames[keep].reshape(-1)


def synth(text, pack, speaker, speed):
    if pack not in packs():
        raise ValueError(f"unknown pack {pack}; have {packs()}")
    with lock:
        syn = get(pack)
        names = syn.tts_model.speaker_manager.speaker_names if syn.tts_model.speaker_manager else []
        if names and speaker not in names:
            raise ValueError(f"unknown speaker {speaker}; {pack} has {names}")
        syn.tts_model.length_scale = max(0.6, min(2.5, speed))
        audio = np.clip(np.array(syn.tts(clean(text), speaker_name=speaker if names else None)), -1, 1)
        audio = squeeze_silence(audio, syn.output_sample_rate)
    print(f"[{pack}/{speaker}] speed={speed} chars={len(text)} -> {len(audio)/syn.output_sample_rate:.1f}s", flush=True)
    buf = io.BytesIO()
    import wave
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(syn.output_sample_rate)
        wf.writeframes((audio * 32767).astype("<i2").tobytes())
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self._send(200, json.dumps({"ok": True, "packs": {p: speakers_of(p) for p in packs()}}).encode(), "application/json")

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, synth(req["text"], req.get("pack", "en+hi"), req.get("speaker", "hindifemale"),
                                  float(req.get("speed", 1.0))), "audio/wav")
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    get("en+hi")  # warm the main pack; others load on first use
    print(f"indic worker on 127.0.0.1:{PORT}, packs {packs()}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
