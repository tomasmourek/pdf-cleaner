from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "upravpdf-backend"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    DATABASE_URL: str
    REDIS_URL: str

    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_PDF: str = "pdf-files"
    MINIO_SECURE: bool = False

    AUTH_SERVICE_URL: str
    UPRAVCSV_BACKEND_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    CLAUDE_API_KEY: str = ""
    GOOGLE_VISION_API_KEY: str = ""

    FRONTEND_URLS: str = "https://upravpdf.eu"

    @property
    def allowed_origins(self) -> List[str]:
        return [u.strip() for u in self.FRONTEND_URLS.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
