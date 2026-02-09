/**
 * Main App component - orchestrates the entire speech-to-speech UI.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Message, TranscriptEvent, ConversationState } from './types';
import { SpeechToSpeechAPI } from './api';
import { AudioManager } from './audioManager';
import { TranscriptPanel } from './components/TranscriptPanel';
import { MicButton } from './components/MicButton';

const SYSTEM_PROMPT = `You are a helpful voice assistant. Keep responses concise and conversational. Use short sentences suitable for speech. Avoid markdown or technical formatting. Be friendly and natural.`;

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [conversationState, setConversationState] = useState<ConversationState>('listening');
  const [error, setError] = useState<string | null>(null);

  // Refs for WebSocket connections
  const audioInputWs = useRef<WebSocket | null>(null);
  const audioOutputWs = useRef<WebSocket | null>(null);
  const transcriptWs = useRef<WebSocket | null>(null);
  const audioManager = useRef<AudioManager>(new AudioManager());

  // Track partial message for updates
  const partialMessageRef = useRef<string | null>(null);

  /**
   * Initialize session and WebSocket connections.
   */
  const initializeSession = useCallback(async () => {
    try {
      // Create session
      const newSessionId = await SpeechToSpeechAPI.createSession(SYSTEM_PROMPT);
      setSessionId(newSessionId);

      // Initialize audio
      await audioManager.current.initialize();

      // Connect WebSockets
      connectWebSockets(newSessionId);

      setError(null);
    } catch (err) {
      console.error('Failed to initialize session:', err);
      setError('Failed to initialize. Please check your connection.');
    }
  }, []);

  /**
   * Connect all WebSocket connections.
   */
  const connectWebSockets = (sessionId: string) => {
    // Audio input WebSocket
    audioInputWs.current = SpeechToSpeechAPI.createAudioInputSocket(sessionId);
    audioInputWs.current.onopen = () => console.log('Audio input connected');
    audioInputWs.current.onerror = (err) => console.error('Audio input error:', err);

    // Audio output WebSocket
    audioOutputWs.current = SpeechToSpeechAPI.createAudioOutputSocket(sessionId);
    audioOutputWs.current.onopen = () => console.log('Audio output connected');
    audioOutputWs.current.onmessage = async (event) => {
      // Play received audio
      if (event.data instanceof Blob) {
        const arrayBuffer = await event.data.arrayBuffer();
        await audioManager.current.playAudio(arrayBuffer);
      } else if (event.data instanceof ArrayBuffer) {
        await audioManager.current.playAudio(event.data);
      }
    };
    audioOutputWs.current.onerror = (err) => console.error('Audio output error:', err);

    // Transcript WebSocket
    transcriptWs.current = SpeechToSpeechAPI.createTranscriptSocket(sessionId);
    transcriptWs.current.onopen = () => console.log('Transcript connected');
    transcriptWs.current.onmessage = (event) => {
      const transcriptEvent: TranscriptEvent = JSON.parse(event.data);
      handleTranscriptEvent(transcriptEvent);
    };
    transcriptWs.current.onerror = (err) => console.error('Transcript error:', err);
  };

  /**
   * Handle incoming transcript events.
   */
  const handleTranscriptEvent = (event: TranscriptEvent) => {
    const messageId = `${event.role}-${Date.now()}`;

    if (event.is_partial) {
      // Update or add partial message
      setMessages((prev) => {
        const existingIndex = prev.findIndex(
          (m) => m.role === event.role && m.is_partial
        );

        const newMessage: Message = {
          id: messageId,
          role: event.role,
          text: event.text,
          is_partial: true,
          timestamp: new Date(),
        };

        if (existingIndex >= 0) {
          // Update existing partial
          const updated = [...prev];
          updated[existingIndex] = newMessage;
          return updated;
        } else {
          // Add new partial
          return [...prev, newMessage];
        }
      });

      partialMessageRef.current = messageId;
    } else {
      // Final message
      setMessages((prev) => {
        // Remove any partial messages for this role
        const filtered = prev.filter((m) => !(m.role === event.role && m.is_partial));

        // Add final message
        return [
          ...filtered,
          {
            id: messageId,
            role: event.role,
            text: event.text,
            is_partial: false,
            timestamp: new Date(),
          },
        ];
      });

      partialMessageRef.current = null;

      // Update conversation state
      if (event.role === 'assistant') {
        setConversationState('listening');
      }
    }
  };

  /**
   * Toggle recording on/off.
   */
  const toggleRecording = async () => {
    if (!isRecording) {
      // Start recording
      if (!sessionId) {
        await initializeSession();
        // Wait a bit for connections to establish
        await new Promise(resolve => setTimeout(resolve, 1000));
      }

      setIsRecording(true);
      setConversationState('listening');

      await audioManager.current.startRecording((audioData) => {
        // Send audio to backend
        if (audioInputWs.current?.readyState === WebSocket.OPEN) {
          audioInputWs.current.send(audioData);
        }
      });
    } else {
      // Stop recording
      setIsRecording(false);
      audioManager.current.stopRecording();
    }
  };

  /**
   * Cleanup on unmount.
   */
  useEffect(() => {
    return () => {
      audioManager.current.cleanup();
      audioInputWs.current?.close();
      audioOutputWs.current?.close();
      transcriptWs.current?.close();

      if (sessionId) {
        SpeechToSpeechAPI.deleteSession(sessionId).catch(console.error);
      }
    };
  }, [sessionId]);

  return (
    <div className="h-screen w-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex flex-col">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900">
            Speech-to-Speech AI
          </h1>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  sessionId ? 'bg-green-500' : 'bg-gray-300'
                } animate-pulse`}
              />
              <span className="text-sm text-gray-600">
                {sessionId ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4">
          <p className="font-medium">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Transcript panel */}
        <div className="flex-1 bg-white shadow-lg">
          <TranscriptPanel messages={messages} />
        </div>
      </div>

      {/* Control panel */}
      <div className="bg-white border-t border-gray-200 px-6 py-8 shadow-lg">
        <div className="max-w-7xl mx-auto flex justify-center">
          <MicButton
            isRecording={isRecording}
            isListening={conversationState === 'listening' && isRecording}
            isSpeaking={conversationState === 'speaking'}
            onClick={toggleRecording}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
