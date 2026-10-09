"""ElevenLabs Agents as Dikkey's brain (text only: Dikkey does his own listening and speaking).

One agent lives in the ElevenLabs account; its id is kept in settings.json. Every child turn opens a short
conversation over ElevenLabs' websocket, sends the full system prompt (persona + language rule + memory) as an
override, sends what the child said and returns the agent's reply text."""
import asyncio, json, os, ssl, urllib.error, urllib.request

import aiohttp, certifi

API = "https://api.elevenlabs.io/v1/convai"
LLM = os.environ.get("TALKTOY_ELEVEN_LLM", "claude-sonnet-5")
TLS = ssl.create_default_context(cafile=certifi.where())


def _key():
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    return key


def _call(method, path, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"xi-api-key": _key(), "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=TLS) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"elevenlabs {path}: HTTP {e.code} {e.read()[:200]!r}") from None


def create_agent(persona):
    """Makes the Dikkey agent once; returns its id."""
    cfg = {"name": "Dikkey",
           "conversation_config": {
               "agent": {"first_message": "", "language": "en",
                         "prompt": {"prompt": persona, "llm": LLM, "temperature": 0.7, "max_tokens": 900}},
               "conversation": {"text_only": True, "max_duration_seconds": 120}},
           "platform_settings": {"overrides": {"conversation_config_override": {
               "agent": {"prompt": {"prompt": True}, "first_message": True, "language": True},
               "conversation": {"text_only": True}}}}}
    return _call("POST", "/agents/create", cfg)["agent_id"]


async def _ask(agent_id, system, text, timeout):
    url = _call("GET", f"/conversation/get-signed-url?agent_id={agent_id}")["signed_url"]
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(url, ssl=TLS, heartbeat=None) as ws:
            await ws.send_json({"type": "conversation_initiation_client_data",
                                "conversation_config_override": {"agent": {"prompt": {"prompt": system}, "first_message": ""},
                                                                 "conversation": {"text_only": True}}})
            sent = False
            async with asyncio.timeout(timeout):
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    ev = json.loads(msg.data)
                    kind = ev.get("type")
                    if kind == "conversation_initiation_metadata" and not sent:
                        # only now is the conversation set up; a message sent earlier gets a greeting, not an answer
                        await ws.send_json({"type": "user_message", "text": text})
                        sent = True
                    elif kind == "ping":
                        await ws.send_json({"type": "pong", "event_id": ev.get("ping_event", {}).get("event_id")})
                    elif kind == "agent_response" and sent:
                        reply = ev.get("agent_response_event", {}).get("agent_response", "").strip()
                        if reply:
                            return reply
                    elif kind == "error":
                        raise RuntimeError("elevenlabs agent error: " + json.dumps(ev)[:200])
    raise RuntimeError("elevenlabs agent closed without replying")


def ask(agent_id, msgs, timeout=60):
    """msgs in chat format (system, history..., user). History goes into the system prompt,
    because every turn is a fresh ElevenLabs conversation."""
    system = msgs[0]["content"]
    past = msgs[1:-1]
    if past:
        lines = [("Child: " if m["role"] == "user" else "Dikkey: ") + m["content"] for m in past]
        system += "\n\nThe conversation so far (continue it, don't repeat it):\n" + "\n".join(lines)
    return asyncio.run(_ask(agent_id, system, msgs[-1]["content"], timeout))
