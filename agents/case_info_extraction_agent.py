from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt
from util.settings import settings

# Define the input structure
class CaseInfo(BaseModel):
    family_law: bool
    case_name: str
    lower_court_name: str
    has_substance: bool

# Lazy singleton pattern to avoid event loop issues
_case_info_extraction_agent: Agent[None, CaseInfo] | None = None

def get_case_info_extraction_agent() -> Agent[None, CaseInfo]:
    """
    Get or create the case info extraction agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _case_info_extraction_agent
    if _case_info_extraction_agent is None:
        _case_info_extraction_agent = Agent(
            model=configure_model(
                mode="chat",
                no_safety=True,
                override_vendor=settings.seo_title_vendor,
                override_model=settings.seo_title_model
            ),
            output_type=CaseInfo,
            system_prompt=get_prompt("case_info_extraction_agent_system_prompt"),
            name="CaseInfoExtractionAgent",
        )
    return _case_info_extraction_agent

user_prompt = get_prompt("case_info_extraction_agent_user_prompt_template", raise_error=True)
