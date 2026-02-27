from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # MongoDB
    MONGO_URI: str
    MONGO_DB_NAME: str = "platform_db"
    TIMEZONE: str = "America/Sao_Paulo"
    
    # RabbitMQ
    RABBITMQ_URL: str
    
    # Redis
    REDIS_URL: str

    # Selenium slot control
    SELENIUM_MAX_SLOTS: int = 5
    SELENIUM_NODE_COUNT: int = 5
    SELENIUM_NODE_MAX_SESSIONS: int = 1
    
    # Selenium
    SELENIUM_REMOTE_URL: str = "http://selenium-hub:4444/wd/hub"  # Selenium Grid Hub
    VNC_URL_BASE: str = "http://localhost"
    VNC_HOST_PORT_BASE: int = 17901

    # Security
    DATABASE_ENCRYPTION_KEY: str = "qQkYhPB2wmkqTLcJxmiiKjYHrnJpDVRtMne4cxd8SpM="

    # Admin bootstrap
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    ADMIN_FULL_NAME: str | None = None

    # SMTP email
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "Beehus Platform"
    SMTP_USE_TLS: bool = True
    FRONTEND_URL: str = "http://localhost:5173"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
