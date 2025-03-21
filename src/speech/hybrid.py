import azure.cognitiveservices.speech as speechsdk
import time
import asyncio

class HybridSTT:
    def __init__(self, subscription_key, region, silence_threshold=1.5):
        self.speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)
        self.speech_config.speech_recognition_language = "en-US"
        # Create a push stream so we can feed audio data (from our recorded file)
        self.push_stream = speechsdk.audio.PushAudioInputStream()
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)
        self.recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config, audio_config=self.audio_config)
        self.silence_threshold = silence_threshold  # seconds
        self.last_result_time = time.time()
        self.buffered_text = ""
        self.on_finalized = None  # Callback when silence is detected

        # Connect event callbacks
        self.recognizer.recognizing.connect(self._recognizing_cb)
        self.recognizer.recognized.connect(self._recognized_cb)
        self.recognizer.canceled.connect(lambda evt: print(f"[STT] Canceled: {evt}"))
        self.recognizer.session_stopped.connect(lambda evt: print("[STT] Session stopped."))

    def _recognizing_cb(self, evt):
        self.last_result_time = time.time()
        interim = evt.result.text
        # Update the buffer with the latest interim result.
        self.buffered_text = interim
        print(f"[STT] Interim: {interim}")

    def _recognized_cb(self, evt):
        self.last_result_time = time.time()
        final = evt.result.text
        print(f"[STT] Recognized: {final}")
        if final:
            # Append final recognized text.
            self.buffered_text += " " + final

    async def monitor_silence(self):
        # Monitor for silence until the time gap exceeds threshold.
        while True:
            await asyncio.sleep(0.3)
            if time.time() - self.last_result_time >= self.silence_threshold and self.buffered_text.strip():
                finalized = self.buffered_text.strip()
                print(f"[STT] Silence detected; Finalized: {finalized}")
                if self.on_finalized:
                    self.on_finalized(finalized)
                break

    def feed_audio_from_file(self, file_path, chunk_size=1024):
        """
        Reads the recorded audio file and writes its content into the push stream.
        """
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.push_stream.write(chunk)
            # Once done, signal end-of-stream.
            self.push_stream.close()
        except Exception as e:
            print(f"[STT] Error feeding audio: {e}")

    async def start_recognition(self):
        """
        Starts continuous recognition and monitors silence.
        This method should be called after feeding audio into the push stream.
        """
        print("[STT] Starting continuous recognition...")
        self.recognizer.start_continuous_recognition()
        await self.monitor_silence()
        self.recognizer.stop_continuous_recognition()
        return self.buffered_text.strip()
