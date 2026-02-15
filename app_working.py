"""
Flask-based Speech-to-Speech AI with Deepgram STT/TTS and OpenAI
"""
import json
import os
import uuid
import base64
import struct
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
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
# ASSISTANT STORAGE HELPERS
# -------------------------
ASSISTANTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assistants_db.json")

def _load_assistants():
    """Load assistants from JSON file."""
    try:
        with open(ASSISTANTS_FILE, "r") as f:
            data = json.load(f)
            return data.get("assistants", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _save_assistants(assistants):
    """Save assistants to JSON file."""
    with open(ASSISTANTS_FILE, "w") as f:
        json.dump({"assistants": assistants}, f, indent=2)

def _find_assistant(assistant_id):
    """Find an assistant by ID."""
    assistants = _load_assistants()
    for a in assistants:
        if a["id"] == assistant_id:
            return a
    return None


# -------------------------
# SERVE STATIC FILES
# -------------------------
@app.route("/dashboard")
def serve_dashboard():
    """Serve the assistant management dashboard."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")

@app.route("/voicesdk.js")
def serve_voicesdk():
    """Serve VoiceSDK."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "voicesdk.js")

@app.route("/a/<assistant_id>")
def serve_assistant_page(assistant_id):
    """Serve a standalone chat page for a published assistant."""
    assistant = _find_assistant(assistant_id)
    if not assistant:
        return jsonify({"error": "Assistant not found"}), 404
    if not assistant.get("published"):
        return jsonify({"error": "Assistant is not published"}), 403
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "assistant_chat.html")

@app.route("/api/assistant/<assistant_id>/config")
def get_assistant_config(assistant_id):
    """Get published assistant config for the chat page."""
    assistant = _find_assistant(assistant_id)
    if not assistant:
        return jsonify({"error": "Assistant not found"}), 404
    if not assistant.get("published"):
        return jsonify({"error": "Assistant is not published"}), 403
    return jsonify({
        "id": assistant["id"],
        "name": assistant["name"],
        "first_message": assistant.get("first_message", ""),
        "system_prompt": assistant.get("system_prompt", ""),
        "openai_model": assistant.get("openai_model", "gpt-4o-mini"),
        "tts_model": assistant.get("tts_model", "aura-asteria-en"),
        "stt_model": assistant.get("stt_model", "nova-2"),
        "temperature": assistant.get("temperature", 0.7),
        "max_tokens": assistant.get("max_tokens", 200),
    })


# -------------------------
# ASSISTANT CRUD ENDPOINTS
# -------------------------
@app.route("/api/assistants", methods=["GET"])
def list_assistants():
    """List all assistants."""
    assistants = _load_assistants()
    return jsonify({"assistants": assistants})

@app.route("/api/assistants", methods=["POST"])
def create_assistant():
    """Create a new assistant."""
    data = request.get_json() or {}
    assistant = {
        "id": str(uuid.uuid4())[:8] + "-" + str(uuid.uuid4())[:4] + "-" + str(uuid.uuid4())[:4] + "-" + str(uuid.uuid4())[:12],
        "name": data.get("name", "New Assistant"),
        "openai_model": data.get("openai_model", "gpt-4o-mini"),
        "stt_model": data.get("stt_model", "nova-2"),
        "tts_model": data.get("tts_model", "aura-asteria-en"),
        "first_message": data.get("first_message", "Hello! How can I help you today?"),
        "system_prompt": data.get("system_prompt", "You are a helpful voice assistant. Keep responses concise and conversational. Use short sentences suitable for speech."),
        "temperature": data.get("temperature", 0.7),
        "max_tokens": data.get("max_tokens", 200),
        "published": False,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    assistants = _load_assistants()
    assistants.append(assistant)
    _save_assistants(assistants)
    return jsonify(assistant), 201

@app.route("/api/assistants/<assistant_id>", methods=["GET"])
def get_assistant(assistant_id):
    """Get a single assistant by ID."""
    assistant = _find_assistant(assistant_id)
    if not assistant:
        return jsonify({"error": "Assistant not found"}), 404
    return jsonify(assistant)

@app.route("/api/assistants/<assistant_id>", methods=["PUT"])
def update_assistant(assistant_id):
    """Update an assistant."""
    assistants = _load_assistants()
    for i, a in enumerate(assistants):
        if a["id"] == assistant_id:
            data = request.get_json() or {}
            for key in ["name", "openai_model", "stt_model", "tts_model", "first_message", "system_prompt", "temperature", "max_tokens"]:
                if key in data:
                    assistants[i][key] = data[key]
            assistants[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_assistants(assistants)
            return jsonify(assistants[i])
    return jsonify({"error": "Assistant not found"}), 404

@app.route("/api/assistants/<assistant_id>", methods=["DELETE"])
def delete_assistant(assistant_id):
    """Delete an assistant."""
    assistants = _load_assistants()
    new_list = [a for a in assistants if a["id"] != assistant_id]
    if len(new_list) == len(assistants):
        return jsonify({"error": "Assistant not found"}), 404
    _save_assistants(new_list)
    return jsonify({"status": "deleted"})

@app.route("/api/assistants/<assistant_id>/publish", methods=["POST"])
def publish_assistant(assistant_id):
    """Publish an assistant - makes it accessible via unique URL."""
    assistants = _load_assistants()
    for i, a in enumerate(assistants):
        if a["id"] == assistant_id:
            assistants[i]["published"] = True
            assistants[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_assistants(assistants)
            base_url = request.host_url.rstrip("/")
            return jsonify({
                **assistants[i],
                "public_url": f"{base_url}/a/{assistant_id}"
            })
    return jsonify({"error": "Assistant not found"}), 404

@app.route("/api/assistants/<assistant_id>/unpublish", methods=["POST"])
def unpublish_assistant(assistant_id):
    """Unpublish an assistant."""
    assistants = _load_assistants()
    for i, a in enumerate(assistants):
        if a["id"] == assistant_id:
            assistants[i]["published"] = False
            assistants[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_assistants(assistants)
            return jsonify(assistants[i])
    return jsonify({"error": "Assistant not found"}), 404


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
        stt_model = "nova-2"
        
        # Check for assistant-specific STT model
        assistant_id = None
        if request.form:
            assistant_id = request.form.get("assistant_id")
        elif request.is_json:
            try:
                assistant_id = request.get_json().get("assistant_id")
            except Exception:
                pass
        if assistant_id:
            assistant = _find_assistant(assistant_id)
            if assistant:
                stt_model = assistant.get("stt_model", stt_model)
        
        options = {
            "model": stt_model,
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
        
        # Check if using an assistant's settings
        assistant_id = data.get("assistant_id")
        if assistant_id:
            assistant = _find_assistant(assistant_id)
            if assistant:
                model = assistant.get("tts_model", model)
        
        encoding = data.get("encoding", "linear16")
        
        options = {
            "model": model,
            "encoding": encoding,
            "sample_rate": 16000,
        }
        
        # Generate speech (v5.3.2 SDK)
        audio_iter = deepgram_client.speak.v1.audio.generate(
            text=text,
            model=options["model"],
            encoding=options["encoding"],
            sample_rate=options["sample_rate"],
        )
        
        # Get audio data
        audio_data = b""
        for chunk in audio_iter:
            audio_data += chunk
        
        print(f"[TTS] Generated {len(audio_data)} bytes of audio")
        
        # Ensure proper WAV header with correct sizes (Deepgram sends placeholder sizes)
        if encoding == "linear16":
            sample_rate = 16000
            num_channels = 1
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            
            pcm_data = audio_data
            if audio_data[:4] == b'RIFF':
                data_pos = audio_data.find(b'data')
                if data_pos != -1:
                    pcm_data = audio_data[data_pos + 8:]
            
            data_size = len(pcm_data)
            wav_header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE',
                b'fmt ', 16, 1, num_channels, sample_rate, byte_rate, block_align, bits_per_sample,
                b'data', data_size
            )
            audio_data = wav_header + pcm_data
        
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
    Supports assistant_id to use assistant-specific settings.
    """
    if not openai_client:
        return jsonify({"error": "OpenAI not configured"}), 500
    
    try:
        data = request.get_json()
        messages = data.get("messages", [])
        
        if not messages:
            return jsonify({"error": "Missing 'messages' field"}), 400
        
        # Check if using an assistant's settings
        assistant_id = data.get("assistant_id")
        if assistant_id:
            assistant = _find_assistant(assistant_id)
            if assistant:
                model = assistant.get("openai_model", DEFAULT_MODEL)
                temperature = data.get("temperature", assistant.get("temperature", 0.7))
                max_tokens = data.get("max_tokens", assistant.get("max_tokens", 200))
            else:
                model = data.get("model", DEFAULT_MODEL)
                temperature = data.get("temperature", 0.7)
                max_tokens = data.get("max_tokens", 500)
        else:
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
        
        tts_audio_iter = deepgram_client.speak.v1.audio.generate(
            text=ai_response,
            model=speak_options["model"],
            encoding=speak_options["encoding"],
            sample_rate=speak_options["sample_rate"],
        )
        
        audio_data = b""
        for chunk in tts_audio_iter:
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
        audio_iter = deepgram_client.speak.v1.audio.generate(
            text="Hello! This is a test of the text to speech system.",
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
        )
        
        audio_data = b""
        for chunk in audio_iter:
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
