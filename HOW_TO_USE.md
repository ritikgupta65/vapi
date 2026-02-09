# 🎯 HOW TO USE - Speech-to-Speech AI

## ✅ STATUS: READY TO USE!

Your Flask server is **running and operational** with:
- ✅ Deepgram STT (Speech-to-Text)
- ✅ Deepgram TTS (Text-to-Speech)
- ✅ OpenAI Chat
- ✅ Server at http://localhost:5000

## 🚀 Quick Start (3 Steps)

### Step 1: Server is Running ✅
The server is already started! You should see:
```
✅ Deepgram initialized
✅ OpenAI initialized
Server running at: http://localhost:5000
```

### Step 2: Test in Browser
Two browser windows should have opened:
1. **http://localhost:5000/test** - Simple TTS test (you'll hear audio)
2. **test_speech.html** - Full interactive test page

### Step 3: Try the Features
In the test page (test_speech.html):
- Click **"Test TTS"** to hear AI speak
- Click **"Start Recording"** to test STT
- Click **"Send to Chat"** to test AI chat
- Click **"Record Question"** for full speech-to-speech

## 📖 Detailed Usage

### Using the Test Page (test_speech.html)

#### 1. Test Text-to-Speech (TTS)
```
1. Enter text in the box (or use default)
2. Click "Test TTS"
3. Audio will play automatically
4. You'll see status: "TTS Success"
```

**What it does:**
- Sends text to Deepgram TTS API
- Gets back audio in base64 format
- Converts to playable audio
- Plays through your speakers

#### 2. Test Speech-to-Text (STT)
```
1. Click "Start Recording"
2. Allow microphone access (browser will ask)
3. Speak clearly into your microphone
4. Click "Stop Recording"
5. Audio automatically sends to STT
6. See transcript appear below
```

**What it does:**
- Records audio from your microphone
- Converts to WAV format
- Sends to Deepgram STT API
- Returns text transcript

#### 3. Test AI Chat
```
1. Enter a question
2. Click "Send to Chat"
3. See AI response appear
4. Response is also spoken aloud (TTS)
```

**What it does:**
- Sends message to OpenAI
- Gets AI response
- Converts response to speech
- Plays audio response

#### 4. Full Speech-to-Speech Pipeline
```
1. Click "Record Question"
2. Speak your question
3. Click "Stop Recording"
4. Wait for processing (~2-3 seconds)
5. Hear AI's spoken response
```

**What it does:**
- Records your speech → STT
- Sends transcript → OpenAI
- Gets AI response → TTS
- Plays audio response
- Full conversational loop!

## 🔧 Manual Testing (Command Line)

### Test Health Check
```bash
curl http://localhost:5000/
```

Expected response:
```json
{
  "status": "ok",
  "message": "Speech-to-Speech AI Server",
  "deepgram": "available",
  "openai": "available"
}
```

### Test TTS
```bash
curl -X POST http://localhost:5000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}' \
  -o output.wav
```

Then play output.wav - you should hear "Hello world"

### Test Chat
```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

Expected response:
```json
{
  "success": true,
  "response": "2 + 2 equals 4.",
  "model": "gpt-4o-mini"
}
```

## 🎯 Use in Your Own Code

### Python Example
```python
import requests
import base64

# 1. Speech-to-Text
with open("recording.wav", "rb") as f:
    stt_response = requests.post(
        "http://localhost:5000/stt",
        files={"audio": f}
    )
user_text = stt_response.json()["transcript"]
print(f"User said: {user_text}")

# 2. Get AI Response
chat_response = requests.post(
    "http://localhost:5000/chat",
    json={
        "messages": [
            {"role": "user", "content": user_text}
        ]
    }
)
ai_text = chat_response.json()["response"]
print(f"AI says: {ai_text}")

# 3. Text-to-Speech
tts_response = requests.post(
    "http://localhost:5000/tts",
    json={"text": ai_text}
)
audio_base64 = tts_response.json()["audio"]
audio_bytes = base64.b64decode(audio_base64)

# 4. Play or save audio
with open("ai_response.wav", "wb") as f:
    f.write(audio_bytes)
```

### JavaScript Example
```javascript
// 1. Record audio from browser
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const mediaRecorder = new MediaRecorder(stream);
const chunks = [];

mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
mediaRecorder.onstop = async () => {
    const audioBlob = new Blob(chunks, { type: 'audio/wav' });
    
    // 2. Send to speech-to-speech endpoint
    const formData = new FormData();
    formData.append('audio', audioBlob);
    
    const response = await fetch('http://localhost:5000/speech-to-speech', {
        method: 'POST',
        body: formData
    });
    
    const data = await response.json();
    console.log('You said:', data.transcript);
    console.log('AI said:', data.response);
    
    // 3. Play AI response
    const audioData = atob(data.audio);
    const audioArray = new Uint8Array(audioData.length);
    for (let i = 0; i < audioData.length; i++) {
        audioArray[i] = audioData.charCodeAt(i);
    }
    
    const audioBlob2 = new Blob([audioArray], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioBlob2);
    const audio = new Audio(audioUrl);
    audio.play();
};

// Start recording
mediaRecorder.start();

// Stop after 5 seconds
setTimeout(() => mediaRecorder.stop(), 5000);
```

## 🔍 Understanding the Endpoints

### POST /stt (Speech-to-Text)
**Accepts:**
- Audio file upload (multipart/form-data)
- JSON with base64 audio: `{"audio": "base64string..."}`
- Raw audio bytes

**Returns:**
```json
{
  "success": true,
  "transcript": "transcribed text here",
  "confidence": 0.95
}
```

### POST /tts (Text-to-Speech)
**Accepts:**
```json
{
  "text": "Text to speak",
  "model": "aura-asteria-en",  // optional
  "encoding": "linear16",      // optional
  "format": "base64"           // or "raw"
}
```

**Returns (base64 format):**
```json
{
  "success": true,
  "audio": "base64_encoded_audio...",
  "format": "linear16",
  "sample_rate": 16000
}
```

**Returns (raw format):**
- Raw WAV audio bytes
- Content-Type: audio/wav

### POST /chat
**Accepts:**
```json
{
  "messages": [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "User message"}
  ],
  "model": "gpt-4o-mini",      // optional
  "temperature": 0.7           // optional
}
```

**Returns:**
```json
{
  "success": true,
  "response": "AI response text",
  "model": "gpt-4o-mini",
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 20,
    "total_tokens": 35
  }
}
```

### POST /speech-to-speech
**Accepts:**
- Audio file (same as /stt)

**Returns:**
```json
{
  "success": true,
  "transcript": "what user said",
  "response": "what AI said",
  "audio": "base64_audio_of_ai_response"
}
```

### GET /test
Simple TTS test - returns audio file saying:
"Hello! This is a test of the Deepgram text-to-speech system..."

## 🎮 Real-World Usage Examples

### Example 1: Voice Assistant
```python
import requests
import pyaudio
import wave

# Record user's question
def record_audio(filename, duration=5):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, 
                    rate=16000, input=True)
    
    frames = []
    for _ in range(int(16000 * duration)):
        frames.append(stream.read(1024))
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(16000)
        wf.writeframes(b''.join(frames))

# Use speech-to-speech endpoint
print("Recording... Speak now!")
record_audio("question.wav", duration=5)

with open("question.wav", "rb") as f:
    response = requests.post(
        "http://localhost:5000/speech-to-speech",
        files={"audio": f}
    )

data = response.json()
print(f"\nYou: {data['transcript']}")
print(f"AI: {data['response']}\n")

# Play response
import base64
audio_bytes = base64.b64decode(data['audio'])
with open("response.wav", "wb") as f:
    f.write(audio_bytes)

# Play using system player
import os
os.system("start response.wav")  # Windows
# os.system("afplay response.wav")  # Mac
# os.system("aplay response.wav")   # Linux
```

### Example 2: Meeting Transcription
```python
import requests

def transcribe_meeting(audio_file):
    with open(audio_file, "rb") as f:
        response = requests.post(
            "http://localhost:5000/stt",
            files={"audio": f}
        )
    
    return response.json()

# Transcribe recording
result = transcribe_meeting("meeting.wav")
print(f"Transcript: {result['transcript']}")
print(f"Confidence: {result['confidence']}")

# Save to file
with open("meeting_transcript.txt", "w") as f:
    f.write(result['transcript'])
```

### Example 3: Interactive Voice Bot
```python
import requests
import base64

conversation_history = []

def chat_turn(user_audio_file):
    # 1. STT
    with open(user_audio_file, "rb") as f:
        stt_response = requests.post(
            "http://localhost:5000/stt",
            files={"audio": f}
        )
    user_message = stt_response.json()["transcript"]
    
    # 2. Add to history
    conversation_history.append({
        "role": "user",
        "content": user_message
    })
    
    # 3. Get AI response
    chat_response = requests.post(
        "http://localhost:5000/chat",
        json={"messages": conversation_history}
    )
    ai_message = chat_response.json()["response"]
    
    # 4. Add AI response to history
    conversation_history.append({
        "role": "assistant",
        "content": ai_message
    })
    
    # 5. TTS
    tts_response = requests.post(
        "http://localhost:5000/tts",
        json={"text": ai_message}
    )
    audio_base64 = tts_response.json()["audio"]
    
    # Save and return
    audio_bytes = base64.b64decode(audio_base64)
    with open("bot_response.wav", "wb") as f:
        f.write(audio_bytes)
    
    return user_message, ai_message

# Use it
user_said, bot_said = chat_turn("user_question.wav")
print(f"User: {user_said}")
print(f"Bot: {bot_said}")
```

## 🐛 Troubleshooting

### No audio playing
- **Check speakers:** Make sure volume is up
- **Try /test endpoint:** http://localhost:5000/test
- **Check browser console:** Look for errors

### Microphone not working
- **Browser permission:** Allow mic access when prompted
- **Check device:** Ensure mic is connected
- **Try different browser:** Chrome/Firefox recommended

### "Deepgram not available" error
- **Check .env file:** Make sure DEEPGRAM_API_KEY is set
- **Restart server:** Stop and run `python run_server.py` again
- **Check API key:** Verify key at https://console.deepgram.com

### "OpenAI not available" error  
- **Add API key:** Add OPENAI_API_KEY to .env
- **Or:** Chat endpoint will show error (STT/TTS still work)

### Server not responding
- **Check if running:** Look for "Running on http://127.0.0.1:5000"
- **Check port:** Make sure nothing else uses port 5000
- **Restart:** Stop with Ctrl+C, then run `python run_server.py`

## 📊 Performance Tips

### For Best STT Quality:
- Use WAV format (16kHz, 16-bit, mono)
- Speak clearly with good microphone
- Minimize background noise
- Keep audio under 2 minutes per request

### For Best TTS Quality:
- Use punctuation in text
- Break long text into sentences
- Default voice (aura-asteria-en) is excellent
- ~50-100 words per request is optimal

### For Fast Response:
- Use /speech-to-speech for full pipeline (faster than individual calls)
- Keep audio/text short when possible
- Server can handle ~10 concurrent requests

## 🎉 You're Ready!

Your server is **fully operational**. Everything you need to test:

1. ✅ Server running at http://localhost:5000
2. ✅ Test page opened (test_speech.html)
3. ✅ TTS test endpoint (/test)
4. ✅ All APIs working

**Start testing now!** Use the test page or try the examples above.

---

**Questions?** Check [FLASK_GUIDE.md](FLASK_GUIDE.md) or [STATUS.md](STATUS.md)
