# src/main.py

from src.speech import stt, tts
from src.ai import llm_client
from src.data import data_fetcher
from src.utils import logger

def main_flow():
    log = logger.setup_logger()
    
    log.info("Starting AI Voice Support Bot...")
    
    # Step 1: Convert user speech to text
    user_input = stt.speech_to_text()
    if not user_input:
        tts.text_to_speech("Sorry, I didn't catch that. Please try again.")
        return

    log.info("User said: %s", user_input)
    
    # Step 2: Get AI response from the Azure-hosted LLM
    ai_response = llm_client.query_llm(user_input,"You are a customer support executive working for zomato, you are an expert at dealing with customers in food industry, answer all their questions according to how a customer support would. Make sure you have a very nice and gentle tone when dealing with the customer.\n Also make sure to not use any emojis and keep the conversation quite efficient(don't dabble too much into the details regarding the orders, just give a simple explaination to the customer)")
    
    # Step 3: Optionally, fetch additional data based on the query
    if "order" in user_input.lower():
        order_status = data_fetcher.fetch_customer_data("order_12345")  # Example order ID
        ai_response += f"\nAdditional info: {order_status}"
    
    log.info("AI Response: %s", ai_response)
    
    # Step 4: Convert AI response to speech
    tts.text_to_speech(ai_response)

if __name__ == "__main__":
    main_flow()
