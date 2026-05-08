from pydantic_ai import Agent
from agents.util import configure_model, get_prompt
from util.settings import settings

# Lazy singleton pattern to avoid event loop issues
_seo_title_agent: Agent[None, str] | None = None

def get_seo_title_agent() -> Agent[None, str]:
    """
    Get or create the SEO title agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _seo_title_agent
    if _seo_title_agent is None:
        _seo_title_agent = Agent(
            model=configure_model(
                mode="chat",
                no_safety=True,
                override_vendor=settings.seo_title_vendor,
                override_model=settings.seo_title_model
            ),
            output_type=str,
            system_prompt=get_prompt("seo_title_agent_system_prompt"),
            name="SEOTitleAgent",
        )
    return _seo_title_agent

user_prompt = get_prompt("seo_title_agent_user_prompt_template", raise_error=True)
