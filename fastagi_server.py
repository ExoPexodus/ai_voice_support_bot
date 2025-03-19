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
    Removes unwanted tokens from the LLM response.
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
    if "negative" in result:
        return "negative"
    return "positive"

def validate_option(response, valid_options):
    """
    Uses the LLM to determine if the candidate's response clearly indicates one of the valid options.
    If it does, returns that option (in lowercase), otherwise returns None.
    """
    options_str = ", ".join(valid_options)
    prompt = (f"Given the candidate's response: \"{response}\", does it clearly indicate one of the following options: {options_str}? "
              "If yes, return the matching option exactly as one of these; if not, return 'none'.")
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return result if result in valid_options else None

def generate_clarification(valid_options):
    """
    Uses the LLM to generate a short clarification prompt that tells the candidate which options are allowed.
    """
    options_str = ", ".join(valid_options)
    prompt = f"Please answer with one of the following options only: {options_str}."
    conversation = [{"role": "system", "content": prompt}]
    raw_clarification = llm_client.query_llm(conversation)
    return clean_llm_response(raw_clarification)

def is_followup_question(response):
    """
    Uses the LLM to check if the candidate's response is actually a follow-up or clarification question.
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
    Asks a single question using TTS and records the candidate's answer.
    For yes/no questions, uses sentiment analysis; for other questions, validates the answer.
    If the answer is ambiguous, it generates a clarification prompt using the LLM.
    
    question_data: dict with keys:
       - key: identifier for the question
       - question: text to ask
       - valid_options: list of valid answers (all in lowercase)
       - exit_if (optional): if answer equals this, end conversation
       - exit_message (optional): message if exiting early
    Returns the validated answer (in lowercase) if successful, or None if conversation ended.
    """
    valid_options = [opt.lower() for opt in question_data["valid_options"]]
    
    while True:
        # Play the question prompt.
        prompt = question_data["question"]
        wav_file = f"/var/lib/asterisk/sounds/{question_data['key']}_{uniqueid}.wav"
        tts.generate_tts_file(prompt, wav_file)
        agi.verbose(f"Playing prompt: {prompt}", level=1)
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
        
        # For non-yes/no questions, validate the candidate's answer.
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
        
        # Check if candidate's response is a follow-up question.
        if is_followup_question(response):
            composite = response + " " + prompt
            agi.verbose(f"Detected follow-up. Composite answer: {composite}", level=1)
            validated = validate_option(composite, valid_options)
            if validated is not None:
                if "exit_if" in question_data and validated == question_data["exit_if"].lower():
                    goodbye = question_data.get("exit_message", "Thank you for your time. Goodbye!")
                    goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
                    tts.generate_tts_file(goodbye, goodbye_wav)
                    agi.stream_file(f"goodbye_{uniqueid}")
                    agi.hangup()
                    return None
                return validated
            # Generate a clarification prompt using the composite answer.
            clarification = generate_clarification(valid_options)
            full_clarification = f"I didn't quite catch that. {clarification}"
            clar_wav = f"/var/lib/asterisk/sounds/clarify_{question_data['key']}_{uniqueid}.wav"
            tts.generate_tts_file(full_clarification, clar_wav)
            agi.verbose(f"Playing clarification prompt: {full_clarification}", level=1)
            agi.stream_file(f"clarify_{question_data['key']}_{uniqueid}")
            continue
        
        # If still ambiguous, generate a clarification prompt.
        clarification = generate_clarification(valid_options)
        full_clarification = f"I didn't quite catch that. {clarification}"
        clar_wav = f"/var/lib/asterisk/sounds/clarify_{question_data['key']}_{uniqueid}.wav"
        tts.generate_tts_file(full_clarification, clar_wav)
        agi.verbose(f"Playing clarification prompt: {full_clarification}", level=1)
        agi.stream_file(f"clarify_{question_data['key']}_{uniqueid}")
        # Loop back to re-ask the question.

# -------------------------------------------------------------------------
# Main Conversational Flow
# -------------------------------------------------------------------------
def agi_main_flow_custom(agi):
    """
    Main flow for the Hiring Voice Bot.
    Asks a series of questions and uses AI-powered helper functions to decide whether the candidate's responses
    are positive and whether they match the valid options. Ends the conversation if a response is negative.
    """
    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Hiring Voice Bot", level=1)
    
    env = agi.env
    log.info("AGI Environment: %s", env)
    uniqueid = env.get("agi_uniqueid", "default")
    
    candidate_name = env.get("agi_calleridname", "Candidate")
    company_name = os.getenv("COMPANY_NAME", "Maxicus")
    
    # Define our questions.
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
    
    # Loop through each question.
    for q in questions:
        if "condition" in q and not q["condition"](candidate_details):
            continue
        answer = ask_question(agi, q, uniqueid)
        if answer is None:
            return  # Conversation ended early.
        candidate_details[q["key"]] = answer
        agi.verbose(f"Recorded {q['key']}: {answer}", level=1)
    
    # Finalize conversation.
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
