import azure.cognitiveservices.speech as speechsdk
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, AZURE_STT_LANGUAGE

def recognize_from_file(audio_file):
    """
    Recognizes speech from an audio file using Azure STT.
    :param audio_file: Full path to the WAV file to be transcribed.
    :return: Transcribed text or None if recognition fails.
    """
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    # Use the configured language from your config or hard-code (e.g., "en-IN")
    language = AZURE_STT_LANGUAGE if AZURE_STT_LANGUAGE else "en-IN"
    audio_config = speechsdk.audio.AudioConfig(filename=audio_file)
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, language=language, audio_config=audio_config)
    
    result = speech_recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        print(f"[INFO] Recognized from file: {result.text}")
        return result.text
    elif result.reason == speechsdk.ResultReason.NoMatch:
        print("[WARNING] No speech recognized from file.")
        return None
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print(f"[ERROR] Speech recognition canceled: {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print(f"Error details: {cancellation_details.error_details}")
        return None

def speech_to_text(timeout=30):
    """
    Listens for user speech live and returns the recognized text.
    (This is the original live STT function.)
    """
    import concurrent.futures

    def _recognize_once():
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        # Here you can use AZURE_STT_LANGUAGE or a hardcoded language
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, language=AZURE_STT_LANGUAGE)
        print(f"Say something... (Listening in {AZURE_STT_LANGUAGE})")
        result = speech_recognizer.recognize_once()
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print(f"[INFO] Recognized: {result.text}")
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            print("[WARNING] No speech recognized.")
            return None
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"[ERROR] Speech recognition canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                print(f"Error details: {cancellation_details.error_details}")
            return None

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_recognize_once)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print("[WARNING] No speech input for 30 seconds.")
            return None

if __name__ == "__main__":
    # For testing: use a local file for recognition
    text = recognize_from_file("sample.wav")  # Replace with a valid WAV file path
    print("STT Output:", text)
