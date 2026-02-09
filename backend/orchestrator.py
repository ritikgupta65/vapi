"""Conversation Orchestrator - manages turn-taking and state."""
import logging
import asyncio
from typing import Callable, Optional, List
from models import ConversationState, Message, STTResult, TranscriptEvent
from stt_layer import STTLayer
from llm_layer import LLMLayer
from tts_layer import TTSLayer

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """
    Manages conversation flow and turn-taking.
    
    State Machine:
    - LISTENING: User is speaking, AI is silent
    - THINKING: Processing user input, calling LLM
    - SPEAKING: AI is speaking, user can interrupt (barge-in)
    
    Rules:
    - Only send final transcripts to LLM
    - User can interrupt AI at any time
    - Maintains conversation history
    """
    
    def __init__(
        self,
        session_id: str,
        system_prompt: str,
        on_transcript_event: Callable[[TranscriptEvent], None],
        on_audio_output: Callable[[bytes], None]
    ):
        """
        Initialize orchestrator.
        
        Args:
            session_id: Unique session identifier
            system_prompt: System prompt for LLM
            on_transcript_event: Callback for transcript events
            on_audio_output: Callback for audio output chunks
        """
        self.session_id = session_id
        self.state = ConversationState.LISTENING
        self.on_transcript_event = on_transcript_event
        self.on_audio_output = on_audio_output
        
        # Conversation history
        self.messages: List[Message] = [
            Message(role="system", content=system_prompt)
        ]
        
        # Current user utterance buffer
        self.current_user_text = ""
        self.current_partial_text = ""
        
        # Layers
        self.stt = STTLayer(on_transcript=self._handle_stt_result)
        self.llm = LLMLayer()
        self.tts = TTSLayer()
        
        # Control flags
        self.is_active = True
        
    async def start(self):
        """Start the orchestrator."""
        await self.stt.start()
        logger.info(f"Orchestrator started for session {self.session_id}")
    
    async def handle_audio_input(self, audio_data: bytes):
        """
        Handle incoming audio from user.
        
        Args:
            audio_data: Raw audio bytes from microphone
        """
        if not self.is_active:
            return
        
        # If AI is speaking and user starts speaking, interrupt (barge-in)
        if self.state == ConversationState.SPEAKING:
            logger.info("User interrupted AI (barge-in)")
            self.tts.stop()
            self.state = ConversationState.LISTENING
        
        # Send audio to STT
        await self.stt.send_audio(audio_data)
    
    def _handle_stt_result(self, result: STTResult):
        """
        Handle transcript from STT layer.
        
        Args:
            result: STT result with transcript and finality info
        """
        if not self.is_active:
            return
        
        if result.is_final or result.speech_final:
            # Final transcript - send to user and prepare for LLM
            if result.text:
                self.current_user_text = result.text
                
                # Send final transcript event
                event = TranscriptEvent(
                    role="user",
                    text=result.text,
                    is_partial=False
                )
                self.on_transcript_event(event)
                
                # Clear partial text
                self.current_partial_text = ""
                
                # Process with LLM
                asyncio.create_task(self._process_user_input())
        else:
            # Partial transcript - send as partial event
            if result.text and result.text != self.current_partial_text:
                self.current_partial_text = result.text
                
                event = TranscriptEvent(
                    role="user",
                    text=result.text,
                    is_partial=True
                )
                self.on_transcript_event(event)
    
    async def _process_user_input(self):
        """Process finalized user input with LLM."""
        if not self.current_user_text:
            return
        
        # Transition to THINKING state
        self.state = ConversationState.THINKING
        logger.info(f"State: LISTENING -> THINKING")
        
        # Add user message to history
        user_message = Message(role="user", content=self.current_user_text)
        self.messages.append(user_message)
        
        # Clear current user text
        self.current_user_text = ""
        
        try:
            # Generate LLM response
            full_response = ""
            current_sentence = ""
            
            async for chunk in self.llm.generate_response(self.messages):
                if not self.is_active:
                    break
                
                full_response += chunk
                current_sentence += chunk
                
                # Check if we have a complete sentence
                if any(punct in chunk for punct in ['.', '!', '?', '\n']):
                    sentence = current_sentence.strip()
                    if sentence:
                        # Start speaking if not already
                        if self.state == ConversationState.THINKING:
                            self.state = ConversationState.SPEAKING
                            logger.info(f"State: THINKING -> SPEAKING")
                        
                        # Synthesize and stream this sentence
                        await self._speak_sentence(sentence)
                        
                        current_sentence = ""
            
            # Speak any remaining text
            if current_sentence.strip():
                await self._speak_sentence(current_sentence.strip())
            
            # Add assistant message to history
            assistant_message = Message(role="assistant", content=full_response)
            self.messages.append(assistant_message)
            
            # Send final transcript event
            event = TranscriptEvent(
                role="assistant",
                text=full_response,
                is_partial=False
            )
            self.on_transcript_event(event)
            
            # Return to LISTENING state
            self.state = ConversationState.LISTENING
            logger.info(f"State: SPEAKING -> LISTENING")
            
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            self.state = ConversationState.LISTENING
    
    async def _speak_sentence(self, sentence: str):
        """
        Speak a single sentence.
        
        Args:
            sentence: Text to speak
        """
        try:
            async for audio_chunk in self.tts.speak(sentence):
                if not self.is_active or self.state != ConversationState.SPEAKING:
                    # Stop if interrupted
                    break
                
                # Send audio to output
                self.on_audio_output(audio_chunk)
                
        except Exception as e:
            logger.error(f"Error speaking sentence: {e}")
    
    async def stop(self):
        """Stop the orchestrator and clean up."""
        self.is_active = False
        await self.stt.stop()
        self.tts.stop()
        logger.info(f"Orchestrator stopped for session {self.session_id}")
    
    def get_state(self) -> ConversationState:
        """Get current conversation state."""
        return self.state
    
    def get_messages(self) -> List[Message]:
        """Get conversation history."""
        return self.messages
