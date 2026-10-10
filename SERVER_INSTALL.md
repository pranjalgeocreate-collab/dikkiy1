# Dikkey brain: install on a server

Python 3.11, Linux or macOS, and ffmpeg (`sudo apt install ffmpeg` on Ubuntu/Debian). About 2 GB RAM free
and 3 GB disk. The first start downloads the Whisper speech models (about 500 MB), so it needs internet.

```bash
git clone https://github.com/pranjalgeocreate-collab/dikkiy1.git talktoy && cd talktoy/server
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp settings.example.json settings.json     # then set the child's name/age, or use the dashboard
```

API keys go in the environment, never in files:

```bash
export ELEVENLABS_API_KEY=...   # brain + voices (needs the Agents permission)
export DEEPSEEK_API_KEY=...     # optional brain
export CARTESIA_API_KEY=...     # optional voices
```

Piper voices are not in the repo (`voices/` is ignored). Download the `.onnx` + `.onnx.json`
pairs you want (for example en_US-lessac-medium, hi_IN-priyamvada-medium) from
https://huggingface.co/rhasspy/piper-voices into `server/voices/`.

ffmpeg lives in /usr/bin on Linux, but the code looks in /usr/local/bin first, so tell it:

```bash
export FFMPEG=$(which ffmpeg)
```

Run it (keep the exports above in the same shell, or put them in a systemd service):

```bash
nohup .venv/bin/python -u server.py >> server.log 2>&1 &
```

It listens on :8700 (dashboard at `/`). Open that port in the server's firewall, and put it
behind HTTPS if it is reachable from the internet.

## Point the toy at it

On the Mac that flashes the board, copy `esp32/board/config_example.py` to `config.py`, set
`WIFI_SSID`, `WIFI_PASS` and `BRAIN = "http://<server-address>:8700"`, then upload with
`mpremote cp config.py dikkey.py main.py :`.

The offline Indic voice worker (`indic_worker.py`, port 8702) is optional and needs its own environment with `torch`; skip it on a small server.

Local data (child profile, chat log, settings) is created next to the server and is git-ignored.
