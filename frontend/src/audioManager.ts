/**
 * Audio manager for handling microphone input and audio output.
 */

export class AudioManager {
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private isRecording = false;

  /**
   * Initialize audio context and request microphone permission.
   */
  async initialize(): Promise<void> {
    // Create audio context
    this.audioContext = new AudioContext({ sampleRate: 16000 });

    // Request microphone access
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  }

  /**
   * Start recording and streaming audio.
   */
  async startRecording(onAudioData: (data: ArrayBuffer) => void): Promise<void> {
    if (!this.audioContext || !this.mediaStream) {
      throw new Error('Audio not initialized');
    }

    this.isRecording = true;

    // Create source node
    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);

    // Create script processor (alternative to AudioWorklet for better compatibility)
    const processor = this.audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (event) => {
      if (!this.isRecording) return;

      const inputData = event.inputBuffer.getChannelData(0);
      
      // Convert float32 to int16 PCM
      const pcmData = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }

      // Send to callback
      onAudioData(pcmData.buffer);
    };

    // Connect nodes
    this.sourceNode.connect(processor);
    processor.connect(this.audioContext.destination);
  }

  /**
   * Stop recording.
   */
  stopRecording(): void {
    this.isRecording = false;

    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
  }

  /**
   * Play audio data through speakers.
   */
  async playAudio(audioData: ArrayBuffer): Promise<void> {
    if (!this.audioContext) {
      throw new Error('Audio not initialized');
    }

    // Convert Int16 PCM to Float32
    const pcmData = new Int16Array(audioData);
    const float32Data = new Float32Array(pcmData.length);
    
    for (let i = 0; i < pcmData.length; i++) {
      float32Data[i] = pcmData[i] / (pcmData[i] < 0 ? 0x8000 : 0x7FFF);
    }

    // Create audio buffer
    const audioBuffer = this.audioContext.createBuffer(
      1,
      float32Data.length,
      16000
    );
    audioBuffer.getChannelData(0).set(float32Data);

    // Create source and play
    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);
    source.start();
  }

  /**
   * Clean up resources.
   */
  cleanup(): void {
    this.stopRecording();

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }

  /**
   * Check if recording is active.
   */
  get recording(): boolean {
    return this.isRecording;
  }
}
