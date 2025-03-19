#!/fastagi_server.py
"""
fastagi_server.py - FastAGI server for your Hiring Voice Bot.
This server listens for AGI requests over TCP and dispatches them to your AI-powered conversational logic.
Repurposed for calling Maxicus’s job candidates.
"""

import socketserver
import sys
import logging
import io
import time
import os

from asterisk.agi import AGI
from src.utils import logger
from src.speech import tts, stt
from src.ai import llm_client  # Azure LLM client

# -------------------------------------------------------------------------
# LLM Response Cleaner
# -------------------------------------------------------------------------
def clean_llm_response(response):
    """
    Removes unwanted formatting tokens from the LLM response.
    """
    tokens = ["<|im_start|>user<|im_sep|>", "<|im_start|>assistant<|im_sep|>", "<|im_end|>"]
    for token in tokens:
        response = response.replace(token, "")
    return response.strip()

# -------------------------------------------------------------------------
# AI Helper Functions
# -------------------------------------------------------------------------
def determine_sentiment(response):
    """
    Uses the LLM to decide if the candidate's response to a yes/no question is positive or negative.
    Returns "positive" or "negative".
    """
    prompt = f"Determine whether the following response is positive or negative: \"{response}\". Respond with only 'positive' or 'negative'."
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return "negative" if "negative" in result else "positive"

def validate_option(response, valid_options):
    """
    Uses the LLM to determine if the candidate's response clearly indicates one of the valid options.
    Returns that option (in lowercase) if recognized, otherwise returns None.
    """
    options_str = ", ".join(valid_options)
    prompt = (f"Given the candidate's response: \"{response}\", does it clearly indicate one of the following options: {options_str}? "
              "If yes, return the matching option exactly as one of these; if not, return 'none'.")
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return result if result in valid_options else None

def generate_generic_clarification(valid_options):
    """
    Uses the LLM to generate a simple clarification prompt that instructs the candidate to choose one of the valid options.
    """
    options_str = ", ".join(valid_options)
    prompt = f"Please answer with one of the following options only: {options_str}."
    conversation = [{"role": "system", "content": prompt}]
    raw_clarification = llm_client.query_llm(conversation)
    return clean_llm_response(raw_clarification)

def generate_smart_clarification(primary_question, candidate_followup, valid_options):
    """
    Uses the LLM to generate a smart clarification prompt that acknowledges the candidate's follow-up
    while guiding them to answer the primary question. It must keep the conversation context.
    """
    options_str = ", ".join(valid_options)
    prompt = (f"The candidate asked: \"{candidate_followup}\". The primary question is: \"{primary_question}\". "
              f"Provide a smart, friendly response that acknowledges their follow-up and instructs them to answer the primary question by choosing one of the following options: {options_str}. "
              "Do not repeat the entire primary question verbatim; just provide a concise clarification and directive.")
    conversation = [{"role": "system", "content": prompt}]
    raw_response = llm_client.query_llm(conversation)
    return clean_llm_response(raw_response)

def is_followup_question(response):
    """
    Uses the LLM to check if the candidate's response is actually a follow-up clarification question.
    Returns True if it appears to be a question.
    """
    prompt = f"Is the following response a follow-up clarification question? Answer yes or no: \"{response}\"."
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return "yes" in result

# -------------------------------------------------------------------------
# Conversational Question Function
# -------------------------------------------------------------------------
def ask_question(agi, question_data, uniqueid):
    """
    Asks a single question and handles candidate responses using AI.
    
    For yes/no questions (valid_options == ["yes", "no"]), it determines sentiment.
    For other questions, it validates the answer.
    
    If a follow-up question is detected, it uses the entire context to generate a smart clarification prompt
    that instructs the candidate to answer the primary question. Then it waits for a new answer without repeating
    the old question.
    
    Returns the validated answer (in lowercase) or None if the conversation is terminated.
    """
    valid_options = [opt.lower() for opt in question_data["valid_options"]]
    primary_prompt = question_data["question"]
    clarification_mode = False
    smart_prompt = ""
    
    while True:
        # Decide which prompt to play.
        if clarification_mode:
            current_prompt = smart_prompt
        else:
            current_prompt = primary_prompt
        
        # Play the current prompt.
        wav_file = f"/var/lib/asterisk/sounds/{question_data['key']}_{uniqueid}.wav"
        tts.generate_tts_file(current_prompt, wav_file)
        agi.verbose(f"Playing prompt: {current_prompt}", level=1)
        agi.stream_file(f"{question_data['key']}_{uniqueid}")
        
        # Record candidate's response.
        input_filename = f"input_{question_data['key']}_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        agi.verbose("Recording candidate input...", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=5)
        time.sleep(2)
        if not os.path.exists(input_wav):
            agi.verbose(f"Recording file NOT found: {input_wav}", level=1)
        response = stt.recognize_from_file(input_wav)
        response = response.strip().lower() if response else ""
        agi.verbose(f"Candidate said: {response}", level=1)
        
        if response == "":
            goodbye = "No input received. Ending session. Goodbye!"
            goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
            tts.generate_tts_file(goodbye, goodbye_wav)
            agi.stream_file(f"goodbye_{uniqueid}")
            agi.hangup()
            return None
        
        # For yes/no questions.
        if valid_options == ["yes", "no"]:
            sentiment = determine_sentiment(response)
            if sentiment == "negative":
                goodbye = question_data.get("exit_message", "Thank you for your time. Goodbye!")
                goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
                tts.generate_tts_file(goodbye, goodbye_wav)
                agi.stream_file(f"goodbye_{uniqueid}")
                agi.hangup()
                return None
            return "yes"
        
        # If not already in clarification mode, check if the candidate's response is a follow-up question.
        if not clarification_mode and is_followup_question(response):
            smart_prompt = generate_smart_clarification(primary_prompt, response, valid_options)
            agi.verbose(f"Smart clarification generated: {smart_prompt}", level=1)
            clarification_mode = True
            # Instead of re-asking the primary prompt, play the smart clarification and wait for new input.
            continue
        
        # Validate the candidate's answer.
        validated = validate_option(response, valid_options)
        if validated is not None:
            if "exit_if" in question_data and validated == question_data["exit_if"].lower():
                goodbye = question_data.get("exit_message", "Thank you for your time. Goodbye!")
                goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
                tts.generate_tts_file(goodbye, goodbye_wav)
                agi.stream_file(f"goodbye_{uniqueid}")
                agi.hangup()
                return None
            return validated
        
        # If the answer is ambiguous, generate a generic clarification prompt.
        smart_prompt = generate_smart_clarification(primary_prompt, response, valid_options)
        agi.verbose(f"Ambiguous answer. Smart clarification generated: {smart_prompt}", level=1)
        clarification_mode = True
        # Loop back and wait for a new answer using the smart clarification.
        continue

# -------------------------------------------------------------------------
# Main Conversational Flow
# -------------------------------------------------------------------------
def agi_main_flow_custom(agi):
    """
    Main flow for the Hiring Voice Bot.
    Asks a series of predefined questions and uses AI helper functions to determine if the candidate's responses
    are positive and meet the valid options. If a candidate provides a follow-up question, a smart clarification prompt
    is generated (with full conversation context) and the bot waits for a new answer.
    """
    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Hiring Voice Bot", level=1)
    
    env = agi.env
    log.info("AGI Environment: %s", env)
    uniqueid = env.get("agi_uniqueid", "default")
    
    candidate_name = env.get("agi_calleridname", "Candidate")
    company_name = os.getenv("COMPANY_NAME", "Maxicus")
    
    questions = [
        {
            "key": "confirmation",
            "question": f"Hello {candidate_name}, this is {company_name} calling. Are you still interested in joining our team? Answer yes or no.",
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "Thank you for your time. Have a great day!"
        },
        {
            "key": "qualification",
            "question": "What is your highest qualification? Options: 10th, Post-graduate, Graduate, or 12th.",
            "valid_options": ["10th", "post-graduate", "graduate", "12th"]
        },
        {
            "key": "diploma",
            "question": "Since you said 10th, do you have a 3-year diploma? Answer yes or no.",
            "valid_options": ["yes", "no"],
            "condition": lambda responses: responses.get("qualification", "") == "10th"
        },
        {
            "key": "job_type",
            "question": "Are you looking for a permanent full-time role, a part-time position, or a freelance/gig arrangement? Please answer accordingly.",
            "valid_options": ["permanent", "full time", "part-time", "freelance", "gig"]
        },
        {
            "key": "location",
            "question": "What is your preferred location for work? Options: Amritsar, Vadodara, Kolkata, Banglore, Gurugram, or Pune.",
            "valid_options": ["amritsar", "vadodara", "kolkata", "banglore", "gurugram", "pune"]
        },
        {
            "key": "interview_mode",
            "question": "How would you like to have your interview? Options: In-person, Virtual (Video Call), or Telephonic.",
            "valid_options": ["in-person", "virtual", "video call", "telephonic", "phone"]
        },
        {
            "key": "consent",
            "question": "Do we have your permission to share this information with our internal team for follow-up? Answer yes or no.",
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "Thanks for your time. We respect your decision and will not share your details. Goodbye!"
        }
    ]
    
    candidate_details = {}
    
    for q in questions:
        if "condition" in q and not q["condition"](candidate_details):
            continue
        answer = ask_question(agi, q, uniqueid)
        if answer is None:
            return  # Conversation ended early.
        candidate_details[q["key"]] = answer
        agi.verbose(f"Recorded {q['key']}: {answer}", level=1)
    
    final_message = (f"Fantastic, {candidate_name}! That's all we need for now. "
                     f"Thank you for your time. Our team at {company_name} will review your details and reach out soon. Have a great day!")
    final_wav = f"/var/lib/asterisk/sounds/final_{uniqueid}.wav"
    tts.generate_tts_file(final_message, final_wav)
    agi.verbose("Playing final thank you message", level=1)
    agi.stream_file(f"final_{uniqueid}")
    
    agi.hangup()

# -------------------------------------------------------------------------
# FastAGI Server Setup
# -------------------------------------------------------------------------
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
