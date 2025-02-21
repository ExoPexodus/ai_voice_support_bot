# src/main.py

from src.speech import stt, tts
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger
import re

def extract_order_number(text):
    """
    Attempts to extract an order number from the given text.
    Looks for patterns like "order id 12345", "order number 12345", or "order 12345".
    This updated regex also handles phrases like "order id is supposed to be 1113".
    
    :return: The order number as a string if found, otherwise None.
    """
    pattern = r'\border(?:\s*(?:id|number))?\s*(?:is\s*)?(?:[:#]?\s*)?(\d+)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        order_num = match.group(1)
        print(f"[DEBUG] Extracted order number: {order_num}")
        return order_num
    else:
        print("[DEBUG] No order number found in the input.")
    return None

def main_flow():
    log = logger.setup_logger()
    log.info("Starting AI Voice Support Bot...")

    # Play a welcome message when the user connects
    welcome_message = "Welcome to Zomato customer support. How can I assist you today?"
    tts.text_to_speech(welcome_message)
    
    # Set up a simple system prompt for context
    system_prompt = "You are a customer support executive working for zomato, you are an expert at dealing with customers in food industry, answer all their questions according to how a customer support would. Keep in mind that you'll be in a call with the customer so Make sure you have a very nice and gentle tone when dealing with the customer, And also make sure to give very short and very concise and to the point answers(don't use any special caracters or emojis)"
    
    while True:
        # Wait for user input with a 30-second timeout
        user_input = stt.speech_to_text(timeout=30)
        if user_input is None:
            tts.text_to_speech("No input received for 30 seconds. Ending session. Goodbye!")
            break
        
        if user_input.strip().lower() in ["bye", "exit", "quit"]:
            tts.text_to_speech("Thank you for contacting Zomato support. Have a great day!")
            break
        
        log.info("User said: %s", user_input)
        
        # Attempt to extract an order number from the user's input
        order_number = extract_order_number(user_input)
        additional_context = ""
        if order_number:
            # Log the extracted order number
            log.info(f"Extracted Order Number: {order_number}")
            order_data = data_fetcher.fetch_order_data(order_number, source="csv")
            log.info(f"Fetched Order Data: {order_data}")
            additional_context = f" Order details: {order_data}"
        else:
            log.info("No order number found in the input.")
        
        # Combine the user's input with any additional context from the CSV
        full_user_message = user_input + additional_context
        
        # Create a simple conversation: system prompt + user's message
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_user_message}
        ]
        
        # Query the LLM
        ai_response = llm_client.query_llm(conversation)
        log.info("AI Response: %s", ai_response)
        tts.text_to_speech(ai_response)

if __name__ == "__main__":
    main_flow()
