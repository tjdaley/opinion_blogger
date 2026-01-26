from pydantic_ai import Agent
from pydantic import BaseModel
from typing import List
from agents.util import configure_model, get_prompt

# Define the input structure
class QandA(BaseModel):
    question: str
    answer:  str

# Initialize the Agent with Gemini
q_and_a_agent: Agent[None, List[QandA]] = Agent(
    model=configure_model(mode="chat"),
    output_type=List[QandA],
    system_prompt=get_prompt("q_and_a_agent_system_prompt"),
    name="QandAAgent",
)

user_prompt = get_prompt("q_and_a_agent_user_prompt_template", raise_error=True)
