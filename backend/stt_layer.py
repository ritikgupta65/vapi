"""Speech-to-Text layer using Deepgram."""
import asyncio
import logging
from typing import Callable, Optional
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from config import settings
from models import STTResult

logger = logging.getLogger(__name__)


class STTLayer:
    """
    Speech-to-Text layer with Deepgram streaming.
    
    Handles:
    - WebSocket connection to Deepgram
    - Streaming audio chunks
    - Partial and final transcripts
    - Automatic silence detection
    """
    
    def __init__(self, on_transcript: Callable[[STTResult], None]):
        """
        Initialize STT layer.
        
        Args:
            on_transcript: Callback function called when transcript is received
        """
        self.on_transcript = on_transcript
        self.deepgram = DeepgramClient(settings.deepgram_api_key)
        self.connection = None
        self.is_active = False
        
    async def start(self):
        """Start the Deepgram connection."""
        try:
            # Configure Deepgram options
            options = LiveOptions(
                model="nova-2",
                language="en-US",
                smart_format=True,
                encoding="linear16",
                sample_rate=16000,
                channels=1,
                interim_results=True,  # Enable partial transcripts
                utterance_end_ms=1000,  # Detect end of utterance after 1s silence
                vad_events=True,  # Voice activity detection events
            )
            
            # Create connection
            self.connection = self.deepgram.listen.asyncwebsocket.v("1")
            
            # Register event handlers
            self.connection.on(LiveTranscriptionEvents.Transcript, self._on_message)
            self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.connection.on(LiveTranscriptionEvents.Close, self._on_close)
            
            # Start connection
            if await self.connection.start(options):
                self.is_active = True
                logger.info("Deepgram STT connection started")
            else:
                logger.error("Failed to start Deepgram connection")
                
        except Exception as e:
            logger.error(f"Error starting STT: {e}")
            raise
    
    async def send_audio(self, audio_data: bytes):
        """
        Send audio data to Deepgram.
        
        Args:
            audio_data: Raw audio bytes (PCM 16-bit, 16kHz, mono)
        """
        if self.connection and self.is_active:
            try:
                self.connection.send(audio_data)
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
    
    async def stop(self):
        """Stop the Deepgram connection."""
        if self.connection:
            try:
                await self.connection.finish()
                self.is_active = False
                logger.info("Deepgram STT connection stopped")
            except Exception as e:
                logger.error(f"Error stopping STT: {e}")
    
    def _on_message(self, *args, **kwargs):
        """Handle incoming transcript from Deepgram."""
        try:
            result = kwargs.get("result")
            if not result:
                return
            
            # Extract transcript data
            channel = result.channel
            if not channel or not channel.alternatives:
                return
            
            alternative = channel.alternatives[0]
            transcript = alternative.transcript.strip()
            
            if not transcript:
                return
            
            # Determine if this is a final transcript
            is_final = result.is_final
            speech_final = result.speech_final if hasattr(result, 'speech_final') else False
            
            # Create STT result
            stt_result = STTResult(
                text=transcript,
                is_final=is_final,
                speech_final=speech_final
            )
            
            # Call the callback
            self.on_transcript(stt_result)
            
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")
    
    def _on_error(self, *args, **kwargs):
        """Handle Deepgram errors."""
        error = kwargs.get("error")
        logger.error(f"Deepgram error: {error}")
    
    def _on_close(self, *args, **kwargs):
        """Handle connection close."""
        self.is_active = False
        logger.info("Deepgram connection closed")


class MockSTTLayer:
    """Mock STT layer for testing without Deepgram API."""
    
    def __init__(self, on_transcript: Callable[[STTResult], None]):
        self.on_transcript = on_transcript
        self.is_active = False
        
    async def start(self):
        self.is_active = True
        logger.info("Mock STT started")
        
    async def send_audio(self, audio_data: bytes):
        # Simulate receiving transcript after some audio
        pass
        
    async def stop(self):
        self.is_active = False
        logger.info("Mock STT stopped")
