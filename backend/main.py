"""Main FastAPI application."""
import logging
import uuid
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from models import SessionCreate, SessionResponse, TranscriptEvent
from orchestrator import ConversationOrchestrator
import asyncio
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Speech-to-Speech AI",
    description="Real-time voice conversation system with STT, LLM, and TTS",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active sessions
sessions: Dict[str, ConversationOrchestrator] = {}

# Store WebSocket connections
transcript_connections: Dict[str, WebSocket] = {}
audio_output_connections: Dict[str, WebSocket] = {}


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "speech-to-speech-ai",
        "version": "1.0.0"
    }


@app.post("/session", response_model=SessionResponse)
async def create_session(request: SessionCreate):
    """
    Create a new conversation session.
    
    Args:
        request: Session creation request with system prompt
        
    Returns:
        Session ID
    """
    session_id = str(uuid.uuid4())
    
    logger.info(f"Creating session {session_id}")
    
    # Create orchestrator (will be started when WebSockets connect)
    # Store for later initialization
    sessions[session_id] = {
        "system_prompt": request.system_prompt,
        "orchestrator": None
    }
    
    return SessionResponse(session_id=session_id)


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a conversation session.
    
    Args:
        session_id: Session to delete
    """
    if session_id in sessions:
        session = sessions[session_id]
        if session.get("orchestrator"):
            await session["orchestrator"].stop()
        del sessions[session_id]
        
        # Clean up connections
        if session_id in transcript_connections:
            del transcript_connections[session_id]
        if session_id in audio_output_connections:
            del audio_output_connections[session_id]
        
        logger.info(f"Deleted session {session_id}")
        return {"status": "deleted"}
    
    raise HTTPException(status_code=404, detail="Session not found")


@app.websocket("/session/{session_id}/audio/in")
async def audio_input_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for receiving audio input from client.
    
    Accepts raw audio bytes (PCM 16-bit, 16kHz, mono).
    """
    await websocket.accept()
    logger.info(f"Audio input WebSocket connected for session {session_id}")
    
    if session_id not in sessions:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    session = sessions[session_id]
    
    # Initialize orchestrator if not already done
    if not session.get("orchestrator"):
        # Callbacks for orchestrator
        async def on_transcript(event: TranscriptEvent):
            if session_id in transcript_connections:
                try:
                    await transcript_connections[session_id].send_json(event.dict())
                except Exception as e:
                    logger.error(f"Error sending transcript: {e}")
        
        async def on_audio_output(audio_data: bytes):
            if session_id in audio_output_connections:
                try:
                    await audio_output_connections[session_id].send_bytes(audio_data)
                except Exception as e:
                    logger.error(f"Error sending audio output: {e}")
        
        orchestrator = ConversationOrchestrator(
            session_id=session_id,
            system_prompt=session["system_prompt"],
            on_transcript_event=on_transcript,
            on_audio_output=on_audio_output
        )
        
        await orchestrator.start()
        session["orchestrator"] = orchestrator
    
    orchestrator = session["orchestrator"]
    
    try:
        while True:
            # Receive audio data
            audio_data = await websocket.receive_bytes()
            
            # Send to orchestrator
            await orchestrator.handle_audio_input(audio_data)
            
    except WebSocketDisconnect:
        logger.info(f"Audio input WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"Error in audio input WebSocket: {e}")
    finally:
        # Clean up
        pass


@app.websocket("/session/{session_id}/audio/out")
async def audio_output_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for streaming audio output to client.
    
    Streams synthesized speech audio chunks.
    """
    await websocket.accept()
    logger.info(f"Audio output WebSocket connected for session {session_id}")
    
    if session_id not in sessions:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    # Store connection
    audio_output_connections[session_id] = websocket
    
    try:
        # Keep connection alive
        while True:
            # Wait for messages (though we mainly send data)
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        logger.info(f"Audio output WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"Error in audio output WebSocket: {e}")
    finally:
        if session_id in audio_output_connections:
            del audio_output_connections[session_id]


@app.websocket("/session/{session_id}/transcript")
async def transcript_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for streaming transcript events.
    
    Sends TranscriptEvent objects as JSON.
    """
    await websocket.accept()
    logger.info(f"Transcript WebSocket connected for session {session_id}")
    
    if session_id not in sessions:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    # Store connection
    transcript_connections[session_id] = websocket
    
    try:
        # Keep connection alive
        while True:
            # Wait for messages (though we mainly send data)
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        logger.info(f"Transcript WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"Error in transcript WebSocket: {e}")
    finally:
        if session_id in transcript_connections:
            del transcript_connections[session_id]


@app.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    """
    Get current session state.
    
    Args:
        session_id: Session ID
        
    Returns:
        Current state and conversation history
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    orchestrator = session.get("orchestrator")
    
    if not orchestrator:
        return {
            "state": "not_started",
            "messages": []
        }
    
    return {
        "state": orchestrator.get_state().value,
        "messages": [msg.dict() for msg in orchestrator.get_messages()]
    }


if __name__ == "__main__":
    import uvicorn
    from config import settings
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
