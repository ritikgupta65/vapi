# 📚 Documentation Index

Welcome to the Speech-to-Speech Conversational AI System!

## 🚀 Quick Navigation

### Getting Started
- **[QUICKSTART.md](QUICKSTART.md)** - 5-minute setup guide (START HERE!)
- **[README.md](README.md)** - Complete project overview and features

### Understanding the System
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design, state machine, data flow
- **[FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md)** - Visual workflow diagrams
- **[API.md](API.md)** - Complete API reference with examples

### Development & Deployment
- **[TESTING.md](TESTING.md)** - Testing strategies and examples
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide

### Reference
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - What was built and how to use it
- **[FILE_TREE.md](FILE_TREE.md)** - Complete project structure and file overview

---

## 📖 Documentation by Role

### For Developers Building Features
1. Read [ARCHITECTURE.md](ARCHITECTURE.md) - Understand the design
2. Review [API.md](API.md) - Learn the endpoints
3. Check [TESTING.md](TESTING.md) - Write tests
4. See code in `backend/` and `frontend/` directories

### For DevOps/Deployment Engineers
1. Read [QUICKSTART.md](QUICKSTART.md) - Local setup
2. Review [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
3. Configure environment variables
4. Set up monitoring

### For Product/QA Teams
1. Read [README.md](README.md) - Features overview
2. Check [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md) - How it works
3. Review [TESTING.md](TESTING.md) - Test cases
4. Try the demo!

### For Integration Engineers
1. Read [API.md](API.md) - API endpoints
2. Check examples in API.md
3. Review `frontend/src/api.ts` - Client implementation
4. See [ARCHITECTURE.md](ARCHITECTURE.md) for WebSocket patterns

---

## 🎯 Documentation Hierarchy

```
📚 Documentation Root
│
├── 🚀 Getting Started
│   ├── QUICKSTART.md ⭐ (Start here!)
│   └── README.md
│
├── 🏗️ Architecture & Design
│   ├── ARCHITECTURE.md
│   ├── FLOW_DIAGRAMS.md
│   └── PROJECT_SUMMARY.md
│
├── 🔌 API & Integration
│   └── API.md
│
└── 🚢 Deployment & Testing
    ├── DEPLOYMENT.md
    └── TESTING.md
```

---

## 📁 Code Structure

```
Backend (Python/FastAPI)
├── main.py              → FastAPI app, WebSocket handlers
├── orchestrator.py      → State machine, conversation logic
├── stt_layer.py         → Deepgram speech-to-text
├── llm_layer.py         → OpenAI integration
├── tts_layer.py         → Text-to-speech (pluggable)
├── config.py            → Configuration management
└── models.py            → Data models

Frontend (React/TypeScript)
├── src/
│   ├── App.tsx          → Main application
│   ├── api.ts           → Backend client
│   ├── audioManager.ts  → Web Audio API
│   ├── types.ts         → TypeScript types
│   └── components/
│       ├── MessageBubble.tsx
│       ├── MicButton.tsx
│       └── TranscriptPanel.tsx
```

---

## ⚡ Quick Links

**Essential Files:**
- [Backend Main](backend/main.py) - FastAPI server
- [Frontend App](frontend/src/App.tsx) - React app
- [Orchestrator](backend/orchestrator.py) - Core logic
- [API Client](frontend/src/api.ts) - Frontend API

**Configuration:**
- [Backend .env.example](backend/.env.example) - Environment template
- [Frontend package.json](frontend/package.json) - Dependencies
- [Backend requirements.txt](backend/requirements.txt) - Python packages

**Documentation:**
- [README](README.md) - Project overview
- [QUICKSTART](QUICKSTART.md) - Setup guide
- [API Reference](API.md) - API docs
- [Architecture](ARCHITECTURE.md) - System design

---

## 🎓 Learning Path

### Beginner (Just want to run it)
1. [QUICKSTART.md](QUICKSTART.md) - Follow the 5-minute guide
2. Run and test the application
3. Done!

### Intermediate (Want to customize)
1. [README.md](README.md) - Understand features
2. [ARCHITECTURE.md](ARCHITECTURE.md) - Learn the design
3. [API.md](API.md) - Study the API
4. Modify code to fit your needs

### Advanced (Want to integrate/deploy)
1. All above documents
2. [DEPLOYMENT.md](DEPLOYMENT.md) - Production setup
3. [TESTING.md](TESTING.md) - Testing strategies
4. [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md) - Deep understanding
5. Build your integration

---

## 🔍 Search by Topic

### Audio Processing
- [audioManager.ts](frontend/src/audioManager.ts) - Web Audio API
- [stt_layer.py](backend/stt_layer.py) - STT integration
- [tts_layer.py](backend/tts_layer.py) - TTS integration

### State Management
- [orchestrator.py](backend/orchestrator.py) - State machine
- [models.py](backend/models.py) - State definitions
- [ARCHITECTURE.md](ARCHITECTURE.md) - State diagrams

### WebSockets
- [main.py](backend/main.py) - WebSocket handlers
- [api.ts](frontend/src/api.ts) - WebSocket client
- [API.md](API.md) - WebSocket docs

### UI/UX
- [App.tsx](frontend/src/App.tsx) - Main UI
- [components/](frontend/src/components/) - React components
- [index.css](frontend/src/index.css) - Tailwind styles

### Configuration
- [config.py](backend/config.py) - Backend config
- [.env.example](backend/.env.example) - Environment vars
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production config

---

## 📊 Feature Matrix

| Feature | File | Documentation |
|---------|------|---------------|
| Session Management | [main.py](backend/main.py) | [API.md](API.md#create-session) |
| Audio Input | [audioManager.ts](frontend/src/audioManager.ts) | [API.md](API.md#audio-input-stream) |
| Audio Output | [audioManager.ts](frontend/src/audioManager.ts) | [API.md](API.md#audio-output-stream) |
| Transcripts | [orchestrator.py](backend/orchestrator.py) | [API.md](API.md#transcript-stream) |
| Barge-in | [orchestrator.py](backend/orchestrator.py) | [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md#barge-in) |
| State Machine | [orchestrator.py](backend/orchestrator.py) | [ARCHITECTURE.md](ARCHITECTURE.md#state-machine) |

---

## 🎯 Common Tasks

### How do I...

**...run the system?**
→ [QUICKSTART.md](QUICKSTART.md)

**...customize the AI's personality?**
→ Edit system prompt in [App.tsx](frontend/src/App.tsx) or [README.md#customization](README.md#customization)

**...change the TTS voice?**
→ [README.md#configuration](README.md#configuration) or [DEPLOYMENT.md](DEPLOYMENT.md#configuration)

**...deploy to production?**
→ [DEPLOYMENT.md](DEPLOYMENT.md)

**...integrate into my app?**
→ [API.md](API.md) and [api.ts](frontend/src/api.ts)

**...add new features?**
→ [ARCHITECTURE.md](ARCHITECTURE.md) then modify relevant layer

**...test the system?**
→ [TESTING.md](TESTING.md)

**...understand the architecture?**
→ [ARCHITECTURE.md](ARCHITECTURE.md) and [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md)

---

## 💡 Tips

- **New users:** Start with [QUICKSTART.md](QUICKSTART.md)
- **Visual learners:** Check [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md)
- **API users:** Go straight to [API.md](API.md)
- **Deploying:** Read [DEPLOYMENT.md](DEPLOYMENT.md) carefully
- **Customizing:** Understand [ARCHITECTURE.md](ARCHITECTURE.md) first

---

## 📞 Support

If you're stuck:
1. Check relevant documentation above
2. Review code comments in source files
3. Check [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for overview
4. Review error logs in terminal

---

**Ready to start?** → [QUICKSTART.md](QUICKSTART.md) ⭐

**Want to understand?** → [ARCHITECTURE.md](ARCHITECTURE.md) 🏗️

**Need API docs?** → [API.md](API.md) 🔌

**Deploying?** → [DEPLOYMENT.md](DEPLOYMENT.md) 🚀
