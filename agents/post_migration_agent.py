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

# Lazy singleton pattern to avoid event loop issues
_migration_extraction_agent: Agent[None, MigrationExtraction] | None = None

def get_migration_extraction_agent() -> Agent[None, MigrationExtraction]:
    """
    Get or create the migration extraction agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _migration_extraction_agent
    if _migration_extraction_agent is None:
        _migration_extraction_agent = Agent(
            model=configure_model(mode="chat", no_safety=True),
            output_type=MigrationExtraction,
            system_prompt=get_prompt("post_migration_agent_system_prompt"),
            name="MigrationExtractionAgent",
        )
    return _migration_extraction_agent

user_prompt = get_prompt("post_migration_agent_user_prompt_template", raise_error=True)
