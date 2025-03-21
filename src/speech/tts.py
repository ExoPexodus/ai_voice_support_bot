# src/speech/tts.py
import azure.cognitiveservices.speech as speechsdk
import subprocess
import os
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, AZURE_TTS_VOICE

def ensure_symlink():
    """
    Ensure that a symlink exists from the Asterisk sounds directory to /dev/shm.
    This allows Asterisk to access in-memory TTS audio files.
    """
    sounds_dir = "/var/lib/asterisk/sounds"
    symlink_path = os.path.join(sounds_dir, "dev_shm")
    
    # If the symlink already exists and points to /dev/shm, we're done.
    if os.path.islink(symlink_path):
        if os.readlink(symlink_path) == "/dev/shm":
            return symlink_path
        else:
            os.remove(symlink_path)  # Remove incorrect symlink

    # Create the symlink if it doesn't exist.
    try:
        os.symlink("/dev/shm", symlink_path)
        print(f"Symlink created: {symlink_path} -> /dev/shm")
    except Exception as e:
        print(f"Failed to create symlink: {e}")
    return symlink_path


def speak_text_stream(text, filename_base):
    """
    Synthesizes speech from text using Azure TTS streaming, writing audio bytes to a file.
    The output file is written in a symlinked in-memory folder for low latency.
    
    NOTE: We use a supported format (PCM) since your neural voice may not support mu-law directly.
    """
    # Get the symlink path (e.g., /var/lib/asterisk/sounds/dev_shm)
    symlink_path = ensure_symlink()
    # Build the output file path in the symlinked directory.
    output_path = os.path.join(symlink_path, f"{filename_base}.wav")
    
    # Configure speech synthesis settings.
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    speech_config.speech_synthesis_voice_name = AZURE_TTS_VOICE or "en-IN-NeerjaNeural"
    # Use a supported output format (PCM)
    speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    
    # Create a synthesizer without an audio output configuration.
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    
    # Synthesize the text.
    result = synthesizer.speak_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        cancellation_details = result.cancellation_details
        raise Exception(f"Speech synthesis canceled: {cancellation_details.reason}, {cancellation_details.error_details}")
    
    # Get the audio data stream.
    audio_stream = speechsdk.AudioDataStream(result)
    
    # Write the stream data in chunks.
    chunk_size = 1024
    with open(output_path, "wb") as f:
        while True:
            chunk = audio_stream.read_data(chunk_size)
            if len(chunk) == 0:
                break
            f.write(chunk)
    
    return output_path

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
