import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
    deep_link: Mapped[str] = mapped_column(String(1000))
    watched: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    service: Mapped[Service] = relationship(back_populates="titles")
