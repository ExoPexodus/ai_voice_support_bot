#!/storage/code/ai_voice_support_bot/venv/bin/python3
"""
agi_main.py - AGI entry point for your Zomato customer support bot.
This script is invoked by Asterisk via AGI and uses file-based audio I/O.
"""

import os
import re
import sys
import spacy
from asterisk.agi import AGI

# Import your existing modules
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger

# Load spaCy English model
nlp = spacy.load("en_core_web_sm")


def extract_order_number(text):
    """
    Extracts order numbers from user input using NLP and regex.
    """
    doc = nlp(text)
    # Try extracting numbers using NLP
    for ent in doc.ents:
        if ent.label_ == "CARDINAL":
            if any(token.text.lower() in ["order", "id", "number"] for token in ent.root.head.lefts):
                return ent.text

    # Fallback: Use regex
    pattern = r'\b(?:order(?:\s*(?:id|number))?|id|number)?\s*(?:is|was|should be|supposed to be)?\s*[:#]?\s*(\d{3,10})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Final fallback: If the input is a standalone number
    if text.strip().isdigit():
        return text.strip()

    return None


def agi_main_flow():
    # Initialize AGI interface and logger
    agi = AGI()
    log = logger.setup_logger()
    agi.verbose("Starting AGI Voice Support Bot", level=1)

    # Dump AGI environment for debugging purposes
    env = agi.get_environment()
    log.info("AGI Environment: %s", env)

    # === Play Welcome Message ===
    welcome_message = "Welcome to Zomato customer support. How can I assist you today?"
    # Generate TTS file (ensure this file is in a directory Asterisk can access)
    # For example, generate to /var/lib/asterisk/sounds/welcome.wav (and call stream_file with 'welcome')
    from src.speech import tts
    welcome_audio_path = "/var/lib/asterisk/sounds/welcome.wav"
    tts.generate_tts_file(welcome_message, welcome_audio_path)
    agi.verbose("Playing welcome message", level=1)
    agi.stream_file("welcome")  # Note: omit file extension per AGI protocol

    # Initialize conversation history with system prompt
    system_prompt = ("You are a female customer support executive working for Zomato. "
                     "Keep your tone friendly, concise, and professional.")
    conversation_history = [{"role": "system", "content": system_prompt}]
    exit_keywords = ["bye", "exit", "quit", "end call", "goodbye", "thank you", "that's all"]

    # Use AGI unique ID for file naming
    uniqueid = env.get("agi_uniqueid", "default")

    while True:
        # === Record Caller Input ===
        agi.verbose("Recording caller input", level=1)
        # Define a temporary filename (without extension as AGI expects files in its sounds directory)
        input_filename = f"input_{uniqueid}"
        # Record for up to 60 seconds with 2 seconds of silence allowed.
        # (The AGI record_file command automatically appends the extension based on the format.)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=2)

        # Full path to the recorded file (adjust path as needed)
        input_audio_path = f"/var/lib/asterisk/sounds/{input_filename}.wav"

        # Process recorded audio using STT (this function should return the transcribed text)
        from src.speech import stt
        user_input = stt.recognize_from_file(input_audio_path)
        if not user_input:
            goodbye = "No input received. Ending session. Goodbye!"
            tts.generate_tts_file(goodbye, "/var/lib/asterisk/sounds/goodbye.wav")
            agi.stream_file("goodbye")
            break

        agi.verbose(f"User said: {user_input}", level=1)
        conversation_history.append({"role": "user", "content": user_input})

        # Check for exit keywords
        if any(keyword in user_input.lower() for keyword in exit_keywords):
            goodbye = "Thank you for contacting Zomato support. Have a great day!"
            tts.generate_tts_file(goodbye, "/var/lib/asterisk/sounds/goodbye.wav")
            agi.stream_file("goodbye")
            break

        # === Order Number Extraction ===
        order_number = extract_order_number(user_input)
        if order_number:
            order_data = data_fetcher.fetch_order_data(order_number, source="csv")
            log.info("Fetched Order Data: %s", order_data)
            order_context = f"Order details for order {order_number}: {order_data}"
            conversation_history.append({"role": "system", "content": order_context})

        # === Query LLM for Response ===
        ai_response = llm_client.query_llm(conversation_history)
        # Clean the response of any unwanted tokens
        clean_response = ai_response.replace("<|im_start|>assistant<|im_sep|>", "") \
                                    .replace("<|im_end|>", "").strip()
        conversation_history.append({"role": "assistant", "content": clean_response})
        agi.verbose(f"AI Response: {clean_response}", level=1)

        # === Generate and Play AI Response ===
        response_filename = f"response_{uniqueid}"
        response_audio_path = f"/var/lib/asterisk/sounds/{response_filename}.wav"
        tts.generate_tts_file(clean_response, response_audio_path)
        agi.verbose("Playing AI response", level=1)
        agi.stream_file(response_filename)

    agi.hangup()


if __name__ == "__main__":
    agi_main_flow()
