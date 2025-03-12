import azure.cognitiveservices.speech as speechsdk
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, AZURE_STT_LANGUAGE
import concurrent.futures

def _recognize_once():
    """
    Recognizes speech once using Azure STT with a configurable language.
    """
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, language="en-IN")
#    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, language=AZURE_STT_LANGUAGE)

    print(f"Say something... (Listening in {AZURE_STT_LANGUAGE})")

    result = speech_recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        print(f"[INFO] Recognized: {result.text}")
        return result.text
    elif result.reason == speechsdk.ResultReason.NoMatch:
        print(f"[WARNING] No speech recognized.")
        return None
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print(f"[ERROR] Speech recognition canceled: {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print(f"Error details: {cancellation_details.error_details}")
        return None

def speech_to_text(timeout=120):
    """
    Listens for user speech and returns the recognized text.
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_recognize_once)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print("[WARNING] No speech input for 30 seconds.")
            return None

if __name__ == "__main__":
    text = speech_to_text()
    print("STT Output:", text)
