#!/storage/code/ai_voice_support_bot/venv/bin/python3
"""
fastagi_server.py - FastAGI server for your Zomato customer support bot.
This server listens for AGI requests over TCP and dispatches them to your AGI logic.
"""

import socketserver
import sys
import logging
import os

# Import your AGI logic wrapper (we create one below)
from asterisk.agi import AGI

# --- Wrapper for your AGI main flow that uses a provided AGI instance ---
def agi_main_flow_custom(agi):
    """
    This wrapper uses the provided AGI instance and runs your conversation loop.
    It mirrors the logic in your existing agi_main_flow(), but is designed
    for FastAGI where AGI is constructed from the connection's I/O streams.
    """
    from src.utils import logger
    from src.ai import llm_client
    from src.data import data_fetcher
    from src.speech import tts, stt
    import time, re

    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Voice Support Bot", level=1)
    
    # Get AGI environment from the connection
    env = agi.get_environment()
    log.info("AGI Environment: %s", env)
    
    uniqueid = env.get("agi_uniqueid", "default")
    
    # --- Play Welcome Message ---
    welcome_message = "Welcome to Zomato customer support. How can I assist you today?"
    welcome_wav = f"/var/lib/asterisk/sounds/welcome_{uniqueid}.wav"
    tts.generate_tts_file(welcome_message, welcome_wav)
    agi.verbose("Playing welcome message", level=1)
    # Asterisk will look for a file named "welcome_<uniqueid>" in its sounds directory.
    agi.stream_file(f"welcome_{uniqueid}")
    
    # --- Initialize conversation history ---
    system_prompt = ("You are a female customer support executive working for Zomato. "
                     "Answer all customer queries in a friendly, concise, and professional manner.")
    conversation_history = [{"role": "system", "content": system_prompt}]
    exit_keywords = ["bye", "exit", "quit", "end call", "goodbye", "thank you", "that's all"]
    
    # --- Main Conversation Loop ---
    while True:
        agi.verbose("Recording caller input", level=1)
        input_filename = f"input_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        
        agi.verbose("About to record caller input", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=2)
        # Allow a short delay to ensure the file is written
        time.sleep(2)
        
        if not os.path.exists(input_wav):
            agi.verbose(f"Recording file NOT found: {input_wav}", level=1)
        else:
            agi.verbose(f"Recording file exists: {input_wav}", level=1)
        
        # Process recorded audio using STT
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
        
        # Extract order number if present
        pattern = r'\b(?:order(?:\s*(?:id|number))?|id|number)?\s*(?:is|was|should be|supposed to be)?\s*[:#]?\s*(\d{3,10})'
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            order_number = match.group(1)
            agi.verbose(f"Extracted order number: {order_number}", level=1)
            order_data = data_fetcher.fetch_order_data(order_number, source="csv")
            log.info("Fetched Order Data: %s", order_data)
            order_context = f"Order details for order {order_number}: {order_data}"
            conversation_history.append({"role": "system", "content": order_context})
        else:
            log.info("No order number found in input.")
        
        # Query LLM for a response
        ai_response = llm_client.query_llm(conversation_history)
        clean_response = ai_response.replace("<|im_start|>assistant<|im_sep|>", "").replace("<|im_end|>", "").strip()
        conversation_history.append({"role": "assistant", "content": clean_response})
        agi.verbose(f"AI Response: {clean_response}", level=1)
        
        # Generate TTS for the AI response and play it
        response_wav = f"/var/lib/asterisk/sounds/response_{uniqueid}.wav"
        tts.generate_tts_file(clean_response, response_wav)
        agi.verbose("Playing AI response", level=1)
        agi.stream_file(f"response_{uniqueid}")
    
    agi.hangup()

# --- FastAGI Handler using ForkingTCPServer ---
class FastAGIHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            # Create an AGI instance with the connection's streams.
            agi = AGI(stdin=self.rfile, stdout=self.wfile)
            self.server.logger.info("FastAGI request from %s", self.client_address)
            agi_main_flow_custom(agi)
        except Exception as e:
            self.server.logger.error("Exception in FastAGIHandler: %s", e)

# Use ForkingTCPServer to avoid thread-related signal issues.
class FastAGIServer(socketserver.ForkingTCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 4577
    # Set up a basic logger for the FastAGI server.
    logger_server = logging.getLogger("FastAGIServer")
    logger_server.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger_server.addHandler(handler)
    
    server = FastAGIServer((HOST, PORT), FastAGIHandler)
    server.logger = logger_server
    logger_server.info(f"Starting FastAGI server on {HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger_server.info("FastAGI server shutting down")
        server.shutdown()
