# 🚀 Quick Start Guide

## Prerequisites
- Python 3.9+
- Node.js 18+
- API Keys: OpenAI, Deepgram

## 1. Backend Setup (5 minutes)

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env

# Edit .env with your API keys
notepad .env  # Windows
nano .env     # Mac/Linux
```

**Required in .env:**
```
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...
```

## 2. Frontend Setup (3 minutes)

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install
```

## 3. Run the System

### Option A: Separate Terminals

**Terminal 1 - Backend:**
```bash
cd backend
python main.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### Option B: Quick Start Script

**Windows:**
```bash
start.bat
```

**Mac/Linux:**
```bash
chmod +x start.sh
./start.sh
```

## 4. Access the Application

Open your browser to: **http://localhost:3000**

## 5. Using the System

1. **Click the microphone button** to start
2. **Speak** - your words will appear as you talk
3. **AI responds** with voice and text
4. **Interrupt anytime** - just start speaking
5. **Click again** to end the conversation

## 🎯 System Flow

```
User speaks → STT (Deepgram) → LLM (OpenAI) → TTS (Deepgram) → User hears
                                     ↓
                              Live transcript on screen
```

## ⚙️ Configuration Options

### Change TTS Provider

Edit `backend/.env`:
```bash
TTS_PROVIDER=deepgram    # Fast, natural
TTS_PROVIDER=elevenlabs  # High quality (requires API key)
TTS_PROVIDER=openai      # OpenAI TTS
TTS_PROVIDER=mock        # Testing only
```

### Change LLM Model

Edit `backend/.env`:
```bash
OPENAI_MODEL=gpt-4o-mini    # Fast, cheap
OPENAI_MODEL=gpt-4o         # Better quality
```

### Customize System Prompt

Edit `frontend/src/App.tsx` line 11:
```typescript
const SYSTEM_PROMPT = "Your custom prompt here...";
```

## 🐛 Troubleshooting

### Backend won't start
- Check Python version: `python --version` (need 3.9+)
- Verify API keys in `.env`
- Check port 8000 is available

### Frontend won't start
- Check Node version: `node --version` (need 18+)
- Delete `node_modules` and run `npm install` again
- Check port 3000 is available

### No microphone access
- Allow microphone in browser permissions
- Use HTTPS or localhost only
- Check browser console for errors

### No audio output
- Check WebSocket connections in browser dev tools
- Verify backend is running
- Check browser audio settings

### API Errors
- Verify API keys are correct
- Check API rate limits
- Review backend terminal for error messages

## 📁 Project Structure

```
.
├── backend/          # Python FastAPI backend
│   ├── main.py      # Main server
│   ├── config.py    # Configuration
│   ├── models.py    # Data models
│   ├── stt_layer.py # Speech-to-Text
│   ├── llm_layer.py # LLM integration
│   ├── tts_layer.py # Text-to-Speech
│   └── orchestrator.py # State machine
│
├── frontend/        # React TypeScript frontend
│   └── src/
│       ├── App.tsx  # Main app
│       ├── api.ts   # Backend client
│       └── components/
│
└── README.md        # Full documentation
```

## 🔗 API Endpoints

- `POST /session` - Create session
- `DELETE /session/{id}` - Delete session
- `WS /session/{id}/audio/in` - Stream audio input
- `WS /session/{id}/audio/out` - Receive audio output
- `WS /session/{id}/transcript` - Get live transcripts

## 🎓 Next Steps

1. **Customize the UI** - Edit React components in `frontend/src/components/`
2. **Add features** - Modify orchestrator in `backend/orchestrator.py`
3. **Integrate elsewhere** - Use the API endpoints in your own apps
4. **Deploy** - Use Docker, AWS, or any cloud provider

## 📚 Learn More

- Full documentation: [README.md](README.md)
- Deepgram docs: https://developers.deepgram.com/
- OpenAI docs: https://platform.openai.com/docs/

---

**Need help?** Check the troubleshooting section or review the logs in your terminal.
