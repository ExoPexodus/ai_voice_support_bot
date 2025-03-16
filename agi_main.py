#!/storage/code/ai_voice_support_bot/venv/bin/python3
"""
agi_main.py - AGI entry point for your Zomato customer support bot.
This script is invoked by Asterisk via AGI and uses file-based audio I/O.
"""

import os
import re
import sys
import time
from asterisk.agi import AGI

# Import modules from your existing codebase
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger
from src.speech import tts, stt

def extract_order_number(text):
    """
    Extracts order numbers from user input using regex.
    """

    # Fallback: Use regex
    pattern = r'\b(?:order(?:\s*(?:id|number))?|id|number)?\s*(?:is|was|should be|supposed to be)?\s*[:#]?\s*(\d{3,10})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        print(f"[DEBUG] Extracted order number via Regex: {match.group(1)}")
        return match.group(1)

    # Final fallback: if input is just a number
    if text.strip().isdigit():
        print(f"[DEBUG] Extracted standalone order number: {text.strip()}")
        return text.strip()

    print("[DEBUG] No order number found in the input.")
    return None

def agi_main_flow():
    # Initialize AGI and logger
    agi = AGI()
    log = logger.setup_logger()
    agi.verbose("Starting AGI Voice Support Bot", level=1)
    
    # Dump AGI environment for debugging
    env = agi.get_environment()
    log.info("AGI Environment: %s", env)
    
    # Use AGI uniqueid for file naming
    uniqueid = env.get("agi_uniqueid", "default")
    
    # === Play Welcome Message ===
    welcome_message = "Welcome to Zomato customer support. How can I assist you today?"
    # Generate a TTS file in a directory accessible by Asterisk (e.g., /var/lib/asterisk/sounds)
    welcome_audio_path = "/var/lib/asterisk/sounds/welcome.wav"
    tts.generate_tts_file(welcome_message, welcome_audio_path)
    agi.verbose("Playing welcome message", level=1)
    # Use stream_file (omit file extension per AGI protocol)
    agi.stream_file("welcome")
    
    # Initialize conversation history with a system prompt
    system_prompt = ("You are a female customer support executive working for Zomato. "
                     "Answer all customer queries in a friendly, concise, and professional manner.")
    conversation_history = [{"role": "system", "content": system_prompt}]
    exit_keywords = ["bye", "exit", "quit", "end call", "goodbye", "thank you", "that's all"]
    
    while True:
        # === Record Caller Input ===
        agi.verbose("Recording caller input", level=1)
        input_filename = f"input_{uniqueid}"
        # Construct the full path of the recorded file
        input_audio_path = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        
        agi.verbose("About to record caller input", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=2)
        # Wait a couple of seconds to ensure file is written
        time.sleep(2)
        if os.path.exists(input_audio_path):
            agi.verbose(f"Recording file exists: {input_audio_path}", level=1)
        else:
            agi.verbose(f"Recording file NOT found: {input_audio_path}", level=1)
        
        # Process recorded audio using STT (this function should return the transcribed text)
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
        
        # === Extract Order Number if Present ===
        order_number = extract_order_number(user_input)
        if order_number:
            order_data = data_fetcher.fetch_order_data(order_number, source="csv")
            log.info("Fetched Order Data: %s", order_data)
            order_context = f"Order details for order {order_number}: {order_data}"
            conversation_history.append({"role": "system", "content": order_context})
        else:
            log.info("No order number found in input.")
        
        # === Query LLM for Response ===
        ai_response = llm_client.query_llm(conversation_history)
        clean_response = (ai_response.replace("<|im_start|>assistant<|im_sep|>", "")
                                    .replace("<|im_end|>", "")
                                    .strip())
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
