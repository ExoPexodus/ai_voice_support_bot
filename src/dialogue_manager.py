import asyncio
from src.ai import llm_client
from src.ai.ai_helpers import (
    clean_llm_response,
    determine_sentiment,
    validate_option,
    generate_generic_clarification,
    generate_smart_clarification,
    is_followup_question
)
# Import the synchronous ask_question function (assumed to be defined in fastagi_server.py)
from fastagi_server import ask_question

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

    async def run_conversation(self, agi):
        """
        Asynchronously runs through the conversation by processing candidate input for each question.
        Uses the synchronous ask_question function in an executor.
        Returns a dict with the final action and prompt.
        """
        loop = asyncio.get_running_loop()
        while self.current_index < len(self.questions):
            question = self.get_current_question()
            # Run ask_question in an executor so it doesn't block the event loop.
            answer = await loop.run_in_executor(None, ask_question, agi, question, self.uniqueid)
            if answer is None:
                # Candidate ended conversation early.
                return {"action": "end", "prompt": question.get("exit_message", "Goodbye")}
            self.candidate_responses[question["key"]] = answer
            self.conversation_history.append({"role": "user", "content": answer})
            self.current_index += 1
        final_msg = (
            f"Fantastic, {self.candidate_name}! That's all we need for now. "
            f"Thank you for your time. Our team at {self.company_name} will review your details and reach out soon. Have a great day!"
        )
        return {"action": "complete", "prompt": final_msg}

# For testing purposes:
if __name__ == "__main__":
    # Sample questions for testing.
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
        current_q = dm.get_current_question()
        print("Bot:", current_q["question"])
        # Simulate candidate input. In real usage, this would come from ASR.
        user_input = "yes, I am interested"
        response = await dm.process_input(user_input)  # If you have process_input testing; otherwise use run_conversation.
        print("Bot Action:", response)
    
    asyncio.run(test_dialogue())
