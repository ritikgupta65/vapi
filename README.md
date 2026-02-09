# Speech-to-Speech Conversational AI System

A production-ready, real-time voice conversation system with Speech-to-Text (STT), Large Language Model (LLM), and Text-to-Speech (TTS) integration.

> **📚 [Documentation Index](INDEX.md)** | **⚡ [Quick Start](QUICKSTART.md)** | **🔌 [API Reference](API.md)** | **🏗️ [Architecture](ARCHITECTURE.md)**

## 🎯 Features

- **Real-time voice conversation** with turn-by-turn interaction
- **Barge-in support** - interrupt the AI while it's speaking
- **Streaming responses** - AI starts speaking before completing its thought
- **Live transcripts** - see the conversation unfold in real-time
- **Pluggable architecture** - easily swap STT/TTS providers
- **Clean APIs** - reusable in any project
- **Modern UI** - built with React, TypeScript, and Tailwind CSS

## 🏗️ Architecture

### Backend (Python + FastAPI)

The backend is organized into 4 modular layers:

1. **STT Layer** (`stt_layer.py`)
   - Deepgram WebSocket streaming
   - Partial and final transcripts
   - Automatic silence detection
   - Voice activity detection (VAD)

2. **Conversation Orchestrator** (`orchestrator.py`)
   - State machine: LISTENING → THINKING → SPEAKING
   - Turn-taking management
   - Barge-in handling (user can interrupt AI)
   - Conversation history maintenance

3. **LLM Layer** (`llm_layer.py`)
   - OpenAI/Azure OpenAI integration
   - Streaming responses
   - Voice-optimized system prompts

4. **TTS Layer** (`tts_layer.py`)
   - Pluggable providers: Deepgram, ElevenLabs, OpenAI
   - Streaming audio synthesis
   - Sentence-by-sentence output
   - Immediate interruption support

### Frontend (React + TypeScript)

- **Web Audio API** for microphone access and audio playback
- **WebSocket connections** for real-time communication
- **Modern UI** with Tailwind CSS
- **Responsive design** for all screen sizes

## 📦 Installation

### Prerequisites

- Python 3.9+ (backend)
- Node.js 18+ (frontend)
- API Keys:
  - OpenAI API key
  - Deepgram API key
  - (Optional) ElevenLabs API key

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env and add your API keys
# Required: OPENAI_API_KEY, DEEPGRAM_API_KEY
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# (Optional) Create .env file for custom API URL
echo "VITE_API_URL=http://localhost:8000" > .env
```

## 🚀 Running the Application

### Start Backend

```bash
cd backend
python main.py
```

Backend will run on `http://localhost:8000`

### Start Frontend

```bash
cd frontend
npm run dev
```

Frontend will run on `http://localhost:3000`

## 🔌 API Documentation

### REST Endpoints

#### Create Session
```http
POST /session
Content-Type: application/json

{
  "system_prompt": "You are a helpful voice assistant."
}

Response:
{
  "session_id": "uuid-string"
}
```

#### Delete Session
```http
DELETE /session/{session_id}
```

#### Get Session State
```http
GET /session/{session_id}/state

Response:
{
  "state": "listening" | "thinking" | "speaking",
  "messages": [...]
}
```

### WebSocket Endpoints

#### Audio Input
```
WS /session/{session_id}/audio/in
```
- Send: Raw audio bytes (PCM 16-bit, 16kHz, mono)
- Receive: Nothing (one-way stream)

#### Audio Output
```
WS /session/{session_id}/audio/out
```
- Send: Keepalive messages (optional)
- Receive: Audio chunks as bytes

#### Transcript Events
```
WS /session/{session_id}/transcript
```
- Send: Keepalive messages (optional)
- Receive: JSON transcript events

Transcript event format:
```json
{
  "role": "user" | "assistant",
  "text": "transcript text",
  "is_partial": false
}
```

## ⚙️ Configuration

### Backend Configuration

Edit `backend/.env`:

```bash
# OpenAI / Azure OpenAI
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini

# Deepgram
DEEPGRAM_API_KEY=your_key_here

# ElevenLabs (optional)
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# TTS Provider: deepgram, elevenlabs, or openai
TTS_PROVIDER=deepgram

# Server
HOST=0.0.0.0
PORT=8000
```

### Frontend Configuration

Edit `frontend/.env` (optional):

```bash
VITE_API_URL=http://localhost:8000
```

## 🧪 Testing Without API Keys

The system includes mock implementations for testing:

1. **Mock STT** - Replace `STTLayer` with `MockSTTLayer` in `orchestrator.py`
2. **Mock LLM** - Replace `LLMLayer` with `MockLLMLayer` in `orchestrator.py`
3. **Mock TTS** - Set `TTS_PROVIDER=mock` in `.env`

## 🎨 Customization

### Change System Prompt

Frontend: Edit `SYSTEM_PROMPT` in `frontend/src/App.tsx`

Backend: Pass `system_prompt` in session creation request

### Switch TTS Provider

Set `TTS_PROVIDER` in `backend/.env`:
- `deepgram` - Fast, natural voices
- `elevenlabs` - High-quality, expressive voices
- `openai` - Consistent, clear voices
- `mock` - Testing without API

### Adjust LLM Model

Set `OPENAI_MODEL` in `backend/.env`:
- `gpt-4o-mini` - Fast and cost-effective
- `gpt-4o` - Higher quality
- Any OpenAI-compatible model

## 🛠️ Development

### Project Structure

```
.
├── backend/
│   ├── main.py                 # FastAPI app and WebSocket handlers
│   ├── config.py               # Configuration management
│   ├── models.py               # Pydantic models
│   ├── stt_layer.py            # Speech-to-Text layer
│   ├── llm_layer.py            # LLM integration
│   ├── tts_layer.py            # Text-to-Speech layer
│   ├── orchestrator.py         # Conversation orchestrator
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment variables template
│
└── frontend/
    ├── src/
    │   ├── App.tsx             # Main application component
    │   ├── main.tsx            # Entry point
    │   ├── types.ts            # TypeScript types
    │   ├── api.ts              # API client
    │   ├── audioManager.ts     # Audio handling
    │   └── components/         # React components
    │       ├── MessageBubble.tsx
    │       ├── MicButton.tsx
    │       └── TranscriptPanel.tsx
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── tsconfig.json
```

### Key Design Patterns

1. **State Machine** - Conversation orchestrator uses explicit states
2. **Observer Pattern** - Callbacks for transcript and audio events
3. **Strategy Pattern** - Pluggable TTS providers
4. **Singleton Pattern** - WebSocket connection management

## 🔧 Troubleshooting

### Audio Issues

- **No microphone access**: Check browser permissions
- **No audio output**: Verify WebSocket connection to `/audio/out`
- **Echo/feedback**: Ensure echo cancellation is enabled

### WebSocket Disconnections

- Check CORS settings in `main.py`
- Verify session exists before connecting
- Monitor browser console for errors

### API Errors

- Verify API keys in `.env`
- Check API rate limits
- Review backend logs for detailed errors

## 📝 License

This project is provided as-is for educational and commercial use.

## 🤝 Contributing

This is a standalone project. Feel free to fork and customize for your needs.

## 📚 Additional Resources

- [Deepgram API Documentation](https://developers.deepgram.com/)
- [OpenAI API Documentation](https://platform.openai.com/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)

---

Built with ❤️ for real-time voice AI applications
