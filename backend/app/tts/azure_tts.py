import azure.cognitiveservices.speech as speechsdk


def synth_wav(text: str, key: str, region: str, voice: str) -> bytes:
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(text).get()
    return bytes(result.audio_data)
