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
# AI Helper Functions
# -------------------------------------------------------------------------
def analyze_sentiment(response):
    """
    Uses AI to determine if the response sentiment is positive, negative, or neutral.
    """
    prompt = f"Determine the sentiment (positive, negative, or neutral) of the following response: \"{response}\"."
    conversation = [{"role": "system", "content": prompt}]
    result = llm_client.query_llm(conversation).strip().lower()
    if "positive" in result:
        return "positive"
    elif "negative" in result:
        return "negative"
    else:
        return "neutral"

def is_followup_question(response):
    """
    Uses AI to check if the candidate's response is actually a follow-up or clarification question.
    Returns True if the answer appears to be a question.
    """
    prompt = f"Is the following response a follow-up clarification question? Answer yes or no: \"{response}\"."
    conversation = [{"role": "system", "content": prompt}]
    result = llm_client.query_llm(conversation).strip().lower()
    return "yes" in result

def validate_answer(response, valid_options):
    """
    Uses AI to check if the candidate's response clearly indicates one of the valid options.
    If it does, returns that option (in lowercase); otherwise, returns None.
    """
    options_str = ", ".join(valid_options)
    prompt = (f"Given the candidate's response: \"{response}\", does it clearly indicate one of the following options: {options_str}? "
              "If yes, return the matched option exactly as one of the options; if not, return 'none'.")
    conversation = [{"role": "system", "content": prompt}]
    result = llm_client.query_llm(conversation).strip().lower()
    return result if result in valid_options else None

# -------------------------------------------------------------------------
# Conversational Question Loop
# -------------------------------------------------------------------------
def ask_question_with_ai(agi, q, uniqueid):
    """
    Asks a question using TTS and records the candidate's answer.
    Uses separate AI functions to check:
      - if the candidate's response has the expected sentiment,
      - if the candidate's answer is a follow-up question,
      - and if the candidate's answer is valid as per provided options.
    
    q: dict with keys:
         key: identifier for the question
         question: text to ask
         valid_options: list of valid (lowercase) options
         exit_if (optional): if answer matches this, exit the conversation
         exit_message (optional): message to play if exiting early.
         condition (optional): lambda to decide if question should be asked.
    """
    valid_options = [opt.lower() for opt in q["valid_options"]]
    
    while True:
        # Play the main question prompt.
        prompt = q["question"]
        wav_file = f"/var/lib/asterisk/sounds/{q['key']}_{uniqueid}.wav"
        tts.generate_tts_file(prompt, wav_file)
        agi.verbose(f"Playing prompt: {prompt}", level=1)
        agi.stream_file(f"{q['key']}_{uniqueid}")
        
        # Record candidate's response.
        input_filename = f"input_{q['key']}_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        agi.verbose("Recording candidate input...", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=5)
        time.sleep(2)
        if not os.path.exists(input_wav):
            agi.verbose(f"Recording file NOT found: {input_wav}", level=1)
        answer = stt.recognize_from_file(input_wav)
        answer = answer.strip().lower() if answer else ""
        agi.verbose(f"Candidate said: {answer}", level=1)
        
        # If no answer, exit.
        if answer == "":
            goodbye = "No input received. Ending session. Goodbye!"
            goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
            tts.generate_tts_file(goodbye, goodbye_wav)
            agi.stream_file(f"goodbye_{uniqueid}")
            agi.hangup()
            return None

        # For confirmation questions, use sentiment analysis.
        if q["key"] == "confirmation":
            sentiment = analyze_sentiment(answer)
            if sentiment == "negative":
                goodbye = q.get("exit_message", "Thank you for your time. Goodbye!")
                goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
                tts.generate_tts_file(goodbye, goodbye_wav)
                agi.stream_file(f"goodbye_{uniqueid}")
                agi.hangup()
                return None

        # Check if the candidate's response is a follow-up question.
        if is_followup_question(answer):
            # Create a composite answer by appending the main question.
            composite_answer = answer + " " + prompt
            agi.verbose(f"Detected follow-up. Composite answer: {composite_answer}", level=1)
            # Validate the composite answer.
            validated = validate_answer(composite_answer, valid_options)
            if validated is not None:
                # If the answer triggers exit.
                if "exit_if" in q and validated == q["exit_if"].lower():
                    goodbye = q.get("exit_message", "Thank you for your time. Goodbye!")
                    goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
                    tts.generate_tts_file(goodbye, goodbye_wav)
                    agi.stream_file(f"goodbye_{uniqueid}")
                    agi.hangup()
                    return None
                return validated
            # If still ambiguous, generate a clarification prompt using the composite answer.
            conv_history = [
                {"role": "system", "content": "You are a friendly voice bot helping candidates select one of the valid options."},
                {"role": "user", "content": composite_answer},
                {"role": "assistant", "content": f"The valid options are: {', '.join(valid_options)}. Please choose one of these options."}
            ]
            clarification = llm_client.query_llm(conv_history).strip()
            clar_wav = f"/var/lib/asterisk/sounds/clarify_{q['key']}_{uniqueid}.wav"
            tts.generate_tts_file(clarification, clar_wav)
            agi.verbose(f"Playing clarification prompt: {clarification}", level=1)
            agi.stream_file(f"clarify_{q['key']}_{uniqueid}")
            continue  # Loop back to re-ask using composite context.
        
        # Validate the answer against valid options.
        validated = validate_answer(answer, valid_options)
        if validated is not None:
            # If the answer triggers exit.
            if "exit_if" in q and validated == q["exit_if"].lower():
                goodbye = q.get("exit_message", "Thank you for your time. Goodbye!")
                goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
                tts.generate_tts_file(goodbye, goodbye_wav)
                agi.stream_file(f"goodbye_{uniqueid}")
                agi.hangup()
                return None
            return validated
        
        # If still ambiguous, generate a clarifying prompt.
        conv_history = [
            {"role": "system", "content": "You are a friendly voice bot helping candidates select one of the valid options."},
            {"role": "user", "content": answer},
            {"role": "assistant", "content": f"The valid options are: {', '.join(valid_options)}. Please choose one of these options."}
        ]
        clarification = llm_client.query_llm(conv_history).strip()
        clar_wav = f"/var/lib/asterisk/sounds/clarify_{q['key']}_{uniqueid}.wav"
        tts.generate_tts_file(clarification, clar_wav)
        agi.verbose(f"Playing clarification prompt: {clarification}", level=1)
        agi.stream_file(f"clarify_{q['key']}_{uniqueid}")
        # Loop back to re-ask.
        
# -------------------------------------------------------------------------
# Main Conversational Flow
# -------------------------------------------------------------------------
def agi_main_flow_custom(agi):
    """
    Main flow for the Hiring Voice Bot using AI-powered functions.
    """
    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Hiring Voice Bot", level=1)
    
    env = agi.env
    log.info("AGI Environment: %s", env)
    uniqueid = env.get("agi_uniqueid", "default")
    
    candidate_name = env.get("agi_calleridname", "Candidate")
    company_name = os.getenv("COMPANY_NAME", "Maxicus")
    
    # Define questions with expected valid options.
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
            "question": "Since you answered 10th, do you have a 3-year diploma? Answer yes or no.",
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
    
    # Iterate through the questions.
    for q in questions:
        # Skip question if a condition is specified and not met.
        if "condition" in q and not q["condition"](candidate_details):
            continue
        answer = ask_question_with_ai(agi, q, uniqueid)
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
