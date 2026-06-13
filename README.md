# 🎙️ Recruiter Voice Agent

> An AI-powered voice agent that answers AI recruiter calls on your behalf in real-time, using your resume as context — and automatically detects when a human recruiter is calling so you can take over.

[![CI — PR Checks](https://github.com/Pavan789bhanu/recruiter-voice-agent/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/Pavan789bhanu/recruiter-voice-agent/actions/workflows/pr-checks.yml)
[![Deploy to Dev](https://github.com/Pavan789bhanu/recruiter-voice-agent/actions/workflows/deploy-dev.yml/badge.svg)](https://github.com/Pavan789bhanu/recruiter-voice-agent/actions/workflows/deploy-dev.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## How It Works

```
Recruiter calls your Twilio number
        │
        ▼
Twilio opens real-time audio WebSocket → FastAPI backend (AWS EC2)
        │
        ▼
Deepgram transcribes speech < 300ms latency
        │
        ▼
Human/AI Detector analyzes caller (first 15-30 seconds)
        │
   ┌────┴────┐
   ▼         ▼
AI Caller   Human Caller
   │              │
Claude API    Push notification
reads resume  to your iPhone
& responds        │
   │          You take the call
ElevenLabs
voices reply
        │
        ▼
iOS companion app — live transcript + AI toggle
```

---

## Features

- **Real-time AI response** — Claude answers using your resume context, < 5s end-to-end
- **Human/AI detection** — Classifies callers by speech patterns; never intercepts a real human
- **Live iOS companion app** — Watch the transcript, toggle AI on/off mid-call
- **Voice cloning ready** — ElevenLabs can sound exactly like you
- **Audit trail** — Every call saved as a JSON transcript
- **Push notifications** — Instant iPhone alert when a human recruiter calls

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Voice / Phone | Twilio (number + Media Streams) |
| Speech-to-Text | Deepgram Nova-2 (real-time WebSocket) |
| AI / LLM | Anthropic Claude (claude-opus-4-8) |
| Text-to-Speech | ElevenLabs Turbo v2.5 |
| Backend | Python 3.12 · FastAPI · Uvicorn |
| Infra | AWS EC2 · Docker · Nginx · Let's Encrypt |
| iOS App | SwiftUI · iOS 17+ |
| Push Notifications | Firebase Cloud Messaging |

---

## Project Structure

```
recruiter-voice-agent/
├── backend/                        # FastAPI backend
│   ├── main.py                     # App entry point, all routes
│   ├── call_handler.py             # Per-call orchestration
│   ├── ai_engine.py                # Claude integration + session state
│   ├── stt.py                      # Deepgram real-time STT
│   ├── tts.py                      # ElevenLabs / Polly TTS
│   ├── human_ai_detector.py        # Caller classification
│   ├── notifications.py            # Firebase push
│   ├── config.py                   # Env-var configuration
│   ├── resume_context.md           # 🔑 YOUR RESUME — edit this
│   ├── requirements.txt
│   └── Dockerfile
├── ios/                            # SwiftUI iOS companion app
│   └── AIRecruiterAgent/
│       ├── AIRecruiterAgentApp.swift
│       ├── ContentView.swift       # All UI screens
│       ├── Models.swift
│       ├── CallManager.swift
│       └── BackendAPI.swift
├── scripts/
│   ├── deploy.sh                   # AWS EC2 deploy script
│   └── nginx.conf                  # Nginx reverse proxy config
├── .github/
│   ├── workflows/
│   │   ├── pr-checks.yml           # Runs on every PR
│   │   ├── deploy-dev.yml          # Runs on merge to dev
│   │   └── deploy-prod.yml         # Runs on merge to main
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
├── tests/
│   ├── test_detector.py
│   ├── test_ai_engine.py
│   └── conftest.py
├── SETUP_GUIDE.md                  # Full step-by-step setup
├── CONTRIBUTING.md
└── .env.example
```

---

## Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/Pavan789bhanu/recruiter-voice-agent.git
cd recruiter-voice-agent/backend
cp .env.example .env
# Fill in all API keys in .env
```

### 2. Fill your resume

Edit `backend/resume_context.md` — this is what Claude uses to answer questions.

### 3. Run locally (dev)

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# In another terminal, expose via ngrok for Twilio testing:
ngrok http 8000
# Copy the https:// URL → paste into Twilio webhook config
```

### 4. Deploy to AWS

See **[SETUP_GUIDE.md](SETUP_GUIDE.md)** for full AWS EC2 + Nginx + HTTPS + Twilio + iOS setup.

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production — deployed to AWS, protected, requires PR + review |
| `dev` | Integration — all features merge here first, deployed to staging |
| `feature/*` | Individual features — branch from `dev`, PR back to `dev` |
| `hotfix/*` | Emergency fixes — branch from `main`, PR to both `main` and `dev` |

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Required keys:

```
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
DEEPGRAM_API_KEY
ANTHROPIC_API_KEY
ELEVENLABS_API_KEY
PUBLIC_URL
```

---

## Cost Estimate

~$25–40/month during an active job search:

| Service | Cost |
|---------|------|
| AWS t3.small | ~$15/mo |
| Twilio number | ~$1.15/mo |
| Deepgram | ~$2–5/mo |
| Anthropic Claude | ~$3–10/mo |
| ElevenLabs | ~$2–5/mo |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
