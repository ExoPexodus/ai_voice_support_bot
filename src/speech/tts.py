# src/speech/tts.py
import azure.cognitiveservices.speech as speechsdk
import subprocess
import os
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, AZURE_TTS_VOICE

def text_to_speech(text):
    """
    Converts text to speech using Azure TTS and plays via default speaker.
    """
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    # Choose your voice
    speech_config.speech_synthesis_voice_name = AZURE_TTS_VOICE or "en-IN-NeerjaNeural"
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
    Converts text to speech using Azure TTS and saves the audio output as a WAV file.
    Then it converts the WAV file to mu-law (ulaw) format using ffmpeg.
    
    :param text: Text to be synthesized.
    :param output_file: Full path for the generated WAV file (e.g., /var/lib/asterisk/sounds/response.wav).
                        The final file will be saved as the same base name with a .ulaw extension.
    """
    # Generate the WAV file using Azure TTS
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    speech_config.speech_synthesis_voice_name = AZURE_TTS_VOICE or "en-IN-NeerjaNeural"
    # Do not set an output format here since we'll do conversion with ffmpeg.
    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    result = synthesizer.speak_text_async(text).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"[INFO] Generated TTS WAV file at: {output_file}")
        # Convert the WAV file to mu-law using ffmpeg.
        base, _ = os.path.splitext(output_file)
        final_file = base + ".ulaw"
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", output_file,
                "-ar", "8000", "-ac", "1", "-f", "mulaw", final_file
            ], check=True)
            print(f"[INFO] Converted to mu-law file: {final_file}")
        except subprocess.CalledProcessError as e:
            print("[ERROR] ffmpeg conversion failed:", e)
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("[ERROR] TTS file generation canceled:", cancellation_details.reason)

if __name__ == "__main__":
    # Test TTS: generate a file and play via default speaker
    test_output = "/var/lib/asterisk/sounds/test_tts.wav"
    generate_tts_file("Hello, how can I assist you today?", test_output)
    text_to_speech("Hello, how can I assist you today?")
