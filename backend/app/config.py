"""
Central application configuration.
Reads from environment variables / .env file. See .env.example for all options.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "bhoomitrust_db"

    JWT_SECRET: str = "change-this-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # "bcrypt" or "argon2"
    PASSWORD_HASH_SCHEME: str = "bcrypt"

    LLM_PROVIDER: str = "demo"
    LLM_API_KEY: str = ""
    # Local Document AI inference is opt-in and never calls a cloud provider.
    OLLAMA_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.2"
    OLLAMA_EMBEDDING_MODEL: str = "bge-m3"
    OLLAMA_EMBEDDINGS_ENABLED: bool = False
    OLLAMA_TIMEOUT_SECONDS: int = 120
    OLLAMA_NUM_CTX: int = 4096
    # Comma-separated exact HTTPS hostnames permitted for public webpage ingestion.
    WEB_IMPORT_ALLOWED_DOMAINS: str = ""

    OCR_PROVIDER: str = "tesseract"       # demo | tesseract | paddleocr | trocr_handwritten | hybrid
    EXTRACTION_PROVIDER: str = "regex"    # demo | regex | llm
    TRANSLATE_ENABLED: bool = True        # deep-translator; requires outbound internet

    DEMO_MODE: bool = True
    CORS_ORIGINS: str = "http://localhost:3000"

    # Confidence thresholds (configurable per section 9 of spec)
    CONFIDENCE_HIGH_THRESHOLD: int = 85
    CONFIDENCE_REVIEW_THRESHOLD: int = 70

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 20
    ALLOWED_EXTENSIONS: tuple = (".pdf", ".jpg", ".jpeg", ".png")

    UPLOAD_DIR: str = "./uploads"

    # --- Notifications: fired when a record lands with anomaly_level=HIGH ---
    NOTIFICATIONS_ENABLED: bool = False

    # Email (SMTP)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    NOTIFY_EMAIL_TO: str = ""

    # SMS provider configuration. Credentials must be supplied outside Git.
    SMS_PROVIDER: str = "none"          # none | fast2sms | twilio
    NOTIFY_PHONE_NUMBER: str = ""
    FAST2SMS_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""


settings = Settings()
