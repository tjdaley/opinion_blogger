from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt

# Define the input structure
class OpinionTag(BaseModel):
    tags_top_k: list[str]
    tags_discarded: list[str]
    tag_rationale: str

# Lazy singleton pattern to avoid event loop issues
_opinion_tagger_agent: Agent[None, OpinionTag] | None = None

def get_opinion_tagger_agent() -> Agent[None, OpinionTag]:
    """
    Get or create the opinion tagger agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _opinion_tagger_agent
    if _opinion_tagger_agent is None:
        _opinion_tagger_agent = Agent(
            model=configure_model(mode="chat", no_safety=True),
            output_type=OpinionTag,
            system_prompt=get_prompt("opinion_tagger_agent_system_prompt"),
            name="OpinionTaggerAgent",
        )
    return _opinion_tagger_agent

user_prompt = get_prompt("opinion_tagger_agent_user_prompt_template", raise_error=True)
