from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt

# Define the input structure
class FamilyAngle(BaseModel):
    is_procedurally_relevant: bool
    reasoning:  str
    new_headline: str

# Initialize the Agent with Gemini
family_angle_agent: Agent[None, FamilyAngle] = Agent(
    model=configure_model(mode="chat"),
    output_type=FamilyAngle,
    system_prompt=get_prompt("family_angle_agent_system_prompt"),
    name="FamilyAngleAgent",
)

user_prompt = get_prompt("family_angle_agent_user_prompt_template", raise_error=True)
