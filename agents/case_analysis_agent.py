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
    seo_focuskw: str
    meta_description: str

# Initialize the Agent with Gemini
case_analysis_agent: Agent[None, CaseAnalysis] = Agent(
    model=configure_model(mode="chat"),
    output_type=CaseAnalysis,
    system_prompt=get_prompt("case_analysis_agent_system_prompt"),
    name="CaseAnalysisAgent",
)

user_prompt = get_prompt("case_analysis_agent_user_prompt_template", raise_error=True)
