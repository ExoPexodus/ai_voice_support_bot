# src/speech/stt.py

import azure.cognitiveservices.speech as speechsdk
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION

def speech_to_text():
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    # For now, using the default microphone; in production, you may adjust this
    audio_config = speechsdk.AudioConfig(use_default_microphone=True)
    
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    print("Listening for your voice...")
    
    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        print(f"Recognized: {result.text}")
        return result.text
    else:
        print("Uh-oh, didn't catch that.")
        return None

if __name__ == "__main__":
    text = speech_to_text()
    print("STT Output:", text)
