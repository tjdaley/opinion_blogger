from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt

# Define the input structure
from pydantic import BaseModel, Field

class FamilyAngle(BaseModel):
    is_procedurally_relevant: bool = Field(description="Whether the case has relevance to family law.")
    new_headline: str = Field(description="A catchy, legally-accurate headline focusing on the family law angle.")
    crossover_strategy: str = Field(description="Specific advice on how a family lawyer can use this ruling in a civil context.")

# Initialize the Agent with Gemini (no_safety=True for legal content)
family_angle_agent: Agent[None, FamilyAngle] = Agent(
    model=configure_model(mode="chat", no_safety=True),
    output_type=FamilyAngle,
    system_prompt=get_prompt("family_angle_agent_system_prompt"),
    name="FamilyAngleAgent",
)

user_prompt = get_prompt("family_angle_agent_user_prompt_template", raise_error=True)
