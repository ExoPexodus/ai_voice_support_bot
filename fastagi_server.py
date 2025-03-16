#!/storage/code/ai_voice_support_bot/venv/bin/python3
"""
fastagi_server.py - FastAGI server for your Zomato customer support bot.
This server listens for AGI requests over TCP and dispatches them to your AGI logic.
"""

import socketserver
import sys
from agi_main import agi_main_flow  # Ensure your agi_main_flow is refactored to accept custom I/O if needed
from asterisk.agi import AGI

# You may need to modify agi_main_flow to accept stdin/stdout streams.
# For simplicity, here's a basic handler that instantiates AGI using the request's rfile and wfile.

class FastAGIHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            # Create an AGI instance with the connection's input/output streams.
            agi = AGI(stdin=self.rfile, stdout=self.wfile)
            # Optionally, you can log the AGI environment here
            self.server.logger.info("FastAGI request from %s", self.client_address)
            
            # Call your main AGI flow
            # If your agi_main_flow() uses AGI() without parameters, you need to refactor it
            # to accept an AGI instance. For now, let's assume it can be called as follows:
            agi_main_flow_custom(agi)  # We'll create a wrapper for this below.
        except Exception as e:
            self.server.logger.error("Exception in FastAGIHandler: %s", e)

# Wrapper for your AGI main flow that uses the provided AGI instance.
def agi_main_flow_custom(agi):
    from src.utils import logger
    from src.ai import llm_client
    from src.data import data_fetcher
    from src.speech import tts, stt
    import time, os, re

    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Voice Support Bot", level=1)
    
    # Get AGI environment from the connection.
    env = agi.get_environment()
    log.info("AGI Environment: %s", env)
    
    uniqueid = env.get("agi_uniqueid", "default")
    
    # Play welcome message
    welcome_message = "Welcome to Zomato customer support. How can I assist you today?"
    welcome_wav = f"/var/lib/asterisk/sounds/welcome_{uniqueid}.wav"
    tts.generate_tts_file(welcome_message, welcome_wav)
    agi.verbose("Playing welcome message", level=1)
    agi.stream_file(f"welcome_{uniqueid}")
    
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
        
        # Extract order number if present
        order_number = None
        pattern = r'\b(?:order(?:\s*(?:id|number))?|id|number)?\s*(?:is|was|should be|supposed to be)?\s*[:#]?\s*(\d{3,10})'
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            order_number = match.group(1)
            agi.verbose(f"Extracted order number: {order_number}", level=1)
        
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
        agi.stream_file(f"response_{uniqueid}")
    
    agi.hangup()

class FastAGIServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 4573
    # Set up a basic logger for the FastAGI server
    import logging
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
