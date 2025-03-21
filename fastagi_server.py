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
    
    # Instead of writing to /var/lib/asterisk/sounds directly, we use our new TTS streaming function,
    # which writes to the symlinked in-memory folder (e.g., /var/lib/asterisk/sounds/dev_shm).
    # The filename passed (without extension) will be used by speak_text_stream() to generate a file ending in .ulaw.
    # Use the new TTS streaming function to write the TTS output to in-memory storage.
    init_filename = f"init_{uniqueid}"
    try:
        init_wav_full = tts.speak_text_stream(current_prompt, init_filename)
    except Exception as e:
        agi.verbose(f"TTS streaming error: {e}", level=1)
        return conversation_history

    agi.verbose(f"Playing initial prompt: {current_prompt}", level=1)
    # Stream the file from the symlinked in-memory folder.
    agi.stream_file(f"dev_shm/{init_filename}")
    
    while True:
        # Record candidate's response.
        input_filename = f"input_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        agi.verbose("Recording candidate input...", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="", silence=10)
        time.sleep(0.005)
        user_response = stt.recognize_from_file(input_wav)
        user_response = user_response.strip() if user_response else ""
        agi.verbose(f"Candidate said: {user_response}", level=1)
        
        if user_response == "":
            farewell = "No input received. Ending session. Goodbye!"
            farewell_filename = f"farewell_{uniqueid}"
            try:
                farewell_wav_full = tts.speak_text_stream(farewell, farewell_filename)
            except Exception as e:
                agi.verbose(f"TTS streaming error: {e}", level=1)
                break
            agi.stream_file(f"dev_shm/{farewell_filename}")
            break
        
        if detect_exit_intent(user_response):
            final_prompt = "I understand. Thank you for your time. Goodbye! [END_CONVERSATION]"
            conversation_history.append({"role": "assistant", "content": final_prompt})
            final_filename = f"final_{uniqueid}"
            try:
                final_wav_full = tts.speak_text_stream(final_prompt.replace("[END_CONVERSATION]", "").strip(), final_filename)
            except Exception as e:
                agi.verbose(f"TTS streaming error: {e}", level=1)
                break
            agi.verbose(f"Playing final prompt: {final_prompt}", level=1)
            agi.stream_file(f"dev_shm/{final_filename}")
            break
        
        conversation_history.append({"role": "user", "content": user_response})
        
        next_prompt = llm_client.query_llm(conversation_history)
        next_prompt = next_prompt.strip() if next_prompt else ""
        next_prompt = next_prompt.replace("<|im_start|>assistant<|im_sep|>", "").replace("<|im_end|>", "")
        conversation_history.append({"role": "assistant", "content": next_prompt})
        
        if "[EARY_END_CONVERSATION]" in next_prompt or "[END_CONVERSATION]" in next_prompt:
            final_prompt = next_prompt.replace("[EARY_END_CONVERSATION]", "").replace("[END_CONVERSATION]", "").strip()
            final_filename = f"final_{uniqueid}"
            try:
                final_wav_full = tts.speak_text_stream(final_prompt, final_filename)
            except Exception as e:
                agi.verbose(f"TTS streaming error: {e}", level=1)
                break
            agi.verbose(f"Playing final prompt: {final_prompt}", level=1)
            agi.stream_file(f"dev_shm/{final_filename}")
            break
        
        next_filename = f"next_{uniqueid}"
        try:
            next_wav_full = tts.speak_text_stream(next_prompt, next_filename)
        except Exception as e:
            agi.verbose(f"TTS streaming error: {e}", level=1)
            break
        agi.verbose(f"Playing next prompt: {next_prompt}", level=1)
        agi.stream_file(f"dev_shm/{next_filename}")
    
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
    candidate_name = "Jatin"
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        conversation_history = loop.run_until_complete(
            conversation_agent(agi, candidate_name, company_name, uniqueid)
        )
    finally:
        loop.close()
    
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