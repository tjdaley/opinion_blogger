from pydantic_ai import Agent
from agents.util import configure_model, get_prompt


# Initialize the Agent with Gemini
blog_post_agent: Agent[None, str] = Agent(
    model=configure_model(mode="chat"),
    output_type=str,
    system_prompt=get_prompt("blog_post_agent_system_prompt"),
    name="BlogPostAgent",
)

user_prompt = get_prompt("blog_post_agent_user_prompt_template", raise_error=True)