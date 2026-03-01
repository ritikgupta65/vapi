"""
Flask-based Speech-to-Speech AI with Deepgram STT/TTS and OpenAI
"""
import json
import os
import re
import uuid
import base64
import struct
import time as _time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

import threading
import traceback
import warnings
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings("ignore", category=DeprecationWarning, module="audioop")
# ...existing code...
try:
    import audioop  # Python <= 3.12 (built-in)
except ModuleNotFoundError:
    try:
        import audioop_lts as audioop  # Python 3.13+ (installed via pip)
    except ModuleNotFoundError:
        raise RuntimeError("audioop not available. Run: pip install audioop-lts")
# ...existing code...

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
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")  # Custom endpoint (Azure, GitHub Models, etc.)
DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")  # Your Twilio number e.g. +1234567890

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # anon/service key
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "call_logs")  # per-user table name

# Public URL — REQUIRED for Twilio to reach your local server
# Set this to your ngrok URL, e.g. https://abc123.ngrok-free.app
# Or it will be auto-detected from ngrok's local API
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SERVER_PUBLIC_URL = os.getenv("SERVER_PUBLIC_URL", "").rstrip("/")
# ...

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
# SUPABASE CLIENT (lightweight, httpx-based)
# -------------------------
import httpx as _httpx

class SupabaseLogger:
    """Lightweight Supabase REST client for call logging (no heavy SDK needed)."""
    def __init__(self, url, key, table):
        self.enabled = bool(url and key)
        self.base = url.rstrip("/") + "/rest/v1/" + table if url else ""
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        } if key else {}
        if self.enabled:
            print(f"✅ Supabase logging enabled → table '{table}'")
        else:
            print("ℹ️  Supabase not configured – call logs stored locally only")

    def insert(self, row):
        """Insert a call log row. Non-blocking (fire-and-forget in thread)."""
        if not self.enabled:
            return
        def _do():
            try:
                _httpx.post(self.base, json=row, headers=self.headers, timeout=10)
            except Exception as e:
                print(f"[Supabase] insert error: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def update(self, call_id, data):
        """Update a call log row by call_id. Non-blocking."""
        if not self.enabled:
            return
        def _do():
            try:
                url = self.base + "?call_id=eq." + call_id
                h = {**self.headers, "Prefer": "return=minimal"}
                _httpx.patch(url, json=data, headers=h, timeout=10)
            except Exception as e:
                print(f"[Supabase] update error: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def fetch_all(self, order="created_at.desc", limit=500):
        """Fetch all rows (synchronous)."""
        if not self.enabled:
            return None
        try:
            url = self.base + f"?order={order}&limit={limit}"
            r = _httpx.get(url, headers=self.headers, timeout=10)
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            print(f"[Supabase] fetch error: {e}")
            return None

supa_logger = SupabaseLogger(SUPABASE_URL, SUPABASE_KEY, SUPABASE_TABLE)


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
    resp = send_from_directory(os.path.dirname(os.path.abspath(__file__)), "voicesdk.js")
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route("/a/<assistant_id>")
def serve_assistant_page(assistant_id):
    """Serve a standalone chat page for a published assistant."""
    assistant = _find_assistant(assistant_id)
    if not assistant:
        return jsonify({"error": "Assistant not found"}), 404
    if not assistant.get("published"):
        return jsonify({"error": "Assistant is not published"}), 403
    resp = send_from_directory(os.path.dirname(os.path.abspath(__file__)), "assistant_chat.html")
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

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
        "max_tokens": assistant.get("max_tokens", 100),
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
        "stt_provider": data.get("stt_provider", "deepgram"),
        "stt_model": data.get("stt_model", "nova-2"),
        "tts_provider": data.get("tts_provider", "deepgram"),
        "tts_model": data.get("tts_model", "aura-asteria-en"),
        "first_message": data.get("first_message", "Hello! How can I help you today?"),
        "system_prompt": data.get("system_prompt", "You are a helpful voice assistant. Keep responses concise and conversational. Use short sentences suitable for speech."),
        "temperature": data.get("temperature", 0.7),
        "max_tokens": data.get("max_tokens", 100),
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
            for key in ["name", "openai_model", "stt_provider", "stt_model", "tts_provider", "tts_model", "first_message", "system_prompt", "temperature", "max_tokens"]:
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
# PROVIDER MODELS ENDPOINT
# -------------------------
PROVIDER_MODELS = {
    "deepgram": {
        "stt": [
            {"value": "nova-2", "label": "Nova-2 (Best quality)"},
            {"value": "nova-2-general", "label": "Nova-2 General"},
            {"value": "nova-2-meeting", "label": "Nova-2 Meeting"},
            {"value": "nova-2-phonecall", "label": "Nova-2 Phone Call"},
            {"value": "nova-2-conversationalai", "label": "Nova-2 Conversational AI"},
            {"value": "nova", "label": "Nova"},
            {"value": "enhanced", "label": "Enhanced"},
            {"value": "base", "label": "Base"},
        ],
        "tts": [
            {"value": "aura-asteria-en", "label": "Asteria (Female, US English)"},
            {"value": "aura-luna-en", "label": "Luna (Female, US English)"},
            {"value": "aura-stella-en", "label": "Stella (Female, US English)"},
            {"value": "aura-athena-en", "label": "Athena (Female, UK English)"},
            {"value": "aura-hera-en", "label": "Hera (Female, US English)"},
            {"value": "aura-orion-en", "label": "Orion (Male, US English)"},
            {"value": "aura-arcas-en", "label": "Arcas (Male, US English)"},
            {"value": "aura-perseus-en", "label": "Perseus (Male, US English)"},
            {"value": "aura-angus-en", "label": "Angus (Male, Irish English)"},
            {"value": "aura-orpheus-en", "label": "Orpheus (Male, US English)"},
            {"value": "aura-helios-en", "label": "Helios (Male, UK English)"},
            {"value": "aura-zeus-en", "label": "Zeus (Male, US English)"},
        ],
    },
    "sarvam": {
        "stt": [
            {"value": "saarika:v2", "label": "Saarika v2 (Latest, Multilingual)"},
            {"value": "saarika:v1", "label": "Saarika v1 (Stable)"},
        ],
        "tts": [
            {"value": "bulbul:v1", "label": "Bulbul v1 (Hindi, Female)"},
            {"value": "bulbul:v1-male", "label": "Bulbul v1 (Hindi, Male)"},
            {"value": "bulbul:v2", "label": "Bulbul v2 (Multilingual, Female)"},
        ],
    },
}

@app.route("/api/provider-models", methods=["GET"])
def get_provider_models():
    """Get available models for a given provider and type (stt/tts)."""
    provider = request.args.get("provider", "deepgram")
    model_type = request.args.get("type", "stt")
    models = PROVIDER_MODELS.get(provider, {}).get(model_type, [])
    return jsonify({"provider": provider, "type": model_type, "models": models})


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
# SENTENCE SPLITTER HELPER
# -------------------------
_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+')

def _split_sentences(text):
    """Split text into sentences at . ! ? boundaries."""
    parts = _SENTENCE_END_RE.split(text.strip())
    return [s.strip() for s in parts if s.strip()]


# -------------------------
# LLM CHAT ENDPOINT (non-streaming — kept for backward compat)
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
                max_tokens = data.get("max_tokens", assistant.get("max_tokens", 100))
            else:
                model = data.get("model", DEFAULT_MODEL)
                temperature = data.get("temperature", 0.7)
                max_tokens = data.get("max_tokens", 100)
        else:
            model = data.get("model", DEFAULT_MODEL)
            temperature = data.get("temperature", 0.7)
            max_tokens = data.get("max_tokens", 100)
        
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
# STREAMING LLM CHAT (SSE) — token-by-token
# -------------------------
@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    """
    Streaming chat with OpenAI LLM using SSE.
    Tokens arrive one-by-one for ultra-low perceived latency.

    SSE events:
      {"type": "token",    "text": "word "}
      {"type": "sentence", "text": "Full sentence.", "audio": "base64..."}
      {"type": "done",     "full_text": "..."}
    
    When tts=true (default), each completed sentence is immediately
    converted to TTS audio and streamed back alongside the text tokens.
    """
    from flask import Response, stream_with_context
    
    if not openai_client:
        return jsonify({"error": "OpenAI not configured"}), 500
    
    try:
        data = request.get_json()
        messages = data.get("messages", [])
        if not messages:
            return jsonify({"error": "Missing 'messages' field"}), 400
        
        tts_enabled = data.get("tts", True)
        
        # Resolve settings
        assistant_id = data.get("assistant_id")
        model = data.get("model", DEFAULT_MODEL)
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 100)
        tts_model = data.get("tts_model", "aura-asteria-en")
        
        if assistant_id:
            assistant = _find_assistant(assistant_id)
            if assistant:
                model = assistant.get("openai_model", model)
                temperature = assistant.get("temperature", temperature)
                max_tokens = assistant.get("max_tokens", max_tokens)
                tts_model = assistant.get("tts_model", tts_model)
        
        def generate():
            full_text = ""
            sentence_buffer = ""
            
            try:
                # Stream from OpenAI
                stream = openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True
                )
                
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta or not delta.content:
                        continue
                    
                    token = delta.content
                    full_text += token
                    sentence_buffer += token
                    
                    # Send token immediately for progressive display
                    yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
                    
                    # Check if we have a complete sentence
                    if re.search(r'[.!?]\s*$', sentence_buffer):
                        sentence = sentence_buffer.strip()
                        sentence_buffer = ""
                        
                        if sentence and tts_enabled and deepgram_client:
                            # Generate TTS for this sentence immediately
                            try:
                                tts_audio = b""
                                for audio_chunk in deepgram_client.speak.v1.audio.generate(
                                    text=sentence,
                                    model=tts_model,
                                    encoding="linear16",
                                    sample_rate=16000,
                                ):
                                    tts_audio += audio_chunk
                                
                                audio_b64 = base64.b64encode(tts_audio).decode('utf-8')
                                yield f"data: {json.dumps({'type': 'sentence_audio', 'text': sentence, 'audio': audio_b64})}\n\n"
                            except Exception as tts_err:
                                print(f"[Chat Stream] TTS error for sentence: {tts_err}")
                
                # Flush remaining buffer as final sentence
                if sentence_buffer.strip():
                    sentence = sentence_buffer.strip()
                    if tts_enabled and deepgram_client:
                        try:
                            tts_audio = b""
                            for audio_chunk in deepgram_client.speak.v1.audio.generate(
                                text=sentence,
                                model=tts_model,
                                encoding="linear16",
                                sample_rate=16000,
                            ):
                                tts_audio += audio_chunk
                            
                            audio_b64 = base64.b64encode(tts_audio).decode('utf-8')
                            yield f"data: {json.dumps({'type': 'sentence_audio', 'text': sentence, 'audio': audio_b64})}\n\n"
                        except Exception as tts_err:
                            print(f"[Chat Stream] TTS error for final sentence: {tts_err}")
                
                yield f"data: {json.dumps({'type': 'done', 'full_text': full_text})}\n\n"
                
            except Exception as e:
                print(f"Chat Stream Error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )
    
    except Exception as e:
        print(f"Chat Stream Error: {e}")
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
        
        # Get assistant settings if provided
        assistant_id = None
        stt_model = "nova-2"
        tts_model = "aura-asteria-en"
        llm_model = DEFAULT_MODEL
        system_prompt = "You are a helpful voice assistant. Keep responses concise and conversational."
        temperature = 0.7
        max_tokens_val = 100
        if request.is_json:
            req_data = request.get_json()
            assistant_id = req_data.get("assistant_id")
        if assistant_id:
            assistant = _find_assistant(assistant_id)
            if assistant:
                stt_model = assistant.get("stt_model", stt_model)
                tts_model = assistant.get("tts_model", tts_model)
                llm_model = assistant.get("openai_model", llm_model)
                system_prompt = assistant.get("system_prompt", system_prompt)
                temperature = assistant.get("temperature", temperature)
                max_tokens_val = assistant.get("max_tokens", max_tokens_val)
        
        # ── STT ──────────────────────────────────────────────────────
        stt_response = deepgram_client.listen.v1.media.transcribe_file(
            request=audio_data,
            model=stt_model,
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
        
        # ── PARALLEL: Send raw transcript to LLM immediately ────────
        #    (Part 1: transcript is available for display NOW while LLM processes)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript}
        ]
        
        llm_response = openai_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens_val
        )
        
        ai_response = llm_response.choices[0].message.content
        
        # ── PARALLEL: AI response is available for display NOW ──────
        #    Start TTS generation in background thread while we prepare the text response
        #    (Part 2: display text + generate audio simultaneously)
        tts_future = None
        with ThreadPoolExecutor(max_workers=1) as executor:
            def _generate_tts():
                tts_audio_iter = deepgram_client.speak.v1.audio.generate(
                    text=ai_response,
                    model=tts_model,
                    encoding="linear16",
                    sample_rate=16000,
                )
                audio = b""
                for chunk in tts_audio_iter:
                    audio += chunk
                return audio
            
            tts_future = executor.submit(_generate_tts)
            # TTS runs in background while we could do other processing
            audio_data = tts_future.result()  # wait for TTS to complete for response
        
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


@app.route("/speech-to-speech-stream", methods=["POST"])
def speech_to_speech_stream():
    """
    LOW-LATENCY speech-to-speech pipeline using Server-Sent Events (SSE).
    Returns partial results as they become available:
      1. {"type": "transcript", "text": "..."} — immediately after STT
      2. {"type": "response",   "text": "..."} — immediately after LLM (display + TTS start in parallel)
      3. {"type": "audio",      "audio": "base64..."} — when TTS completes
      4. {"type": "done"}
    
    This lets the client display user text and AI text BEFORE audio is ready.
    """
    from flask import Response, stream_with_context
    
    if not deepgram_client or not openai_client:
        return jsonify({"error": "Services not fully configured"}), 500
    
    # Parse audio from request
    audio_data = None
    assistant_id = None
    if 'audio' in request.files:
        audio_data = request.files['audio'].read()
        assistant_id = request.form.get("assistant_id")
    elif request.is_json:
        data = request.get_json()
        audio_data = base64.b64decode(data.get("audio", ""))
        assistant_id = data.get("assistant_id")
    else:
        audio_data = request.data
    
    if not audio_data:
        return jsonify({"error": "No audio data provided"}), 400
    
    # Resolve assistant settings
    stt_model = "nova-2"
    tts_model = "aura-asteria-en"
    llm_model = DEFAULT_MODEL
    system_prompt = "You are a helpful voice assistant. Keep responses concise and conversational."
    temperature = 0.7
    max_tokens_val = 100
    if assistant_id:
        assistant = _find_assistant(assistant_id)
        if assistant:
            stt_model = assistant.get("stt_model", stt_model)
            tts_model = assistant.get("tts_model", tts_model)
            llm_model = assistant.get("openai_model", llm_model)
            system_prompt = assistant.get("system_prompt", system_prompt)
            temperature = assistant.get("temperature", temperature)
            max_tokens_val = assistant.get("max_tokens", max_tokens_val)
    
    def generate():
        try:
            # ── Step 1: STT ──
            stt_response = deepgram_client.listen.v1.media.transcribe_file(
                request=audio_data,
                model=stt_model,
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
                yield f"data: {json.dumps({'type': 'error', 'message': 'Could not transcribe audio'})}\n\n"
                return
            
            # ── PART 1: Send transcript immediately for display ──
            yield f"data: {json.dumps({'type': 'transcript', 'text': transcript})}\n\n"
            
            # ── Step 2: STREAMING LLM — tokens arrive one-by-one ──
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript}
            ]
            
            full_response = ""
            sentence_buffer = ""
            
            stream = openai_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens_val,
                stream=True
            )
            
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta or not delta.content:
                    continue
                
                token = delta.content
                full_response += token
                sentence_buffer += token
                
                # Send each token for progressive text display
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
                
                # When a sentence is complete, immediately generate TTS for it
                if re.search(r'[.!?]\s*$', sentence_buffer):
                    sentence = sentence_buffer.strip()
                    sentence_buffer = ""
                    
                    if sentence:
                        try:
                            tts_audio = b""
                            for audio_chunk in deepgram_client.speak.v1.audio.generate(
                                text=sentence,
                                model=tts_model,
                                encoding="linear16",
                                sample_rate=16000,
                            ):
                                tts_audio += audio_chunk
                            audio_b64 = base64.b64encode(tts_audio).decode('utf-8')
                            yield f"data: {json.dumps({'type': 'sentence_audio', 'text': sentence, 'audio': audio_b64})}\n\n"
                        except Exception as tts_err:
                            print(f"[Stream] TTS error: {tts_err}")
            
            # Flush remaining text as final sentence
            if sentence_buffer.strip():
                sentence = sentence_buffer.strip()
                try:
                    tts_audio = b""
                    for audio_chunk in deepgram_client.speak.v1.audio.generate(
                        text=sentence,
                        model=tts_model,
                        encoding="linear16",
                        sample_rate=16000,
                    ):
                        tts_audio += audio_chunk
                    audio_b64 = base64.b64encode(tts_audio).decode('utf-8')
                    yield f"data: {json.dumps({'type': 'sentence_audio', 'text': sentence, 'audio': audio_b64})}\n\n"
                except Exception as tts_err:
                    print(f"[Stream] TTS error for final: {tts_err}")
            
            yield f"data: {json.dumps({'type': 'done', 'full_text': full_response})}\n\n"
            
        except Exception as e:
            print(f"Stream Pipeline Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


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
        max_tokens = 100
        
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
            "call_type": "outbound",
            "created_at": datetime.utcnow().isoformat()
        }
        calls = _load_call_log()
        calls.insert(0, call_record)
        _save_call_log(calls)
        # Supabase
        supa_logger.insert({"call_id": session_id, "call_type": "outbound", "phone_number": phone_number, "customer_name": customer_name, "assistant_id": assistant_id, "from_number": from_number, "twilio_sid": call.sid, "status": call.status, "created_at": datetime.utcnow().isoformat()})
        
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
    supa_update = {"status": call_status}
    if call_duration:
        supa_update["duration"] = int(call_duration) if call_duration.isdigit() else 0
    for c in calls:
        if c["id"] == session_id:
            c["status"] = call_status
            if call_duration:
                c["duration"] = call_duration
            # Save conversation transcript when call ends
            if call_status in ("completed", "busy", "no-answer", "canceled", "failed"):
                session = active_call_sessions.get(session_id, {})
                if session.get("conversation"):
                    c["conversation"] = session["conversation"]
                    supa_update["conversation"] = json.dumps(session["conversation"])
                c["ended_at"] = datetime.utcnow().isoformat()
                supa_update["ended_at"] = c["ended_at"]
            break
    _save_call_log(calls)
    supa_logger.update(session_id, supa_update)
    
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

        # ── PART 1: Display user text IMMEDIATELY (before LLM) ────────────
        #    Log transcript to active session right away so dashboard/UI sees it
        conversation_history.append({"role": "user", "content": transcript})
        if session_id in active_call_sessions:
            active_call_sessions[session_id]["conversation"].append({
                "role": "user", "text": transcript,
                "timestamp": datetime.utcnow().isoformat()
            })

        if stop_ai.is_set():
            return

        # ── Step 3: STREAMING LLM — token by token ────────────────────────
        #    Stream tokens from OpenAI. As each sentence completes, immediately
        #    generate TTS and queue audio — so human hears first sentence while
        #    LLM is still generating the rest. Massive latency reduction.
        ai_response = ""
        sentence_buffer = ""
        sentence_count = 0

        ai_speaking.set()
        CHUNK = 640   # ~40 ms at 8 kHz mulaw

        try:
            llm_stream = openai_client.chat.completions.create(
                model=openai_model,
                messages=conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )

            for llm_chunk in llm_stream:
                if stop_ai.is_set():
                    print(f"[Voice Agent {session_id}] ⚡ Barge-in during LLM stream — stopping")
                    break

                delta = llm_chunk.choices[0].delta if llm_chunk.choices else None
                if not delta or not delta.content:
                    continue

                token = delta.content
                ai_response += token
                sentence_buffer += token

                # Check if we have a complete sentence
                if re.search(r'[.!?]\s*$', sentence_buffer):
                    sentence = sentence_buffer.strip()
                    sentence_buffer = ""

                    if sentence and not stop_ai.is_set():
                        sentence_count += 1
                        # Generate TTS for this sentence immediately
                        try:
                            tts_raw = b""
                            for tts_chunk in deepgram_client.speak.v1.audio.generate(
                                text=sentence, model=tts_model,
                                encoding="linear16", sample_rate=8000,
                            ):
                                tts_raw += tts_chunk

                            pcm_tts = tts_raw
                            if tts_raw[:4] == b'RIFF':
                                dp = tts_raw.find(b'data')
                                if dp != -1:
                                    pcm_tts = tts_raw[dp + 8:]

                            tts_mulaw = audioop.lin2ulaw(pcm_tts, 2)

                            for i in range(0, len(tts_mulaw), CHUNK):
                                if stop_ai.is_set():
                                    break
                                _q(json.dumps({
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": base64.b64encode(tts_mulaw[i:i + CHUNK]).decode()}
                                }))
                        except Exception as tts_err:
                            print(f"[Voice Agent {session_id}] Sentence TTS error: {tts_err}")

            # Flush remaining buffer as final sentence
            if sentence_buffer.strip() and not stop_ai.is_set():
                sentence = sentence_buffer.strip()
                try:
                    tts_raw = b""
                    for tts_chunk in deepgram_client.speak.v1.audio.generate(
                        text=sentence, model=tts_model,
                        encoding="linear16", sample_rate=8000,
                    ):
                        tts_raw += tts_chunk

                    pcm_tts = tts_raw
                    if tts_raw[:4] == b'RIFF':
                        dp = tts_raw.find(b'data')
                        if dp != -1:
                            pcm_tts = tts_raw[dp + 8:]

                    tts_mulaw = audioop.lin2ulaw(pcm_tts, 2)

                    for i in range(0, len(tts_mulaw), CHUNK):
                        if stop_ai.is_set():
                            break
                        _q(json.dumps({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": base64.b64encode(tts_mulaw[i:i + CHUNK]).decode()}
                        }))
                except Exception as tts_err:
                    print(f"[Voice Agent {session_id}] Final sentence TTS error: {tts_err}")

        finally:
            ai_speaking.clear()

        # Log completed response
        conversation_history.append({"role": "assistant", "content": ai_response})
        print(f"[Voice Agent {session_id}] 🤖 AI: {ai_response}")

        # ── PART 2: Display AI response (text visible in session) ──────────
        if session_id in active_call_sessions:
            active_call_sessions[session_id]["conversation"].append({
                "role": "assistant", "text": ai_response,
                "timestamp": datetime.utcnow().isoformat()
            })

        if not stop_ai.is_set():
            _q(json.dumps({
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {"name": f"resp_{len(conversation_history)}"}
            }))

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


@app.route("/api/call-logs", methods=["GET"])
def get_call_logs_enhanced():
    """
    Enhanced call logs endpoint — returns all logs (outbound + chat) with stats.
    Tries Supabase first, falls back to local JSON.
    """
    # Try Supabase
    supa_data = supa_logger.fetch_all()
    if supa_data is not None:
        logs = []
        for row in supa_data:
            conv = row.get("conversation")
            if isinstance(conv, str):
                try:
                    conv = json.loads(conv)
                except:
                    conv = []
            logs.append({
                "id": row.get("call_id", row.get("id", "")),
                "call_type": row.get("call_type", "outbound"),
                "phone_number": row.get("phone_number", ""),
                "customer_name": row.get("customer_name", ""),
                "assistant_id": row.get("assistant_id", ""),
                "status": row.get("status", "unknown"),
                "duration": row.get("duration", 0),
                "from_number": row.get("from_number", ""),
                "twilio_sid": row.get("twilio_sid", ""),
                "created_at": row.get("created_at", ""),
                "ended_at": row.get("ended_at", ""),
                "conversation": conv if conv else [],
            })
    else:
        # Fallback to local JSON
        logs = _load_call_log()

    # Compute stats
    total = len(logs)
    answered = sum(1 for c in logs if c.get("status") == "completed")
    unanswered = sum(1 for c in logs if c.get("status") in ("busy", "no-answer", "canceled", "failed"))
    total_duration = sum(int(c.get("duration", 0) or 0) for c in logs)

    return jsonify({
        "logs": logs,
        "stats": {
            "total_calls": total,
            "answered": answered,
            "unanswered": unanswered,
            "total_duration": total_duration,
        }
    })


@app.route("/api/chat-log", methods=["POST"])
def log_chat_session():
    """
    Log a completed chat session (from the dashboard chat window).
    Stores in both local JSON and Supabase.
    """
    data = request.get_json() or {}
    session_id = data.get("session_id", str(uuid.uuid4())[:12])
    chat_record = {
        "id": session_id,
        "call_type": "chat",
        "provider": "voice-agent",
        "phone_number": "",
        "customer_name": data.get("customer_name", "Dashboard User"),
        "assistant_id": data.get("assistant_id", ""),
        "from_number": "",
        "twilio_sid": "",
        "status": "completed",
        "duration": str(data.get("duration", 0)),
        "created_at": data.get("started_at", datetime.utcnow().isoformat()),
        "ended_at": datetime.utcnow().isoformat(),
        "conversation": data.get("conversation", []),
    }
    # Save locally
    calls = _load_call_log()
    calls.insert(0, chat_record)
    _save_call_log(calls)
    # Supabase
    supa_row = {**chat_record, "call_id": session_id}
    supa_row["conversation"] = json.dumps(chat_record["conversation"])
    del supa_row["id"]
    supa_logger.insert(supa_row)
    return jsonify({"success": True, "session_id": session_id})


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
# PHONE PROVIDERS (Twilio & Vobiz credentials + number listing)
# -------------------------
PROVIDERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone_providers.json")

def _load_providers():
    try:
        with open(PROVIDERS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_providers(data):
    with open(PROVIDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.route("/api/phone-providers", methods=["GET"])
def get_phone_providers():
    """Get saved provider credentials (keys masked)."""
    providers = _load_providers()
    result = {}
    for name, creds in providers.items():
        masked = {}
        for k, v in creds.items():
            if v and len(str(v)) > 8:
                masked[k] = str(v)[:4] + "•" * (len(str(v)) - 8) + str(v)[-4:]
            else:
                masked[k] = v
        masked["_connected"] = creds.get("_connected", False)
        result[name] = masked
    return jsonify(result)


@app.route("/api/phone-providers/<provider>", methods=["POST"])
def save_phone_provider(provider):
    """Save credentials for a provider (twilio or vobiz) and test connection."""
    global twilio_client, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
    data = request.get_json() or {}
    providers = _load_providers()

    if provider == "twilio":
        sid = data.get("account_sid", "").strip()
        token = data.get("auth_token", "").strip()
        if not sid or not token:
            return jsonify({"error": "Account SID and Auth Token are required"}), 400
        # Test connection
        try:
            test_client = TwilioClient(sid, token)
            numbers = test_client.incoming_phone_numbers.list(limit=100)
            num_list = [{"sid": n.sid, "phone_number": n.phone_number, "friendly_name": n.friendly_name} for n in numbers]
            # Save
            providers["twilio"] = {"account_sid": sid, "auth_token": token, "_connected": True}
            _save_providers(providers)
            # Update global twilio client
            TWILIO_ACCOUNT_SID = sid
            TWILIO_AUTH_TOKEN = token
            twilio_client = test_client
            if num_list:
                TWILIO_PHONE_NUMBER = num_list[0]["phone_number"]
            return jsonify({"success": True, "message": f"Connected! Found {len(num_list)} phone number(s).", "numbers": num_list})
        except Exception as e:
            providers["twilio"] = {"account_sid": sid, "auth_token": token, "_connected": False}
            _save_providers(providers)
            return jsonify({"error": f"Connection failed: {str(e)}"}), 400

    elif provider == "vobiz":
        auth_id = data.get("auth_id", "").strip()
        auth_token = data.get("auth_token", "").strip()
        if not auth_id or not auth_token:
            return jsonify({"error": "Auth ID and Auth Token are required"}), 400
        # Test connection — Vobiz uses Basic Auth (auth_id:auth_token)
        try:
            r = _httpx.get("https://api.vobiz.ai/v1/phone-numbers/",
                           auth=(auth_id, auth_token), timeout=10)
            if r.status_code == 200:
                resp_data = r.json()
                nums = resp_data if isinstance(resp_data, list) else resp_data.get("objects", resp_data.get("results", resp_data.get("numbers", [])))
                if not isinstance(nums, list):
                    nums = []
                num_list = [{"id": n.get("id", n.get("sid", "")), "phone_number": n.get("number", n.get("phone_number", "")), "name": n.get("alias", n.get("friendly_name", ""))} for n in nums]
                providers["vobiz"] = {"auth_id": auth_id, "auth_token": auth_token, "_connected": True}
                _save_providers(providers)
                return jsonify({"success": True, "message": f"Connected! Found {len(num_list)} phone number(s).", "numbers": num_list})
            elif r.status_code == 401:
                providers["vobiz"] = {"auth_id": auth_id, "auth_token": auth_token, "_connected": False}
                _save_providers(providers)
                return jsonify({"error": "Invalid credentials. Check your Auth ID and Auth Token from console.vobiz.ai"}), 400
            else:
                providers["vobiz"] = {"auth_id": auth_id, "auth_token": auth_token, "_connected": False}
                _save_providers(providers)
                return jsonify({"error": f"Vobiz returned {r.status_code}: {r.text[:200]}"}), 400
        except Exception as e:
            providers["vobiz"] = {"auth_id": auth_id, "auth_token": auth_token, "_connected": False}
            _save_providers(providers)
            return jsonify({"error": f"Connection failed: {str(e)}"}), 400
    else:
        return jsonify({"error": "Unknown provider. Use 'twilio' or 'vobiz'."}), 400


@app.route("/api/phone-numbers/<provider>", methods=["GET"])
def get_phone_numbers(provider):
    """List phone numbers from a provider using saved credentials."""
    providers = _load_providers()
    creds = providers.get(provider)
    if not creds:
        return jsonify({"error": f"No credentials saved for {provider}. Connect first."}), 400

    if provider == "twilio":
        try:
            tc = TwilioClient(creds["account_sid"], creds["auth_token"])
            numbers = tc.incoming_phone_numbers.list(limit=100)
            num_list = [{"sid": n.sid, "phone_number": n.phone_number, "friendly_name": n.friendly_name, "capabilities": {"voice": n.capabilities.get("voice", False), "sms": n.capabilities.get("sms", False)}} for n in numbers]
            return jsonify({"numbers": num_list, "count": len(num_list)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif provider == "vobiz":
        try:
            r = _httpx.get("https://api.vobiz.ai/v1/phone-numbers/",
                           auth=(creds["auth_id"], creds["auth_token"]), timeout=10)
            if r.status_code == 200:
                resp_data = r.json()
                nums = resp_data if isinstance(resp_data, list) else resp_data.get("objects", resp_data.get("results", resp_data.get("numbers", [])))
                if not isinstance(nums, list):
                    nums = []
                num_list = [{"id": n.get("id", n.get("sid", "")), "phone_number": n.get("number", n.get("phone_number", "")), "name": n.get("alias", n.get("friendly_name", ""))} for n in nums]
                return jsonify({"numbers": num_list, "count": len(num_list)})
            return jsonify({"error": f"Vobiz returned {r.status_code}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Unknown provider"}), 400


@app.route("/api/phone-providers/<provider>", methods=["DELETE"])
def disconnect_phone_provider(provider):
    """Disconnect a provider (remove saved credentials)."""
    providers = _load_providers()
    if provider in providers:
        del providers[provider]
        _save_providers(providers)
    return jsonify({"success": True})


# -------------------------
# MIGRATE LOCAL LOGS TO SUPABASE
# -------------------------
@app.route("/api/migrate-logs", methods=["POST"])
def migrate_logs_to_supabase():
    """Migrate all local call_log.json entries to Supabase (skips duplicates)."""
    if not supa_logger.enabled:
        return jsonify({"error": "Supabase not configured"}), 400

    calls = _load_call_log()
    if not calls:
        return jsonify({"message": "No local logs to migrate", "migrated": 0})

    migrated = 0
    skipped = 0
    errors = 0
    for c in calls:
        try:
            row = {
                "call_id": c.get("id", str(uuid.uuid4())[:12]),
                "call_type": c.get("call_type", "outbound"),
                "phone_number": c.get("phone_number", ""),
                "customer_name": c.get("customer_name", ""),
                "assistant_id": c.get("assistant_id", ""),
                "from_number": c.get("from_number", ""),
                "twilio_sid": c.get("twilio_sid", ""),
                "status": c.get("status", "unknown"),
                "duration": int(c.get("duration", 0) or 0),
                "conversation": json.dumps(c.get("conversation", [])),
                "created_at": c.get("created_at", datetime.utcnow().isoformat()),
                "ended_at": c.get("ended_at", ""),
            }
            # Try insert — on conflict (duplicate call_id) it will fail, that's ok
            r = _httpx.post(supa_logger.base, json=row, headers=supa_logger.headers, timeout=10)
            if r.status_code in (200, 201):
                migrated += 1
            elif r.status_code == 409:
                skipped += 1
            else:
                # Check if duplicate by message
                resp_text = r.text
                if "duplicate" in resp_text.lower() or "unique" in resp_text.lower():
                    skipped += 1
                else:
                    errors += 1
                    print(f"[Migrate] Error for {row['call_id']}: {r.status_code} {resp_text[:100]}")
        except Exception as e:
            errors += 1
            print(f"[Migrate] Exception: {e}")

    return jsonify({"success": True, "migrated": migrated, "skipped": skipped, "errors": errors, "total_local": len(calls)})


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
    print("  POST /stt                       - Speech to Text")
    print("  POST /tts                       - Text to Speech")
    print("  POST /chat                      - LLM Chat")
    print("  POST /speech-to-speech          - Full pipeline")
    print("  POST /speech-to-speech-stream   - Low-latency SSE pipeline ⚡")
    print("  POST /api/outbound-call         - Outbound Call")
    print("  GET  /test                      - Test TTS")
    print("="*50 + "\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000)

