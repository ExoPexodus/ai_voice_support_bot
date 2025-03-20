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
import asyncio

from asterisk.agi import AGI
from src.utils import logger
from src.speech import tts, stt
from src.ai import llm_client  # Azure LLM client
from src.dialogue_manager import DialogueManager

# --- MongoDB and AMI Integration ---
from pymongo import MongoClient
from asterisk.manager import Manager  # Ensure you have a suitable asterisk.manager module installed

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

def fetch_candidates():
    """Fetch candidates from the 'hra' database in the 'users' collection."""
    client = MongoClient(MONGO_URI)
    db = client["hra"]
    users_collection = db["users"]
    # Filter for active candidates who haven't verified yet.
    candidates = list(users_collection.find({"hasVerified": False, "IsActive": True}))
    return candidates

def initiate_outgoing_call(candidate):
    """
    Initiates an outgoing call to the candidate using AMI.
    Passes candidate name and phone as variables.
    """
    try:
        manager = Manager()
        manager.connect("localhost")
        # Use your AMI username and password here.
        manager.login("agiuser", "asgfaksdgja23123127ygu12uh3ixjk213i21ix3n21")
        action = {
            "Action": "Originate",
            "Channel": f"PJSIP/{candidate['phone']}",
            "Context": "custom-agi",  # This should match the dialplan context for your AGI script.
            "Exten": "s",
            "Priority": "1",
            "CallerID": candidate["phone"],
            "Timeout": "30000",
            # Pass candidate ID and name as channel variables so the AGI can access them.
            "Variable": f"CANDIDATE_ID={candidate['_id']},CANDIDATE_NAME={candidate['name']}"
        }
        response = manager.send_action(action)
        manager.logoff()
        return response
    except Exception as e:
        print(f"Error initiating call for {candidate['name']}: {e}")
        return None

def initiate_outgoing_calls():
    """Fetches candidates and initiates outgoing calls for each."""
    candidates = fetch_candidates()
    for candidate in candidates:
        print(f"Initiating call to {candidate['name']} at {candidate['phone']}")
        initiate_outgoing_call(candidate)

def update_candidate(candidate_id, conversation_data):
    """Updates a candidate's record in MongoDB with conversation data."""
    client = MongoClient(MONGO_URI)
    db = client["hra"]
    users_collection = db["users"]
    users_collection.update_one({"_id": candidate_id}, {"$set": conversation_data})

# --- Synchronous wrapper for async dialogue ---
def run_async_dialogue(agi, dm):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        final_action = loop.run_until_complete(dm.run_conversation(agi))
    finally:
        loop.close()
    return final_action

def agi_main_flow_custom(agi):
    log = logger.setup_logger()
    agi.verbose("Starting FastAGI Hiring Voice Bot", level=1)

    env = agi.env
    log.info("AGI Environment: %s", env)
    uniqueid = env.get("agi_uniqueid", "default")
    candidate_name = env.get("CANDIDATE_NAME", env.get("agi_calleridname", "Candidate"))
    candidate_id = env.get("CANDIDATE_ID", None)
    company_name = os.getenv("COMPANY_NAME", "Maxicus")

    # Define the conversation questions.
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
            "question": "Awesome. Now, what’s your preferred location for work? We're currently offering positions in Amritsar, Vadodara, Kolkata, Bangalore, Gurugram, and Pune.",
            "valid_options": ["amritsar", "vadodara", "kolkata", "bangalore", "gurugram", "pune"]
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

    dm = DialogueManager(questions, candidate_name, company_name, uniqueid)
    final_action = run_async_dialogue(agi, dm)

    # If candidate consented, update the candidate record in Mongo.
    if dm.candidate_responses.get("consent") == "yes" and candidate_id:
        update_candidate(candidate_id, dm.candidate_responses)
        agi.verbose(f"Candidate details updated in MongoDB for candidate_id {candidate_id}", level=1)
    else:
        agi.verbose("Candidate did not consent or candidate_id not provided.", level=1)

    if final_action and "prompt" in final_action:
        final_wav = f"/var/lib/asterisk/sounds/final_{uniqueid}.wav"
        tts.generate_tts_file(final_action["prompt"], final_wav)
        agi.verbose("Playing final thank you message", level=1)
        agi.stream_file(f"final_{uniqueid}")

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
    # Initiate outgoing calls first.
    print("Initiating outgoing calls to candidates...")
    from pymongo import MongoClient
    from asterisk.manager import Manager

    def initiate_outgoing_call(candidate):
        try:
            manager = Manager()
            manager.connect("localhost")
            manager.login("manager", "secret")
            action = {
                "Action": "Originate",
                "Channel": f"PJSIP/{candidate['phone']}",
                "Context": "custom-agi",  # This should match your dialplan.
                "Exten": "s",
                "Priority": "1",
                "CallerID": candidate["phone"],
                "Timeout": "30000",
                "Variable": f"CANDIDATE_ID={candidate['_id']},CANDIDATE_NAME={candidate['name']}"
            }
            response = manager.send_action(action)
            manager.logoff()
            return response
        except Exception as e:
            print(f"Error initiating call for {candidate['name']}: {e}")
            return None

    def fetch_candidates():
        client = MongoClient("mongodb://localhost:27017/")
        db = client["hra"]
        users_collection = db["users"]
        candidates = list(users_collection.find({"hasVerified": False, "IsActive": True}))
        return candidates

    def initiate_outgoing_calls():
        candidates = fetch_candidates()
        for candidate in candidates:
            print(f"Initiating call to {candidate['name']} at {candidate['phone']}")
            initiate_outgoing_call(candidate)

    initiate_outgoing_calls()

    # Start the FastAGI server.
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
