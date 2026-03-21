from pydantic_ai import Agent
from pydantic import BaseModel
from agents.util import configure_model, get_prompt
from util.settings import settings


class CanonicalQuestion(BaseModel):
    canonical_question: str
    subject: str


# Lazy singleton pattern to avoid event loop issues
_canonical_question_agent: Agent[None, CanonicalQuestion] | None = None


def get_canonical_question_agent() -> Agent[None, CanonicalQuestion]:
    """
    Get or create the canonical question agent instance.
    Uses lazy initialization to ensure it's created within an async context.
    """
    global _canonical_question_agent
    if _canonical_question_agent is None:
        _canonical_question_agent = Agent(
            model=configure_model(
                mode="chat",
                override_vendor=settings.llm_canonical_question_vendor,
                override_model=settings.anthropic_canonical_question_model,
                no_safety=True,
            ),
            output_type=CanonicalQuestion,
            system_prompt=get_prompt("canonical_question_agent_system_prompt"),
            name="CanonicalQuestionAgent",
        )
    return _canonical_question_agent


user_prompt = get_prompt("canonical_question_agent_user_prompt_template", raise_error=True)
