"""
Flask-based Speech-to-Speech AI with Deepgram STT/TTS and OpenAI
"""
import json
import os
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Try to import required packages
try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError as e:
    DEEPGRAM_AVAILABLE = False
    print(f"⚠️  Deepgram not installed. Run: pip install deepgram-sdk (Error: {e})")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  OpenAI not installed. Run: pip install openai")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load environment variables
load_dotenv()

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "6985219805a7076276962e72ee835d9bd9961747")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")

# Initialize clients
deepgram_client = None
openai_client = None

if DEEPGRAM_AVAILABLE and DEEPGRAM_API_KEY:
    try:
        deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
        print("✅ Deepgram initialized")
    except Exception as e:
        print(f"❌ Deepgram initialization failed: {e}")
        deepgram_client = None
else:
    print("❌ Deepgram not available")

if OPENAI_AVAILABLE and OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI initialized")
else:
    print("❌ OpenAI not available")


# -------------------------
# STT ENDPOINT (Speech-to-Text)
# -------------------------
@app.route("/stt", methods=["POST"])
def speech_to_text():
    """
    Convert speech to text using Deepgram.
    
    Request body (JSON):
    {
        "audio": "base64-encoded audio data",
        "mimetype": "audio/wav" (optional)
    }
    
    Or send audio file directly as multipart/form-data
    """
    if not deepgram_client:
        return jsonify({"error": "Deepgram not configured"}), 500
    
    try:
        # Check if audio is sent as file or base64
        if 'audio' in request.files:
            # Audio file upload
            audio_file = request.files['audio']
            audio_data = audio_file.read()
        elif request.is_json:
            # Base64 encoded audio
            data = request.get_json()
            audio_base64 = data.get("audio")
            if not audio_base64:
                return jsonify({"error": "Missing 'audio' field"}), 400
            audio_data = base64.b64decode(audio_base64)
        else:
            # Raw audio bytes
            audio_data = request.data
        
        if not audio_data:
            return jsonify({"error": "No audio data provided"}), 400
        
        # Configure Deepgram options (v5 SDK uses dict-based options)
        options = {
            "model": "nova-2",
            "language": "en-US",
            "smart_format": True,
            "punctuate": True,
            "diarize": False,
        }
        
        # Send to Deepgram (v5 SDK - pass audio buffer directly)
        payload = {"buffer": audio_data}
        response = deepgram_client.listen.rest.v("1").transcribe_file(
            payload,
            options
        )
        
        # Extract transcript
        transcript = ""
        confidence = 0.0
        if response and response.results and response.results.channels:
            alternatives = response.results.channels[0].alternatives
            if alternatives:
                transcript = alternatives[0].transcript
                confidence = alternatives[0].confidence if hasattr(alternatives[0], 'confidence') else 0.0
        
        return jsonify({
            "success": True,
            "transcript": transcript,
            "confidence": confidence
        })
    
    except Exception as e:
        print(f"STT Error: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# TTS ENDPOINT (Text-to-Speech)
# -------------------------
@app.route("/tts", methods=["POST"])
def text_to_speech():
    """
    Convert text to speech using Deepgram.
    
    Request body (JSON):
    {
        "text": "Text to convert to speech",
        "model": "aura-asteria-en" (optional),
        "encoding": "linear16" (optional)
    }
    
    Returns audio as base64 encoded string or raw bytes
    """
    if not deepgram_client:
        return jsonify({"error": "Deepgram not configured"}), 500
    
    try:
        data = request.get_json()
        text = data.get("text")
        
        if not text:
            return jsonify({"error": "Missing 'text' field"}), 400
        
        # Configure Deepgram TTS options (v5 SDK uses dict-based options)
        model = data.get("model", "aura-asteria-en")
        encoding = data.get("encoding", "linear16")
        
        options = {
            "model": model,
            "encoding": encoding,
            "sample_rate": 16000,
        }
        
        # Generate speech (v5 SDK)
        payload = {"text": text}
        response = deepgram_client.speak.rest.v("1").stream(
            payload,
            options
        )
        
        # Get audio data
        audio_data = b""
        for chunk in response.stream_memory:
            audio_data += chunk
        
        # Return as base64 or raw
        return_format = data.get("format", "base64")
        
        if return_format == "raw":
            return audio_data, 200, {'Content-Type': 'audio/wav'}
        else:
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            return jsonify({
                "success": True,
                "audio": audio_base64,
                "format": encoding,
                "sample_rate": 16000
            })
    
    except Exception as e:
        print(f"TTS Error: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# LLM CHAT ENDPOINT
# -------------------------
@app.route("/chat", methods=["POST"])
def chat():
    """
    Chat with OpenAI LLM.
    
    Request body (JSON):
    {
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "model": "gpt-4o-mini" (optional),
        "temperature": 0.7 (optional),
        "max_tokens": 500 (optional)
    }
    """
    if not openai_client:
        return jsonify({"error": "OpenAI not configured"}), 500
    
    try:
        data = request.get_json()
        messages = data.get("messages", [])
        
        if not messages:
            return jsonify({"error": "Missing 'messages' field"}), 400
        
        model = data.get("model", DEFAULT_MODEL)
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 500)
        
        # Call OpenAI
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract response
        assistant_message = response.choices[0].message.content
        
        return jsonify({
            "success": True,
            "response": assistant_message,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        })
    
    except Exception as e:
        print(f"Chat Error: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# FULL SPEECH-TO-SPEECH ENDPOINT
# -------------------------
@app.route("/speech-to-speech", methods=["POST"])
def speech_to_speech():
    """
    Complete speech-to-speech pipeline:
    Audio → STT → LLM → TTS → Audio
    
    Send audio file or base64 encoded audio
    Returns audio response as base64
    """
    if not deepgram_client or not openai_client:
        return jsonify({"error": "Services not fully configured"}), 500
    
    try:
        # Step 1: Speech to Text
        if 'audio' in request.files:
            audio_file = request.files['audio']
            audio_data = audio_file.read()
        elif request.is_json:
            data = request.get_json()
            audio_base64 = data.get("audio")
            audio_data = base64.b64decode(audio_base64)
        else:
            audio_data = request.data
        
        # Transcribe (v5 SDK - dict-based options)
        options = {
            "model": "nova-2",
            "language": "en-US",
            "smart_format": True,
            "punctuate": True,
        }
        
        payload = {"buffer": audio_data}
        stt_response = deepgram_client.listen.rest.v("1").transcribe_file(
            payload,
            options
        )
        
        transcript = ""
        if stt_response and stt_response.results and stt_response.results.channels:
            alternatives = stt_response.results.channels[0].alternatives
            if alternatives:
                transcript = alternatives[0].transcript
        
        if not transcript:
            return jsonify({"error": "Could not transcribe audio"}), 400
        
        # Step 2: Get LLM response
        messages = [
            {"role": "system", "content": "You are a helpful voice assistant. Keep responses concise and conversational."},
            {"role": "user", "content": transcript}
        ]
        
        llm_response = openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=200
        )
        
        ai_response = llm_response.choices[0].message.content
        
        # Step 3: Text to Speech (v5 SDK - dict-based options)
        speak_options = {
            "model": "aura-asteria-en",
            "encoding": "linear16",
            "sample_rate": 16000,
        }
        
        tts_payload = {"text": ai_response}
        tts_response = deepgram_client.speak.rest.v("1").stream(
            tts_payload,
            speak_options
        )
        
        audio_data = b""
        for chunk in tts_response.stream_memory:
            audio_data += chunk
        
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        return jsonify({
            "success": True,
            "transcript": transcript,
            "response": ai_response,
            "audio": audio_base64
        })
    
    except Exception as e:
        print(f"Speech-to-Speech Error: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# HEALTH CHECK
# -------------------------
@app.route("/", methods=["GET"])
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "services": {
            "deepgram": deepgram_client is not None,
            "openai": openai_client is not None
        },
        "endpoints": {
            "stt": "/stt",
            "tts": "/tts",
            "chat": "/chat",
            "speech_to_speech": "/speech-to-speech"
        }
    })


# -------------------------
# TEST ENDPOINT
# -------------------------
@app.route("/test", methods=["GET"])
def test():
    """Test TTS with sample text"""
    if not deepgram_client:
        return jsonify({"error": "Deepgram not configured"}), 500
    
    try:
        options = SpeakOptions(
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
        )
        
        response = deepgram_client.speak.rest.v("1").stream(
            {"text": "Hello! This is a test of the text to speech system."},
            options
        )
        
        audio_data = b""
        for chunk in response.stream_memory:
            audio_data += chunk
        
        return audio_data, 200, {'Content-Type': 'audio/wav'}
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------
# RUN APP
# -------------------------
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🎙️  Speech-to-Speech AI Server")
    print("="*50)
    print(f"Deepgram: {'✅' if deepgram_client else '❌'}")
    print(f"OpenAI: {'✅' if openai_client else '❌'}")
    print("\nEndpoints:")
    print("  POST /stt              - Speech to Text")
    print("  POST /tts              - Text to Speech")
    print("  POST /chat             - LLM Chat")
    print("  POST /speech-to-speech - Full pipeline")
    print("  GET  /test             - Test TTS")
    print("="*50 + "\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000)
