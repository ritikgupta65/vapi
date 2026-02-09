# System Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              React Frontend (Port 3000)                 │ │
│  │                                                          │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │ │
│  │  │ Mic      │  │ Speaker  │  │ Transcript Display   │ │ │
│  │  │ Input    │  │ Output   │  │ (Live Updates)       │ │ │
│  │  └────┬─────┘  └─────┬────┘  └──────────┬───────────┘ │ │
│  │       │              │                   │              │ │
│  │  ┌────▼──────────────▼───────────────────▼───────────┐ │ │
│  │  │         WebSocket Connections                      │ │ │
│  │  │  - /audio/in     - /audio/out    - /transcript    │ │ │
│  │  └────────────────────┬───────────────────────────────┘ │ │
│  └───────────────────────┼─────────────────────────────────┘ │
└────────────────────────┬─┼─────────────────────────────────┘
                         │ │
                    ┌────▼─▼────────────────────────────────┐
                    │   FastAPI Backend (Port 8000)         │
                    │                                        │
                    │  ┌──────────────────────────────────┐ │
                    │  │  WebSocket Handler Layer         │ │
                    │  │  - Audio In  - Audio Out         │ │
                    │  │  - Transcript Events             │ │
                    │  └──────────┬───────────────────────┘ │
                    │             │                          │
                    │  ┌──────────▼───────────────────────┐ │
                    │  │   Conversation Orchestrator      │ │
                    │  │   (State Machine)                │ │
                    │  │                                  │ │
                    │  │   LISTENING → THINKING → SPEAKING│ │
                    │  │                                  │ │
                    │  └──┬────────┬────────┬────────────┘ │
                    │     │        │        │               │
                    │  ┌──▼───┐ ┌─▼───┐ ┌─▼───┐          │
                    │  │ STT  │ │ LLM │ │ TTS │          │
                    │  │Layer │ │Layer│ │Layer│          │
                    │  └──┬───┘ └──┬──┘ └──┬──┘          │
                    └─────┼────────┼───────┼──────────────┘
                          │        │       │
                    ┌─────▼────┐ ┌─▼───┐ ┌▼──────────┐
                    │Deepgram  │ │OpenAI│ │Deepgram/ │
                    │STT API   │ │API   │ │ElevenLabs│
                    └──────────┘ └─────┘ └──────────┘
```

## State Machine Flow

```
┌──────────────┐
│              │
│  LISTENING   │◄──────────────┐
│              │               │
└──────┬───────┘               │
       │                       │
       │ User stops speaking   │
       │ (final transcript)    │
       │                       │
       ▼                       │
┌──────────────┐               │
│              │               │
│  THINKING    │               │
│              │               │
└──────┬───────┘               │
       │                       │
       │ LLM generates         │
       │ first sentence        │
       │                       │
       ▼                       │
┌──────────────┐               │
│              │               │
│  SPEAKING    │───────────────┘
│              │   Response complete
└──────┬───────┘   OR user interrupts
       │
       │ User speaks
       │ (barge-in)
       │
       └───────────────────────┘
```

## Data Flow

### 1. User Input Flow
```
Microphone
    │
    ▼
Web Audio API (PCM 16-bit, 16kHz)
    │
    ▼
WebSocket /audio/in
    │
    ▼
STT Layer (Deepgram)
    │
    ├─► Partial Transcript ──► Frontend (gray text)
    │
    └─► Final Transcript ────► Orchestrator
                                    │
                                    ▼
                              Add to history
```

### 2. AI Response Flow
```
Orchestrator
    │
    ▼
LLM Layer (OpenAI)
    │
    ├─► Stream chunks ──► Buffer sentences
    │
    └─► Complete sentence
            │
            ▼
        TTS Layer
            │
            ├─► Audio chunk 1 ──► WebSocket /audio/out ──► Browser
            ├─► Audio chunk 2 ──► WebSocket /audio/out ──► Browser
            ├─► Audio chunk 3 ──► WebSocket /audio/out ──► Browser
            │
            └─► Full text ──────► WebSocket /transcript ──► Frontend
```

## Component Responsibilities

### Frontend Components

**App.tsx**
- Main application orchestrator
- WebSocket connection management
- State management (messages, recording status)
- Callback handlers

**AudioManager.ts**
- Microphone access
- Audio format conversion (Float32 ↔ Int16)
- Audio playback
- Web Audio API management

**API Client (api.ts)**
- REST endpoint calls
- WebSocket factory methods
- Session management

**UI Components**
- MessageBubble: Display user/AI messages
- MicButton: Interactive mic control with states
- TranscriptPanel: Scrollable conversation view

### Backend Layers

**STT Layer (stt_layer.py)**
- Deepgram WebSocket connection
- Audio streaming
- Transcript event handling
- Partial vs. final transcript detection

**LLM Layer (llm_layer.py)**
- OpenAI API integration
- Streaming response handling
- Message history management
- Voice-optimized prompts

**TTS Layer (tts_layer.py)**
- Provider abstraction (Deepgram/ElevenLabs/OpenAI)
- Sentence-by-sentence synthesis
- Streaming audio output
- Interruption handling

**Orchestrator (orchestrator.py)**
- State machine implementation
- Turn-taking logic
- Barge-in detection
- Layer coordination
- Event broadcasting

## Key Design Decisions

### 1. Why State Machine?
- **Explicit states** prevent race conditions
- **Clear transitions** make debugging easier
- **Barge-in support** is trivial (SPEAKING → LISTENING)

### 2. Why Streaming?
- **Lower latency** - don't wait for full response
- **Better UX** - user sees progress immediately
- **Reduced perception of delay**

### 3. Why WebSockets?
- **Real-time bidirectional** communication
- **Low overhead** compared to polling
- **Native browser support**

### 4. Why Separate STT/LLM/TTS Layers?
- **Modularity** - swap providers easily
- **Testability** - mock individual components
- **Reusability** - use layers in other projects
- **Separation of concerns**

### 5. Why Partial Transcripts?
- **User feedback** - see what's being heard
- **Confidence building** - user knows system is working
- **Better UX** - reduced perceived latency

## Threading and Async Model

### Backend (Python)
- **FastAPI** uses async/await (asyncio)
- **WebSocket handlers** are async coroutines
- **STT/LLM/TTS** all use async generators
- **No threading** - pure async I/O

### Frontend (TypeScript)
- **React** uses single-threaded event loop
- **WebSockets** use native browser threads
- **Web Audio API** uses AudioWorklet (separate thread)
- **State updates** trigger re-renders

## Security Considerations

### Current Implementation (Development)
- ❌ No authentication
- ❌ No rate limiting
- ❌ No input validation
- ❌ CORS allows all origins

### Production Recommendations
- ✅ Add JWT authentication
- ✅ Implement rate limiting per user/IP
- ✅ Validate and sanitize all inputs
- ✅ Restrict CORS to specific domains
- ✅ Use HTTPS/WSS only
- ✅ Add request size limits
- ✅ Implement session timeouts
- ✅ Add logging and monitoring

## Scalability Considerations

### Horizontal Scaling
- **Stateless sessions** stored in Redis
- **Load balancer** for multiple backend instances
- **WebSocket sticky sessions** or message queue

### Vertical Scaling
- **Async I/O** handles many connections per instance
- **Connection pooling** for external APIs
- **Stream processing** keeps memory usage low

### Bottlenecks
1. **External APIs** (Deepgram, OpenAI) - most significant
2. **WebSocket connections** - manageable with async
3. **Audio processing** - minimal CPU usage (already PCM)

## Monitoring Points

### Backend
- WebSocket connection count
- Session creation/deletion rate
- STT latency (partial → final)
- LLM response time
- TTS synthesis time
- Error rates per component

### Frontend
- WebSocket connection stability
- Audio buffer health
- Message display latency
- User interaction events

## Future Enhancements

### Phase 2
- [ ] Persistent conversation storage (database)
- [ ] Multi-user support with authentication
- [ ] Voice activity detection (VAD) client-side
- [ ] Audio quality selection
- [ ] Multiple language support

### Phase 3
- [ ] Function calling / tool use
- [ ] Integration with external services
- [ ] Custom wake word detection
- [ ] Voice cloning options
- [ ] Sentiment analysis

---

This architecture prioritizes:
1. **Low latency** - streaming everywhere
2. **Clean separation** - easy to modify/extend
3. **Real-time UX** - instant feedback to user
4. **Production-ready** - proper error handling
