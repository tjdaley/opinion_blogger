"""
settings.py - Configuration settings for the application.

Rf. https://docs.pydantic.dev/latest/concepts/pydantic_settings/
"""
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Local File Cache
    opinion_local_path: str = "./scotx"
    posts_local_path: str = "./draft_posts"

    # Google Sheets Table
    google_sheet_name: str = "Texas Appellate Blog Tracker"
    json_keyfile: str = "attorney-bot-290510-ce9813b675da.json"
    # AI Parameters
    max_opinion_size: int = 12000

    # For Posting to Blog
    wp_base_url: str = "https://www.thomasjdaley.com/wp-json/wp/v2"
    wp_username: str = "tdaley"
    wp_app_password: str = ""
    author_id: int = 3
    scotx_category_ids: tuple[int, ...] = (0,0)
    scotx_tag_ids: tuple[int, ...] = (0,0)
    scotx_media_id: int = 771
    coatx_category_ids: tuple[int, ...] = (0,0)
    coatx_tag_ids: tuple[int, ...] = (0,0)
    coatx_media_id: int = 771

    # For Copying from Blog to Landing Page
    wp_post_tag: str = "ok_to_publish"
    wp_error_tag: str = "publication_failed"
    wp_success_tag: str = "published_to_landing_pages"

    # SCOTXBLOG Settings
    table_element_id: str = "stagingDateTable"
    scotx_url: str = "https://data.scotxblog.com/scotx/staging/decided"

    # COA Web site Settings
    coa_base_url: str = "https://search.txcourts.gov/"
    coa_lookback_days: int = 10

    # Logging settings
    log_format: str = "%(asctime)s - %(name)-15s - %(levelname)-8s - %(message)s"
    log_level: str = "WARNING"  # Default log level for API

    # AI Settings
    llm_vendor: str = "gemini"  # Options: 'gemini', 'openai', 'anthropic', 'groq'
    llm_fast_vendor: str = "gemini"  # Vendor for fast models
    llm_chat_temperature: float = 0.1
    llm_chat_top_p: float = 0.1
    llm_strategy_temperature: float = 0.7
    llm_strategy_top_p: float = 0.8

    # LLM settings
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"
    gemini_fast_model: str = "gemini-2.0-flash-lite"
    gemini_model_prefix: str = "google-gla"
    gemini_chat_temperature: float = 1.0
    gemini_chat_top_p: float = 0.95

    openai_api_key: str = ""
    openai_model: str = ""
    openai_fast_model: str = "gpt-5-nano"

    anthropic_api_key: str = ""
    anthropic_model: str = ""
    anthropic_fast_model: str = "claude-haiku-4-5"

    groq_api_key: str = ""
    groq_model: str = "groq/compound"
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.ai/v1/"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-reasoner"
    deepseek_fast_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseekr.com/v1/"

    # Database Settings
    supabase_url: str = ""
    supabase_service_role_key: str = "" 
    
    class Config:
        env_file = ".env"
        # extra = "forbid"  # Pydantic will throw an error if unexpected env vars are present

    def getattr(self, item: str, default: Optional[str] = None):
        """Get an attribute from the settings"""
        return getattr(self, item, default)

settings = Settings()
