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

import threading
import warnings
import urllib.request
import urllib.error
warnings.filterwarnings("ignore", category=DeprecationWarning, module="audioop")
import audioop

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

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("⚠️  Twilio not installed. Run: pip install twilio")

try:
    from flask_sock import Sock
    FLASK_SOCK_AVAILABLE = True
except ImportError:
    FLASK_SOCK_AVAILABLE = False
    print("⚠️  flask-sock not installed. Run: pip install flask-sock")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize WebSocket support
sock = None
if FLASK_SOCK_AVAILABLE:
    sock = Sock(app)

# Load environment variables
load_dotenv()

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "6985219805a7076276962e72ee835d9bd9961747")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")  # Custom endpoint (Azure, GitHub Models, etc.)
DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "AC8c8a633943c4c317e824100d5219edc7")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "0de71e45e303e30539ecfe4b18eb1c5a")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+19086330783")  # Your Twilio number e.g. +1234567890

# Public URL — REQUIRED for Twilio to reach your local server
# Set this to your ngrok URL, e.g. https://abc123.ngrok-free.app
# Or it will be auto-detected from ngrok's local API
SERVER_PUBLIC_URL = os.getenv("SERVER_PUBLIC_URL", "").rstrip("/")

def _detect_ngrok_url():
    """Try to auto-detect ngrok tunnel URL from ngrok's local API."""
    try:
        req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"].rstrip("/")
            # Fallback: return any tunnel
            if tunnels:
                return tunnels[0]["public_url"].rstrip("/")
    except Exception:
        pass
    return None

def get_public_url():
    """Return the public base URL for Twilio callbacks.
    Priority: SERVER_PUBLIC_URL env var > ngrok auto-detect > None"""
    global SERVER_PUBLIC_URL
    if SERVER_PUBLIC_URL:
        return SERVER_PUBLIC_URL
    # Try ngrok auto-detect
    ngrok_url = _detect_ngrok_url()
    if ngrok_url:
        SERVER_PUBLIC_URL = ngrok_url
        print(f"🔗 Auto-detected ngrok URL: {ngrok_url}")
        return ngrok_url
    return None

# Initialize Twilio client
twilio_client = None
if TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("✅ Twilio initialized")
    except Exception as e:
        print(f"❌ Twilio initialization failed: {e}")
else:
    if not TWILIO_AVAILABLE:
        print("⚠️  Twilio SDK not installed")
    else:
        print("⚠️  Twilio credentials not configured")

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
    if OPENAI_BASE_URL:
        openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        print(f"✅ OpenAI initialized with custom endpoint: {OPENAI_BASE_URL}")
    else:
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
# OUTBOUND CALL STORAGE
# -------------------------
CALL_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "call_log.json")

def _load_call_log():
    """Load call log from JSON file."""
    try:
        with open(CALL_LOG_FILE, "r") as f:
            data = json.load(f)
            return data.get("calls", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _save_call_log(calls):
    """Save call log to JSON file."""
    with open(CALL_LOG_FILE, "w") as f:
        json.dump({"calls": calls}, f, indent=2)


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
        
        # Send to Deepgram (v5 SDK)
        response = deepgram_client.listen.v1.media.transcribe_file(
            request=audio_data,
            model=stt_model,
            language="en-US",
            smart_format=True,
            punctuate=True,
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
        
        # Transcribe (v5 SDK)
        stt_response = deepgram_client.listen.v1.media.transcribe_file(
            request=audio_data,
            model="nova-2",
            language="en-US",
            smart_format=True,
            punctuate=True,
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
# OUTBOUND CALL ENDPOINTS
# -------------------------

# In-memory store for active call sessions (call_sid -> session data)
active_call_sessions = {}


@app.route("/api/outbound-call", methods=["POST"])
def outbound_call():
    """
    Make an outbound call using Twilio + your own real-time voice agent.
    Twilio dials the number, then streams audio to our WebSocket where
    Deepgram STT → OpenAI LLM → Deepgram TTS handles the conversation.
    
    Request body (JSON):
    {
        "phone_number": "+919876543210",
        "customer_name": "John" (optional),
        "assistant_id": "..." (optional — picks system_prompt, model, voice from your assistant),
        "system_prompt": "..." (optional — override),
        "greeting": "Hello! How can I help you?" (optional),
        "from_number": "+1234567890" (optional, overrides default Twilio number)
    }
    """
    if not TWILIO_AVAILABLE:
        return jsonify({"error": "Twilio SDK not installed. Run: pip install twilio"}), 500
    
    if not twilio_client:
        return jsonify({"error": "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in .env"}), 500
    
    if not FLASK_SOCK_AVAILABLE:
        return jsonify({"error": "flask-sock not installed. Run: pip install flask-sock"}), 500
    
    try:
        data = request.get_json() or {}
        phone_number = data.get("phone_number", "").strip()
        
        if not phone_number:
            return jsonify({"error": "Missing 'phone_number' field"}), 400
        
        # Normalize phone number
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number
        
        from_number = data.get("from_number", TWILIO_PHONE_NUMBER)
        if not from_number:
            return jsonify({"error": "No Twilio phone number configured. Set TWILIO_PHONE_NUMBER in .env or pass 'from_number'"}), 400
        
        customer_name = data.get("customer_name", "Customer")
        
        # Resolve assistant settings
        assistant_id = data.get("assistant_id")
        system_prompt = data.get("system_prompt", "You are a helpful voice assistant. Keep responses concise and conversational. Use short sentences suitable for speech.")
        greeting = data.get("greeting", f"Hello {customer_name}! How can I help you today?")
        openai_model = DEFAULT_MODEL
        tts_model = "aura-asteria-en"
        temperature = 0.7
        max_tokens = 200
        
        if assistant_id:
            assistant = _find_assistant(assistant_id)
            if assistant:
                system_prompt = assistant.get("system_prompt", system_prompt)
                greeting = data.get("greeting") or assistant.get("first_message", greeting)
                openai_model = assistant.get("openai_model", openai_model)
                tts_model = assistant.get("tts_model", tts_model)
                temperature = assistant.get("temperature", temperature)
                max_tokens = assistant.get("max_tokens", max_tokens)
        
        # Generate a unique session ID for this call
        session_id = str(uuid.uuid4())[:12]
        
        # Store session config so the WebSocket handler can access it
        active_call_sessions[session_id] = {
            "phone_number": phone_number,
            "customer_name": customer_name,
            "assistant_id": assistant_id,
            "system_prompt": system_prompt,
            "greeting": greeting,
            "openai_model": openai_model,
            "tts_model": tts_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "conversation": [],
            "status": "initiating",
        }
        
        # Build the TwiML URL — Twilio will call this when the person answers
        # IMPORTANT: Twilio needs a publicly accessible URL. localhost won't work!
        public_url = get_public_url()
        if not public_url:
            return jsonify({
                "error": "No public URL configured. Twilio cannot reach localhost. "
                         "Start ngrok with: ngrok http 5000  — then either set SERVER_PUBLIC_URL in .env "
                         "or the ngrok URL will be auto-detected."
            }), 400
        
        base_url = public_url
        twiml_url = f"{base_url}/api/outbound-call/twiml/{session_id}"
        
        print(f"[Outbound Call] Using public URL: {base_url}")
        print(f"[Outbound Call] TwiML URL: {twiml_url}")
        
        # Place the call via Twilio
        call = twilio_client.calls.create(
            to=phone_number,
            from_=from_number,
            url=twiml_url,
            status_callback=f"{base_url}/api/outbound-call/status-callback/{session_id}",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        
        # Update session with Twilio SID
        active_call_sessions[session_id]["twilio_sid"] = call.sid
        active_call_sessions[session_id]["status"] = call.status
        
        # Log the call
        call_record = {
            "id": session_id,
            "provider": "voice-agent",
            "phone_number": phone_number,
            "customer_name": customer_name,
            "assistant_id": assistant_id,
            "from_number": from_number,
            "twilio_sid": call.sid,
            "status": call.status,
            "created_at": datetime.utcnow().isoformat()
        }
        calls = _load_call_log()
        calls.insert(0, call_record)
        _save_call_log(calls)
        
        return jsonify({
            "success": True,
            "message": f"Call initiated to {phone_number} with your AI voice agent",
            "call_id": session_id,
            "twilio_sid": call.sid,
            "status": call.status
        })
    
    except Exception as e:
        print(f"Outbound Call Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/outbound-call/twiml/<session_id>", methods=["POST", "GET"])
def outbound_call_twiml(session_id):
    """
    TwiML endpoint — Twilio calls this when the outbound call is answered.
    Returns TwiML that tells Twilio to:
    1. Optionally <Say> a greeting
    2. Open a bi-directional <Stream> WebSocket to our server
    """
    try:
        session = active_call_sessions.get(session_id)
        
        # Build the WebSocket URL using the public URL
        public_url = get_public_url()
        if public_url:
            # Convert https://xxx.ngrok-free.app → wss://xxx.ngrok-free.app
            ws_url = public_url.replace("https://", "wss://").replace("http://", "ws://")
            stream_url = f"{ws_url}/api/outbound-call/media-stream/{session_id}"
        else:
            # Fallback (won't work for Twilio from cloud, but useful for local testing)
            ws_scheme = "wss" if request.is_secure else "ws"
            ws_host = request.host
            stream_url = f"{ws_scheme}://{ws_host}/api/outbound-call/media-stream/{session_id}"
        
        print(f"[TwiML {session_id}] Stream URL: {stream_url}")
        
        greeting = ""
        if session and session.get("greeting"):
            # Escape XML special characters in greeting
            g = session["greeting"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            greeting = f'<Say voice="Polly.Joanna">{g}</Say>'
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {greeting}
    <Connect>
        <Stream url="{stream_url}">
            <Parameter name="session_id" value="{session_id}"/>
        </Stream>
    </Connect>
</Response>"""
        
        print(f"[TwiML {session_id}] Returning TwiML:\n{twiml}")
        return twiml, 200, {"Content-Type": "application/xml"}
    
    except Exception as e:
        print(f"[TwiML {session_id}] ERROR generating TwiML: {e}")
        # Return a valid TwiML with error message so user hears something useful
        error_twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, there was a server error setting up the voice agent. Please try again later.</Say>
</Response>"""
        return error_twiml, 200, {"Content-Type": "application/xml"}


@app.route("/api/outbound-call/status-callback/<session_id>", methods=["POST"])
def outbound_call_status_callback(session_id):
    """
    Twilio status callback — receives call status updates.
    Updates the call log and active session.
    """
    call_status = request.form.get("CallStatus", "unknown")
    call_sid = request.form.get("CallSid", "")
    call_duration = request.form.get("CallDuration", "0")
    
    print(f"[Call {session_id}] Status: {call_status} (SID: {call_sid})")
    
    # Update active session
    if session_id in active_call_sessions:
        active_call_sessions[session_id]["status"] = call_status
        if call_status in ("completed", "busy", "no-answer", "canceled", "failed"):
            active_call_sessions[session_id]["ended_at"] = datetime.utcnow().isoformat()
    
    # Update call log
    calls = _load_call_log()
    for c in calls:
        if c["id"] == session_id:
            c["status"] = call_status
            if call_duration:
                c["duration"] = call_duration
            break
    _save_call_log(calls)
    
    return "", 204


# -------------------------
# TWILIO MEDIA STREAM WEBSOCKET — REAL-TIME VOICE AGENT
# -------------------------

def _process_voice_agent_stream(ws, session_id):
    """
    Handle a Twilio Media Stream WebSocket connection.
      Twilio audio → Deepgram STT → OpenAI LLM → Deepgram TTS → Twilio audio

    Barge-in: if the human speaks while the AI is talking, the AI stops immediately.

    Thread-safety: ws.send() and ws.receive() are ONLY called from this main thread.
    The utterance thread communicates via a send_queue and threading.Events.
    """
    import queue as _queue

    session = active_call_sessions.get(session_id, {})
    system_prompt = session.get("system_prompt", "You are a helpful voice assistant.")
    openai_model  = session.get("openai_model", DEFAULT_MODEL)
    tts_model     = session.get("tts_model", "aura-asteria-en")
    temperature   = session.get("temperature", 0.7)
    max_tokens    = session.get("max_tokens", 200)

    conversation_history = [{"role": "system", "content": system_prompt}]

    stream_sid_ref   = [None]   # mutable ref so threads always see current value
    send_queue       = _queue.Queue()   # utterance thread puts WS messages here
    ai_speaking      = threading.Event()  # set while AI audio is being queued
    stop_ai          = threading.Event()  # set to abort current utterance
    utterance_thread = [None]

    MULAW_SAMPLE_RATE  = 8000
    SILENCE_THRESHOLD  = 500
    SILENCE_FRAMES_NEEDED = int(MULAW_SAMPLE_RATE * 1.2)  # ~1.2 s

    audio_buffer  = b""
    is_speaking   = False
    silence_frames = 0

    # ── helpers ──────────────────────────────────────────────────────────────

    def _flush_send_queue():
        """Drain any queued outgoing messages — called from main thread only."""
        try:
            while True:
                ws.send(send_queue.get_nowait())
        except _queue.Empty:
            pass

    def _do_barge_in():
        """
        Called from the main thread when user speech arrives while AI is speaking.
        Stops the utterance thread, discards queued audio, and sends Twilio 'clear'.
        """
        nonlocal audio_buffer, is_speaking, silence_frames
        if not ai_speaking.is_set():
            return

        print(f"[Voice Agent {session_id}] ⚡ Barge-in — stopping AI")
        stop_ai.set()

        # Wait briefly for thread to see stop_ai (it checks it between every chunk)
        if utterance_thread[0] and utterance_thread[0].is_alive():
            utterance_thread[0].join(timeout=0.8)

        # Discard all stale audio the thread may have queued
        try:
            while True:
                send_queue.get_nowait()
        except _queue.Empty:
            pass

        # Tell Twilio to flush its own playback buffer
        try:
            ws.send(json.dumps({"event": "clear", "streamSid": stream_sid_ref[0]}))
        except Exception:
            pass

        ai_speaking.clear()
        stop_ai.clear()
        audio_buffer  = b""
        is_speaking   = False
        silence_frames = 0

    def _dispatch_utterance(buf):
        """Interrupt any ongoing AI response, then start processing the new utterance."""
        _do_barge_in()
        stop_ai.clear()
        t = threading.Thread(
            target=_handle_utterance,
            args=(send_queue, stream_sid_ref, session_id, buf,
                  conversation_history, openai_model, tts_model,
                  temperature, max_tokens, ai_speaking, stop_ai),
            daemon=True
        )
        utterance_thread[0] = t
        t.start()

    # ── main receive loop ─────────────────────────────────────────────────────
    print(f"[Voice Agent {session_id}] WebSocket connected")

    try:
        while True:
            # Drain any AI audio the utterance thread has produced — this is the
            # ONLY place ws.send() is called, keeping ws access single-threaded.
            _flush_send_queue()

            message = ws.receive()
            if message is None:
                break

            try:
                data = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                continue

            event = data.get("event")

            if event == "connected":
                print(f"[Voice Agent {session_id}] Twilio stream connected")

            elif event == "start":
                stream_sid_ref[0] = data.get("start", {}).get("streamSid")
                print(f"[Voice Agent {session_id}] Stream started: {stream_sid_ref[0]}")

            elif event == "media":
                payload = data.get("media", {}).get("payload", "")
                if not payload:
                    continue

                audio_chunk = base64.b64decode(payload)

                try:
                    pcm_chunk = audioop.ulaw2lin(audio_chunk, 2)
                    rms = audioop.rms(pcm_chunk, 2)
                except Exception:
                    rms = 0

                if rms > SILENCE_THRESHOLD:
                    # ── human is speaking ──────────────────────────────────
                    if ai_speaking.is_set():
                        # Barge-in: interrupt AI immediately (from main thread)
                        _do_barge_in()

                    is_speaking   = True
                    silence_frames = 0
                    audio_buffer  += audio_chunk

                elif is_speaking:
                    # trailing silence after speech
                    silence_frames += len(audio_chunk)
                    audio_buffer   += audio_chunk

                    if silence_frames >= SILENCE_FRAMES_NEEDED and len(audio_buffer) > MULAW_SAMPLE_RATE:
                        _dispatch_utterance(audio_buffer)
                        audio_buffer   = b""
                        is_speaking    = False
                        silence_frames = 0

                else:
                    # pure background silence
                    if len(audio_buffer) > 0:
                        silence_frames += len(audio_chunk)
                        audio_buffer   += audio_chunk
                        if silence_frames >= SILENCE_FRAMES_NEEDED and len(audio_buffer) > MULAW_SAMPLE_RATE:
                            _dispatch_utterance(audio_buffer)
                            audio_buffer   = b""
                            silence_frames = 0

            elif event == "stop":
                print(f"[Voice Agent {session_id}] Stream stopped")
                if len(audio_buffer) > MULAW_SAMPLE_RATE:
                    _dispatch_utterance(audio_buffer)
                break

    except Exception as e:
        print(f"[Voice Agent {session_id}] WebSocket error: {e}")
    finally:
        stop_ai.set()
        print(f"[Voice Agent {session_id}] WebSocket disconnected")
        def _cleanup():
            import time; time.sleep(60)
            active_call_sessions.pop(session_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()


def _handle_utterance(send_queue, stream_sid_ref, session_id, audio_buffer,
                      conversation_history, openai_model, tts_model,
                      temperature, max_tokens, ai_speaking, stop_ai):
    """
    Runs in a background thread. Processes one user utterance:
      mulaw → WAV → Deepgram STT → OpenAI LLM → Deepgram TTS → mulaw

    All outgoing WebSocket messages are placed into send_queue; the main
    thread is the only one that actually calls ws.send().
    """
    if not deepgram_client or not openai_client:
        print(f"[Voice Agent {session_id}] Services not available")
        return

    stream_sid = stream_sid_ref[0]

    def _q(msg):
        """Queue a message for the main thread to send — never blocks long."""
        if not stop_ai.is_set():
            send_queue.put(msg)

    try:
        # ── Step 1: mulaw → WAV ──────────────────────────────────────────────
        pcm_data     = audioop.ulaw2lin(audio_buffer, 2)
        pcm_data_16k = audioop.ratecv(pcm_data, 2, 1, 8000, 16000, None)[0]

        sr, ch, bps  = 16000, 1, 16
        data_size    = len(pcm_data_16k)
        wav_header   = struct.pack('<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36 + data_size, b'WAVE',
            b'fmt ', 16, 1, ch, sr, sr * ch * bps // 8,
            ch * bps // 8, bps, b'data', data_size
        )
        wav_data = wav_header + pcm_data_16k

        # ── Step 2: STT ──────────────────────────────────────────────────────
        stt_resp = deepgram_client.listen.v1.media.transcribe_file(
            request=wav_data,
            model="nova-2",
            language="en-US",
            smart_format=True,
            punctuate=True,
        )

        transcript = ""
        if stt_resp and stt_resp.results and stt_resp.results.channels:
            alts = stt_resp.results.channels[0].alternatives
            if alts:
                transcript = alts[0].transcript

        if not transcript or not transcript.strip():
            print(f"[Voice Agent {session_id}] Empty transcript, skipping")
            return

        print(f"[Voice Agent {session_id}] 👤 User: {transcript}")

        if stop_ai.is_set():
            return

        # ── Step 3: LLM ──────────────────────────────────────────────────────
        conversation_history.append({"role": "user", "content": transcript})

        llm_resp = openai_client.chat.completions.create(
            model=openai_model,
            messages=conversation_history,
            temperature=temperature,
            max_tokens=max_tokens
        )

        ai_response = llm_resp.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": ai_response})
        print(f"[Voice Agent {session_id}] 🤖 AI: {ai_response}")

        if session_id in active_call_sessions:
            active_call_sessions[session_id]["conversation"].append({
                "user": transcript, "ai": ai_response,
                "timestamp": datetime.utcnow().isoformat()
            })

        if stop_ai.is_set():
            print(f"[Voice Agent {session_id}] Barge-in before TTS — skipping")
            return

        # ── Step 4: TTS ──────────────────────────────────────────────────────
        tts_raw = b""
        for chunk in deepgram_client.speak.v1.audio.generate(
            text=ai_response, model=tts_model,
            encoding="linear16", sample_rate=8000,
        ):
            tts_raw += chunk

        pcm_tts = tts_raw
        if tts_raw[:4] == b'RIFF':
            dp = tts_raw.find(b'data')
            if dp != -1:
                pcm_tts = tts_raw[dp + 8:]

        tts_mulaw = audioop.lin2ulaw(pcm_tts, 2)
        print(f"[Voice Agent {session_id}] TTS {len(tts_mulaw)} bytes — queuing")

        # ── Step 5: Queue audio chunks for main thread to send ────────────────
        ai_speaking.set()
        CHUNK = 640   # ~40 ms at 8 kHz
        try:
            for i in range(0, len(tts_mulaw), CHUNK):
                if stop_ai.is_set():
                    print(f"[Voice Agent {session_id}] ⚡ Barge-in mid-queue — stopping")
                    break
                _q(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": base64.b64encode(tts_mulaw[i:i + CHUNK]).decode()}
                }))

            if not stop_ai.is_set():
                _q(json.dumps({
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": f"resp_{len(conversation_history)}"}
                }))
        finally:
            ai_speaking.clear()

    except Exception as e:
        import traceback
        print(f"[Voice Agent {session_id}] Utterance error: {e}")
        traceback.print_exc()
        ai_speaking.clear()
        if not stop_ai.is_set():
            try:
                err_raw = b""
                for chunk in deepgram_client.speak.v1.audio.generate(
                    text="Sorry, I had trouble with that. Could you repeat?",
                    model="aura-asteria-en", encoding="linear16", sample_rate=8000,
                ):
                    err_raw += chunk
                if err_raw[:4] == b'RIFF':
                    dp = err_raw.find(b'data')
                    if dp != -1: err_raw = err_raw[dp + 8:]
                err_mu = audioop.lin2ulaw(err_raw, 2)
                for i in range(0, len(err_mu), 640):
                    if stop_ai.is_set(): break
                    send_queue.put(json.dumps({
                        "event": "media", "streamSid": stream_sid,
                        "media": {"payload": base64.b64encode(err_mu[i:i + 640]).decode()}
                    }))
            except Exception as fe:
                print(f"[Voice Agent {session_id}] Fallback TTS error: {fe}")


# Register WebSocket route for Twilio Media Stream
if sock:
    @sock.route("/api/outbound-call/media-stream/<session_id>")
    def media_stream_ws(ws, session_id):
        """WebSocket endpoint for Twilio Media Streams."""
        _process_voice_agent_stream(ws, session_id)


@app.route("/api/outbound-call/status/<call_sid>", methods=["GET"])
def twilio_call_status(call_sid):
    """Get the status of a Twilio call by SID."""
    if not twilio_client:
        return jsonify({"error": "Twilio not configured"}), 500
    try:
        call = twilio_client.calls(call_sid).fetch()
        return jsonify({
            "sid": call.sid,
            "status": call.status,
            "direction": call.direction,
            "duration": call.duration,
            "from": call.from_formatted,
            "to": call.to_formatted,
            "start_time": str(call.start_time) if call.start_time else None,
            "end_time": str(call.end_time) if call.end_time else None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/outbound-call/session/<session_id>", methods=["GET"])
def get_call_session(session_id):
    """Get the live conversation log of an active call session."""
    session = active_call_sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found or expired"}), 404
    return jsonify({
        "session_id": session_id,
        "status": session.get("status", "unknown"),
        "phone_number": session.get("phone_number"),
        "customer_name": session.get("customer_name"),
        "conversation": session.get("conversation", []),
    })


@app.route("/api/call-log", methods=["GET"])
def get_call_log():
    """Get the outbound call history."""
    calls = _load_call_log()
    return jsonify({"calls": calls})


@app.route("/api/call-config", methods=["GET"])
def get_call_config():
    """Get current outbound call configuration status."""
    public_url = get_public_url()
    return jsonify({
        "twilio": {
            "configured": twilio_client is not None,
            "sdk_installed": TWILIO_AVAILABLE,
            "phone_number": TWILIO_PHONE_NUMBER if TWILIO_PHONE_NUMBER else None,
        },
        "deepgram": {
            "configured": deepgram_client is not None,
        },
        "openai": {
            "configured": openai_client is not None,
        },
        "websocket": {
            "available": FLASK_SOCK_AVAILABLE and sock is not None,
        },
        "public_url": {
            "configured": public_url is not None,
            "url": public_url,
        },
        "assistants": [{"id": a["id"], "name": a["name"]} for a in _load_assistants()]
    })


@app.route("/api/set-public-url", methods=["POST"])
def set_public_url():
    """Set the public URL for Twilio callbacks (e.g. ngrok URL)."""
    global SERVER_PUBLIC_URL
    data = request.get_json() or {}
    url = data.get("url", "").strip().rstrip("/")
    if not url:
        return jsonify({"error": "Missing 'url' field"}), 400
    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify({"error": "URL must start with http:// or https://"}), 400
    SERVER_PUBLIC_URL = url
    print(f"🔗 Public URL set to: {url}")
    return jsonify({"success": True, "url": url})


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
            "openai": openai_client is not None,
            "twilio": twilio_client is not None,
            "websocket": FLASK_SOCK_AVAILABLE and sock is not None
        },
        "endpoints": {
            "stt": "/stt",
            "tts": "/tts",
            "chat": "/chat",
            "speech_to_speech": "/speech-to-speech",
            "outbound_call": "/api/outbound-call",
            "call_log": "/api/call-log",
            "call_config": "/api/call-config"
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
    print(f"Twilio: {'✅' if twilio_client else '❌'}")
    print(f"WebSocket: {'✅' if (FLASK_SOCK_AVAILABLE and sock) else '❌'}")
    
    # Check for public URL
    pub_url = get_public_url()
    if pub_url:
        print(f"Public URL: ✅ {pub_url}")
    else:
        print("Public URL: ❌ Not configured")
        print("  ⚠️  Outbound calls REQUIRE a public URL!")
        print("  Run:  ngrok http 5000")
        print("  Then set SERVER_PUBLIC_URL in .env or paste the URL in the dashboard")
    
    print("\nEndpoints:")
    print("  POST /stt              - Speech to Text")
    print("  POST /tts              - Text to Speech")
    print("  POST /chat             - LLM Chat")
    print("  POST /speech-to-speech - Full pipeline")
    print("  POST /api/outbound-call - Outbound Call")
    print("  GET  /test             - Test TTS")
    print("="*50 + "\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000)

