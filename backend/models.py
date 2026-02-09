"""Data models for the speech-to-speech system."""
from pydantic import BaseModel
from typing import Literal, List, Optional
from enum import Enum


class ConversationState(str, Enum):
    """State machine for conversation management."""
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class Message(BaseModel):
    """Conversation message."""
    role: Literal["user", "assistant", "system"]
    content: str


class SessionCreate(BaseModel):
    """Request to create a new conversation session."""
    system_prompt: str = "You are a helpful voice assistant. Keep responses concise and conversational. Use short sentences suitable for speech. Avoid markdown or technical formatting."


class SessionResponse(BaseModel):
    """Response after creating a session."""
    session_id: str


class TranscriptEvent(BaseModel):
    """Transcript event sent to frontend."""
    role: Literal["user", "assistant"]
    text: str
    is_partial: bool = False


class STTResult(BaseModel):
    """Speech-to-text result."""
    text: str
    is_final: bool
    speech_final: bool = False
