/**
 * VoiceSDK v1.0.0 — Embeddable Voice Conversation SDK
 * 
 * Add real-time voice conversation (STT + LLM + TTS) to ANY web app
 * with just a few lines of code.
 * 
 * QUICK START:
 * ─────────────────────────────────────────────────────────────
 *   <script src="https://YOUR_SERVER/voicesdk.js"></script>
 *   <script>
 *     const voice = new VoiceSDK({
 *       serverUrl: 'https://YOUR_SERVER',
 *       systemPrompt: 'You are a helpful assistant.',
 *       onUserTranscript: (text) => addMessage('user', text),
 *       onAIResponse:     (text) => addMessage('ai', text),
 *       onStateChange:    (state) => updateUI(state),
 *     });
 *     document.getElementById('callBtn').onclick = () => voice.toggleCall();
 *   </script>
 * ─────────────────────────────────────────────────────────────
 * 
 * @license MIT
 */
(function (root, factory) {
    if (typeof define === 'function' && define.amd) {
        define([], factory);
    } else if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.VoiceSDK = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    var VERSION = '1.0.0';

    /**
     * VoiceSDK — Main class
     * 
     * States: 'idle' | 'listening' | 'thinking' | 'speaking'
     * 
     * @param {Object} config
     * @param {string}   config.serverUrl        - Voice server URL (required)
     * @param {string}   config.systemPrompt     - System prompt for LLM
     * @param {Function} config.onUserTranscript - Called with (text) when user speech is finalized
     * @param {Function} config.onAIResponse     - Called with (text) when AI response is ready
     * @param {Function} config.onStateChange    - Called with (state) on state transitions
     * @param {Function} config.onError          - Called with (Error) on errors
     * @param {Function} config.onInterim        - Called with (text) for interim/partial speech
     * @param {Function} config.onCallStart      - Called when voice call starts
     * @param {Function} config.onCallEnd        - Called when voice call ends
     * @param {string}   config.greeting         - Auto-play greeting on first call (optional)
     * @param {number}   config.silenceTimeout   - ms of silence before sending to LLM (default: 1200)
     * @param {boolean}  config.ttsEnabled       - Enable text-to-speech (default: true)
     * @param {boolean}  config.useServerSTT     - Use server-side Deepgram STT instead of browser (default: false)
     * @param {string}   config.model            - LLM model name (optional, uses server default)
     * @param {number}   config.temperature      - LLM temperature (default: 0.7)
     * @param {number}   config.maxTokens        - LLM max tokens (default: 200)
     * @param {string}   config.lang             - Speech recognition language (default: 'en-US')
     * @param {string}   config.ttsModel         - TTS voice model (default: server default)
     */
    function VoiceSDK(config) {
        if (!config) config = {};
        if (!config.serverUrl) {
            throw new Error('VoiceSDK: serverUrl is required');
        }

        // Server
        this.serverUrl = config.serverUrl.replace(/\/+$/, '');

        // Callbacks (all optional, defaults to no-op)
        this.onUserTranscript = config.onUserTranscript || noop;
        this.onAIResponse     = config.onAIResponse     || noop;
        this.onStateChange    = config.onStateChange    || noop;
        this.onError          = config.onError          || noop;
        this.onInterim        = config.onInterim        || noop;
        this.onCallStart      = config.onCallStart      || noop;
        this.onCallEnd        = config.onCallEnd        || noop;

        // Options
        this.systemPrompt   = config.systemPrompt || 'You are a helpful voice assistant. Keep responses concise and conversational.';
        this.silenceTimeout = config.silenceTimeout || 1200;
        this.ttsEnabled     = config.ttsEnabled !== false;
        this.useServerSTT   = config.useServerSTT || false;
        this.model          = config.model || undefined;
        this.temperature    = config.temperature != null ? config.temperature : 0.7;
        this.maxTokens      = config.maxTokens || 200;
        this.lang           = config.lang || 'en-US';
        this.greeting       = config.greeting || null;
        this.ttsModel       = config.ttsModel || undefined;

        // Internal state
        this._state        = 'idle';
        this._callActive   = false;
        this._history      = [];
        this._recognition  = null;
        this._silenceTimer = null;
        this._currentAudio = null;
        this._isSpeaking   = false;
        this._pendingLLM   = false;
        this._aiPaused     = false;
        this._aiCooldown   = false;
        this._processedIdx = new Set();
        this._mediaRecorder = null;
        this._audioChunks   = [];
        this._silenceCtx    = null;
        this._hasGreeted    = false;
    }

    // ─── Static ───
    VoiceSDK.VERSION = VERSION;

    // ─── Public API ───

    /**
     * Start a voice call. Begins listening for user speech.
     */
    VoiceSDK.prototype.startCall = function () {
        var self = this;
        if (this._callActive) return Promise.resolve();
        this._callActive = true;
        this._setState('listening');
        this.onCallStart();

        // Greeting on first call
        var greetingPromise = Promise.resolve();
        if (this.greeting && !this._hasGreeted) {
            this._hasGreeted = true;
            this._history.push({ role: 'assistant', content: this.greeting });
            this.onAIResponse(this.greeting);
            if (this.ttsEnabled) {
                greetingPromise = this._playTTS(this.greeting);
            }
        }

        return greetingPromise.then(function () {
            if (!self._callActive) return;
            if (self.useServerSTT) {
                return self._startServerSTT();
            } else {
                self._startBrowserSTT();
            }
        });
    };

    /**
     * End the voice call.
     */
    VoiceSDK.prototype.endCall = function () {
        if (!this._callActive) return;
        this._callActive = false;
        this._stopAudio();
        clearTimeout(this._silenceTimer);

        if (this._recognition) {
            try { this._recognition.stop(); } catch (e) { /* ignore */ }
        }
        if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
            try { this._mediaRecorder.stop(); } catch (e) { /* ignore */ }
        }
        if (this._silenceCtx) {
            try { this._silenceCtx.close(); } catch (e) { /* ignore */ }
            this._silenceCtx = null;
        }

        // If last message was user and no LLM call pending, fire it
        var last = this._history[this._history.length - 1];
        if (last && last.role === 'user' && !this._pendingLLM) {
            this._sendToLLM();
        }

        this._setState('idle');
        this.onCallEnd();
    };

    /**
     * Toggle call on/off. Returns true if call is now active.
     */
    VoiceSDK.prototype.toggleCall = function () {
        if (this._callActive) {
            this.endCall();
        } else {
            this.startCall();
        }
        return this._callActive;
    };

    /**
     * Send a text message (works both during call and when idle).
     * During a call: sends to LLM and plays TTS response.
     * When idle: sends to LLM, returns response text only.
     */
    VoiceSDK.prototype.sendText = function (text) {
        if (!text || !text.trim()) return Promise.resolve();
        text = text.trim();

        // Stop current audio if speaking (barge-in)
        if (this._isSpeaking) {
            this._stopAudio();
        }

        this._history.push({ role: 'user', content: text });
        this.onUserTranscript(text);
        return this._sendToLLM();
    };

    /**
     * Get conversation history.
     */
    VoiceSDK.prototype.getHistory = function () {
        return this._history.slice();
    };

    /**
     * Get current state: 'idle' | 'listening' | 'thinking' | 'speaking'
     */
    VoiceSDK.prototype.getState = function () {
        return this._state;
    };

    /**
     * Check if call is active.
     */
    VoiceSDK.prototype.isActive = function () {
        return this._callActive;
    };

    /**
     * Clear conversation history.
     */
    VoiceSDK.prototype.clearHistory = function () {
        this._history = [];
        this._hasGreeted = false;
    };

    /**
     * Set a new system prompt (takes effect on next LLM call).
     */
    VoiceSDK.prototype.setSystemPrompt = function (prompt) {
        this.systemPrompt = prompt;
    };

    /**
     * Destroy the SDK instance and clean up all resources.
     */
    VoiceSDK.prototype.destroy = function () {
        this.endCall();
        this._history = [];
        this._recognition = null;
    };

    // ─── Private: State ───

    VoiceSDK.prototype._setState = function (state) {
        if (this._state !== state) {
            this._state = state;
            this.onStateChange(state);
        }
    };

    // ─── Private: Browser STT (Web Speech API) ───

    VoiceSDK.prototype._startBrowserSTT = function () {
        var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            this.onError(new Error('Speech recognition not supported. Use Chrome or Edge.'));
            this.endCall();
            return;
        }

        var self = this;
        this._recognition = new SR();
        this._recognition.continuous = true;
        this._recognition.interimResults = true;
        this._recognition.lang = this.lang;
        this._processedIdx = new Set();

        this._recognition.onresult = function (event) {
            // Block input while AI is speaking
            if (self._isSpeaking || self._aiPaused || self._aiCooldown) return;

            var currentInterim = '';

            for (var i = 0; i < event.results.length; i++) {
                var result = event.results[i];
                var text = result[0].transcript.trim();

                if (result.isFinal && text && !self._processedIdx.has(i)) {
                    self._processedIdx.add(i);
                    self.onInterim(''); // clear interim display

                    self._history.push({ role: 'user', content: text });
                    self.onUserTranscript(text);

                    // Wait for more sentences before sending
                    clearTimeout(self._silenceTimer);
                    self._silenceTimer = setTimeout(function () {
                        if (!self._pendingLLM) self._sendToLLM();
                    }, self.silenceTimeout);

                } else if (!result.isFinal) {
                    currentInterim += text;
                }
            }

            if (currentInterim && self._callActive) {
                self.onInterim(currentInterim);
            }
        };

        this._recognition.onend = function () {
            self._processedIdx = new Set();
            if (self._callActive && !self._aiPaused) {
                try { self._recognition.start(); } catch (e) { /* ignore */ }
            }
        };

        this._recognition.onerror = function (event) {
            if (event.error === 'no-speech' || event.error === 'aborted') return;
            self.onError(new Error('Speech recognition error: ' + event.error));
        };

        try {
            this._recognition.start();
        } catch (e) {
            this._recognition.stop();
            setTimeout(function () {
                try { self._recognition.start(); } catch (e2) { /* ignore */ }
            }, 150);
        }
    };

    // ─── Private: Server STT (Deepgram via /stt) ───

    VoiceSDK.prototype._startServerSTT = function () {
        var self = this;

        return navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        }).then(function (stream) {
            self._mediaStream = stream;
            var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : 'audio/webm';
            self._mediaRecorder = new MediaRecorder(stream, { mimeType: mimeType });
            self._audioChunks = [];

            self._mediaRecorder.ondataavailable = function (event) {
                if (event.data.size > 0) self._audioChunks.push(event.data);
            };

            self._mediaRecorder.onstop = function () {
                if (self._audioChunks.length === 0) return;
                var blob = new Blob(self._audioChunks, { type: mimeType });
                self._audioChunks = [];

                // Send to server for STT
                var formData = new FormData();
                formData.append('audio', blob, 'recording.webm');

                fetch(self.serverUrl + '/stt', { method: 'POST', body: formData })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.transcript && data.transcript.trim()) {
                            var text = data.transcript.trim();
                            self._history.push({ role: 'user', content: text });
                            self.onUserTranscript(text);
                            self._sendToLLM();
                        } else {
                            // No speech detected, resume recording
                            if (self._callActive && !self._isSpeaking) {
                                self._serverSTTRecord();
                            }
                        }
                    })
                    .catch(function (err) {
                        self.onError(err);
                        if (self._callActive && !self._isSpeaking) {
                            self._serverSTTRecord();
                        }
                    });
            };

            // Start silence detection + recording
            self._setupSilenceDetection(stream);
            self._serverSTTRecord();

        }).catch(function (err) {
            self.onError(new Error('Microphone access denied: ' + err.message));
            self.endCall();
        });
    };

    VoiceSDK.prototype._serverSTTRecord = function () {
        if (this._mediaRecorder && this._mediaRecorder.state === 'inactive' && this._callActive) {
            this._audioChunks = [];
            try { this._mediaRecorder.start(); } catch (e) { /* ignore */ }
        }
    };

    VoiceSDK.prototype._setupSilenceDetection = function (stream) {
        var self = this;
        this._silenceCtx = new (window.AudioContext || window.webkitAudioContext)();
        var src = this._silenceCtx.createMediaStreamSource(stream);
        var analyser = this._silenceCtx.createAnalyser();
        analyser.fftSize = 512;
        src.connect(analyser);

        var data = new Uint8Array(analyser.frequencyBinCount);
        var silentFrames = 0;
        var THRESHOLD = 10;
        var FRAMES_NEEDED = 30; // ~1s at rAF rate

        function check() {
            if (!self._callActive) return;
            analyser.getByteFrequencyData(data);
            var sum = 0;
            for (var i = 0; i < data.length; i++) sum += data[i];
            var avg = sum / data.length;

            if (avg < THRESHOLD) {
                silentFrames++;
                if (silentFrames >= FRAMES_NEEDED && self._mediaRecorder && self._mediaRecorder.state === 'recording') {
                    self._mediaRecorder.stop();
                    silentFrames = 0;
                }
            } else {
                silentFrames = 0;
                if (self._mediaRecorder && self._mediaRecorder.state === 'inactive' && !self._isSpeaking) {
                    self._serverSTTRecord();
                }
            }
            requestAnimationFrame(check);
        }
        requestAnimationFrame(check);
    };

    // ─── Private: LLM ───

    VoiceSDK.prototype._sendToLLM = function () {
        if (this._pendingLLM) return Promise.resolve();
        var self = this;
        this._pendingLLM = true;
        this._setState('thinking');

        var messages = [{ role: 'system', content: this.systemPrompt }].concat(this._history);
        var body = {
            messages: messages,
            temperature: this.temperature,
            max_tokens: this.maxTokens
        };
        if (this.model) body.model = this.model;

        return fetch(this.serverUrl + '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(function (resp) {
            if (!resp.ok) {
                return resp.json().catch(function () { return {}; }).then(function (err) {
                    throw new Error(err.error || 'Server error ' + resp.status);
                });
            }
            return resp.json();
        })
        .then(function (data) {
            var aiText = data.response;
            if (!aiText) throw new Error('Empty LLM response');

            self._history.push({ role: 'assistant', content: aiText });
            self.onAIResponse(aiText);

            // Play TTS if enabled and call is active
            if (self.ttsEnabled && self._callActive) {
                return self._playTTS(aiText);
            }
        })
        .catch(function (err) {
            self.onError(err);
        })
        .then(function () {
            self._pendingLLM = false;
            if (self._callActive) self._setState('listening');
        });
    };

    // ─── Private: TTS ───

    VoiceSDK.prototype._playTTS = function (text) {
        var self = this;

        this._setState('speaking');
        this._isSpeaking = true;
        this._aiPaused = true;

        // Pause browser STT so mic doesn't pick up AI audio
        if (this._recognition) {
            try { this._recognition.stop(); } catch (e) { /* ignore */ }
        }

        var body = { text: text };
        if (this.ttsModel) body.model = this.ttsModel;

        return fetch(this.serverUrl + '/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(function (resp) {
            if (!resp.ok) throw new Error('TTS request failed');
            return resp.json();
        })
        .then(function (data) {
            if (!data.audio) throw new Error('No audio in TTS response');

            var raw = atob(data.audio);
            var bytes = new Uint8Array(raw.length);
            for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

            var blob = new Blob([bytes], { type: 'audio/wav' });
            var url = URL.createObjectURL(blob);

            return new Promise(function (resolve) {
                self._currentAudio = new Audio(url);

                var cleanup = function () {
                    self._isSpeaking = false;
                    URL.revokeObjectURL(url);
                    // Brief cooldown to flush stale buffered results
                    self._aiCooldown = true;
                    setTimeout(function () {
                        self._aiCooldown = false;
                        self._aiPaused = false;
                        // Resume listening
                        if (self._callActive && self._recognition) {
                            try { self._recognition.start(); } catch (e) { /* ignore */ }
                        }
                        if (self._callActive && self.useServerSTT) {
                            self._serverSTTRecord();
                        }
                        if (self._callActive) self._setState('listening');
                        resolve();
                    }, 500);
                };

                self._currentAudio.onended = cleanup;
                self._currentAudio.onerror = cleanup;
                self._currentAudio.play().catch(cleanup);
            });
        })
        .catch(function (err) {
            self._isSpeaking = false;
            self._aiPaused = false;
            self._aiCooldown = false;
            // Still resume listening on error
            if (self._callActive && self._recognition) {
                try { self._recognition.start(); } catch (e) { /* ignore */ }
            }
            // Don't call onError for TTS failures — degrade gracefully
            console.warn('VoiceSDK TTS error:', err);
        });
    };

    VoiceSDK.prototype._stopAudio = function () {
        if (this._currentAudio) {
            this._currentAudio.pause();
            this._currentAudio.currentTime = 0;
            this._currentAudio = null;
        }
        this._isSpeaking = false;
        this._aiPaused = false;
        this._aiCooldown = false;
    };

    // ─── Helpers ───

    function noop() {}

    return VoiceSDK;
}));
