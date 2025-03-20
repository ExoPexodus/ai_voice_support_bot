# dialogue_manager.py
import asyncio
from src.ai import llm_client
from src.ai_helpers import (
    clean_llm_response,
    determine_sentiment,
    validate_option,
    generate_smart_clarification,
    is_followup_question
)

class DialogueManager:
    def __init__(self, questions, candidate_name, company_name, uniqueid):
        """
        questions: a list of dictionaries, each containing:
            - key: a unique identifier (e.g., "qualification")
            - question: the text prompt to ask
            - valid_options: a list of valid responses (in lowercase)
            - exit_if (optional): a response that should trigger ending the conversation
            - exit_message (optional): the message to use when ending early
            - condition (optional): a function that returns True if the question should be asked, based on candidate responses
        candidate_name: candidate's name (e.g., from callerid)
        company_name: your company name
        uniqueid: unique identifier for the call (used in filenames)
        """
        self.questions = questions
        self.candidate_name = candidate_name
        self.company_name = company_name
        self.uniqueid = uniqueid
        self.current_index = 0
        self.candidate_responses = {}
        self.conversation_history = []  # Optional: store full dialogue context if needed

    def get_current_question(self):
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    async def process_input(self, user_input):
        """
        Processes the candidate's input for the current question.
        Returns a dict with:
            - "action": one of "clarify", "next", "complete", or "end"
            - "prompt": the text to speak next
        """
        current_question = self.get_current_question()
        if not current_question:
            return {"action": "complete", "prompt": ""}

        valid_options = [opt.lower() for opt in current_question["valid_options"]]
        # For yes/no questions, check sentiment
        if valid_options == ["yes", "no"]:
            sentiment = determine_sentiment(user_input)
            if sentiment == "negative":
                return {"action": "end", "prompt": current_question.get("exit_message", "Thank you for your time. Goodbye!")}
            answer = "yes"
        else:
            # Check if the input is a follow-up clarification
            if is_followup_question(user_input, valid_options):
                smart = generate_smart_clarification(current_question["question"], user_input, valid_options)
                return {"action": "clarify", "prompt": smart}
            # Validate candidate's answer against options
            answer = validate_option(user_input, valid_options)
            if answer is None:
                smart = generate_smart_clarification(current_question["question"], user_input, valid_options)
                return {"action": "clarify", "prompt": smart}

        # Check if the answer should trigger an early end.
        if "exit_if" in current_question and answer == current_question["exit_if"].lower():
            return {"action": "end", "prompt": current_question.get("exit_message", "Thank you for your time. Goodbye!")}
        
        # If valid answer, record it and move to the next question.
        self.candidate_responses[current_question["key"]] = answer
        self.conversation_history.append({"role": "user", "content": user_input})
        self.current_index += 1
        next_question = self.get_current_question()
        if next_question:
            return {"action": "next", "prompt": next_question["question"]}
        else:
            # Conversation complete; return final message.
            final_msg = (
                f"Fantastic, {self.candidate_name}! That's all we need for now. "
                f"Thank you for your time. Our team at {self.company_name} will review your details and reach out soon. Have a great day!"
            )
            return {"action": "complete", "prompt": final_msg}

# Async helper to simulate LLM calls without blocking
async def query_llm_async(conversation_history, max_tokens=1000):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, llm_client.query_llm, conversation_history, max_tokens)

# Example usage:
if __name__ == "__main__":
    # For testing purposes, define some sample questions.
    sample_questions = [
        {
            "key": "confirmation",
            "question": "Hello Candidate! This is Maxicus calling. Are you still interested in joining our team? Answer yes or no.",
            "valid_options": ["yes", "no"],
            "exit_if": "no",
            "exit_message": "I understand, thank you for your time. Have a nice day!"
        },
        {
            "key": "qualification",
            "question": "What is your highest qualification? Options: 10th, Post-graduate, Graduate, or 12th.",
            "valid_options": ["10th", "post-graduate", "graduate", "12th"]
        }
    ]
    dm = DialogueManager(sample_questions, "Candidate", "Maxicus", "test123")
    
    async def test_dialogue():
        # Simulate a conversation loop.
        current_q = dm.get_current_question()
        print("Bot:", current_q["question"])
        # Simulate candidate input.
        # (In real usage, this would come from ASR)
        user_input = "yes, I am interested"
        response = await dm.process_input(user_input)
        print("Bot Action:", response)
    
    asyncio.run(test_dialogue())
