# src/ai/llm_client.py

import os
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from src.config import AZURE_INFERENCE_SDK_ENDPOINT, AZURE_INFERENCE_SDK_KEY, DEPLOYMENT_NAME

# Initialize Azure AI Inference SDK Client
client = ChatCompletionsClient(
    endpoint=AZURE_INFERENCE_SDK_ENDPOINT,
    credential=AzureKeyCredential(AZURE_INFERENCE_SDK_KEY)
)

def query_llm(prompt, system_message="You are an AI assistant helping with customer support.", max_tokens=1000):
    """
    Queries the Azure-hosted LLM using the Azure AI Inference SDK.

    :param prompt: User's input message.
    :param system_message: System role description.
    :param max_tokens: Maximum tokens to generate.
    :return: LLM-generated response.
    """
    try:
        response = client.complete(
            messages=[
                SystemMessage(content=system_message),
                UserMessage(content=prompt),
            ],
            model=DEPLOYMENT_NAME,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content  # Extract response text

    except Exception as e:
        print(f"LLM Error: {e}")
        return "Sorry, I encountered an issue processing your request."

if __name__ == "__main__":
    test_prompt = "How can I reset my password?"
    print("LLM Response:", query_llm(test_prompt))
