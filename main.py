from src.speech import stt, tts
from src.ai import llm_client
from src.utils import logger

def vary_prompt(prompt):
    """
    Uses the LLM to produce a variation of the given prompt.
    """
    system_prompt = (
        "You are a creative assistant. Given the following question prompt, produce a varied version of it "
        "without using any special characters. The meaning should remain the same."
    )
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    response = llm_client.query_llm(conversation)
    clean_response = (
        response.replace("<|im_start|>assistant<|im_sep|>", "")
                .replace("<|im_end|>", "")
                .strip()
    )
    return clean_response if clean_response else prompt

def is_followup_question(candidate_response):
    """
    Determines if the candidate's response is actually a follow-up question asking for clarification.
    """
    system_prompt = (
        "You are a question classifier. Given the candidate's response, determine if it contains a follow-up "
        "question asking for clarification or more details. Answer exactly 'yes' or 'no'."
    )
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": candidate_response}
    ]
    analysis = llm_client.query_llm(conversation)
    clean_analysis = (
        analysis.replace("<|im_start|>assistant<|im_sep|>", "")
                .replace("<|im_end|>", "")
                .strip().lower()
    )
    return "yes" in clean_analysis

def handle_followup(candidate_followup):
    """
    Uses the LLM to answer a candidate's follow-up question.
    """
    system_prompt = (
        "You are an assistant providing clarifications for a job application conversation. "
        "Answer the candidate's follow up question in a clear and concise manner without using any special characters."
    )
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": candidate_followup}
    ]
    response = llm_client.query_llm(conversation)
    clean_response = (
        response.replace("<|im_start|>assistant<|im_sep|>", "")
                .replace("<|im_end|>", "")
                .strip()
    )
    return clean_response

def interpret_candidate_response(candidate_response):
    """
    Uses the LLM to interpret the candidate's response as either positive or negative.
    Outputs exactly one word: 'positive' or 'negative'.
    """
    system_prompt = (
        "You are a sentiment analysis assistant. Given the candidate's response, determine if it indicates "
        "a positive or negative intent. Output exactly one word: 'positive' if the candidate is affirming, "
        "or 'negative' if they are not. Do not include any extra text."
    )
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": candidate_response}
    ]
    analysis = llm_client.query_llm(conversation)
    clean_analysis = (
        analysis.replace("<|im_start|>assistant<|im_sep|>", "")
                .replace("<|im_end|>", "")
                .strip().lower()
    )
    return "negative" if "negative" in clean_analysis else "positive"

def main_flow():
    log = logger.setup_logger()
    log.info("Starting scripted job application conversation with selective LLM functions...")

    # Define the conversation script. Each question includes flags for LLM usage.
    conversation_script = [
        {
            "prompt": "Hi, This is Aisha from Maxicus, Are you looking for a Job?",
            "variable": "job_interest",
            "exit_on_no": True,
            "llm_vary": True,
            "llm_intent": True,
            "llm_followup": False
        },
        {
            "prompt": "Thanks, We have currently an opening for customer care executive role. Will you be interested in same?",
            "variable": "role_interest",
            "exit_on_no": True,
            "llm_vary": True,
            "llm_intent": True,
            "llm_followup": False
        },
        {
            "prompt": "Ok, Let me explain the job role: as a customer care executive, you will have to support customers over chat and voice. Are you comfortable with that?",
            "variable": "comfort",
            "exit_on_no": True,
            "llm_vary": True,
            "llm_intent": True,
            "llm_followup": True
        },
        {
            "prompt": "For which location do you want to apply? Current openings are for Amritsar, Gurgaon, Kolkata, Vadodara.",
            "variable": "location",
            "exit_on_no": False,
            "llm_vary": True,
            "llm_intent": False,
            "llm_followup": True
        },
        {
            "prompt": "May I know your qualification?",
            "variable": "qualification",
            "exit_on_no": False,
            "llm_vary": True,
            "llm_intent": False,
            "llm_followup": True
        },
        {
            "prompt": "Do you have any previous experience?",
            "variable": "experience",
            "exit_on_no": False,
            "llm_vary": False,
            "llm_intent": False,
            "llm_followup": True
        },
        {
            "prompt": "Any salary expectation?",
            "variable": "salary_expectation",
            "exit_on_no": False,
            "llm_vary": False,
            "llm_intent": False,
            "llm_followup": True
        },
        {
            "prompt": "Thanks, can I upload the provided information?",
            "variable": "upload_permission",
            "exit_on_no": True,
            "llm_vary": False,
            "llm_intent": True,
            "llm_followup": False
        }
    ]

    candidate_info = {}

    for step in conversation_script:
        # Use LLM to vary the prompt if required.
        prompt = step["prompt"]
        if step.get("llm_vary", False):
            prompt = vary_prompt(prompt)
        tts.text_to_speech(prompt)

        candidate_response = stt.speech_to_text(timeout=60)
        if candidate_response is None:
            tts.text_to_speech("No input received. Ending session. Goodbye!")
            log.info("No input received for prompt: {}".format(step["prompt"]))
            return

        # If follow-up handling is enabled for this question, check if the response is a follow-up.
        if step.get("llm_followup", False) and is_followup_question(candidate_response):
            followup_answer = handle_followup(candidate_response)
            tts.text_to_speech(followup_answer)
            tts.text_to_speech("Now, please answer the question: " + prompt)
            candidate_response = stt.speech_to_text(timeout=60)
            if candidate_response is None:
                tts.text_to_speech("No input received. Ending session. Goodbye!")
                log.info("No input received after follow-up for prompt: {}".format(step["prompt"]))
                return

        log.info("Candidate raw response for {}: {}".format(step["variable"], candidate_response.strip()))
        
        # If intent checking is enabled and the question has exit_on_no, interpret the response.
        if step.get("exit_on_no", False) and step.get("llm_intent", False):
            intent = interpret_candidate_response(candidate_response)
            log.info("LLM interpreted response for {} as: {}".format(step["variable"], intent))
            if intent == "negative":
                tts.text_to_speech("Alright, thank you for your time. Goodbye!")
                log.info("Exiting conversation due to negative response for prompt: {}".format(step["prompt"]))
                return

        candidate_info[step["variable"]] = candidate_response.strip()
        log.info("Stored response for {}: {}".format(step["variable"], candidate_response.strip()))

    final_message = (
        "Ok! I have forwarded the provided information and you will soon get a call from our end. "
        "Have a great day ahead."
    )
    tts.text_to_speech(final_message)
    log.info("Final message: {}".format(final_message))
    log.info("Candidate Information Collected: {}".format(candidate_info))

if __name__ == "__main__":
    main_flow()
