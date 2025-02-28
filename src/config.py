# src/config.py

import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Azure Speech Services Config
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
AZURE_TTS_VOICE = os.getenv("AZURE_TTS_VOICE", "en-IN-AashiNeural")  # Default to Indian English
AZURE_STT_LANGUAGE = os.getenv("AZURE_STT_LANGUAGE", "en-IN")  # Default to Indian English

# Azure LLM (Inference SDK) Config
AZURE_INFERENCE_SDK_ENDPOINT = os.getenv("AZURE_INFERENCE_SDK_ENDPOINT")
AZURE_INFERENCE_SDK_KEY = os.getenv("AZURE_INFERENCE_SDK_KEY")
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME")