"""Text-to-Speech layer with pluggable providers."""
import logging
import asyncio
from typing import AsyncGenerator, Protocol
from abc import ABC, abstractmethod
from deepgram import DeepgramClient, SpeakOptions
from elevenlabs import AsyncElevenLabs
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""
    
    @abstractmethod
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to speech audio.
        
        Args:
            text: Text to convert to speech
            
        Yields:
            Audio chunks as bytes
        """
        pass


class DeepgramTTS(TTSProvider):
    """Deepgram TTS provider."""
    
    def __init__(self):
        self.client = DeepgramClient(settings.deepgram_api_key)
        
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize using Deepgram."""
        try:
            options = SpeakOptions(
                model="aura-asteria-en",
                encoding="linear16",
                sample_rate=16000,
            )
            
            response = self.client.speak.v("1").stream(
                {"text": text},
                options
            )
            
            # Stream audio chunks
            for chunk in response.stream_memory:
                if chunk:
                    yield chunk
                    
        except Exception as e:
            logger.error(f"Deepgram TTS error: {e}")
            raise


class ElevenLabsTTS(TTSProvider):
    """ElevenLabs TTS provider."""
    
    def __init__(self):
        self.client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)
        self.voice_id = settings.elevenlabs_voice_id
        
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize using ElevenLabs."""
        try:
            audio_stream = await self.client.generate(
                text=text,
                voice=self.voice_id,
                model="eleven_turbo_v2",
                stream=True
            )
            
            async for chunk in audio_stream:
                if chunk:
                    yield chunk
                    
        except Exception as e:
            logger.error(f"ElevenLabs TTS error: {e}")
            raise


class OpenAITTS(TTSProvider):
    """OpenAI TTS provider."""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize using OpenAI."""
        try:
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
                response_format="pcm",
            )
            
            # Stream the response
            async for chunk in response.iter_bytes():
                if chunk:
                    yield chunk
                    
        except Exception as e:
            logger.error(f"OpenAI TTS error: {e}")
            raise


class MockTTS(TTSProvider):
    """Mock TTS for testing."""
    
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Generate mock audio data."""
        # Generate some fake audio bytes
        for _ in range(5):
            yield b'\x00' * 1024  # Silent audio
            await asyncio.sleep(0.1)


class TTSLayer:
    """
    Text-to-Speech layer with provider abstraction.
    
    Features:
    - Pluggable TTS providers
    - Streaming audio output
    - Sentence-by-sentence synthesis
    - Interruption support
    """
    
    def __init__(self, provider: str = None):
        """
        Initialize TTS layer.
        
        Args:
            provider: TTS provider name (deepgram, elevenlabs, openai, mock)
        """
        provider = provider or settings.tts_provider
        
        self.provider: TTSProvider
        if provider == "deepgram":
            self.provider = DeepgramTTS()
        elif provider == "elevenlabs":
            self.provider = ElevenLabsTTS()
        elif provider == "openai":
            self.provider = OpenAITTS()
        elif provider == "mock":
            self.provider = MockTTS()
        else:
            raise ValueError(f"Unknown TTS provider: {provider}")
            
        self.is_speaking = False
        self.should_stop = False
        
    async def speak(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Convert text to speech and stream audio.
        
        Args:
            text: Text to synthesize
            
        Yields:
            Audio chunks
        """
        self.is_speaking = True
        self.should_stop = False
        
        try:
            async for audio_chunk in self.provider.synthesize(text):
                # Check if we should stop (user interrupted)
                if self.should_stop:
                    logger.info("TTS interrupted by user")
                    break
                    
                yield audio_chunk
                
        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise
        finally:
            self.is_speaking = False
    
    def stop(self):
        """Stop current speech synthesis."""
        self.should_stop = True
        logger.info("TTS stop requested")
    
    def split_into_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences for streaming.
        
        Args:
            text: Text to split
            
        Returns:
            List of sentences
        """
        import re
        
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
