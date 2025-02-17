# ai_voice_support_bot
A bot that will perform customer support through voice calls by using Azure Serivces


## Project file structure

ai_voice_support_bot/
├── README.md                # Project overview, setup, and usage instructions
├── requirements.txt         # List of all Python dependencies
├── Dockerfile               # Containerization instructions
├── src/
│   ├── main.py              # Entry point for the application (or orchestration server)
│   ├── config.py            # Configuration settings (API keys, endpoints, etc.)
│   ├── speech/              # Modules for speech processing
│   │   ├── stt.py           # Speech-to-text functionality using Azure Speech SDK
│   │   └── tts.py           # Text-to-speech functionality using Azure Speech SDK
│   ├── ai/                 # Modules for AI interactions (GPT-4 calls)
│   │   └── gpt4_client.py   # Integration with Azure OpenAI (GPT-4)
│   ├── data/               # Data fetching and external API integration
│   │   └── data_fetcher.py  # Module to fetch data (customer info, order status, etc.)
│   ├── call/               # Call handling logic (integrate with ACS or Twilio)
│   │   └── call_handler.py  # Manages incoming/outgoing calls
│   └── utils/              # Utility modules
│       └── logger.py        # Custom logging setup (or any helper functions)
└── tests/                   # Unit and integration tests for your modules
    ├── test_stt.py
    ├── test_tts.py
    └── test_ai.py
