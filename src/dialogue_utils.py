# src/dialogue_utils.py

import time
from src.speech import tts, stt
from src.ai.ai_helpers import (
    determine_sentiment,
    validate_option,
    generate_smart_clarification,
    is_followup_question
)

def ask_question(agi, question_data, uniqueid):
    """
    Asks a single question and handles candidate responses using AI.
    
    For yes/no questions (valid_options == ["yes", "no"]), it determines sentiment.
    For other questions, it validates the answer.
    
    If a follow-up question is detected, it generates a smart clarification prompt
    that instructs the candidate to answer the primary question, then waits for a new answer.
    
    Returns the validated answer (in lowercase) or None if the conversation is terminated.
    """
    valid_options = [opt.lower() for opt in question_data["valid_options"]]
    primary_prompt = question_data["question"]
    clarification_mode = False
    smart_prompt = ""
    
    while True:
        current_prompt = smart_prompt if clarification_mode else primary_prompt
        
        # Play the prompt.
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
        if not agi:
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
        
        # Check if response is a follow-up question.
        if not clarification_mode and is_followup_question(response, valid_options):
            smart_prompt = generate_smart_clarification(primary_prompt, response, valid_options)
            agi.verbose(f"Smart clarification generated: {smart_prompt}", level=1)
            clarification_mode = True
            continue
        
        # Validate candidate's answer.
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
