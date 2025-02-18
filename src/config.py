# src/config.py

import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Azure Speech Services Config
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")

# Azure LLM (Inference SDK) Config
AZURE_INFERENCE_SDK_ENDPOINT = os.getenv("AZURE_INFERENCE_SDK_ENDPOINT")
AZURE_INFERENCE_SDK_KEY = os.getenv("AZURE_INFERENCE_SDK_KEY")
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME")
