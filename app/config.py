from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://streamdeck:streamdeck@db:5432/streamdeck"
    tmdb_api_key: str = ""
    neko_public_url: str = "http://localhost:8080"
    neko_user_password: str = "neko"
    neko_cdp_url: str = ""
    sites_file: str = "/data/sites.json"


settings = Settings()
