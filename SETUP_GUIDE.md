# AI Recruiter Agent — Complete Setup Guide

## How It Works (Architecture)

```
Recruiter calls your Twilio number
        ↓
Twilio answers → opens audio WebSocket to your AWS server
        ↓
Deepgram transcribes speech in real-time (<300ms)
        ↓
Human/AI Detector analyzes first 15-30 seconds
        ↓
    ┌───────────────────────┬──────────────────────────┐
    ▼                       ▼
AI Caller                Human Caller
    │                       │
Claude reads your          Push notification
resume & responds          sent to your iPhone
    │                       │
ElevenLabs TTS             You take the call
plays voice back           (or it forwards to
to recruiter               your real number)
    ↓
iOS companion app shows
live transcript + lets you
toggle AI on/off mid-call
```

**Cost estimate**: ~$15–25/month (AWS t3.micro + Twilio + API calls per call)

---

## Part 1: API Keys to Collect First

Get these before anything else. Open all in separate tabs:

| Service | URL | What you need | Cost |
|---------|-----|---------------|------|
| Twilio | twilio.com | Account SID, Auth Token, Phone Number | ~$1/mo for number |
| Deepgram | deepgram.com | API Key | Free tier: 45 mins/mo free |
| Anthropic | console.anthropic.com | API Key | ~$0.015/min of calls |
| ElevenLabs | elevenlabs.io | API Key + Voice ID | Free: 10k chars/mo |
| Firebase | console.firebase.google.com | Server Key | Free |

---

## Part 2: Fill Your Resume (IMPORTANT — do this now)

Edit `backend/resume_context.md` with your real info. This is what Claude uses to answer questions. Replace every `[PLACEHOLDER]` section with your actual details.

The more detail you add, the better the AI answers. Include:
- All your work experience with specific achievements and tech stacks
- All projects with what they do, scale, and technologies used
- Answers to the FAQ section at the bottom of the file
- Your salary range, start date, and work authorization

---

## Part 3: AWS EC2 Setup

### 3.1 Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose: **Ubuntu Server 22.04 LTS**
3. Instance type: **t3.small** (recommended) or t3.micro (budget)
4. Storage: **20 GB** minimum
5. Security Group — open these ports:
   - **22** (SSH)
   - **80** (HTTP)
   - **443** (HTTPS) ← Twilio requires HTTPS
   - **8000** (optional, for testing only — close in production)
6. Create/download a key pair (.pem file)
7. Launch. Note your **Public IPv4 address**.

### 3.2 Assign Elastic IP (so your IP doesn't change)

1. EC2 → Elastic IPs → Allocate Elastic IP
2. Associate it with your instance
3. Note this IP — it's your permanent server address

### 3.3 Point a Domain (strongly recommended)

Twilio requires HTTPS. Get a free domain or use one you own:
- **Easiest**: Register a cheap domain on Namecheap (~$1/year for .xyz)
- In your domain registrar's DNS settings, add an **A record** → your Elastic IP
- Wait 5-10 min for DNS to propagate

### 3.4 SSH into your server

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

### 3.5 Upload and deploy the backend

On your local machine (from the `ai-recruiter-agent` folder):
```bash
# Upload backend files to EC2
scp -i your-key.pem -r backend/ ubuntu@YOUR_IP:/home/ubuntu/ai-recruiter-agent/

# SSH in
ssh -i your-key.pem ubuntu@YOUR_IP

# Create .env from example
cd /home/ubuntu/ai-recruiter-agent/backend
cp .env.example .env
nano .env   # Fill in all your API keys
```

### 3.6 Run deploy script

```bash
cd /home/ubuntu/ai-recruiter-agent
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### 3.7 Set up Nginx + HTTPS

```bash
# Install Nginx config
sudo cp scripts/nginx.conf /etc/nginx/sites-available/ai-recruiter
# Edit the domain name in the file
sudo nano /etc/nginx/sites-available/ai-recruiter
# Replace YOUR_DOMAIN_OR_IP with your actual domain

sudo ln -s /etc/nginx/sites-available/ai-recruiter /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Get SSL certificate (free via Let's Encrypt)
sudo certbot --nginx -d YOUR_DOMAIN.com
# Follow prompts — enter your email when asked

# Verify
curl https://YOUR_DOMAIN.com/health
# Should return: {"status": "ok", "active_calls": 0}
```

---

## Part 4: Twilio Setup

### 4.1 Buy a phone number

1. Log into twilio.com → Phone Numbers → Buy a Number
2. Search for a number in your area code
3. Make sure it has **Voice** capability
4. Buy it (~$1.15/month)

### 4.2 Configure webhooks

1. Go to the phone number's configuration
2. Under **Voice Configuration**:
   - **A call comes in**: Webhook → `https://YOUR_DOMAIN.com/webhook/incoming`
   - **Method**: POST
   - **Call status changes**: `https://YOUR_DOMAIN.com/webhook/status`
3. Under **Advanced**:
   - Enable **Media Streams** (this is what sends real-time audio)
4. Click Save

### 4.3 Enable Media Streams

1. In Twilio Console → Voice → Settings
2. Enable **Twilio Media Streams** (it may need to be enabled for your account)

### 4.4 Test the number

Call your Twilio number from another phone. You should hear the greeting from ElevenLabs. If you get a Twilio error message, check your server logs:
```bash
docker logs ai-recruiter-agent -f
```

---

## Part 5: iOS App Setup

### Prerequisites

- Mac with Xcode 15+
- Apple Developer account (free for TestFlight, $99/year for App Store)
- iPhone running iOS 17+

### 5.1 Open the project

```bash
# On your Mac
cd ai-recruiter-agent/ios
# Open in Xcode
open AIRecruiterAgent.xcodeproj
```

If you don't have an `.xcodeproj` yet, create a new Xcode project:
1. Open Xcode → New Project → iOS App
2. Product Name: `AIRecruiterAgent`
3. Interface: SwiftUI
4. Add all the `.swift` files from `ios/AIRecruiterAgent/`

### 5.2 Configure signing

1. In Xcode → select the project → Signing & Capabilities
2. Team: Select your Apple Developer account
3. Bundle ID: `com.yourname.airecruiteragent` (must be unique)

### 5.3 Add Push Notification capability

1. Xcode → Signing & Capabilities → + Capability → Push Notifications
2. Also add: Background Modes → check "Remote notifications"

### 5.4 Set your server URL

1. Run the app on your iPhone (plug in via USB, select device, hit ▶)
2. Go to Settings tab
3. Enter your server URL: `https://YOUR_DOMAIN.com`
4. Tap "Test Connection" — should show "✓ Connected successfully"

### 5.5 Firebase Push Notifications (for human caller alerts)

1. Go to console.firebase.google.com → Create Project
2. Add iOS app → enter your Bundle ID
3. Download `GoogleService-Info.plist` → drag into Xcode project
4. Add Firebase SDK via Swift Package Manager:
   - Xcode → File → Add Packages → `https://github.com/firebase/firebase-ios-sdk`
   - Add `FirebaseMessaging`
5. Copy your Firebase Server Key → paste into `.env` as `FIREBASE_SERVER_KEY`

---

## Part 6: Give Recruiters Your Twilio Number

This is the key step. Instead of giving your real phone number:

- **LinkedIn**: Update your contact info to your Twilio number
- **Job applications**: Use Twilio number on resumes/applications
- **Email signatures**: Add Twilio number

When someone calls, the AI takes over. You watch on the iOS app in real-time.

---

## Part 7: Testing

### Test 1 — Basic call (most important)

1. Call your Twilio number from your personal phone
2. You should hear a professional greeting within 3-5 seconds
3. Ask: "Tell me about yourself"
4. The AI should respond using your resume context
5. Check the iOS app — you should see the live transcript

### Test 2 — AI detection

Say the following script (mimicking an AI recruiter):
> "Hi, this is Alex calling on behalf of our talent acquisition team. I'm reaching out regarding your application for the Software Engineer position. Is this a good time to speak?"

The app should classify this as "AI Recruiter Detected" within the first 2-3 sentences.

### Test 3 — Human detection

Say naturally:
> "Hey um, hi, is this Venu? Yeah so I uh, I came across your resume..."

The app should classify as "Human Recruiter Detected" and send a push notification.

### Test 4 — Toggle AI mid-call

During a live call, flip the "AI Responding" toggle in the app. The AI should immediately stop/start responding.

### Test 5 — Transcript history

After a call ends, go to History tab. You should see the call transcript saved.

---

## Part 8: Troubleshooting

### "Twilio error 11200 — HTTP retrieval failure"
Your webhook URL isn't accessible. Check:
- Server is running: `docker ps`
- Nginx is running: `systemctl status nginx`
- HTTPS is working: `curl https://YOUR_DOMAIN.com/health`
- Twilio webhook URL is exactly correct (no trailing slash)

### "No audio / silence on call"
- Check ElevenLabs API key and quota
- Check logs: `docker logs ai-recruiter-agent -f`
- Verify PUBLIC_URL in .env matches your actual domain exactly

### "AI takes too long to respond (>5 seconds)"
- Switch Claude model to `claude-haiku-4-5-20251001` in .env (faster, slightly less smart)
- Check server region — use AWS us-east-1 for lowest latency to Twilio

### "iOS app can't connect to server"
- Verify server URL in Settings has no trailing slash
- Make sure you're using `https://` not `http://`
- Check if your iPhone is on the same network as an office firewall (use cellular to test)

### "Human detected as AI"
- Lower `AI_CONFIDENCE_THRESHOLD` to `0.50` in .env
- Restart container: `docker restart ai-recruiter-agent`

---

## Part 9: Customization

### Clone your voice (optional but impressive)

1. Go to elevenlabs.io → Voice Lab → Add Voice
2. Upload 5-10 minutes of your own voice recordings (clear audio)
3. Copy the Voice ID it generates
4. Set `ELEVENLABS_VOICE_ID` in `.env` to that ID
5. Now the AI sounds exactly like you

### Add more context

Edit `backend/resume_context.md` anytime. Restart server to reload:
```bash
docker restart ai-recruiter-agent
```

### Adjust AI tone

Edit the `SYSTEM_PROMPT` in `backend/ai_engine.py` to change how the AI speaks.

---

## Project File Structure

```
ai-recruiter-agent/
├── backend/
│   ├── main.py                 ← FastAPI app (entry point)
│   ├── call_handler.py         ← Orchestrates each call
│   ├── ai_engine.py            ← Claude integration
│   ├── stt.py                  ← Deepgram real-time STT
│   ├── tts.py                  ← ElevenLabs TTS
│   ├── human_ai_detector.py    ← Human vs AI classification
│   ├── notifications.py        ← Firebase push notifications
│   ├── config.py               ← Config from .env
│   ├── resume_context.md       ← YOUR RESUME (edit this!)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example            ← Copy to .env and fill in
├── ios/
│   └── AIRecruiterAgent/
│       ├── AIRecruiterAgentApp.swift   ← App entry + push setup
│       ├── ContentView.swift           ← All UI screens
│       ├── Models.swift                ← Data models
│       ├── CallManager.swift           ← App state
│       └── BackendAPI.swift            ← Network layer
├── scripts/
│   ├── deploy.sh               ← AWS deployment script
│   └── nginx.conf              ← Nginx config template
└── SETUP_GUIDE.md              ← This file
```

---

## Monthly Cost Breakdown

| Item | Cost |
|------|------|
| AWS t3.small EC2 | ~$15/mo |
| Twilio phone number | ~$1.15/mo |
| Twilio call minutes | ~$0.013/min |
| Deepgram (first 45 min free, then $0.0043/min) | ~$2-5/mo |
| Anthropic Claude (per call ~$0.05) | ~$3-10/mo |
| ElevenLabs (10k chars free, then $0.30/1k) | ~$2-5/mo |
| **Total** | **~$25-40/mo** |

For a job search period of 2-3 months, this is well worth it.
