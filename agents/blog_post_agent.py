from pydantic_ai import Agent
from agents.util import configure_model, get_prompt


# Lazy singleton pattern to avoid event loop issues
_blog_post_agent: Agent[None, str] | None = None

def get_blog_post_agent() -> Agent[None, str]:
    """
    Get or create the blog post agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _blog_post_agent
    if _blog_post_agent is None:
        _blog_post_agent = Agent(
            model=configure_model(mode="chat", no_safety=True),
            output_type=str,
            system_prompt=get_prompt("blog_post_agent_system_prompt"),
            name="BlogPostAgent",
        )
    return _blog_post_agent

user_prompt = get_prompt("blog_post_agent_user_prompt_template", raise_error=True)