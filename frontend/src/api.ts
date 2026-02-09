/**
 * API client for the speech-to-speech backend.
 */

import { SessionCreate, SessionResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace('http', 'ws');

export class SpeechToSpeechAPI {
  /**
   * Create a new conversation session.
   */
  static async createSession(systemPrompt: string): Promise<string> {
    const response = await fetch(`${API_BASE_URL}/session`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        system_prompt: systemPrompt,
      } as SessionCreate),
    });

    if (!response.ok) {
      throw new Error('Failed to create session');
    }

    const data: SessionResponse = await response.json();
    return data.session_id;
  }

  /**
   * Delete a conversation session.
   */
  static async deleteSession(sessionId: string): Promise<void> {
    await fetch(`${API_BASE_URL}/session/${sessionId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Create WebSocket connection for audio input.
   */
  static createAudioInputSocket(sessionId: string): WebSocket {
    return new WebSocket(`${WS_BASE_URL}/session/${sessionId}/audio/in`);
  }

  /**
   * Create WebSocket connection for audio output.
   */
  static createAudioOutputSocket(sessionId: string): WebSocket {
    return new WebSocket(`${WS_BASE_URL}/session/${sessionId}/audio/out`);
  }

  /**
   * Create WebSocket connection for transcript events.
   */
  static createTranscriptSocket(sessionId: string): WebSocket {
    return new WebSocket(`${WS_BASE_URL}/session/${sessionId}/transcript`);
  }
}
