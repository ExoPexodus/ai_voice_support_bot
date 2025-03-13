import csv
from src.speech import stt, tts
from src.ai import llm_client
from src.utils import logger
import json

def clean_response(response):
    return (
        response.replace("<|im_start|>assistant<|im_sep|>", "")
                .replace("<|im_end|>", "")
                .strip()
    )

def interpret_candidate_response(candidate_response, conversation_history):
    """
    Uses the LLM to determine if the candidate's response is positive or negative.
    Returns exactly one word: 'positive' or 'negative'.
    """
    system_prompt = (
        "You are a sentiment analysis assistant. Given the conversation history and the candidate's latest response, "
        "determine if the intent is positive or negative. Output exactly one word: 'positive' or 'negative'."
    )
    conversation = [{"role": "system", "content": system_prompt}] + conversation_history
    conversation.append({"role": "user", "content": candidate_response})
    analysis = llm_client.query_llm(conversation)
    return "negative" if "negative" in clean_response(analysis).lower() else "positive"

def custom_check(candidate_response, check_type, conversation_history, original_prompt):
    """
    Uses the LLM to verify that the candidate's response is appropriate for the current question.
    
    For check_type "role_interest": if the candidate's answer indicates they're asking about other positions,
      return (False, <custom message>).
    
    For check_type "location": if the candidate's answer does not mention one of the required cities,
      return (False, <custom message>).
    
    For check_type "qualifications": if the candidate's response is asking for further details about what qualifications 
      are required for this role, return (False, <custom message> with a brief overview of required qualifications).
    
    For check_type "experience": if the candidate's response asks for further details about whether certain experience 
      is relevant or not, return (False, <custom message> explaining what experience is considered relevant).
    
    For check_type "expectation": if the candidate's response asks for further salary details, return (False, <custom message>
      indicating that detailed salary information is not disclosed and asking them to state their own expectations).
    
    Otherwise, return (True, "").
    """
    if check_type == "role_interest":
        system_prompt = (
            "You are an assistant verifying candidate responses for a job role interest question. "
            "The candidate is asked: 'We have currently an opening for customer care executive role. Will you be interested in it?'. "
            "If the candidate's response is asking about alternative positions (e.g. 'Are there any other positions available?'), "
            "answer 'inappropriate'. Otherwise, answer 'appropriate'."
        )
        conversation = [{"role": "system", "content": system_prompt}] + conversation_history
        conversation.append({"role": "user", "content": candidate_response})
        analysis = llm_client.query_llm(conversation)
        cleaned = clean_response(analysis).lower()
        if "inappropriate" in cleaned:
            return (False, "This is the only position currently open. Please answer if you're interested in this opportunity.")
        else:
            return (True, "")
    elif check_type == "location":
        system_prompt = (
            "You are an assistant verifying candidate responses for a job location question. "
            "The candidate is asked: 'For which location would you like to apply? Our options are Amritsar, Gurgaon, Kolkata, and Vadodara.' "
            "If the candidate's response does not mention one of these cities, answer 'invalid'. Otherwise, answer 'valid'."
            " If the candidate asks if there's any position available in another city, answer 'invalid'."
        )
        conversation = [{"role": "system", "content": system_prompt}] + conversation_history
        conversation.append({"role": "user", "content": candidate_response})
        analysis = llm_client.query_llm(conversation)
        cleaned = clean_response(analysis).lower()
        if "invalid" in cleaned:
            return (False, "Our available options are Amritsar, Gurgaon, Kolkata, and Vadodara. Please choose one of these.")
        else:
            return (True, "")
    elif check_type == "qualifications":
        system_prompt = (
            "You are an assistant verifying candidate responses for a qualifications question. "
            "The candidate is asked: 'May I know your qualification?'. "
            "If the candidate's response is asking for further details about the required qualifications for this role, "
            "answer 'inappropriate'. Otherwise, answer 'appropriate'."
        )
        conversation = [{"role": "system", "content": system_prompt}] + conversation_history
        conversation.append({"role": "user", "content": candidate_response})
        analysis = llm_client.query_llm(conversation)
        cleaned = clean_response(analysis).lower()
        if "inappropriate" in cleaned:
            return (False, "For this role, a minimum of a high school diploma is required, and a college degree may be preferred. Please confirm your qualification.")
        else:
            return (True, "")
    elif check_type == "experience":
        system_prompt = (
            "You are an assistant verifying candidate responses for an experience question. "
            "The candidate is asked: 'Do you have any previous experience?'. "
            "If the candidate's response is asking for further details about whether a certain type of experience is relevant or counts, "
            "answer 'inappropriate'. Otherwise, answer 'appropriate'."
        )
        conversation = [{"role": "system", "content": system_prompt}] + conversation_history
        conversation.append({"role": "user", "content": candidate_response})
        analysis = llm_client.query_llm(conversation)
        cleaned = clean_response(analysis).lower()
        if "inappropriate" in cleaned:
            return (False, "For this role, any relevant experience in customer service or communication is valuable. Please indicate if you have such experience.")
        else:
            return (True, "")
    elif check_type == "expectation":
        system_prompt = (
            "You are an assistant verifying candidate responses for a salary expectation question. "
            "The candidate is asked: 'What are your salary expectations?'. "
            "If the candidate's response is asking for further details about the salary range or other salary information, even if its something as vague as what can you offer, basically if they ask a question,"
            "answer 'inappropriate'. Otherwise, answer 'appropriate'."
        )
        conversation = [{"role": "system", "content": system_prompt}] + conversation_history
        conversation.append({"role": "user", "content": candidate_response})
        analysis = llm_client.query_llm(conversation)
        cleaned = clean_response(analysis).lower()
        if "inappropriate" in cleaned:
            return (False, "I'm not allowed to disclose detailed salary information for this position as that is determined internally. Please state your salary expectations.")
        else:
            return (True, "")
    return (True, "")

def refine_candidate_data(candidate_info):
    """
    Uses the LLM to refine and normalize candidate data.
    The candidate_info dictionary is converted to JSON and sent to the LLM with instructions to output a refined JSON.
    """
    system_prompt = (
        "You are a data refinement assistant. Given the following candidate data in JSON format, "
        "refine the data by applying proper capitalization, punctuation, and clarity. "
        "Return the refined data in JSON format with the same keys."
        "Make the data more concise and precise as well"
        "this information will be stored in csv file"
        "so make sure all the information that you keep after refining is as small and as to the point as possible"
    )
    # Convert candidate_info to a JSON string.
    raw_data = json.dumps(candidate_info)
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_data}
    ]
    response = llm_client.query_llm(conversation)
    refined_str = clean_response(response)
    try:
        refined_data = json.loads(refined_str)
    except Exception as e:
        refined_data = candidate_info  # Fallback to original data if parsing fails.
    return refined_data

def save_candidate_info(candidate_info, filename="candidate_info.csv"):
    """
    Saves the candidate's information (a dictionary) to a CSV file.
    If the file doesn't exist, a header row is added.
    """
    import os
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=candidate_info.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(candidate_info)

def main_flow():
    log = logger.setup_logger()
    log.info("Starting job application conversation with custom checks for qualifications, experience, and salary expectation...")

    conversation_script = [
        {
            "prompt": "Hi, this is Aisha from Maxicus, are you looking for a job?",
            "variable": "job_interest",
            "exit_on_no": True,
            "llm_intent": True
        },
        {
            "prompt": "We have currently an opening for a customer care executive role. Will you be interested in it?",
            "variable": "role_interest",
            "exit_on_no": True,
            "llm_intent": True,
            "custom_check": "role_interest"
        },
        {
            "prompt": "Ok, let me explain the job role: as a customer care executive, you will support customers via chat and phone. Are you comfortable with that?",
            "variable": "comfort",
            "exit_on_no": True,
            "llm_intent": True
        },
        {
            "prompt": "For which location would you like to apply? Our options are Amritsar, Gurgaon, Kolkata, and Vadodara.",
            "variable": "location",
            "exit_on_no": False,
            "custom_check": "location"
        },
        {
            "prompt": "May I know your qualification?",
            "variable": "qualification",
            "exit_on_no": False,
            "custom_check": "qualifications"
        },
        {
            "prompt": "Do you have any previous experience?",
            "variable": "experience",
            "exit_on_no": False,
            "custom_check": "experience"
        },
        {
            "prompt": "What are your salary expectations?",
            "variable": "salary_expectation",
            "exit_on_no": False,
            "custom_check": "expectation"
        },
        {
            "prompt": "Thanks, can I upload the provided information for review?",
            "variable": "upload_permission",
            "exit_on_no": True,
            "llm_intent": True
        }
    ]

    candidate_info = {}
    conversation_history = []

    for step in conversation_script:
        original_prompt = step["prompt"]
        tts.text_to_speech(original_prompt)
        conversation_history.append({"role": "assistant", "content": original_prompt})

        candidate_response = stt.speech_to_text(timeout=60)
        if candidate_response is None:
            tts.text_to_speech("No input received. Ending session. Goodbye!")
            return
        conversation_history.append({"role": "user", "content": candidate_response})

        # If a custom check is defined, verify the response.
        if "custom_check" in step:
            valid, message = custom_check(candidate_response, step["custom_check"], conversation_history, original_prompt)
            if not valid:
                tts.text_to_speech(message)
                # Wait for the candidate's revised answer.
                candidate_response = stt.speech_to_text(timeout=60)
                if candidate_response is None:
                    tts.text_to_speech("No input received. Ending session. Goodbye!")
                    return
                conversation_history.append({"role": "user", "content": candidate_response})

        # For yes/no questions with exit_on_no enabled, check sentiment.
        if step.get("exit_on_no", False) and step.get("llm_intent", False):
            intent = interpret_candidate_response(candidate_response, conversation_history)
            if intent == "negative":
                tts.text_to_speech("Alright, thank you for your time. Goodbye!")
                return

        candidate_info[step["variable"]] = candidate_response.strip()
        log.info("Stored {}: {}".format(step["variable"], candidate_response.strip()))

    final_message = "Ok! I have forwarded the provided information and you will soon get a call from our end. Have a great day ahead."
    tts.text_to_speech(final_message)
    log.info("Candidate Information Collected: {}".format(candidate_info))

    # Refine the candidate data using LLM before saving.
    refined_info = refine_candidate_data(candidate_info)
    save_candidate_info(refined_info)

if __name__ == "__main__":
    main_flow()
