"""
AI Recruiter Agent — FastAPI Backend
=====================================

Endpoints:
  POST /webhook/incoming          ← Twilio calls this when a call arrives
  POST /webhook/speech/{call_sid} ← Twilio Gather fallback
  WS   /ws/media/{call_sid}       ← Twilio Media Streams audio
  WS   /ws/app/{client_id}        ← iOS companion app live updates
  GET  /audio/{filename}          ← Serve synthesized audio files
  POST /api/toggle-ai             ← Enable/disable AI for a call
  POST /api/register-device       ← Register iOS push token
  GET  /api/transcripts           ← List past call transcripts
  GET  /health                    ← Health check
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from twilio.request_validator import RequestValidator

from call_handler import CallOrchestrator, twiml_answer
from config import HOST, PORT, PUBLIC_URL, TWILIO_AUTH_TOKEN
from notifications import register_device

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Audio storage ─────────────────────────────────────────────────────────────
AUDIO_DIR = "/tmp/ai_recruiter_audio"
TRANSCRIPT_DIR = "/tmp/transcripts"
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

# ── Connected iOS app clients (for live transcript push) ──────────────────────
# Maps call_sid → list of connected WebSocket clients
_app_clients: dict[str, list[WebSocket]] = {}


async def broadcast_to_clients(call_sid: str, message: dict):
    """Push a message to all iOS app clients watching this call."""
    clients = _app_clients.get(call_sid, [])
    disconnected = []
    for ws in clients:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        clients.remove(ws)


# ── Active call orchestrators ──────────────────────────────────────────────────
_orchestrators: dict[str, CallOrchestrator] = {}


# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"AI Recruiter Agent starting on {HOST}:{PORT}")
    logger.info(f"Public URL: {PUBLIC_URL}")
    yield
    logger.info("Shutting down")


app = FastAPI(title="AI Recruiter Agent", version="1.0.0", lifespan=lifespan)
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")

twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)


# ── Twilio signature validation middleware ─────────────────────────────────────

async def validate_twilio(request: Request):
    """Validate that the request genuinely comes from Twilio."""
    url = str(request.url)
    form = dict(await request.form())
    signature = request.headers.get("X-Twilio-Signature", "")
    if not twilio_validator.validate(url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    return form


# ── Webhooks ───────────────────────────────────────────────────────────────────

@app.post("/webhook/incoming")
async def incoming_call(request: Request):
    """
    Twilio calls this as soon as someone dials your Twilio number.
    We answer with TwiML that opens a Media Stream WebSocket.
    """
    form = await validate_twilio(request)
    call_sid = str(form.get("CallSid", "unknown"))
    from_number = str(form.get("From", "unknown"))
    logger.info(f"Incoming call: {call_sid} from {from_number}")

    twiml = twiml_answer(call_sid)
    return Response(content=twiml, media_type="application/xml")


@app.post("/webhook/speech/{call_sid}")
async def speech_result(call_sid: str, request: Request):
    """
    Twilio Gather fallback — used if Media Streams WebSocket isn't available.
    """
    form = await validate_twilio(request)
    speech_text = str(form.get("SpeechResult", ""))
    logger.info(f"[{call_sid}] Gather speech: {speech_text}")

    orchestrator = _orchestrators.get(call_sid)
    if orchestrator and speech_text:
        asyncio.create_task(orchestrator._on_transcript(speech_text))

    return Response(content="<Response/>", media_type="application/xml")


@app.post("/webhook/status")
async def call_status(request: Request):
    """Twilio calls this when call status changes (ringing, completed, etc.)"""
    form = dict(await request.form())
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    logger.info(f"[{call_sid}] Status: {status}")
    return Response(content="<Response/>", media_type="application/xml")


# ── Media Stream WebSocket ─────────────────────────────────────────────────────

@app.websocket("/ws/media/{call_sid}")
async def media_stream(websocket: WebSocket, call_sid: str):
    """
    Twilio connects here to stream call audio in real-time.
    One connection per call.
    """
    await websocket.accept()

    orchestrator = CallOrchestrator(call_sid, websocket)
    _orchestrators[call_sid] = orchestrator

    try:
        await orchestrator.run()
    finally:
        _orchestrators.pop(call_sid, None)
        logger.info(f"[{call_sid}] Orchestrator removed")


# ── iOS App Live Updates WebSocket ─────────────────────────────────────────────

@app.websocket("/ws/app/{call_sid}")
async def app_client(websocket: WebSocket, call_sid: str):
    """
    iOS companion app connects here to receive live transcript + events.
    Multiple clients can watch the same call.
    """
    await websocket.accept()
    if call_sid not in _app_clients:
        _app_clients[call_sid] = []
    _app_clients[call_sid].append(websocket)
    logger.info(f"[{call_sid}] iOS client connected ({len(_app_clients[call_sid])} total)")

    try:
        # Send current state
        await websocket.send_json({"type": "connected", "call_sid": call_sid})

        # Keep alive — wait for client disconnect
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)

            # Handle toggle AI command from app
            if data.get("action") == "toggle_ai":
                orchestrator = _orchestrators.get(call_sid)
                if orchestrator:
                    orchestrator.ai_active = data.get("enabled", True)
                    await websocket.send_json({
                        "type": "ai_toggled",
                        "enabled": orchestrator.ai_active,
                    })

    except WebSocketDisconnect:
        if call_sid in _app_clients:
            try:
                _app_clients[call_sid].remove(websocket)
            except ValueError:
                pass
        logger.info(f"[{call_sid}] iOS client disconnected")


# ── REST API for iOS App ───────────────────────────────────────────────────────

@app.post("/api/register-device")
async def register_device_endpoint(request: Request):
    """Register iOS device push token."""
    body = await request.json()
    device_id = body.get("device_id")
    push_token = body.get("push_token")
    if not device_id or not push_token:
        raise HTTPException(status_code=400, detail="device_id and push_token required")
    register_device(device_id, push_token)
    return {"status": "registered"}


@app.get("/api/transcripts")
async def list_transcripts():
    """Return list of all saved call transcripts."""
    transcripts = []
    for p in Path(TRANSCRIPT_DIR).glob("*.json"):
        try:
            import json as _json
            data = _json.loads(p.read_text())
            transcripts.append({
                "filename": p.name,
                "call_sid": p.stem.split("_")[0],
                "turns": len(data),
                "preview": data[0]["text"][:80] if data else "",
            })
        except Exception as e:
            logger.debug("Skipping unreadable transcript %s: %s", p.name, e)
    return {"transcripts": sorted(transcripts, key=lambda x: x["filename"], reverse=True)}


@app.get("/api/transcript/{call_sid}")
async def get_transcript(call_sid: str):
    """Return the transcript for a specific call."""
    matches = list(Path(TRANSCRIPT_DIR).glob(f"{call_sid}_*.json"))
    if not matches:
        raise HTTPException(status_code=404, detail="Transcript not found")
    import json as _json
    return {"transcript": _json.loads(matches[0].read_text())}


@app.post("/api/toggle-ai")
async def toggle_ai(request: Request):
    """Enable or disable AI response for an active call."""
    body = await request.json()
    call_sid = body.get("call_sid")
    enabled = body.get("enabled", True)
    orchestrator = _orchestrators.get(call_sid)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Active call not found")
    orchestrator.ai_active = enabled
    return {"call_sid": call_sid, "ai_active": enabled}


@app.get("/api/active-calls")
async def active_calls():
    """Return list of currently active calls."""
    return {
        "calls": [
            {
                "call_sid": sid,
                "turn_count": orch.session.turn_count,
                "caller_type": orch.caller_type,
                "ai_active": orch.ai_active,
            }
            for sid, orch in _orchestrators.items()
        ]
    }


@app.get("/health")
async def health():
    return {"status": "ok", "active_calls": len(_orchestrators)}


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
