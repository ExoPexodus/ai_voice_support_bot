import azure.cognitiveservices.speech as speechsdk
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, AZURE_TTS_VOICE

def text_to_speech(text):
    """
    Converts text to speech using Azure TTS and plays via default speaker.
    """
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    # You can choose your voice here (for example, "en-IN-NeerjaNeural")
    speech_config.speech_synthesis_voice_name = "en-IN-NeerjaNeural"
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    result = synthesizer.speak_text_async(text).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"[INFO] Synthesized speech: {text}")
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("[ERROR] Speech synthesis canceled:", cancellation_details.reason)

def generate_tts_file(text, output_file):
    """
    Converts text to speech using Azure TTS and saves the audio output to a file.
    The output_file should be a full path (e.g., /var/lib/asterisk/sounds/welcome.wav).
    """
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    # Configure the desired voice
    speech_config.speech_synthesis_voice_name = "en-IN-NeerjaNeural"
    # Use AudioOutputConfig with filename to save to file
    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    result = synthesizer.speak_text_async(text).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"[INFO] Generated TTS file at: {output_file}")
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("[ERROR] TTS file generation canceled:", cancellation_details.reason)

if __name__ == "__main__":
    # For testing: generate a TTS file and play via default speaker
    generate_tts_file("Hello, how can I assist you today?", "output.wav")
    text_to_speech("Hello, how can I assist you today?")
