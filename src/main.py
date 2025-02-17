# src/main.py

from src.speech import stt, tts
from src.ai import gpt4_client
from src.data import data_fetcher
from src.call import call_handler

def main_flow():
    # 1. Handle an incoming call (stub)
    call_status = call_handler.handle_incoming_call("CALL123")
    print(call_status)
    
    # 2. Convert speech to text (simulate a single interaction)
    user_input = stt.speech_to_text()
    if not user_input:
        tts.text_to_speech("Sorry, I didn't catch that. Please try again.")
        return

    # 3. Get a response from the AI engine
    ai_response = gpt4_client.get_ai_response(user_input)
    
    # 4. Optionally, if data is needed, fetch it
    # For example, if the response mentions an order, fetch order status:
    if "order" in user_input.lower():
        order_status = data_fetcher.fetch_customer_data("order_12345")
        ai_response += f"\n{order_status}"

    # 5. Convert the AI response back to speech and respond
    tts.text_to_speech(ai_response)

if __name__ == "__main__":
    main_flow()
