import os
from typing import Optional
from pydantic_ai.models import Model
from pydantic_ai import ModelSettings

from util.settings import settings
from util.loggerfactory import LoggerFactory

LOGGER = LoggerFactory.create_logger(__name__)

def get_prompt(prompt_name: str, raise_error: bool = False) -> str:
    """
    Retrieve the prompt text from the prompts directory based on the prompt name.

    :param prompt_name: The name of the prompt file (without extension)
    :type prompt_name: str
    :param raise_error: Whether to raise an error if the prompt file is not found. Default is False.
    :type raise_error: bool

    :return: The content of the prompt file
    :rtype: str
    """
    prompt_path = os.path.join("agents", "prompts", f"{prompt_name}.txt")
    try:
        with open(prompt_path, "r") as file:
            return file.read()
    except FileNotFoundError:
        if raise_error:
            LOGGER.error(f"Prompt file not found: {prompt_path}")
            raise
        LOGGER.warning(f"Prompt file not found: {prompt_path}")
        return ""

def get_llm_param(vendor: str, param_name: str, mode: str) -> str:
    """
    Retrieve the LLM parameter from settings based on vendor and parameter name.

    :param vendor: The LLM vendor name
    :type vendor: str
    :param param_name: The parameter name to retrieve
    :type param_name: str
    :param mode: Mode of the model, either 'chat' or 'strategy'. Default is 'chat'.
    :type mode: str

    :return: The value of the requested parameter
    :rtype: str
    """
    vendor = vendor.lower()
    mode = mode.lower()
    param_name = param_name.lower()

    vendor_param_key = f"{vendor}_{mode}_{param_name}"
    generic_param_key = f"llm_{mode}_{param_name}"
    if hasattr(settings, vendor_param_key):
        return getattr(settings, vendor_param_key)
    if hasattr(settings, generic_param_key):
        return getattr(settings, generic_param_key)

    raise ValueError(f"Unsupported property: {param_name}")

def configure_model(mode: str = "chat", override_vendor: Optional[str] = None, override_model: Optional[str] = None, no_safety: bool = True) -> Model:
    """
    Configure and return the appropriate LLM model based on settings.
    Rf: https://ai.pydantic.dev/models/overview/

    Override settings in .env.

    :param mode: Mode of the model, either 'chat' or 'strategy'. Default is 'chat'.
    :type mode: str
    :param override_vendor: Optional vendor name to override the default from settings.
    :type override_vendor: Optional[str]
    :param override_model: Optional model name to override the default from settings.
    :type override_model: Optional[str]
    :param no_safety: If True, disable safety settings (if applicable). Default is True.
    :type no_safety: bool

    :return: Configured LLM model
    :rtype: Model
    """

    mode = mode.lower()
    if mode not in ["chat", "strategy"]:
        raise ValueError("Mode must be either 'chat' or 'strategy'.")

    vendors = ['gemini', 'openai', 'anthropic', 'groq', 'deepseek']
    vendor = settings.llm_vendor.lower()
    if vendor not in vendors:
        raise ValueError(f"Unsupported LLM vendor: {settings.llm_vendor}")

    try:
        temperature = float(get_llm_param(settings.llm_vendor, "temperature", mode))
    except Exception as e:
        LOGGER.warning(f"Could not get temperature for {settings.llm_vendor} in {mode} mode: {e}")
        temperature = 0.1  # Default temperature

    try:
        top_p = float(get_llm_param(settings.llm_vendor, "top_p", mode))
    except Exception as e:
        LOGGER.warning(f"Could not get top_p for {settings.llm_vendor} in {mode} mode: {e}")
        top_p = .1  # Default top_p

    model_settings = ModelSettings(
        temperature=temperature,
        top_p=top_p,
    )

    LOGGER.debug(f"Configuring model for vendor: {settings.llm_vendor} in {mode} mode with temperature: {temperature}, top_p: {top_p}")

    llm_vendor = override_vendor or settings.llm_vendor.lower()
    if llm_vendor == 'gemini':
        from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
        from pydantic_ai.providers.google import GoogleProvider
        from google.genai.types import HarmBlockThreshold, HarmCategory, SafetySettingDict
        if no_safety:
            safety_settings: list[SafetySettingDict] = []
        else:
            # Use ONLY the 4 standard categories supported by Gemini
            # Rf. https://ai.google.dev/gemini-api/docs/safety-settings
            safety_settings: list[SafetySettingDict] = [
                {'category': HarmCategory.HARM_CATEGORY_HARASSMENT, 'threshold': HarmBlockThreshold.BLOCK_NONE},
                {'category': HarmCategory.HARM_CATEGORY_HATE_SPEECH, 'threshold': HarmBlockThreshold.BLOCK_NONE},
                {'category': HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, 'threshold': HarmBlockThreshold.BLOCK_NONE},
                {'category': HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, 'threshold': HarmBlockThreshold.BLOCK_NONE},
            ]

        google_model_settings = GoogleModelSettings(
            temperature=temperature,
            top_p=top_p,
            google_safety_settings=safety_settings,
        )
        provider = GoogleProvider(api_key=settings.gemini_api_key)
        model = GoogleModel(override_model or settings.gemini_model, provider=provider, settings=google_model_settings)
        return model

    if llm_vendor == 'openai':
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        provider = OpenAIProvider(api_key=settings.openai_api_key)
        model = OpenAIChatModel(override_model or settings.openai_model, provider=provider, settings=model_settings)
        return model

    if llm_vendor == 'anthropic':
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
        model = AnthropicModel(override_model or settings.anthropic_model, provider=provider, settings=model_settings)
        return model

    if llm_vendor == 'groq':
        from pydantic_ai.models.groq import GroqModel
        from pydantic_ai.providers.groq import GroqProvider
        provider = GroqProvider(api_key=settings.groq_api_key)
        model = GroqModel(override_model or settings.groq_model, provider=provider, settings=model_settings)
        return model

    if llm_vendor == 'deepseek':
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider(api_key=settings.deepseek_api_key)
        model = OpenAIChatModel(override_model or settings.deepseek_model, provider=provider, settings=model_settings)
        return model

    # Just because it's in our list doesn't mean we coded for it. :)
    raise ValueError(f"Unsupported LLM vendor: {llm_vendor}")

def configure_fast_model() -> Model:
    """
    Configure and return a fast LLM model (lower cost, lower latency).

    :return: Configured fast LLM model
    :rtype: Model
    """
    llm_vendor = settings.llm_fast_vendor.lower()
    if hasattr(settings, f"{llm_vendor}_fast_model"):
        fast_model_name = getattr(settings, f"{llm_vendor}_fast_model")
    else:
        raise ValueError(f"Fast model not configured for vendor: {llm_vendor}")

    model = configure_model(mode="chat", override_model=fast_model_name, override_vendor=llm_vendor, no_safety=True)

    return model