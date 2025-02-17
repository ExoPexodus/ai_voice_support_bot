# src/ai/gpt4_client.py

import openai
from src.config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_API_VERSION

openai.api_type = "azure"
openai.api_base = OPENAI_API_BASE
openai.api_version = OPENAI_API_VERSION
openai.api_key = OPENAI_API_KEY

def get_ai_response(prompt):
    response = openai.ChatCompletion.create(
        engine="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful AI support assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response["choices"][0]["message"]["content"]

if __name__ == "__main__":
    user_prompt = "What is the status of my order?"
    print("AI Response:", get_ai_response(user_prompt))
