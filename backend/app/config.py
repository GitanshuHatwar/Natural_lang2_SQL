from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    sqlite_path: str = "app.db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_num_ctx: int = 8192
    metadata_max_chars: int = 12000
    result_row_limit: int = 1000
    query_timeout_seconds: int = 30
    extract_query_timeout_seconds: int = 10
    extract_sample_rows: int = 10000
    summary_sample_rows: int = 50
    history_pairs: int = 3
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
