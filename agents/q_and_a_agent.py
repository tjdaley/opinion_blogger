from pydantic_ai import Agent
from pydantic import BaseModel
from typing import List
from agents.util import configure_model, get_prompt

# Define the input structure
class QandA(BaseModel):
    question: str
    answer:  str

# Lazy singleton pattern to avoid event loop issues
_q_and_a_agent: Agent[None, List[QandA]] | None = None

def get_q_and_a_agent() -> Agent[None, List[QandA]]:
    """
    Get or create the Q&A agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _q_and_a_agent
    if _q_and_a_agent is None:
        _q_and_a_agent = Agent(
            model=configure_model(mode="chat"),
            output_type=List[QandA],
            system_prompt=get_prompt("q_and_a_agent_system_prompt"),
            name="QandAAgent",
        )
    return _q_and_a_agent

user_prompt = get_prompt("q_and_a_agent_user_prompt_template", raise_error=True)
