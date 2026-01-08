import asyncio
import html
import azure.cognitiveservices.speech as speechsdk

def _voice_locale(voice: str) -> str:
    parts = voice.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "en-US"

def _build_ssml(text: str, voice: str, rate: str) -> str:
    locale = _voice_locale(voice)
    escaped = html.escape(text)
    return f'<speak version="1.0" xml:lang="{locale}"><voice name="{voice}"><prosody rate="{rate}">{escaped}</prosody></voice></speak>'

def synth_wav(text: str, key: str, region: str, voice: str, rate: str = "medium") -> bytes:
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    # speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    ssml = _build_ssml(text, voice, rate)
    result = synthesizer.speak_ssml_async(ssml).get()
    return bytes(result.audio_data)

async def stream_pcm(text: str, key: str, region: str, voice: str, sample_rate: int, rate: str = "medium"):
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    format_map = {
        8000: speechsdk.SpeechSynthesisOutputFormat.Raw8Khz16BitMonoPcm,
        16000: speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm,
        24000: speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm,
        48000: speechsdk.SpeechSynthesisOutputFormat.Raw48Khz16BitMonoPcm,
    }
    output_format = format_map.get(sample_rate)
    if not output_format:
        raise ValueError(f"Unsupported TTS sample rate: {sample_rate}")
    speech_config.set_speech_synthesis_output_format(output_format)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    done = asyncio.Event()

    def on_synth(evt):
        audio = evt.result.audio_data
        if audio:
            loop.call_soon_threadsafe(queue.put_nowait, audio)

    def on_done(_evt):
        loop.call_soon_threadsafe(done.set)

    synthesizer.synthesizing.connect(on_synth)
    synthesizer.synthesis_completed.connect(on_done)
    synthesizer.synthesis_canceled.connect(on_done)

    ssml = _build_ssml(text, voice, rate)
    synthesizer.start_speaking_ssml_async(ssml)
    while True:
        if done.is_set() and queue.empty():
            break
        try:
            chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue
        yield chunk
