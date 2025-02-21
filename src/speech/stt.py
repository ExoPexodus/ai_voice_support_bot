# src/speech/stt.py

import azure.cognitiveservices.speech as speechsdk
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
import concurrent.futures

def _recognize_once():
    # Create an instance of a speech config with your subscription key and service region.
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    
    # Creates a recognizer with the given settings
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)
    
    print("Say something...")
    
    # Starts speech recognition (single utterance)
    result = speech_recognizer.recognize_once()
    
    # Checks result as per the official Azure guide
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        print("Recognized: {}".format(result.text))
        return result.text
    elif result.reason == speechsdk.ResultReason.NoMatch:
        print("No speech could be recognized: {}".format(result.no_match_details))
        return None
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("Speech Recognition canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print("Error details: {}".format(cancellation_details.error_details))
        return None

def speech_to_text(timeout=30):
    """
    Listens for user speech and returns the recognized text.
    If no speech is detected within 'timeout' seconds, returns None.
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_recognize_once)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print("No speech input for 30 seconds.")
            return None

if __name__ == "__main__":
    text = speech_to_text()
    print("STT Output:", text)
