/**
 * Microphone button component with visual feedback.
 */

import React from 'react';

interface MicButtonProps {
  isRecording: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  onClick: () => void;
}

export const MicButton: React.FC<MicButtonProps> = ({
  isRecording,
  isListening,
  isSpeaking,
  onClick,
}) => {
  const getButtonState = () => {
    if (!isRecording) {
      return {
        bg: 'bg-blue-500 hover:bg-blue-600',
        text: 'Start Conversation',
        icon: 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z',
        animation: '',
      };
    }

    if (isSpeaking) {
      return {
        bg: 'bg-purple-500',
        text: 'AI Speaking',
        icon: 'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z',
        animation: 'animate-pulse-slow',
      };
    }

    if (isListening) {
      return {
        bg: 'bg-green-500',
        text: 'Listening...',
        icon: 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z',
        animation: 'animate-bounce-slow',
      };
    }

    return {
      bg: 'bg-yellow-500',
      text: 'Processing...',
      icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
      animation: 'animate-spin',
    };
  };

  const state = getButtonState();

  return (
    <div className="flex flex-col items-center space-y-4">
      <button
        onClick={onClick}
        className={`
          relative w-20 h-20 rounded-full ${state.bg} 
          shadow-2xl transition-all duration-300 
          transform hover:scale-110 active:scale-95
          flex items-center justify-center
          ${state.animation}
        `}
      >
        <svg
          className="w-10 h-10 text-white"
          fill="currentColor"
          viewBox="0 0 24 24"
        >
          <path d={state.icon} />
        </svg>

        {isRecording && (
          <div className="absolute -inset-2 rounded-full border-4 border-blue-300 animate-ping opacity-75" />
        )}
      </button>

      <p className="text-sm font-medium text-gray-700">{state.text}</p>
    </div>
  );
};
