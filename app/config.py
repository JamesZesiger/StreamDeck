from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://streamdeck:streamdeck@db:5432/streamdeck"
    tmdb_api_key: str = ""
    sites_file: str = "/data/sites.json"
    # homenet's dashBoard: when set, the nav shows a Dashboard button pointing
    # at this port on whichever host the browser reached streamDeck through.
    # Unset (standalone streamDeck) hides the button.
    dashboard_port: int | None = None


settings = Settings()
