from deepgram import DeepgramClient

client = DeepgramClient(api_key='6985219805a7076276962e72ee835d9bd9961747')

with open('debug_audio_converted.wav', 'rb') as f:
    audio_data = f.read()

print(f'WAV size: {len(audio_data)} bytes')

response = client.listen.v1.media.transcribe_file(
    request=audio_data,
    model='nova-2',
    smart_format=True,
    punctuate=True,
)

if response and response.results and response.results.channels:
    alt = response.results.channels[0].alternatives[0]
    print(f'Transcript: "{alt.transcript}"')
    print(f'Confidence: {alt.confidence}')
else:
    print('No results')
