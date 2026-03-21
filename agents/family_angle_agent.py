from pydantic_ai import Agent
from pydantic import BaseModel, Field
from agents.util import configure_model, get_prompt

class FamilyAngle(BaseModel):
    is_procedurally_relevant: bool = Field(description="Whether the case has relevance to family law.")
    new_headline: str = Field(description="A catchy, legally-accurate headline focusing on the family law angle.")
    crossover_strategy: str = Field(description="Specific advice on how a family lawyer can use this ruling in a civil context.")

# Lazy singleton pattern to avoid event loop issues
_family_angle_agent: Agent[None, FamilyAngle] | None = None

def get_family_angle_agent() -> Agent[None, FamilyAngle]:
    """
    Get or create the family angle agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _family_angle_agent
    if _family_angle_agent is None:
        _family_angle_agent = Agent(
            model=configure_model(mode="chat", no_safety=True),
            output_type=FamilyAngle,
            system_prompt=get_prompt("family_angle_agent_system_prompt"),
            name="FamilyAngleAgent",
        )
    return _family_angle_agent

user_prompt = get_prompt("family_angle_agent_user_prompt_template", raise_error=True)
