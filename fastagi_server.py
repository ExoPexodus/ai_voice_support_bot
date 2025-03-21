#/fastagi_server.py
"""
fastagi_server.py - FastAGI server for your Hiring Voice Bot.
This server listens for AGI requests over TCP and dispatches them to a unified AI conversation agent,
which dynamically manages the conversation with the candidate.
"""

import socketserver
import sys
import logging
import io
import time
import os
import json
import asyncio

from asterisk.agi import AGI
from src.utils import logger
from src.speech import tts, stt
from src.ai import llm_client  # Azure LLM client
from src.ai.ai_helpers import clean_llm_response
from pymongo import MongoClient


def detect_exit_intent(response):
    """
    Determines if the candidate's response indicates an intent to end the conversation.
    Uses a rule-based check with negative keywords and a simple sentiment score.
    If the result is ambiguous, falls back to an LLM call.
    
    Returns True if exit intent is detected, otherwise False.
    """
    if not response:
        return False

    resp = response.lower().strip()
    
    # Rule-based negative keyword check.
    negative_keywords = [
        "no", "not interested", "bye", "exit", "quit", "stop", "end", "later",
        "i'm done", "i'm leaving", "goodbye", "see you", "thank you, bye", "nah", "nope"
    ]
    
    # If any negative keyword is present, return True immediately.
    for kw in negative_keywords:
        if kw in resp:
            return True

    # A simple lexicon-based sentiment heuristic:
    negative_words = ["not", "never", "can't", "won't", "don't", "dislike", "uninterested"]
    negative_score = sum(1 for word in negative_words if word in resp)
    
    # If we detect multiple negative words, consider it as exit intent.
    if negative_score >= 2:
        return True

    # Fallback: use LLM to decide if the response signals an exit intent.
    prompt = (
        f"Does the following candidate response indicate an intent to end the conversation? \"{response}\" "
        "Respond with only 'yes' or 'no'."
    )
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).strip().lower()
    return result == "yes"

def fetch_candidate_info():
    """
    Connects to MongoDB, fetches a candidate's document from the 'hra' database in the 'users' collection.
    Returns a dict with 'name' and 'phone' if found, otherwise None.
    """
    try:
        client = MongoClient("mongodb://root:1KKjasndawdsa1@172.17.52.65:27017/hra?authSource=admin")
        db = client["hra"]
        # Fetch one active user; adjust your query as needed.
        user = db.users.find_one({"IsActive": True})
        if user:
            return {"name": user.get("name"), "phone": user.get("phone")}
    except Exception as e:
        # Yeah, log the error and move on.
        logging.error("MongoDB connection/query error: %s", e)
    return None

def send_outgoing_call(agi, phone_number,company_name):
    """
    Initiates an outgoing call using Asterisk's Originate command.
    
    Required parameters:
      - channel: e.g. "SIP/<phone_number>"
      - exten: dialplan extension to handle the call (must be defined in your dialplan)
      - context: dialplan context where the extension is defined
      - priority: starting priority (usually "1")
      - timeout: timeout (in seconds) to wait for the call to be answered
      - callerid: Caller ID string in proper format
      - (Optional) Additional variable assignments if needed
    
    Example Originate command:
      Originate SIP/+917696040116 6001 outgoing 1 30 "CompanyName" ""
    """
    # Set up the necessary parameters
    channel = f"SIP/{phone_number}"
    exten = "6001"              # The extension defined in your dialplan to handle the call
    context = "outgoing"        # The dialplan context where your extension is located
    priority = "1"              # Starting priority for the dialplan extension
    timeout = "30"              # Wait 30 seconds for an answer
    callerid = f'{company_name}'  # Your desired caller ID
    
    # Build the Originate command
    originate_cmd = f"Originate {channel} {exten} {context} {priority} {timeout} {callerid}"
    agi.verbose(f"Executing Originate command: {originate_cmd}", level=1)
    
    # Execute the command via AGI (this will vary based on your AGI setup)
    result = agi.exec_command(originate_cmd)
    agi.verbose(f"Originate command result: {result}", level=1)


# -------------------------------------------------------------------------
# Unified Conversation Agent
# -------------------------------------------------------------------------
async def conversation_agent(agi, candidate_name, company_name, uniqueid):
    """
    Runs a single conversation with the candidate.
    Maintains conversation history and sends it to the LLM to generate the next prompt.
    The system prompt instructs the AI on the necessary details to collect and when to end.
    Returns the final conversation history.
    """
    # Define a system prompt that instructs the AI on conversation goals.
    system_prompt = (
        f"You are a friendly, conversational AI recruiter for {company_name}. "
        f"you're currently talking to {candidate_name}"
        "Your goal is to collect the following details from the candidate: confirmation of interest, highest qualification, "
        "job type preference, preferred work location, and interview mode. "
        "for highest qualification, we'll be asking the user from these options: [10th, post-graduate, graduate, 12th]"
        "If the user says 10th grade as their highest qualification, then also ask if they have a 3yr diploma(only if the user says that he's from 10th grade)"
        "For the job type prefrence, we offer them 3 options:[full time/parmanent, part-time, freelance/gig]"
        "For preffered work locations, we can only offer these locations: [amritsar, vadodara, kolkata, bangalore, gurugram, pune]"
        "For interview mode, we offer 3 options: [in-person, virtual/video call,telephoni/phone]"
        "Engage in a natural conversation by asking one question at a time and building context as the conversation progresses. "
        "Do not overwhelm the candidate by asking all questions at once. "
        "keep your sentenses as concise and little as possible"
        "If the candidate expresses disinterest (for example, says 'no' or 'bye' or says he's not interested), end the conversation immediately and output a final prompt that includes the marker [EARY_END_CONVERSATION]. "
        "Once all required details are collected, ask for the candidate's consent to store the information. "
        "When you have all the information and consent is given, output a final prompt that includes the marker [END_CONVERSATION] "
        "at the end of your message."
        "Also, you're not allowed to go out of this context to answer user's questions that does not seem relevant to the details we're trying to get"
    )
    
    conversation_history = [{"role": "system", "content": system_prompt}]
    
    # Start conversation by generating the initial prompt.
    current_prompt = f"Hi! Am i speaking with {candidate_name}?"
    conversation_history.append({"role": "assistant", "content": current_prompt})
    
    # Send initial prompt to candidate via TTS.
    init_wav = f"/var/lib/asterisk/sounds/init_{uniqueid}.wav"
    tts.generate_tts_file(current_prompt, init_wav)
    agi.verbose(f"Playing initial prompt: {current_prompt}", level=1)
    agi.stream_file(f"init_{uniqueid}")
    
    while True:
        # Record candidate's response.
        input_filename = f"input_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        agi.verbose("Recording candidate input...", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="", silence=10)
        time.sleep(2)
        user_response = stt.recognize_from_file(input_wav)
        user_response = user_response.strip() if user_response else ""
        agi.verbose(f"Candidate said: {user_response}", level=1)
        
        if user_response == "":
            farewell = "No input received. Ending session. Goodbye!"
            farewell_wav = f"/var/lib/asterisk/sounds/farewell_{uniqueid}.wav"
            tts.generate_tts_file(farewell, farewell_wav)
            agi.stream_file(f"farewell_{uniqueid}")
            break
        
        # NEW: Use our hybrid exit intent detector.
        if detect_exit_intent(user_response):
            final_prompt = "I understand. Thank you for your time. Goodbye! [END_CONVERSATION]"
            conversation_history.append({"role": "assistant", "content": final_prompt})
            final_wav = f"/var/lib/asterisk/sounds/final_{uniqueid}.wav"
            tts.generate_tts_file(final_prompt.replace("[END_CONVERSATION]", "").strip(), final_wav)
            agi.verbose(f"Playing final prompt: {final_prompt}", level=1)
            agi.stream_file(f"final_{uniqueid}")
            break
        
        # Append candidate response to conversation history.
        conversation_history.append({"role": "user", "content": user_response})
        
        # Call the LLM with full conversation history.
        next_prompt = llm_client.query_llm(conversation_history)
        next_prompt = next_prompt.strip() if next_prompt else ""
        next_prompt = next_prompt.replace("<|im_start|>assistant<|im_sep|>", "").replace("<|im_end|>", "")
        
        # Append AI response to conversation history.
        conversation_history.append({"role": "assistant", "content": next_prompt})
        
        # Check if the AI indicates that the conversation is complete.
        if "[EARY_END_CONVERSATION]" in next_prompt:
            # Remove marker from the final prompt.
            final_prompt = next_prompt.replace("[EARY_END_CONVERSATION]", "").strip()
            final_wav = f"/var/lib/asterisk/sounds/final_{uniqueid}.wav"
            tts.generate_tts_file(final_prompt, final_wav)
            agi.verbose(f"Playing final prompt: {final_prompt}", level=1)
            agi.stream_file(f"final_{uniqueid}")
            break
        
        # Check if the AI indicates that the conversation is complete.
        if "[END_CONVERSATION]" in next_prompt:
            # Remove marker from the final prompt.
            final_prompt = next_prompt.replace("[END_CONVERSATION]", "").strip()
            final_wav = f"/var/lib/asterisk/sounds/final_{uniqueid}.wav"
            tts.generate_tts_file(final_prompt, final_wav)
            agi.verbose(f"Playing final prompt: {final_prompt}", level=1)
            agi.stream_file(f"final_{uniqueid}")
            break
        
        # Otherwise, play the next prompt.
        next_wav = f"/var/lib/asterisk/sounds/next_{uniqueid}.wav"
        tts.generate_tts_file(next_prompt, next_wav)
        agi.verbose(f"Playing next prompt: {next_prompt}", level=1)
        agi.stream_file(f"next_{uniqueid}")
    
    return conversation_history

# -------------------------------------------------------------------------
# FastAGI Server Integration
# -------------------------------------------------------------------------
def save_candidate_details(candidate_details, uniqueid):
    data_dir = "/var/lib/asterisk/candidate_data"
    os.makedirs(data_dir, exist_ok=True)
    filename = os.path.join(data_dir, f"candidate_{uniqueid}.json")
    with open(filename, "w") as f:
        json.dump(candidate_details, f, indent=4)
    return filename

def agi_main_flow_custom(agi):
    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Hiring Voice Bot (Unified AI Agent)", level=1)
    
    env = agi.env
    log.info("AGI Environment: %s", env)
    uniqueid = env.get("agi_uniqueid", "default")
    candidate_name = env.get("agi_calleridname", "Candidate")
    company_name = os.getenv("COMPANY_NAME", "Maxicus")
    candidate_name="Jatin"
    
    # Run the unified conversation agent asynchronously.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        conversation_history = loop.run_until_complete(
            conversation_agent(agi, candidate_name, company_name, uniqueid)
        )
    finally:
        loop.close()
    
    # Here you would extract useful information from conversation_history.
    # For simplicity, we'll assume the candidate's details are within the conversation_history.
    # If the conversation included consent (e.g., "yes" in the final part), then store data.
    # In a real implementation, you'd parse the conversation_history to extract structured data.
    # For now, we can store the entire conversation_history.
    # Check for consent in the conversation_history, for example by searching for "permission" responses.
    consent_given = any("permission" in msg.get("content", "").lower() and "yes" in msg.get("content", "").lower() 
                        for msg in conversation_history if msg["role"] == "user")
    
    if consent_given:
        filename = save_candidate_details(conversation_history, uniqueid)
        agi.verbose(f"Candidate details saved to {filename}", level=1)
    
    agi.hangup()

class FastAGIHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            self.rfile = io.TextIOWrapper(self.rfile, encoding="utf-8")
            self.wfile = io.TextIOWrapper(self.wfile, encoding="utf-8", write_through=True)
            agi = AGI(stdin=self.rfile, stdout=self.wfile)
            self.server.logger.info("FastAGI request from %s", self.client_address)
            agi_main_flow_custom(agi)
        except Exception as e:
            self.server.logger.error("Exception in FastAGIHandler: %s", e)

class FastAGIServer(socketserver.ForkingTCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 4577
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
        logger_server.info("FastAGIServer shutting down")
        server.shutdown()
