import os
from twilio.rest import Client
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from src.speech.tts import text_to_speech
from src.speech.stt import speech_to_text
from src.config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, TWILIO_WEBHOOK_URL
)

app = Flask(__name__)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def make_call(to_number, message):
    """
    Initiates a call and reads the given message using Azure TTS.
    """
    print(f"[INFO] Calling {to_number}...")

    # Convert text to speech and generate an audio file (MP3)
    audio_file = f"tts_output_{to_number}.mp3"
    text_to_speech(message)

    # Create Twilio call
    call = twilio_client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=TWILIO_WEBHOOK_URL  # Twilio fetches response from this webhook
    )

    print(f"[INFO] Call initiated: {call.sid}")
    return call.sid

@app.route("/twilio/webhook", methods=["POST"])
def twilio_webhook():
    """
    Handles incoming Twilio calls, records speech, and processes it with Azure STT.
    """
    print("[INFO] Incoming call detected!")

    response = VoiceResponse()
    response.say("Hello! you are being redirected to our customer support service.", voice="alice")
    response.record(max_length=10, timeout=5, play_beep=True, action="/twilio/process_voice")

    return Response(str(response), mimetype="text/xml")

@app.route("/twilio/process_voice", methods=["POST"])
def process_voice():
    """
    Processes recorded voice message from Twilio and transcribes it.
    """
    recording_url = request.form.get("RecordingUrl")
    print(f"[INFO] Recording received: {recording_url}")

    # Download audio and transcribe using Azure STT
    transcribed_text = speech_to_text()
    
    if transcribed_text:
        print(f"[INFO] Transcribed: {transcribed_text}")
        response_text = f"Thank you. Your order ID is {transcribed_text}."
    else:
        response_text = "Sorry, I couldn't understand your response."

    # Respond with the transcribed text
    response = VoiceResponse()
    response.say(response_text, voice="alice")
    
    return Response(str(response), mimetype="text/xml")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
