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

# Import modules from your codebase
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger
from src.speech import tts, stt

def extract_order_number(text):
    """
    Extracts order numbers from user input using regex.
    """
    pattern = r'\b(?:order(?:\s*(?:id|number))?|id|number)?\s*(?:is|was|should be|supposed to be)?\s*[:#]?\s*(\d{3,10})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        print(f"[DEBUG] Extracted order number via Regex: {match.group(1)}")
        return match.group(1)
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
    welcome_message = "Hi! am i speaking with jatin?"
    welcome_wav = f"/var/lib/asterisk/sounds/welcome_{uniqueid}.wav"
    tts.generate_tts_file(welcome_message, welcome_wav)
    # Assume the conversion creates /var/lib/asterisk/sounds/welcome_{uniqueid}.ulaw
    agi.verbose("Playing welcome message", level=1)
    # Play using stream_file (omit extension)
    agi.stream_file(f"welcome_{uniqueid}")
    
    # Initialize conversation history with a system prompt
    system_prompt = ("You are a female customer support executive working for Zomato. "
                     "Answer all customer queries in a friendly, concise, and professional manner.")
    conversation_history = [{"role": "system", "content": system_prompt}]
    exit_keywords = ["bye", "exit", "quit", "end call", "goodbye", "thank you", "that's all"]
    
    while True:
        agi.verbose("Recording caller input", level=1)
        input_filename = f"input_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        
        agi.verbose("About to record caller input", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=2)
        time.sleep(2)
        
        if os.path.exists(input_wav):
            agi.verbose(f"Recording file exists: {input_wav}", level=1)
        else:
            agi.verbose(f"Recording file NOT found: {input_wav}", level=1)
        
        user_input = stt.recognize_from_file(input_wav)
        agi.verbose(f"STT returned: {user_input}", level=1)
        
        if not user_input:
            goodbye_message = "No input received. Ending session. Goodbye!"
            goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
            tts.generate_tts_file(goodbye_message, goodbye_wav)
            agi.verbose("Playing goodbye message", level=1)
            agi.stream_file(f"goodbye_{uniqueid}")
            break
        
        agi.verbose(f"User said: {user_input}", level=1)
        conversation_history.append({"role": "user", "content": user_input})
        
        if any(keyword in user_input.lower() for keyword in exit_keywords):
            goodbye_message = "Thank you for contacting Zomato support. Have a great day!"
            goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
            tts.generate_tts_file(goodbye_message, goodbye_wav)
            agi.verbose("Playing goodbye message", level=1)
            agi.stream_file(f"goodbye_{uniqueid}")
            break
        
        order_number = extract_order_number(user_input)
        if order_number:
            order_data = data_fetcher.fetch_order_data(order_number, source="csv")
            log.info("Fetched Order Data: %s", order_data)
            order_context = f"Order details for order {order_number}: {order_data}"
            conversation_history.append({"role": "system", "content": order_context})
        else:
            log.info("No order number found in input.")
        
        ai_response = llm_client.query_llm(conversation_history)
        clean_response = ai_response.replace("<|im_start|>assistant<|im_sep|>", "").replace("<|im_end|>", "").strip()
        conversation_history.append({"role": "assistant", "content": clean_response})
        agi.verbose(f"AI Response: {clean_response}", level=1)
        
        response_wav = f"/var/lib/asterisk/sounds/response_{uniqueid}.wav"
        tts.generate_tts_file(clean_response, response_wav)
        agi.verbose("Playing AI response", level=1)
        # Play the converted ulaw file (base name without extension)
        agi.stream_file(f"response_{uniqueid}")
    
    agi.hangup()

if __name__ == "__main__":
    agi_main_flow()