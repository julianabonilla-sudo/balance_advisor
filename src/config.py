from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    olibia_api_key: str
    olibia_base_url: str = "https://integrations.bia.app/ms-olibia-energy/v1"
    olibia_user_email: str
    olibia_user_id: str = "1"

    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"

    default_version_name: str = "Tx2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
