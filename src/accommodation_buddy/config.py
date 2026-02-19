from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Models
    scaffolding_model: str = "qwen3:8b"
    ocr_model: str = "deepseek-ocr"
    translation_model: str = "aya:8b"

    # Database
    database_url: str = "postgresql+asyncpg://buddy:buddypass@postgres:5432/accommodation_buddy"
    database_url_sync: str = "postgresql://buddy:buddypass@postgres:5432/accommodation_buddy"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Ollama
    ollama_url: str = "http://ollama:11434"

    # App
    app_port: int = 8000
    app_host: str = "0.0.0.0"
    workers: int = 1
    secret_key: str = "change-me-in-production"

    # File storage
    upload_dir: str = "./data/uploads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
