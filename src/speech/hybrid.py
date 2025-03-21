import azure.cognitiveservices.speech as speechsdk
import time
import asyncio

class HybridSTT:
    def __init__(self, subscription_key, region, silence_threshold=1.5):
        self.speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)
        self.speech_config.speech_recognition_language = "en-US"
        self.recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config)
        self.silence_threshold = silence_threshold  # seconds
        self.last_result_time = time.time()
        self.buffered_text = ""
        self.on_finalized = None  # Callback when silence is detected

        self.recognizer.recognizing.connect(self._recognizing_cb)
        self.recognizer.recognized.connect(self._recognized_cb)
        self.recognizer.canceled.connect(lambda evt: print(f"[STT] Canceled: {evt}"))
        self.recognizer.session_stopped.connect(lambda evt: print("[STT] Session stopped."))

    def _recognizing_cb(self, evt):
        # Update timestamp on interim results
        self.last_result_time = time.time()
        interim = evt.result.text
        # You can choose to update the buffer gradually; here we just replace it.
        self.buffered_text = interim
        print(f"[STT] Interim result: {interim}")

    def _recognized_cb(self, evt):
        self.last_result_time = time.time()
        final = evt.result.text
        print(f"[STT] Final result: {final}")
        if final:
            # Append to buffer (or replace, depending on your use case)
            self.buffered_text += " " + final

    async def monitor_silence(self):
        # Monitor until silence exceeds threshold
        while True:
            await asyncio.sleep(0.3)
            if time.time() - self.last_result_time >= self.silence_threshold and self.buffered_text.strip():
                finalized = self.buffered_text.strip()
                print(f"[STT] Silence detected. Finalized: {finalized}")
                if self.on_finalized:
                    self.on_finalized(finalized)
                break

    async def start_recognition(self):
        # Start continuous recognition and monitor silence concurrently.
        print("[STT] Starting continuous recognition...")
        self.recognizer.start_continuous_recognition()
        await self.monitor_silence()
        self.recognizer.stop_continuous_recognition()
        # Return the buffered text
        return self.buffered_text.strip()