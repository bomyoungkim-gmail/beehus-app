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
    
    # Selenium
    SELENIUM_REMOTE_URL: str = "http://selenium:4444/wd/hub"  # Selenium Standalone

    # Security
    DATABASE_ENCRYPTION_KEY: str = "qQkYhPB2wmkqTLcJxmiiKjYHrnJpDVRtMne4cxd8SpM="

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
