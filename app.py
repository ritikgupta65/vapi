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
from flask import Flask, request, jsonify, Response, stream_with_context, send_file
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
print("="*50 + "\n")


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
        
        # Add WAV header if raw PCM (linear16 is raw PCM)
        if encoding == "linear16" and not audio_data.startswith(b'RIFF'):
            # Create WAV header for 16-bit mono 16kHz audio
            sample_rate = 16000
            num_channels = 1
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            data_size = len(audio_data)
            
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
            audio_data = wav_header + audio_data
            print(f"[TTS] Added WAV header, total size: {len(audio_data)} bytes")
        
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
        
        return audio_data, 200, {'Content-Type': 'audio/wav'}
    
    except Exception as e:
        print(f"Test TTS Error: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# RUN APP
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
