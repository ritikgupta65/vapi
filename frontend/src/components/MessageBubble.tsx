/**
 * Message component for displaying user and AI messages.
 */

import React from 'react';
import { Message } from '../types';

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const isPartial = message.is_partial;

  return (
    <div
      className={`mb-4 animate-fade-in ${
        isUser ? 'text-right' : 'text-left'
      }`}
    >
      <div
        className={`inline-block max-w-[80%] px-4 py-3 rounded-2xl ${
          isUser
            ? 'bg-blue-500 text-white rounded-br-none'
            : 'bg-gray-200 text-gray-900 rounded-bl-none'
        } ${isPartial ? 'opacity-50 italic' : ''}`}
      >
        <p className="text-sm md:text-base leading-relaxed whitespace-pre-wrap">
          {message.text}
        </p>
        {isPartial && (
          <span className="text-xs opacity-70 mt-1 block">
            (transcribing...)
          </span>
        )}
      </div>
    </div>
  );
};
