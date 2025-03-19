#!/fastagi_server.py
"""
fastagi_server.py - FastAGI server for your Hiring Voice Bot.
This server listens for AGI requests over TCP and dispatches them to your AI-powered conversational logic.
Repurposed for calling Maxicus’s job candidates for customer support roles.
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
from src.ai import llm_client  # Our Azure LLM client

def ask_question_with_ai(agi, q, uniqueid):
    """
    Ask a single question and use AI to clarify if the candidate's response is not one of the valid options.
    Loops until a valid answer is received.
    
    q: dictionary with keys:
      - key: identifier for the question
      - question: question text
      - valid_options: list of valid (lowercase) answers
      - exit_if (optional): if candidate answers this, end the conversation
      - exit_message (optional): goodbye message if exiting early
    """
    # Setup conversation history for this question.
    system_prompt = ("You are a friendly, articulate voice bot for a hiring app. "
                     "Your job is to clarify candidate responses so that they pick one of the valid options provided. "
                     "If the candidate's answer does not match the valid options, ask a clear, concise follow-up question.")
    conversation_history = [{"role": "system", "content": system_prompt}]
    valid_options = [opt.lower() for opt in q["valid_options"]]
    
    while True:
        # Use TTS to play the initial prompt (or clarification prompt on subsequent loops).
        prompt = q["question"]
        wav_file = f"/var/lib/asterisk/sounds/{q['key']}_{uniqueid}.wav"
        tts.generate_tts_file(prompt, wav_file)
        agi.verbose(f"Playing prompt: {prompt}", level=1)
        agi.stream_file(f"{q['key']}_{uniqueid}")
        
        # Record the candidate's answer.
        input_filename = f"input_{q['key']}_{uniqueid}"
        input_wav = f"/var/lib/asterisk/sounds/{input_filename}.wav"
        agi.verbose("Recording candidate input...", level=1)
        agi.record_file(input_filename, format="wav", escape_digits="#", timeout=60000, offset=0, beep="beep", silence=5)
        time.sleep(2)
        if os.path.exists(input_wav):
            agi.verbose(f"Recording file exists: {input_wav}", level=1)
        else:
            agi.verbose(f"Recording file NOT found: {input_wav}", level=1)
        
        answer = stt.recognize_from_file(input_wav)
        answer = answer.strip().lower() if answer else ""
        agi.verbose(f"Candidate said: {answer}", level=1)
        
        # If no input received, exit.
        if answer == "":
            goodbye_message = "No input received. Ending session. Goodbye!"
            goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
            tts.generate_tts_file(goodbye_message, goodbye_wav)
            agi.verbose("Playing goodbye message", level=1)
            agi.stream_file(f"goodbye_{uniqueid}")
            agi.hangup()
            return None
        
        # Check if this answer triggers an exit.
        if "exit_if" in q and answer == q["exit_if"].lower():
            goodbye_message = q.get("exit_message", "Thank you for your time. Goodbye!")
            goodbye_wav = f"/var/lib/asterisk/sounds/goodbye_{uniqueid}.wav"
            tts.generate_tts_file(goodbye_message, goodbye_wav)
            agi.verbose("Playing exit message", level=1)
            agi.stream_file(f"goodbye_{uniqueid}")
            agi.hangup()
            return None
        
        # If answer is valid, return it.
        if answer in valid_options:
            return answer
        
        # Otherwise, candidate's answer is ambiguous.
        # Append candidate's ambiguous response to conversation history.
        conversation_history.append({"role": "user", "content": answer})
        # Ask LLM to generate a clarifying question.
        clarify_prompt = (f"The candidate answered: '{answer}'. The valid options are: {', '.join(valid_options)}. "
                          f"Ask a short, friendly clarification question so that the candidate can choose one of the valid options.")
        conversation_history.append({"role": "assistant", "content": clarify_prompt})
        ai_response = llm_client.query_llm(conversation_history)
        clarification_message = ai_response.replace("<|im_start|>assistant<|im_sep|>", "").replace("<|im_end|>", "").strip()
        conversation_history.append({"role": "assistant", "content": clarification_message})
        
        # Use TTS to play the clarifying message.
        clarify_wav = f"/var/lib/asterisk/sounds/clarify_{q['key']}_{uniqueid}.wav"
        tts.generate_tts_file(clarification_message, clarify_wav)
        agi.verbose(f"Playing clarification prompt: {clarification_message}", level=1)
        agi.stream_file(f"clarify_{q['key']}_{uniqueid}")
        # Loop back and ask again.

def agi_main_flow_custom(agi):
    """
    Main flow for the Hiring Voice Bot using AI for conversational clarity.
    """
    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Hiring Voice Bot", level=1)
    
    # Get AGI environment and uniqueid.
    env = agi.env
    log.info("AGI Environment: %s", env)
    uniqueid = env.get("agi_uniqueid", "default")
    
    candidate_name = env.get("agi_calleridname", "Ravinder")
    company_name = os.getenv("COMPANY_NAME", "Maxicus")
    
    # Define our conversation questions.
    questions = [
        {
            "key": "confirmation",
            "question": f"Hello {candidate_name}, this is {company_name} calling. Hope you're doing well! We're excited to chat with you about a potential opportunity. Before we begin, are you still interested in joining our team? Answer yes or no.",
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "Thank you for your time. Have a great day!"
        },
        {
            "key": "qualification",
            "question": ("Great, thanks for confirming! Now, could you tell me what your highest qualification is? "
                         "Please choose from: 10th, Post-graduate, Graduate, or 12th."),
            "valid_options": ["10th", "post-graduate", "graduate", "12th"]
        },
        {
            "key": "diploma",
            "question": "Since you said 10th, do you have a 3-year diploma? Please answer yes or no.",
            "valid_options": ["yes", "no"],
            "condition": lambda responses: responses.get("qualification", "") == "10th"
        },
        {
            "key": "job_type",
            "question": ("Next, are you looking for a permanent full-time position, a part-time role, or a freelance/gig arrangement? "
                         "Please answer with one of these options."),
            "valid_options": ["permanent", "full time", "part-time", "freelance", "gig"]
        },
        {
            "key": "location",
            "question": ("Awesome. Now, what is your preferred location for work? Your options are: Amritsar, Vadodara, Kolkata, Banglore, Gurugram, or Pune."),
            "valid_options": ["amritsar", "vadodara", "kolkata", "banglore", "gurugram", "pune"]
        },
        {
            "key": "interview_mode",
            "question": ("Almost there—how would you like to have your interview? Please choose: In-person, Virtual (Video Call), or Telephonic."),
            "valid_options": ["in-person", "virtual", "video call", "telephonic", "phone"]
        },
        {
            "key": "consent",
            "question": ("Lastly, do we have your permission to share this information with our internal team for follow-up? Answer yes or no."),
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "Thanks for your time. We respect your decision and will not share your details. Goodbye!"
        }
    ]
    
    candidate_details = {}  # Store candidate responses.
    
    # Iterate over each question.
    for q in questions:
        # If a condition is set and not met, skip this question.
        if "condition" in q and not q["condition"](candidate_details):
            continue
        answer = ask_question_with_ai(agi, q, uniqueid)
        if answer is None:
            # Session ended in ask_question_with_ai due to exit condition.
            return
        candidate_details[q["key"]] = answer
        agi.verbose(f"Recorded {q['key']}: {answer}", level=1)
    
    # Finalize the conversation.
    final_message = (f"Fantastic! That's everything we need for now, {candidate_name}. "
                     f"Thank you for your time. Our team at {company_name} will review your details and reach out soon with next steps. Have a great day!")
    final_wav = f"/var/lib/asterisk/sounds/final_{uniqueid}.wav"
    tts.generate_tts_file(final_message, final_wav)
    agi.verbose("Playing final thank you message", level=1)
    agi.stream_file(f"final_{uniqueid}")
    
    agi.hangup()

# --- FastAGI Handler using Forking ---
class FastAGIHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            # Wrap binary streams with TextIOWrapper for text I/O.
            self.rfile = io.TextIOWrapper(self.rfile, encoding="utf-8")
            self.wfile = io.TextIOWrapper(self.wfile, encoding="utf-8", write_through=True)
            
            agi = AGI(stdin=self.rfile, stdout=self.wfile)
            self.server.logger.info("FastAGI request from %s", self.client_address)
            agi_main_flow_custom(agi)
        except Exception as e:
            self.server.logger.error("Exception in FastAGIHandler: %s", e)

# Use ForkingTCPServer to handle each AGI connection in a separate process.
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
        logger_server.info("FastAGI server shutting down")
        server.shutdown()
