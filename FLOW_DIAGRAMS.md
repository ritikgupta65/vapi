# Conversation Flow Diagrams

Visual guides showing how the system works.

## 🎙️ Complete Conversation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER SPEAKS                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                    [Microphone Audio]
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                    WEB AUDIO API                                │
│  • Capture audio from mic                                       │
│  • Convert Float32 → Int16 PCM                                  │
│  • Stream 4096-sample chunks                                    │
└───────────────────────────┬────────────────────────────────────┘
                            │
                    [PCM Audio Chunks]
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│              WebSocket: /audio/in                               │
│  • Sends raw audio bytes to backend                            │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                 CONVERSATION ORCHESTRATOR                       │
│  Current State: LISTENING                                       │
│  • Receives audio chunk                                         │
│  • Checks: Is AI speaking? → YES: Stop AI (barge-in)          │
│  • Sends to STT Layer                                          │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                   STT LAYER (Deepgram)                          │
│  • Streams audio to Deepgram WebSocket                         │
│  • Receives interim results                                     │
│  • Receives final transcripts                                  │
└───┬───────────────────────┴────────────────────────────────────┘
    │                       │
    │ Partial              │ Final
    │ "Hello how..."       │ "Hello how are you?"
    │                       │
    ▼                       ▼
┌────────────────┐   ┌──────────────────────────────────────────┐
│ Frontend UI    │   │      ORCHESTRATOR                         │
│ (gray text)    │   │  State: LISTENING → THINKING              │
└────────────────┘   │  • Add to conversation history           │
                     │  • Call LLM Layer                         │
                     └───────────────┬──────────────────────────┘
                                     │
                     [User Message: "Hello how are you?"]
                                     │
                                     ▼
                     ┌──────────────────────────────────────────┐
                     │        LLM LAYER (OpenAI)                 │
                     │  • Send conversation history              │
                     │  • Stream response chunks                 │
                     │  • Buffer until sentence complete         │
                     └───────────────┬──────────────────────────┘
                                     │
                     [Stream: "I'm", " doing", " great", "!"]
                                     │
                                     ▼
                     ┌──────────────────────────────────────────┐
                     │        ORCHESTRATOR                       │
                     │  State: THINKING → SPEAKING               │
                     │  • Buffer: "I'm doing great!"            │
                     │  • Send sentence to TTS                   │
                     └───────────────┬──────────────────────────┘
                                     │
                     ["I'm doing great!"]
                                     │
                                     ▼
                     ┌──────────────────────────────────────────┐
                     │    TTS LAYER (Deepgram/ElevenLabs)       │
                     │  • Synthesize text to audio               │
                     │  • Stream audio chunks                    │
                     └───────────────┬──────────────────────────┘
                                     │
                     [Audio Chunks: 1024 bytes each]
                                     │
                     ┌───────────────┴──────────────┐
                     │                              │
                     ▼                              ▼
         ┌─────────────────────┐      ┌─────────────────────────┐
         │ WS: /audio/out      │      │ WS: /transcript         │
         │ (binary audio)      │      │ (JSON transcript)       │
         └──────────┬──────────┘      └──────────┬──────────────┘
                    │                            │
                    ▼                            ▼
         ┌─────────────────────┐      ┌─────────────────────────┐
         │  Browser Speaker    │      │  Frontend UI            │
         │  (play audio)       │      │  (show transcript)      │
         └─────────────────────┘      └─────────────────────────┘
                    │                            │
                    ▼                            ▼
         User hears: "I'm doing great!"   User sees: "I'm doing great!"
```

---

## 🔄 State Machine Transitions

```
┌──────────────────────────────────────────────────────────────┐
│                      INITIAL STATE                            │
│                                                               │
│                     ┌──────────────┐                         │
│                     │              │                         │
│                     │  LISTENING   │◄─────────────────────┐  │
│                     │              │                      │  │
│                     └──────┬───────┘                      │  │
│                            │                              │  │
│                            │ Trigger: Final transcript    │  │
│                            │ received from STT            │  │
│                            │                              │  │
│                            ▼                              │  │
│                     ┌──────────────┐                      │  │
│                     │              │                      │  │
│                     │   THINKING   │                      │  │
│                     │              │                      │  │
│                     └──────┬───────┘                      │  │
│                            │                              │  │
│                            │ Trigger: First sentence      │  │
│                            │ from LLM ready               │  │
│                            │                              │  │
│                            ▼                              │  │
│                     ┌──────────────┐                      │  │
│                     │              │                      │  │
│                     │   SPEAKING   │──────────────────────┤  │
│                     │              │                      │  │
│                     └──────┬───────┘                      │  │
│                            │                              │  │
│                            │ Trigger: Response complete   │  │
│                            │                              │  │
│                            └──────────────────────────────┘  │
│                                                               │
│  INTERRUPTION: User speaks while SPEAKING → immediate        │
│  transition to LISTENING (barge-in)                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎯 Barge-in (Interruption) Flow

```
AI is speaking...

         ┌──────────────┐
         │   SPEAKING   │
         └──────┬───────┘
                │
                │ AI: "Let me tell you about..."
                ▼
         [TTS Layer producing audio]
                │
                │ ┌─────────────────────────────┐
                │ │ USER STARTS SPEAKING        │
                │ │ (audio detected)             │
                │ └──────────────┬──────────────┘
                │                │
                ▼                ▼
         ┌────────────────────────────┐
         │   ORCHESTRATOR             │
         │   • Detects new audio      │
         │   • Current state: SPEAKING│
         │   • ACTION: BARGE-IN!      │
         └────────────┬───────────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
         ▼            ▼            ▼
    [Stop TTS]  [Cancel LLM]  [Transition State]
         │            │            │
         │            │            │
         └────────────┴────────────┘
                      │
                      ▼
         ┌──────────────────────┐
         │   LISTENING          │
         │   Ready for new      │
         │   user input         │
         └──────────────────────┘
```

---

## 📊 Latency Breakdown

```
User stops speaking
         │
         │ 0ms
         ▼
    ┌─────────────────────┐
    │ Deepgram STT        │
    │ Processes audio     │
    └─────────┬───────────┘
              │
              │ 100-300ms
              ▼
    ┌─────────────────────┐
    │ Final transcript    │
    │ sent to LLM         │
    └─────────┬───────────┘
              │
              │ 200-500ms
              ▼
    ┌─────────────────────┐
    │ GPT generates       │
    │ first sentence      │
    └─────────┬───────────┘
              │
              │ 200-400ms
              ▼
    ┌─────────────────────┐
    │ TTS synthesizes     │
    │ audio               │
    └─────────┬───────────┘
              │
              │ 50-100ms
              ▼
    ┌─────────────────────┐
    │ User hears AI       │
    └─────────────────────┘

Total: 550-1300ms (realistic)

With streaming: User hears first words after ~550ms,
rest streams while still being generated!
```

---

## 🔌 WebSocket Connection Lifecycle

```
Frontend                Backend
   │                       │
   │  POST /session        │
   ├──────────────────────►│
   │                       │ Create orchestrator
   │  {session_id: "..."}  │
   │◄──────────────────────┤
   │                       │
   │  WS /audio/in         │
   ├──────────────────────►│
   │                       │ Accept connection
   │  [WebSocket Open]     │
   │◄──────────────────────┤
   │                       │
   │  WS /audio/out        │
   ├──────────────────────►│
   │                       │ Accept connection
   │  [WebSocket Open]     │
   │◄──────────────────────┤
   │                       │
   │  WS /transcript       │
   ├──────────────────────►│
   │                       │ Accept connection
   │  [WebSocket Open]     │
   │◄──────────────────────┤
   │                       │
   │  [audio bytes]        │
   ├──────────────────────►│
   │                       │ Process → STT
   │                       │
   │  [transcript JSON]    │
   │◄──────────────────────┤
   │                       │
   │                       │ Process → LLM → TTS
   │  [audio bytes]        │
   │◄──────────────────────┤
   │                       │
   │  DELETE /session      │
   ├──────────────────────►│
   │                       │ Close all connections
   │  {status: "deleted"}  │ Clean up resources
   │◄──────────────────────┤
   │                       │
```

---

## 🧩 Component Interaction

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                      │
│                                                          │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ App.tsx    │  │ AudioManager │  │ API Client     │  │
│  │            │  │              │  │                │  │
│  │ • State    │  │ • Mic        │  │ • Session API  │  │
│  │ • WS mgmt  │  │ • Speakers   │  │ • WebSockets   │  │
│  │ • UI       │  │ • Conversion │  │                │  │
│  └─────┬──────┘  └──────┬───────┘  └────┬───────────┘  │
│        │                │               │               │
└────────┼────────────────┼───────────────┼───────────────┘
         │                │               │
         │                │               │
         ▼                ▼               ▼
    [State Mgmt]     [Audio I/O]    [Network]
         │                │               │
         └────────────────┼───────────────┘
                          │
                  WebSocket Connection
                          │
┌─────────────────────────┼───────────────────────────────┐
│                         │                                │
│                    BACKEND (FastAPI)                     │
│                         │                                │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │         WebSocket Handler Layer                    │  │
│  │  • Accept connections                              │  │
│  │  • Route messages                                  │  │
│  │  • Manage lifecycles                               │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                                │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │        Conversation Orchestrator                   │  │
│  │  • State machine                                   │  │
│  │  • Turn-taking                                     │  │
│  │  • Layer coordination                              │  │
│  └──┬────────────┬─────────────┬────────────────────┘  │
│     │            │             │                        │
│  ┌──▼───┐   ┌───▼────┐   ┌───▼────┐                   │
│  │ STT  │   │  LLM   │   │  TTS   │                   │
│  │Layer │   │ Layer  │   │ Layer  │                   │
│  └──┬───┘   └────┬───┘   └───┬────┘                   │
│     │            │           │                          │
└─────┼────────────┼───────────┼──────────────────────────┘
      │            │           │
      ▼            ▼           ▼
 [Deepgram]   [OpenAI]   [Deepgram/ElevenLabs]
```

---

## 💬 Message Flow Example

**User:** "What's the weather?"

```
Time  | Component        | Action
------|------------------|----------------------------------------
0ms   | User             | Speaks: "What's the weather?"
50ms  | AudioManager     | Captures audio chunk 1
50ms  | WebSocket        | Sends chunk 1 to backend
100ms | STT Layer        | Partial: "What's"
100ms | Frontend         | Shows: "What's" (gray)
150ms | AudioManager     | Captures audio chunk 2
200ms | STT Layer        | Partial: "What's the"
200ms | Frontend         | Updates: "What's the" (gray)
500ms | User             | Stops speaking
600ms | STT Layer        | Final: "What's the weather?"
600ms | Orchestrator     | LISTENING → THINKING
600ms | Frontend         | Shows: "What's the weather?" (black)
650ms | LLM Layer        | Sends to OpenAI
850ms | OpenAI           | Returns chunk: "The current"
900ms | LLM Layer        | Buffer: "The current weather..."
1000ms| LLM Layer        | Complete sentence detected
1000ms| Orchestrator     | THINKING → SPEAKING
1050ms| TTS Layer        | Synthesize sentence 1
1250ms| TTS Layer        | First audio chunk ready
1250ms| WebSocket        | Send audio chunk 1
1250ms| Frontend         | Play audio chunk 1
1300ms| Frontend         | Show: "The current weather is sunny"
1350ms| User             | Hears first words
...   | ...              | More audio chunks stream
2000ms| Orchestrator     | Response complete, SPEAKING → LISTENING
```

---

## 🎭 Partial vs Final Transcript Example

```
Time   | Type     | Text                          | UI Display
-------|----------|-------------------------------|------------------
100ms  | Partial  | "Hello"                       | "Hello" (gray)
200ms  | Partial  | "Hello how"                   | "Hello how" (gray)
300ms  | Partial  | "Hello how are"               | "Hello how are" (gray)
500ms  | Final    | "Hello how are you?"          | "Hello how are you?" (black)
                                                   ↓
                                                   Sent to GPT
```

**Key Points:**
- Partial transcripts = interim results (may change)
- Final transcripts = confirmed (sent to LLM)
- Only final transcripts added to history
- Partials give user feedback that system is working

---

This visual guide helps understand:
1. How data flows through the system
2. When state transitions happen
3. How barge-in works
4. Latency at each step
5. WebSocket communication patterns
6. Component responsibilities
