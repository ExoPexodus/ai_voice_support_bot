# src/ai/ai_helpers.py

from src.ai import llm_client

def clean_llm_response(response):
    """
    Removes unwanted formatting tokens from the LLM response.
    If response is None, returns an empty string.
    """
    if response is None:
        return ""
    tokens = ["<|im_start|>user<|im_sep|>", "<|im_start|>assistant<|im_sep|>", "<|im_end|>"]
    for token in tokens:
        response = response.replace(token, "")
    return response.strip()

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
    Uses the LLM to determine if the candidate's response clearly includes one of the valid options.
    Valid options should be provided as a list of lowercase strings.
    If a valid option is found, returns that option; otherwise, returns None.
    """
    options_str = ", ".join(valid_options)
    prompt = (
        f"Candidate's response: \"{response}\".\n"
        f"Valid options: {options_str}.\n"
        "Check if the candidate's response clearly includes one of these options. "
        "If yes, respond with the matching option exactly as given (one word). "
        "If the response is ambiguous or does not clearly include any of these options, respond with 'none'. "
        "Respond with only one word."
    )
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).strip().lower()
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
    prompt = (
        f"The candidate asked: \"{candidate_followup}\". The primary question is: \"{primary_question}\". "
        f"Provide a smart, friendly response that acknowledges their follow-up and instructs them to answer the main question by choosing one of the following options: {options_str}. "
        "Do not repeat the entire primary question verbatim; just provide a concise clarification and directive. "
        "Do not use any emojis, and keep your answer small and concise."
    )
    conversation = [{"role": "system", "content": prompt}]
    raw_response = llm_client.query_llm(conversation)
    return clean_llm_response(raw_response)

def is_followup_question(response, valid_options):
    """
    Uses the LLM to decide if the candidate's response is a follow-up clarification question rather than a direct answer.
    Valid options should be provided for context.
    Respond with only 'yes' or 'no'.
    """
    options_str = ", ".join(valid_options)
    prompt = (
        f"Candidate's response: \"{response}\".\n"
        "Determine if this response is a follow-up clarification question (i.e., the candidate is asking for more details) "
        f"rather than directly answering the primary question. If the response includes any of these valid options: {options_str}, "
        "or if it clearly answers the question, then respond with 'no'. Otherwise, if it seems like they are asking for clarification, respond with 'yes'. "
        "Respond with only 'yes' or 'no'."
    )
    conversation = [{"role": "system", "content": prompt}]
    raw_result = llm_client.query_llm(conversation)
    result = clean_llm_response(raw_result).strip().lower()
    return result == "yes"
