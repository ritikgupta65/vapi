# API Reference

Complete API documentation for the Speech-to-Speech AI system.

## Base URL

```
http://localhost:8000
```

In production, replace with your deployed URL.

## Authentication

Currently, no authentication is implemented. See [DEPLOYMENT.md](DEPLOYMENT.md#security-hardening) for adding authentication.

---

## REST Endpoints

### Health Check

Check if the server is running.

**Endpoint:** `GET /`

**Response:**
```json
{
  "status": "ok",
  "service": "speech-to-speech-ai",
  "version": "1.0.0"
}
```

**Example:**
```bash
curl http://localhost:8000/
```

---

### Create Session

Create a new conversation session.

**Endpoint:** `POST /session`

**Request Body:**
```json
{
  "system_prompt": "You are a helpful voice assistant."
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/session \
  -H "Content-Type: application/json" \
  -d '{"system_prompt": "You are a helpful voice assistant."}'
```

**Notes:**
- Session ID is required for all subsequent operations
- System prompt customizes AI behavior
- Keep system prompts concise for voice interactions

---

### Delete Session

Delete an existing session and clean up resources.

**Endpoint:** `DELETE /session/{session_id}`

**Response:**
```json
{
  "status": "deleted"
}
```

**Example:**
```bash
curl -X DELETE http://localhost:8000/session/550e8400-e29b-41d4-a716-446655440000
```

**Notes:**
- Stops all active WebSocket connections
- Cleans up orchestrator resources
- Returns 404 if session not found

---

### Get Session State

Retrieve current conversation state and history.

**Endpoint:** `GET /session/{session_id}/state`

**Response:**
```json
{
  "state": "listening",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful voice assistant."
    },
    {
      "role": "user",
      "content": "Hello, how are you?"
    },
    {
      "role": "assistant",
      "content": "I'm doing well, thank you for asking!"
    }
  ]
}
```

**States:**
- `listening` - Ready for user input
- `thinking` - Processing user input with LLM
- `speaking` - AI is generating/speaking response

**Example:**
```bash
curl http://localhost:8000/session/550e8400-e29b-41d4-a716-446655440000/state
```

---

## WebSocket Endpoints

### Audio Input Stream

Stream raw audio from microphone to the backend.

**Endpoint:** `WS /session/{session_id}/audio/in`

**Direction:** Client → Server

**Data Format:** Binary (raw PCM audio)

**Audio Specifications:**
- Format: PCM (Pulse Code Modulation)
- Bit depth: 16-bit
- Sample rate: 16,000 Hz
- Channels: 1 (mono)
- Byte order: Little-endian

**Example (JavaScript):**
```javascript
const ws = new WebSocket(
  'ws://localhost:8000/session/550e8400-e29b-41d4-a716-446655440000/audio/in'
);

ws.onopen = () => {
  // Send audio data as ArrayBuffer
  const audioData = new Int16Array(1024);
  ws.send(audioData.buffer);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

**Example (Python):**
```python
import asyncio
import websockets

async def stream_audio():
    uri = "ws://localhost:8000/session/test-id/audio/in"
    async with websockets.connect(uri) as ws:
        # Send audio chunks
        audio_chunk = b'\x00\x00' * 1024  # 1024 samples
        await ws.send(audio_chunk)

asyncio.run(stream_audio())
```

**Notes:**
- Connection must be established before sending audio
- Audio is streamed continuously while user speaks
- Server processes audio with Deepgram STT
- No response data sent on this connection

---

### Audio Output Stream

Receive synthesized speech audio from the backend.

**Endpoint:** `WS /session/{session_id}/audio/out`

**Direction:** Server → Client

**Data Format:** Binary (raw PCM audio)

**Audio Specifications:**
- Format: PCM
- Bit depth: 16-bit
- Sample rate: 16,000 Hz
- Channels: 1 (mono)

**Example (JavaScript):**
```javascript
const ws = new WebSocket(
  'ws://localhost:8000/session/550e8400-e29b-41d4-a716-446655440000/audio/out'
);

ws.onmessage = async (event) => {
  // event.data is a Blob or ArrayBuffer
  const audioData = await event.data.arrayBuffer();
  
  // Play audio using Web Audio API
  const audioContext = new AudioContext();
  const audioBuffer = audioContext.createBuffer(1, audioData.byteLength / 2, 16000);
  
  // Convert Int16 to Float32
  const channelData = audioBuffer.getChannelData(0);
  const view = new Int16Array(audioData);
  for (let i = 0; i < view.length; i++) {
    channelData[i] = view[i] / (view[i] < 0 ? 0x8000 : 0x7FFF);
  }
  
  // Play
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  source.start();
};
```

**Example (Python):**
```python
import asyncio
import websockets

async def receive_audio():
    uri = "ws://localhost:8000/session/test-id/audio/out"
    async with websockets.connect(uri) as ws:
        while True:
            audio_chunk = await ws.recv()
            # Process audio_chunk (bytes)
            print(f"Received {len(audio_chunk)} bytes")

asyncio.run(receive_audio())
```

**Notes:**
- Audio streams when AI is speaking
- Chunks arrive as they're synthesized
- Client should play audio immediately for low latency
- Connection remains open for entire session

---

### Transcript Stream

Receive real-time transcript events for the conversation.

**Endpoint:** `WS /session/{session_id}/transcript`

**Direction:** Server → Client

**Data Format:** JSON

**Message Schema:**
```typescript
{
  role: "user" | "assistant",
  text: string,
  is_partial: boolean
}
```

**Message Types:**

1. **Partial Transcript** (is_partial: true)
   - Interim transcription results
   - Updates as user speaks
   - May change before finalized

2. **Final Transcript** (is_partial: false)
   - Confirmed transcription
   - Sent to LLM for processing
   - Permanent in conversation history

**Example Messages:**

```json
// Partial user transcript
{
  "role": "user",
  "text": "Hello how are",
  "is_partial": true
}

// Final user transcript
{
  "role": "user",
  "text": "Hello how are you?",
  "is_partial": false
}

// Assistant response
{
  "role": "assistant",
  "text": "I'm doing great, thank you for asking!",
  "is_partial": false
}
```

**Example (JavaScript):**
```javascript
const ws = new WebSocket(
  'ws://localhost:8000/session/550e8400-e29b-41d4-a716-446655440000/transcript'
);

ws.onmessage = (event) => {
  const transcript = JSON.parse(event.data);
  
  if (transcript.is_partial) {
    // Update UI with gray text
    updatePartialTranscript(transcript);
  } else {
    // Add to permanent conversation history
    addToConversation(transcript);
  }
};
```

**Example (Python):**
```python
import asyncio
import websockets
import json

async def receive_transcripts():
    uri = "ws://localhost:8000/session/test-id/transcript"
    async with websockets.connect(uri) as ws:
        while True:
            message = await ws.recv()
            transcript = json.loads(message)
            
            role = transcript['role']
            text = transcript['text']
            is_partial = transcript['is_partial']
            
            if is_partial:
                print(f"[{role}] {text} ...")
            else:
                print(f"[{role}] {text}")

asyncio.run(receive_transcripts())
```

**Notes:**
- Partial transcripts allow live UI updates
- Only final transcripts are sent to LLM
- Multiple partial messages may arrive before final
- Assistant messages are always final (not partial)

---

## Error Responses

### HTTP Errors

**404 Not Found**
```json
{
  "detail": "Session not found"
}
```

**422 Unprocessable Entity**
```json
{
  "detail": [
    {
      "loc": ["body", "system_prompt"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**500 Internal Server Error**
```json
{
  "detail": "Internal server error"
}
```

### WebSocket Errors

**Close Codes:**
- `4004` - Session not found
- `4001` - Authentication failed (if auth enabled)
- `1000` - Normal closure
- `1001` - Going away
- `1011` - Server error

**Example:**
```javascript
ws.onclose = (event) => {
  console.log(`Connection closed: ${event.code} - ${event.reason}`);
};
```

---

## Rate Limits

Currently, no rate limiting is implemented. For production:

**Recommended limits:**
- Session creation: 10 per minute per IP
- WebSocket connections: 5 concurrent per IP
- Audio streaming: 1 MB/second per connection

See [DEPLOYMENT.md](DEPLOYMENT.md#security-hardening) for implementation.

---

## Usage Examples

### Complete Conversation Flow

```javascript
// 1. Create session
const response = await fetch('http://localhost:8000/session', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    system_prompt: 'You are a helpful assistant.'
  })
});
const { session_id } = await response.json();

// 2. Connect WebSockets
const audioInWs = new WebSocket(
  `ws://localhost:8000/session/${session_id}/audio/in`
);
const audioOutWs = new WebSocket(
  `ws://localhost:8000/session/${session_id}/audio/out`
);
const transcriptWs = new WebSocket(
  `ws://localhost:8000/session/${session_id}/transcript`
);

// 3. Handle transcript
transcriptWs.onmessage = (event) => {
  const transcript = JSON.parse(event.data);
  console.log(`${transcript.role}: ${transcript.text}`);
};

// 4. Handle audio output
audioOutWs.onmessage = async (event) => {
  const audioData = await event.data.arrayBuffer();
  // Play audio...
};

// 5. Send audio input
// (from microphone via Web Audio API)
audioInWs.send(audioChunk);

// 6. Clean up when done
await fetch(`http://localhost:8000/session/${session_id}`, {
  method: 'DELETE'
});
```

---

## SDK / Client Libraries

### JavaScript/TypeScript

The frontend includes a ready-to-use API client:

```typescript
import { SpeechToSpeechAPI } from './api';

// Create session
const sessionId = await SpeechToSpeechAPI.createSession("System prompt");

// Create WebSockets
const audioIn = SpeechToSpeechAPI.createAudioInputSocket(sessionId);
const audioOut = SpeechToSpeechAPI.createAudioOutputSocket(sessionId);
const transcript = SpeechToSpeechAPI.createTranscriptSocket(sessionId);

// Delete session
await SpeechToSpeechAPI.deleteSession(sessionId);
```

### Python

Example Python client:

```python
import requests
import websockets
import asyncio

class SpeechToSpeechClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace('http', 'ws')
    
    def create_session(self, system_prompt):
        response = requests.post(
            f"{self.base_url}/session",
            json={"system_prompt": system_prompt}
        )
        return response.json()["session_id"]
    
    async def connect_transcript(self, session_id, callback):
        uri = f"{self.ws_url}/session/{session_id}/transcript"
        async with websockets.connect(uri) as ws:
            async for message in ws:
                callback(json.loads(message))
```

---

## Changelog

### Version 1.0.0 (Current)

- Initial release
- REST API for session management
- WebSocket streaming for audio and transcripts
- Support for Deepgram STT, OpenAI LLM, multiple TTS providers

---

## Support

For issues or questions:
1. Check [README.md](README.md) for basic setup
2. Review [QUICKSTART.md](QUICKSTART.md) for common problems
3. See [ARCHITECTURE.md](ARCHITECTURE.md) for system design
4. Check [DEPLOYMENT.md](DEPLOYMENT.md) for production concerns
