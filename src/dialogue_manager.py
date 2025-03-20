import asyncio
from src.ai import llm_client
from src.ai.ai_helpers import (
    clean_llm_response,
    determine_sentiment,
    validate_option,
    generate_smart_clarification,
    is_followup_question
)
from src.dialogue_utils import ask_question

class DialogueManager:
    def __init__(self, questions, candidate_name, company_name, uniqueid):
        self.questions = questions
        self.candidate_name = candidate_name
        self.company_name = company_name
        self.uniqueid = uniqueid
        self.current_index = 0
        self.candidate_responses = {}
        self.conversation_history = []  # Optional: store full dialogue context

    def get_current_question(self):
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    async def run_conversation(self, agi):
        loop = asyncio.get_running_loop()
        while self.current_index < len(self.questions):
            question = self.get_current_question()
            answer = await loop.run_in_executor(None, ask_question, agi, question, self.uniqueid)
            if answer is None:
                return {"action": "end", "prompt": question.get("exit_message", "Goodbye")}
            self.candidate_responses[question["key"]] = answer
            self.conversation_history.append({"role": "user", "content": answer})
            self.current_index += 1
        final_msg = (
            f"Fantastic, {self.candidate_name}! That's all we need for now. "
            f"Thank you for your time. Our team at {self.company_name} will review your details and reach out soon. Have a great day!"
        )
        return {"action": "complete", "prompt": final_msg}

# Async helper to simulate LLM calls without blocking
async def query_llm_async(conversation_history, max_tokens=1000):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, llm_client.query_llm, conversation_history, max_tokens)

# For testing purposes.
if __name__ == "__main__":
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
        # For a quick test, we call process_input if available or run_conversation.
        result = await dm.run_conversation(None)  # Replace None with a dummy 'agi' if needed.
        print("Final Action:", result)
    
    asyncio.run(test_dialogue())
