# src/ai/llm_client.py

import os
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from src.config import AZURE_INFERENCE_SDK_ENDPOINT, AZURE_INFERENCE_SDK_KEY, DEPLOYMENT_NAME

# Initialize the Azure AI Inference SDK Client
client = ChatCompletionsClient(
    endpoint=AZURE_INFERENCE_SDK_ENDPOINT,
    credential=AzureKeyCredential(AZURE_INFERENCE_SDK_KEY)
)

def query_llm(conversation_history, max_tokens=1000):
    """
    Queries the Azure-hosted LLM with a conversation history containing only system and user messages.
    :param conversation_history: List of dicts with "role" (system/user) and "content".
    :param max_tokens: Maximum tokens to generate.
    :return: The LLM-generated response text.
    """
    messages = []
    for msg in conversation_history:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "user":
            messages.append(UserMessage(content=content))
        # Ignore any assistant messages
    try:
        response = client.complete(
            messages=messages,
            model=DEPLOYMENT_NAME,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content  # Return the generated text
    except Exception as e:
        print(f"LLM Error: {e}")
        return "Sorry, I encountered an issue processing your request."

if __name__ == "__main__":
    # Simple test
    test_history = [
        {"role": "system", "content": "You are a customer support executive for Zomato."},
        {"role": "user", "content": "How do I track my order 12345?"}
    ]
    print("LLM Response:", query_llm(test_history))
