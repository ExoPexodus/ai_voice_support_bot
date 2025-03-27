import asyncio
import ari
import time
import azure.cognitiveservices.speech as speechsdk
from src.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION

# Assume HybridSTT is defined as in our previous implementation.
from src.stt.hybrid import HybridSTT

# ARI configuration (ensure these match your Asterisk settings)
ARI_URL = "http://localhost:8088"
ARI_USERNAME = "asterisk"
ARI_PASSWORD = "pythonaritest"
STASIS_APP = "voicebot"

async def handle_channel(channel):
    """
    Handle a channel from ARI: subscribe to its media events and feed live audio into Azure STT.
    """
    print(f"[ARI] Channel {channel.id} joined.")
    
    # Create our hybrid STT instance
    stt_handler = HybridSTT(AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, silence_threshold=1.5)
    
    def on_media(event, channel):
        # Extract audio data from the event.
        # NOTE: The exact property depends on your ARI version; adjust as needed.
        audio_bytes = event.get("media")  # pseudo-code: adjust to actual ARI media event structure.
        if audio_bytes:
            stt_handler.feed_audio(audio_bytes)
    
    # Subscribe to media events for this channel
    channel.on("Media", on_media)
    print(f"[ARI] Subscribed to media events for channel {channel.id}")
    
    # Start STT recognition concurrently and wait until silence is detected.
    transcript = await stt_handler.start_recognition()
    print(f"[ARI] Final transcript for channel {channel.id}: {transcript}")
    stt_handler.close()
    
    # Here, you can forward the transcript to your LLM for a response.
    return transcript

async def main():
    # Connect to ARI using the ARI library
    client = ari.connect(ARI_URL, ARI_USERNAME, ARI_PASSWORD, app=STASIS_APP)
    print("[ARI] Connected to ARI. Waiting for channels to join...")
    
    # Wait for a channel to join the Stasis application
    future = asyncio.Future()
    
    def on_channel(channel, ev):
        print(f"[ARI] Channel {channel.id} has joined Stasis app.")
        if not future.done():
            future.set_result(channel)
    
    client.on_channel_event("StasisStart", on_channel)
    
    channel = await future  # Wait until a channel joins.
    transcript = await handle_channel(channel)
    print("Final Transcript:", transcript)
    
if __name__ == "__main__":
    asyncio.run(main())
