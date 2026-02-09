# Flask Speech-to-Speech Quick Start

## ✅ Fixed Issues

The original Flask app had several issues:
1. ❌ Required Azure AI SDK (not installed)
2. ❌ Hardcoded to Azure endpoints
3. ❌ No STT or TTS functionality

## ✅ New Features Added

1. **Speech-to-Text (STT)** using Deepgram
2. **Text-to-Speech (TTS)** using Deepgram
3. **Chat with OpenAI** LLM
4. **Full Speech-to-Speech** pipeline
5. Works without Azure dependencies

## 🚀 Quick Start

### 1. Install packages (Already done!)
```bash
pip install flask flask-cors python-dotenv deepgram-sdk openai
```

### 2. Run the server
```bash
python app_working.py
```

### 3. Test the API

**Open the test page:**
- Open `test_speech.html` in your browser
- Or visit: `http://localhost:5000`

**Or use curl:**

```bash
# Test TTS
curl http://localhost:5000/test

# Test Chat
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

## 📡 API Endpoints

### 1. POST /stt (Speech-to-Text)
Convert audio to text

```bash
curl -X POST http://localhost:5000/stt \
  -F "audio=@recording.wav"
```

Response:
```json
{
  "success": true,
  "transcript": "Hello, how are you?",
  "confidence": 0.95
}
```

### 2. POST /tts (Text-to-Speech)
Convert text to audio

```bash
curl -X POST http://localhost:5000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "format": "raw"}' \
  --output speech.wav
```

Response (JSON format):
```json
{
  "success": true,
  "audio": "base64_encoded_audio_data",
  "format": "linear16",
  "sample_rate": 16000
}
```

### 3. POST /chat
Chat with AI

```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

Response:
```json
{
  "success": true,
  "response": "2 + 2 equals 4.",
  "model": "gpt-4o-mini",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

### 4. POST /speech-to-speech
Full pipeline: Audio in → Audio out

```bash
curl -X POST http://localhost:5000/speech-to-speech \
  -F "audio=@recording.wav"
```

Response:
```json
{
  "success": true,
  "transcript": "What is the weather?",
  "response": "I don't have access to real-time weather data.",
  "audio": "base64_encoded_response_audio"
}
```

## 🔧 Configuration

Your Deepgram API key is already configured in `.env`:
```
DEEPGRAM_API_KEY=6985219805a7076276962e72ee835d9bd9961747
```

To add OpenAI (for chat), add to `.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

## 🎯 What's Different from Original?

| Original | New |
|----------|-----|
| Required Azure AI SDK | Uses OpenAI or gracefully degrades |
| No STT/TTS | Full Deepgram integration |
| Complex Azure setup | Simple Flask endpoints |
| Hard to test | Test page included |
| One endpoint | 5 useful endpoints |

## 📝 Files Created

1. **app_working.py** - New Flask server with STT/TTS
2. **test_speech.html** - Browser-based test interface
3. **requirements_flask.txt** - Package list
4. **.env** - Environment configuration (already has Deepgram key)

## 🧪 Testing

### Option 1: Browser Test (Recommended)
1. Run `python app_working.py`
2. Open `test_speech.html` in Chrome/Firefox
3. Click buttons to test each feature

### Option 2: Command Line
```bash
# Test health check
curl http://localhost:5000/

# Test TTS
curl http://localhost:5000/test --output test.wav
# Then play test.wav

# Test chat (if OpenAI key is set)
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hi"}]}'
```

## ⚡ Quick Demo

1. **Start server:**
   ```bash
   python app_working.py
   ```

2. **Test TTS in browser:**
   - Open: http://localhost:5000/test
   - You'll hear: "Hello! This is a test..."

3. **Use test page:**
   - Open `test_speech.html`
   - Test each feature with buttons

## 🐛 Troubleshooting

**Server won't start:**
- Make sure port 5000 is available
- Check that packages are installed: `pip list | grep -E "flask|deepgram|openai"`

**TTS not working:**
- Verify Deepgram key in `.env`
- Check server logs for errors

**Chat not working:**
- Add `OPENAI_API_KEY` to `.env`
- Or it will show error (expected if key not set)

**Browser tests fail:**
- Make sure server is running on port 5000
- Check browser console for CORS errors
- Allow microphone access when prompted

## 🎉 Success!

Your Flask server now has:
- ✅ Working STT (Deepgram)
- ✅ Working TTS (Deepgram)  
- ✅ Chat with AI (OpenAI)
- ✅ Full speech-to-speech pipeline
- ✅ Easy to test
- ✅ No Azure dependencies

## 🚀 Next Steps

1. Add your OpenAI key to `.env` for chat
2. Try the full speech-to-speech pipeline
3. Build a frontend that uses these APIs
4. Deploy to production server

---

**Server running at:** http://localhost:5000
**Test page:** Open `test_speech.html` in your browser
