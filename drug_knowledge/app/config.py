from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./drug_knowledge.db"
    VECTOR_STORE_PATH: str = "./vector_store"
    RAW_DATA_PATH: str = "./raw_data"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    DAILYMED_BASE_URL: str = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
    OPENFDA_BASE_URL: str = "https://api.fda.gov/drug/label.json"
    OPENFDA_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
