import enum
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MediaType(str, enum.Enum):
    movie = "movie"
    tv = "tv"


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    base_domain: Mapped[str] = mapped_column(String(100))
    icon_path: Mapped[str] = mapped_column(String(200), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    titles: Mapped[list["Title"]] = relationship(back_populates="service")


class Title(Base):
    __tablename__ = "titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    tmdb_id: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"))
    title: Mapped[str] = mapped_column(String(300))
    overview: Mapped[str] = mapped_column(Text, default="")
    poster_url: Mapped[str] = mapped_column(String(500), default="")
    backdrop_url: Mapped[str] = mapped_column(String(500), default="")
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Comma-separated TMDB genre names, e.g. "Action, Comedy".
    genres: Mapped[str] = mapped_column(String(300), default="")
    # TMDB's adult flag.
    mature: Mapped[bool] = mapped_column(Boolean, default=False)
    # TMDB community stats, refreshed only when the title is (re)fetched.
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)      # vote_average 0–10
    vote_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    popularity: Mapped[float | None] = mapped_column(Float, nullable=True)
    # US certification ("PG-13", "TV-MA", …). NULL = never fetched,
    # "" = fetched but TMDB has none for this title.
    certification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # IMDb id ("tt0133093"), from TMDB's external_ids. NULL = never fetched,
    # "" = fetched but TMDB has none for this title.
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Comma-separated ISO country codes where this row's service streams the
    # title (TMDB/JustWatch watch-provider data). NULL = never fetched.
    regions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set by the weekly availability refresh when the service stops streaming
    # the title anywhere; cleared if it comes back. NULL = available (or a
    # custom site with no provider id, which can't be checked).
    unavailable_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    deep_link: Mapped[str] = mapped_column(String(1000))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    service: Mapped[Service] = relationship(back_populates="titles")


class Profile(Base):
    """A person using the app. The library is shared; watch state is not."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    # Highest allowed age level (see profiles.RATING_CAPS); NULL = no cap.
    # With a cap set, titles with no known certification are hidden too.
    max_rating_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Comma-separated service slugs this profile may see; "" = all services.
    allowed_services: Mapped[str] = mapped_column(
        String(500), default="", server_default="")
    # Kid mode: changing settings or switching profiles needs the parent PIN.
    kid_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileWatch(Base):
    """A title (combined across services) this profile has watched.
    Keyed by (tmdb_id, media_type) like the library's tile grouping."""

    __tablename__ = "profile_watches"
    __table_args__ = (UniqueConstraint("profile_id", "tmdb_id", "media_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"))
    watched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileListItem(Base):
    """A title on this profile's personal watch list."""

    __tablename__ = "profile_list_items"
    __table_args__ = (UniqueConstraint("profile_id", "tmdb_id", "media_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
