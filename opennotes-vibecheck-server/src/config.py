from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    FIRECRAWL_API_KEY: str = ""
    GOOGLE_FACT_CHECK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    VIBECHECK_SUPABASE_URL: str = ""
    VIBECHECK_SUPABASE_DB_PASSWORD: str = ""
    VIBECHECK_SUPABASE_ANON_KEY: str = ""

    RATE_LIMIT_PER_IP_PER_HOUR: int = 10
    CACHE_TTL_HOURS: int = 72


@lru_cache
def get_settings() -> Settings:
    return Settings()
