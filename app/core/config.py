from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    #secret_key: str
    session_expires_minutes: int = 60*24*7

    model_config = SettingsConfigDict(
        env_file=".env"
    )


settings = Settings()