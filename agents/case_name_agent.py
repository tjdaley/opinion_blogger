from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_fast_model, get_prompt

class CaseName(BaseModel):
    case_name: str

# Lazy singleton pattern to avoid event loop issues
_case_name_agent: Agent[None, CaseName] | None = None

def get_case_name_agent() -> Agent[None, CaseName]:
    """
    Get or create the Case Name agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _case_name_agent
    if _case_name_agent is None:
        _case_name_agent = Agent(
            model=configure_fast_model(), #(mode="chat"),
            output_type=CaseName,
            system_prompt=get_prompt("case_name_agent_system_prompt"),
            name="CaseNameAgent",
        )
    return _case_name_agent

user_prompt = get_prompt("case_name_agent_user_prompt_template", raise_error=True)
