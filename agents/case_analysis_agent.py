from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt

# Define the input structure
class CaseAnalysis(BaseModel):
    family_law: bool
    headline: str
    legal_issue: str
    holding: str
    case_name: str
    lower_court_name: str
    seo_title: str
    seo_focus_kw: str
    meta_description: str
    has_substance: bool

class CaseLegalAnalysis(BaseModel):
    headline: str
    legal_issue: str
    holding: str
    seo_focus_kw: str
    meta_description: str

# Lazy singleton pattern to avoid event loop issues
_case_analysis_agent: Agent[None, CaseLegalAnalysis] | None = None

def get_case_analysis_agent() -> Agent[None, CaseLegalAnalysis]:
    """
    Get or create the case analysis agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _case_analysis_agent
    if _case_analysis_agent is None:
        _case_analysis_agent = Agent(
            model=configure_model(mode="chat", no_safety=True),
            output_type=CaseLegalAnalysis,
            system_prompt=get_prompt("case_analysis_agent_system_prompt"),
            name="CaseAnalysisAgent",
        )
    return _case_analysis_agent

user_prompt = get_prompt("case_analysis_agent_user_prompt_template", raise_error=True)
