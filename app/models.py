import enum
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Enum, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
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
    deep_link: Mapped[str] = mapped_column(String(1000))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    service: Mapped[Service] = relationship(back_populates="titles")


class Profile(Base):
    """A person using the app. The library is shared; watch state is not."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
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
