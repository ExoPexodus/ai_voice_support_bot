# src/main.py

from src.speech import stt, tts
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger
import re
import spacy

# Load spaCy English model
nlp = spacy.load("en_core_web_sm")

def extract_order_number(text):
    """
    Extracts order numbers from user input using NLP + regex.
    """
    doc = nlp(text)
    
    # Try extracting numbers using NLP
    for ent in doc.ents:
        if ent.label_ == "CARDINAL":  # spaCy detects numbers as "CARDINAL"
            # Check if "order" or similar words appear near the number
            if any(token.text.lower() in ["order", "id", "number"] for token in ent.root.head.lefts):
                print(f"[DEBUG] Extracted order number via NLP: {ent.text}")
                return ent.text

    # Fallback: Use regex to catch missed cases
    pattern = r'\b(?:order(?:\s*(?:id|number))?|id|number)?\s*(?:is|was|should be|supposed to be)?\s*[:#]?\s*(\d{3,10})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        print(f"[DEBUG] Extracted order number via Regex: {match.group(1)}")
        return match.group(1)

    # Final fallback: If user ONLY says a number, assume it's an order ID
    if text.strip().isdigit():
        print(f"[DEBUG] Extracted standalone order number: {text.strip()}")
        return text.strip()

    print("[DEBUG] No order number found in the input.")
    return None


def main_flow():
    log = logger.setup_logger()
    log.info("Starting AI Voice Support Bot...")
    
    company_name = "Maxicus"
    candidate_name = "Jatin"
    
    # Play a welcome message when the user connects
    #welcome_message = f"Hi! Am i speaking with {candidate_name}?"
    welcome_message = f"नमस्ते, क्या मैं {candidate_name} से बात कर रही हूँ?"
    tts.text_to_speech(welcome_message)

    # Initialize conversation history with a system prompt for context
    system_prompt = (
    f"You are a friendly female, conversational AI recruiter for {company_name} and you're currently talking to {candidate_name}. After confirming the candidate's identity, immediately generate a dynamic, context-aware opening that naturally sets the purpose of the call. This opening should be creative, engaging, and reflect excitement about the opportunity at {company_name} without relying on pre-written templates."
    "Your duty is to re-engage candidates who dropped out of the application process and to gather the following details: highest qualification, preferred work location (choose only from [amritsar, vadodara, kolkata, bangalore, gurugram, pune]), and interview mode (choose only from [in-person, virtual/video call, telephonic/phone]). If the candidate states 10th grade as their highest qualification, additionally ask if they hold a 3-year diploma."
    "Conduct the conversation naturally by asking one question at a time, building context as you go—do not bombard the candidate with multiple questions at once. Keep your sentences short, clear, and to the point. If the candidate expresses disinterest (for example, by saying 'no', 'bye', or 'not interested'), immediately end the conversation and append the marker [EARLY_END_CONVERSATION] to your final message. Once all required details are collected, ask for the candidate's consent to store their information, and if granted, conclude your conversation by appending the marker [END_CONVERSATION] and no need to tell them to ask you any further questions at the end."
    "Remember, you must stay strictly within this context and refrain from addressing any topics that do not relate to gathering the required details. Also, Strictly do not use any emojis."
    "and Make sure your responses are as concise as possible"
    )
    conversation_history = [{"role": "system", "content": system_prompt}]

    # Define exit keywords for ending the session
    exit_keywords = ["bye", "exit", "quit", "end call", "end the call", "goodbye", "thank you", "that's all", "no", "not really"]

    while True:
        # Wait for user input with a 30-second timeout
        user_input = stt.speech_to_text(timeout=60)
        if user_input is None:
            tts.text_to_speech("No input received. Ending session. Goodbye!")
            break
        
        # Check if any exit keyword is contained in the user input
        if any(keyword in user_input.lower() for keyword in exit_keywords):
            tts.text_to_speech("Thank you for your time. Have a great day!")
            break
        
        log.info("User said: %s", user_input)
        conversation_history.append({"role": "user", "content": user_input})

        # Check for an order number in the user input
        order_number = extract_order_number(user_input)
        if order_number:
            order_data = data_fetcher.fetch_order_data(order_number, source="csv")
            log.info(f"Fetched Order Data: {order_data}")
            # Append a system message with order details as additional context
            order_context_message = f"Order details for order {order_number}: {order_data}"
            conversation_history.append({"role": "system", "content": order_context_message})
        else:
            log.info("No order number found in the input.")
        
        # Query the LLM with the entire conversation history
        ai_response = llm_client.query_llm(conversation_history)
        
        # Clean the response by removing unwanted formatting tokens
        clean_response = (
            ai_response
            .replace("<|im_start|>assistant<|im_sep|>", "")
            .replace("<|im_end|>", "")
            .replace("[EARLY_END_CONVERSATION]", "")
            .replace("[END_CONVERSATION]", "")
            .strip()
        )
        
        log.info("AI Response: %s", clean_response)
        conversation_history.append({"role": "assistant", "content": clean_response})
        tts.text_to_speech(clean_response)

if __name__ == "__main__":
    main_flow()