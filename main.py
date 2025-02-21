# src/main.py

from src.speech import stt, tts
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger
import re

def extract_order_number(text):
    """
    Attempts to extract an order number from the given text.
    Looks for patterns like "order id 1113", "order number 1113", or "order 1113".
    This regex also handles phrases like "order id is supposed to be 1113".
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
    
    # Initialize conversation history with a system prompt for context
    system_prompt = "You are a customer support executive working for zomato, you are an expert at dealing with customers in food industry, answer all their questions according to how a customer support would. Keep in mind that you'll be in a call with the customer so Make sure you have a very nice and gentle tone when dealing with the customer, And also make sure to give very short and very concise and to the point answers(don't use any special caracters or emojis or any brackets to express any additional emotions or actions)"
    conversation_history = [{"role": "system", "content": system_prompt}]

    # Define exit keywords for ending the session
    exit_keywords = ["bye", "exit", "quit", "end call", "end the call", "goodbye"]

    while True:
        # Wait for user input with a 30-second timeout
        user_input = stt.speech_to_text(timeout=30)
        if user_input is None:
            tts.text_to_speech("No input received for 30 seconds. Ending session. Goodbye!")
            break
        
        # Check if any exit keyword is contained in the user input
        if any(keyword in user_input.lower() for keyword in exit_keywords):
            tts.text_to_speech("Thank you for contacting Zomato support. Have a great day!")
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
            .strip()
        )
        
        log.info("AI Response: %s", clean_response)
        conversation_history.append({"role": "assistant", "content": clean_response})
        tts.text_to_speech(clean_response)

if __name__ == "__main__":
    main_flow()
