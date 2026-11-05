from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXAM_ROOT = BACKEND_ROOT.parents[1]
CONTRACTS_ROOT = EXAM_ROOT / "contracts"
RESOURCES_ROOT = EXAM_ROOT / "resources"
DEFAULT_DATABASE_URL = f"sqlite:///{(EXAM_ROOT / 'runtime/data/materialops.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
    allow_exam_reset: bool = True
    exam_now: str = "2026-10-12T02:00:00Z"
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key: str = ""
    model_fault_transport: bool = False
    model_timeout_seconds: float = 15
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"


settings = Settings()

