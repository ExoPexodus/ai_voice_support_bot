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
import json

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
    prompt = f"Determine whether the following response is positive or negative: \"{response}\". Respond with only 'positive' or 'negative'."
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return "negative" if "negative" in result else "positive"

def validate_option(response, valid_options):
    options_str = ", ".join(valid_options)
    prompt = (f"Given the candidate's response: \"{response}\", does it clearly indicate one of the following options: {options_str}? "
              "If yes, return the matching option exactly as one of these; if not, return 'none'.")
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return result if result in valid_options else None

def generate_generic_clarification(valid_options):
    options_str = ", ".join(valid_options)
    prompt = f"Please answer with one of the following options only: {options_str}."
    conversation = [{"role": "system", "content": prompt}]
    raw_clarification = llm_client.query_llm(conversation)
    return clean_llm_response(raw_clarification)

def generate_smart_clarification(primary_question, candidate_followup, valid_options):
    options_str = ", ".join(valid_options)
    prompt = (f"The candidate asked: \"{candidate_followup}\". The primary question is: \"{primary_question}\". "
              f"Provide a smart, friendly response that acknowledges their follow-up and instructs them to answer the main question by choosing one of the following options: {options_str}. "
              "Do not repeat the entire primary question verbatim; just provide a concise clarification and directive. Do Not use any Emojis and make sure your answer is small and concise")
    conversation = [{"role": "system", "content": prompt}]
    raw_response = llm_client.query_llm(conversation)
    return clean_llm_response(raw_response)

def is_followup_question(response, valid_options):
    prompt = (f"Is the following response a follow-up clarification question? Answer yes or no: \"{response}\". "
              f"Also, if the response includes one of these options: {valid_options} and does not feel like they are asking for more details about the options, then just answer no.")
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).lower()
    return "yes" in result

# -------------------------------------------------------------------------
# Conversational Question Function
# -------------------------------------------------------------------------
def ask_question(agi, question_data, uniqueid):
    valid_options = [opt.lower() for opt in question_data["valid_options"]]
    primary_prompt = question_data["question"]
    clarification_mode = False
    smart_prompt = ""
    
    while True:
        current_prompt = smart_prompt if clarification_mode else primary_prompt
        
        wav_file = f"/var/lib/asterisk/sounds/{question_data['key']}_{uniqueid}.wav"
        tts.generate_tts_file(current_prompt, wav_file)
        agi.verbose(f"Playing prompt: {current_prompt}", level=1)
        agi.stream_file(f"{question_data['key']}_{uniqueid}")
        
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
        
        if not clarification_mode and is_followup_question(response, valid_options):
            smart_prompt = generate_smart_clarification(primary_prompt, response, valid_options)
            agi.verbose(f"Smart clarification generated: {smart_prompt}", level=1)
            clarification_mode = True
            continue
        
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
        
        smart_prompt = generate_smart_clarification(primary_prompt, response, valid_options)
        agi.verbose(f"Ambiguous answer. Smart clarification generated: {smart_prompt}", level=1)
        clarification_mode = True
        continue

# -------------------------------------------------------------------------
# Function to Save Candidate Details to JSON
# -------------------------------------------------------------------------
def save_candidate_details(candidate_details, uniqueid):
    """
    Saves candidate details to a JSON file.
    """
    data_dir = "./candidate_data"
    os.makedirs(data_dir, exist_ok=True)
    filename = os.path.join(data_dir, f"candidate_{uniqueid}.json")
    with open(filename, "w") as f:
        json.dump(candidate_details, f, indent=4)
    return filename

# -------------------------------------------------------------------------
# Main Conversational Flow
# -------------------------------------------------------------------------
def agi_main_flow_custom(agi):
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
            "question": f"Hi {candidate_name}! This is {company_name} calling. Hope you're doing well! We're excited to chat with you about an opportunity you might really dig. Before we dive in, can I just confirm—are you still interested in joining our team? Your interest means a lot to us!",
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "I understand, thank you so much for your time. Hope you have a nice day!"
        },
        {
            "key": "qualification",
            "question": "Great, thanks for confirming! Let’s keep things moving. First off, could you tell me what your highest qualification is? Whether it’s 10th, Post-graduate, Graduate, or 12th, just let me know.",
            "valid_options": ["10th", "post-graduate", "graduate", "12th"]
        },
        {
            "key": "diploma",
            "question": "I see. By any chance, do you also have a 3-year diploma along with it?",
            "valid_options": ["yes", "no"],
            "condition": lambda responses: responses.get("qualification", "") == "10th"
        },
        {
            "key": "job_type",
            "question": "Perfect, that really helps. Next up, are you considering a full-time role, a part-time position, or a freelance/gig arrangement? Please answer accordingly.",
            "valid_options": ["permanent", "full time", "part-time", "freelance", "gig"]
        },
        {
            "key": "location",
            "question": "Awesome. Now, what’s your preferred location for work? We're currently offering positions in Amritsar, Vadodara, Kolkata, Banglore, Gurugram, and Pune.",
            "valid_options": ["amritsar", "vadodara", "kolkata", "banglore", "gurugram", "pune"]
        },
        {
            "key": "interview_mode",
            "question": "Almost there—how would you like to have your interview? We offer a few options: an in-person meeting, a video call, or a phone interview. Which one would you prefer?",
            "valid_options": ["in-person", "virtual", "video call", "telephonic", "phone"]
        },
        {
            "key": "consent",
            "question": "Thanks, that’s very helpful. Lastly, before we wrap up—do we have your permission to share all this information with our internal team so they can follow up with you? Your consent is important to us.",
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "I understand, thank you so much for your time. We respect your decision and will not share your details. Have an amazing day!"
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
    
    # Save candidate details only if consent was given.
    if candidate_details.get("consent") == "yes":
        filename = save_candidate_details(candidate_details, uniqueid)
        agi.verbose(f"Candidate details saved to {filename}", level=1)
    
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
