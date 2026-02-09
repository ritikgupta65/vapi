"""LLM layer using OpenAI-compatible APIs."""
import logging
from typing import AsyncGenerator, List
from openai import AsyncOpenAI
from config import settings
from models import Message

logger = logging.getLogger(__name__)


class LLMLayer:
    """
    LLM layer for text-to-text generation.
    
    Supports:
    - OpenAI and Azure OpenAI
    - Streaming responses
    - Conversation history
    """
    
    def __init__(self):
        """Initialize LLM layer."""
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        
    async def generate_response(
        self, 
        messages: List[Message]
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response from LLM.
        
        Args:
            messages: Conversation history in OpenAI format
            
        Yields:
            Text chunks as they are generated
        """
        try:
            # Convert messages to OpenAI format
            openai_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            # Create streaming completion
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                stream=True,
                temperature=0.7,
                max_tokens=500,  # Keep responses concise for voice
            )
            
            # Stream chunks
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield content
                    
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            raise


class MockLLMLayer:
    """Mock LLM layer for testing without OpenAI API."""
    
    async def generate_response(
        self, 
        messages: List[Message]
    ) -> AsyncGenerator[str, None]:
        """Generate mock response."""
        mock_response = "This is a mock AI response. The actual LLM integration would require a valid OpenAI API key."
        
        # Simulate streaming by yielding words
        words = mock_response.split()
        for word in words:
            yield word + " "
            await asyncio.sleep(0.1)  # Simulate network delay


import asyncio
