from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt

# Define the input structure
class MigrationExtraction(BaseModel):
    brief_summary: str
    litigation_takeaway: str
    slug: str
    category: str
    citation: str

# Initialize the Agent with Gemini
migration_extraction_agent: Agent[None, MigrationExtraction] = Agent(
    model=configure_model(mode="chat"),
    output_type=MigrationExtraction,
    system_prompt=get_prompt("post_migration_agent_system_prompt"),
    name="MigrationExtractionAgent",
)

user_prompt = get_prompt("post_migration_agent_user_prompt_template", raise_error=True)
