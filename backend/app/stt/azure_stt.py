import azure.cognitiveservices.speech as speechsdk

def make_speech_recognizer(key: str, region: str, lang: str = "en-US", phrase_list: list[str] | None = None):
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic")
    speech_config.speech_recognition_language = lang
    audio_stream = speechsdk.audio.PushAudioInputStream()
    audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    if phrase_list:
        grammar = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
        for phrase in phrase_list:
            grammar.addPhrase(phrase)
    return recognizer, audio_stream
