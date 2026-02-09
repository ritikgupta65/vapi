/**
 * Type definitions for the speech-to-speech system.
 */

export interface SessionCreate {
  system_prompt: string;
}

export interface SessionResponse {
  session_id: string;
}

export interface TranscriptEvent {
  role: 'user' | 'assistant';
  text: string;
  is_partial: boolean;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  is_partial: boolean;
  timestamp: Date;
}

export type ConversationState = 'listening' | 'thinking' | 'speaking';
