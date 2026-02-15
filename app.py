"""
Flask-based Speech-to-Speech AI with Deepgram STT/TTS and OpenAI
"""
import json
import os
import io
import wave
import struct
import base64
import time
import uuid
import subprocess
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, Response, stream_with_context, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# Try to import required packages
try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError as e:
    DEEPGRAM_AVAILABLE = False
    print(f"⚠️  Deepgram not installed. Run: pip install deepgram-sdk")

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    FFMPEG_AVAILABLE = os.path.exists(FFMPEG_PATH)
except Exception:
    FFMPEG_PATH = 'ffmpeg'
    FFMPEG_AVAILABLE = False

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
OPENAI_BASE_URL = os.getenv("LLM_BASE_URL")  # For Azure/GitHub Models inference
DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")

# Safe content filter (for Azure API compatibility)
SAFE_CONTENT_FILTER = {
    "hate": {"filtered": False, "severity": "safe"},
    "self_harm": {"filtered": False, "severity": "safe"},
    "sexual": {"filtered": False, "severity": "safe"},
    "violence": {"filtered": False, "severity": "safe"},
}

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
    # Use custom base URL if provided (for Azure/GitHub Models)
    if OPENAI_BASE_URL:
        openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        print(f"✅ OpenAI initialized with custom endpoint: {OPENAI_BASE_URL}")
    else:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        print("✅ OpenAI initialized")
else:
    print("⚠️  OpenAI not available (optional)")

# Show startup banner
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
print("  GET  /                 - Health check")
print("  GET  /voicesdk.js      - Embeddable SDK")
print("  GET  /integration-example - Demo page")
print("  GET  /dashboard        - Assistant Manager")
print("  GET  /a/<id>           - Published Assistant")
print("="*50 + "\n")


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

def _save_assistants(assistants_list):
    """Save assistants to JSON file."""
    with open(ASSISTANTS_FILE, "w") as f:
        json.dump({"assistants": assistants_list}, f, indent=2)

def _find_assistant(assistant_id):
    """Find an assistant by ID."""
    for a in _load_assistants():
        if a["id"] == assistant_id:
            return a
    return None


# -------------------------
# SERVE FRONTEND & SDK
# -------------------------
@app.route("/app", methods=["GET"])
def serve_frontend():
    """Serve the index.html frontend"""
    return send_file(os.path.join(os.path.dirname(__file__), "index.html"))


@app.route("/voicesdk.js", methods=["GET"])
def serve_sdk():
    """Serve the VoiceSDK JavaScript file for embedding in other projects."""
    return send_file(
        os.path.join(os.path.dirname(__file__), "voicesdk.js"),
        mimetype='application/javascript'
    )


@app.route("/integration-example", methods=["GET"])
def serve_integration_example():
    """Serve the integration example page."""
    return send_file(
        os.path.join(os.path.dirname(__file__), "integration-example.html")
    )


@app.route("/dashboard", methods=["GET"])
def serve_dashboard():
    """Serve the assistant management dashboard."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")


@app.route("/a/<assistant_id>", methods=["GET"])
def serve_assistant_page(assistant_id):
    """Serve a standalone chat page for a published assistant."""
    assistant = _find_assistant(assistant_id)
    if not assistant:
        return jsonify({"error": "Assistant not found"}), 404
    if not assistant.get("published"):
        return jsonify({"error": "Assistant is not published"}), 403
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "assistant_chat.html")


@app.route("/api/assistant/<assistant_id>/config", methods=["GET"])
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
    return jsonify({"assistants": _load_assistants()})


@app.route("/api/assistants", methods=["POST"])
def create_assistant():
    """Create a new assistant."""
    data = request.get_json() or {}
    assistant = {
        "id": str(uuid.uuid4()),
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
    all_assistants = _load_assistants()
    all_assistants.append(assistant)
    _save_assistants(all_assistants)
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
    all_assistants = _load_assistants()
    for i, a in enumerate(all_assistants):
        if a["id"] == assistant_id:
            data = request.get_json() or {}
            for key in ["name", "openai_model", "stt_model", "tts_model", "first_message", "system_prompt", "temperature", "max_tokens"]:
                if key in data:
                    all_assistants[i][key] = data[key]
            all_assistants[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_assistants(all_assistants)
            return jsonify(all_assistants[i])
    return jsonify({"error": "Assistant not found"}), 404


@app.route("/api/assistants/<assistant_id>", methods=["DELETE"])
def delete_assistant(assistant_id):
    """Delete an assistant."""
    all_assistants = _load_assistants()
    new_list = [a for a in all_assistants if a["id"] != assistant_id]
    if len(new_list) == len(all_assistants):
        return jsonify({"error": "Assistant not found"}), 404
    _save_assistants(new_list)
    return jsonify({"status": "deleted"})


@app.route("/api/assistants/<assistant_id>/publish", methods=["POST"])
def publish_assistant(assistant_id):
    """Publish an assistant - makes it accessible via unique URL."""
    all_assistants = _load_assistants()
    for i, a in enumerate(all_assistants):
        if a["id"] == assistant_id:
            all_assistants[i]["published"] = True
            all_assistants[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_assistants(all_assistants)
            base_url = request.host_url.rstrip("/")
            return jsonify({
                **all_assistants[i],
                "public_url": f"{base_url}/a/{assistant_id}"
            })
    return jsonify({"error": "Assistant not found"}), 404


@app.route("/api/assistants/<assistant_id>/unpublish", methods=["POST"])
def unpublish_assistant(assistant_id):
    """Unpublish an assistant."""
    all_assistants = _load_assistants()
    for i, a in enumerate(all_assistants):
        if a["id"] == assistant_id:
            all_assistants[i]["published"] = False
            all_assistants[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_assistants(all_assistants)
            return jsonify(all_assistants[i])
    return jsonify({"error": "Assistant not found"}), 404


# -------------------------
# HEALTH CHECK
# -------------------------
@app.route("/", methods=["GET"])
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "message": "Speech-to-Speech AI Server",
        "deepgram": "available" if deepgram_client else "not configured",
        "openai": "available" if openai_client else "not configured"
    })


# -------------------------
# STT ENDPOINT (Speech-to-Text)
# -------------------------
@app.route("/stt", methods=["POST"])
def speech_to_text():
    """
    Convert speech to text using Deepgram.
    
    Accepts:
    - multipart/form-data with 'audio' file
    - JSON with 'audio' as base64 string
    - Raw audio bytes
    """
    if not deepgram_client:
        return jsonify({"error": "Deepgram not configured"}), 500
    
    try:
        # Get audio data from different sources
        if 'audio' in request.files:
            audio_file = request.files['audio']
            audio_data = audio_file.read()
        elif request.is_json:
            data = request.get_json()
            audio_base64 = data.get("audio")
            if audio_base64:
                audio_data = base64.b64decode(audio_base64)
            else:
                return jsonify({"error": "Missing 'audio' field in JSON"}), 400
        else:
            audio_data = request.data
        
        if not audio_data:
            return jsonify({"error": "No audio data provided"}), 400
        
        # Debug: save received audio to inspect
        debug_path = os.path.join(os.path.dirname(__file__), "debug_audio.bin")
        with open(debug_path, "wb") as f:
            f.write(audio_data)
        
        # Detect format from magic bytes
        is_webm = audio_data[:4] == b'\x1a\x45\xdf\xa3'
        is_wav = audio_data[:4] == b'RIFF'
        is_ogg = audio_data[:4] == b'OggS'
        print(f"[STT] Audio size: {len(audio_data)} bytes | webm={is_webm} wav={is_wav} ogg={is_ogg}")
        
        # Convert webm/ogg to WAV if needed (browser audio often needs conversion)
        if (is_webm or is_ogg) and FFMPEG_AVAILABLE:
            print(f"[STT] Converting {('webm' if is_webm else 'ogg')} to WAV using ffmpeg...")
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp_in:
                    tmp_in.write(audio_data)
                    tmp_in_path = tmp_in.name
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_out:
                    tmp_out_path = tmp_out.name
                
                result = subprocess.run([
                    FFMPEG_PATH, '-i', tmp_in_path,
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-f', 'wav',
                    tmp_out_path,
                    '-y'
                ], capture_output=True, timeout=10)
                
                if result.returncode == 0 and os.path.exists(tmp_out_path):
                    with open(tmp_out_path, 'rb') as f:
                        audio_data = f.read()
                    print(f"[STT] Converted to WAV: {len(audio_data)} bytes")
                    is_wav = True
                else:
                    print(f"[STT] Conversion failed: {result.stderr[:200]}")
                
                # Cleanup
                try:
                    os.unlink(tmp_in_path)
                    os.unlink(tmp_out_path)
                except:
                    pass
                    
            except Exception as conv_err:
                print(f"[STT] Conversion error: {conv_err}")
        
        transcript = ""
        confidence = 0.0
        
        # Use Deepgram SDK with the (potentially converted) audio
        try:
            response = deepgram_client.listen.v1.media.transcribe_file(
                request=audio_data,
                model="nova-2",
                smart_format=True,
                punctuate=True,
            )
            
            if response and response.results and response.results.channels:
                alternatives = response.results.channels[0].alternatives
                if alternatives:
                    transcript = alternatives[0].transcript
                    confidence = getattr(alternatives[0], 'confidence', 0.0)
            
            print(f"[STT] Result: '{transcript}' (confidence: {confidence})")
        except Exception as err:
            print(f"[STT] Error: {err}")
        
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
        
        print(f"[TTS] Generating speech for: '{text[:50]}...'")
        
        # Generate speech (v5 SDK - keyword args)
        model = data.get("model", "aura-asteria-en")
        
        # Check if using an assistant's TTS settings
        assistant_id = data.get("assistant_id")
        if assistant_id:
            asst = _find_assistant(assistant_id)
            if asst:
                model = asst.get("tts_model", model)
        
        encoding = data.get("encoding", "linear16")
        
        audio_data = b""
        for chunk in deepgram_client.speak.v1.audio.generate(
            text=text,
            model=model,
            encoding=encoding,
            sample_rate=16000,
        ):
            audio_data += chunk
        
        print(f"[TTS] Generated {len(audio_data)} bytes of audio")
        
        # Ensure proper WAV header with correct sizes
        if encoding == "linear16":
            sample_rate = 16000
            num_channels = 1
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            
            # Strip existing WAV header if present (Deepgram often sends a header with wrong size)
            pcm_data = audio_data
            if audio_data[:4] == b'RIFF':
                # Find the 'data' chunk and extract raw PCM
                data_pos = audio_data.find(b'data')
                if data_pos != -1:
                    pcm_data = audio_data[data_pos + 8:]  # skip 'data' + 4-byte size
            
            data_size = len(pcm_data)
            wav_header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF',
                36 + data_size,
                b'WAVE',
                b'fmt ',
                16,  # Subchunk1Size
                1,   # AudioFormat (PCM)
                num_channels,
                sample_rate,
                byte_rate,
                block_align,
                bits_per_sample,
                b'data',
                data_size
            )
            audio_data = wav_header + pcm_data
            print(f"[TTS] WAV header written, total size: {len(audio_data)} bytes")
        
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
        
        # Check if using an assistant's settings
        assistant_id = data.get("assistant_id")
        if assistant_id:
            asst = _find_assistant(assistant_id)
            if asst:
                model = asst.get("openai_model", DEFAULT_MODEL)
                temperature = data.get("temperature", asst.get("temperature", 0.7))
                max_tokens = data.get("max_tokens", asst.get("max_tokens", 200))
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
        
        # Transcribe (v5 SDK - keyword args)
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
        
        # Step 3: Text to Speech (v5 SDK - keyword args)
        audio_data = b""
        for chunk in deepgram_client.speak.v1.audio.generate(
            text=ai_response,
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
        ):
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
# TEST TTS ENDPOINT
# -------------------------
@app.route("/test", methods=["GET"])
def test_tts():
    """Test TTS with a simple message"""
    if not deepgram_client:
        return jsonify({"error": "Deepgram not configured"}), 500
    
    try:
        text = "Hello! This is a test of the Deepgram text-to-speech system. The server is working correctly."
        
        audio_data = b""
        for chunk in deepgram_client.speak.v1.audio.generate(
            text=text,
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
        ):
            audio_data += chunk
        
        # Fix WAV header (Deepgram sends placeholder sizes)
        if audio_data[:4] == b'RIFF':
            data_pos = audio_data.find(b'data')
            if data_pos != -1:
                pcm = audio_data[data_pos + 8:]
                hdr = struct.pack('<4sI4s4sIHHIIHH4sI',
                    b'RIFF', 36+len(pcm), b'WAVE', b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', len(pcm))
                audio_data = hdr + pcm
        
        return audio_data, 200, {'Content-Type': 'audio/wav'}
    
    except Exception as e:
        print(f"Test TTS Error: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# RUN APP
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
