from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://streamdeck:streamdeck@db:5432/streamdeck"
    tmdb_api_key: str = ""
    sites_file: str = "/data/sites.json"


settings = Settings()
