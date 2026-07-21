import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://streamdeck:streamdeck@db:5432/streamdeck"
    tmdb_api_key: str = ""
    neko_public_url: str = "http://localhost:8080"
    neko_user_password: str = "neko"
    neko_cdp_url: str = ""


settings = Settings()


def service_credentials(slug: str) -> dict[str, str] | None:
    """Look up SVC_<SLUG>_USERNAME/PASSWORD from the environment (.env)."""
    key = slug.upper().replace("-", "")
    username = os.environ.get(f"SVC_{key}_USERNAME", "")
    password = os.environ.get(f"SVC_{key}_PASSWORD", "")
    if not username and not password:
        return None
    return {"username": username, "password": password}
