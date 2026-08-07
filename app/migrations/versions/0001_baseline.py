"""Baseline: the full schema as of the switch to Alembic.

Replaces main._init_db's create_all + idempotent ALTER pile. One code path
serves both fresh and pre-Alembic databases: each table is created only if
missing, then the legacy column adds/drops run (every one a no-op on a
schema created just above), then the one-time data migrations — the Default
profile seed and the global watched flag moving into profile_watches.

Revision ID: 0001
Revises:
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _media_type() -> postgresql.ENUM:
    # create_type=False: upgrade() creates the type once, explicitly, so the
    # three columns sharing it don't each try to create it.
    return postgresql.ENUM("movie", "tv", name="media_type", create_type=False)


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    postgresql.ENUM("movie", "tv", name="media_type").create(bind, checkfirst=True)

    if not insp.has_table("services"):
        op.create_table(
            "services",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("slug", sa.String(50), nullable=False),
            sa.Column("base_domain", sa.String(100), nullable=False),
            sa.Column("icon_path", sa.String(200), nullable=False),
            sa.Column("enabled", sa.Boolean, nullable=False),
        )
        op.create_index("ix_services_slug", "services", ["slug"], unique=True)

    if not insp.has_table("titles"):
        op.create_table(
            "titles",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("service_id", sa.Integer, sa.ForeignKey("services.id"),
                      nullable=False),
            sa.Column("tmdb_id", sa.Integer, nullable=False),
            sa.Column("media_type", _media_type(), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("overview", sa.Text, nullable=False),
            sa.Column("poster_url", sa.String(500), nullable=False),
            sa.Column("backdrop_url", sa.String(500), nullable=False),
            sa.Column("runtime_minutes", sa.Integer),
            sa.Column("release_year", sa.Integer),
            sa.Column("genres", sa.String(300), nullable=False),
            sa.Column("mature", sa.Boolean, nullable=False),
            sa.Column("rating", sa.Float),
            sa.Column("vote_count", sa.Integer),
            sa.Column("popularity", sa.Float),
            sa.Column("certification", sa.String(20)),
            sa.Column("imdb_id", sa.String(20)),
            sa.Column("regions", sa.Text),
            sa.Column("unavailable_since", sa.DateTime(timezone=True)),
            sa.Column("deep_link", sa.String(1000), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=_now()),
        )

    if not insp.has_table("app_prefs"):
        op.create_table(
            "app_prefs",
            sa.Column("key", sa.String(50), primary_key=True),
            sa.Column("value", sa.Text, nullable=False),
        )

    if not insp.has_table("profiles"):
        op.create_table(
            "profiles",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(50), nullable=False, unique=True),
            sa.Column("max_rating_level", sa.Integer),
            sa.Column("allowed_services", sa.String(500), nullable=False,
                      server_default=""),
            sa.Column("kid_mode", sa.Boolean, nullable=False,
                      server_default="false"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=_now()),
        )

    if not insp.has_table("profile_watches"):
        op.create_table(
            "profile_watches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("profile_id", sa.Integer,
                      sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("tmdb_id", sa.Integer, nullable=False),
            sa.Column("media_type", _media_type(), nullable=False),
            sa.Column("watched_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=_now()),
            sa.UniqueConstraint("profile_id", "tmdb_id", "media_type"),
        )
        op.create_index("ix_profile_watches_profile_id",
                        "profile_watches", ["profile_id"])

    if not insp.has_table("profile_episode_watches"):
        op.create_table(
            "profile_episode_watches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("profile_id", sa.Integer,
                      sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("tmdb_id", sa.Integer, nullable=False),
            sa.Column("season", sa.Integer, nullable=False),
            sa.Column("episode", sa.Integer, nullable=False),
            sa.Column("watched_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=_now()),
            sa.UniqueConstraint("profile_id", "tmdb_id", "season", "episode"),
        )
        op.create_index("ix_profile_episode_watches_profile_id",
                        "profile_episode_watches", ["profile_id"])
        op.create_index("ix_profile_episode_watches_tmdb_id",
                        "profile_episode_watches", ["tmdb_id"])

    if not insp.has_table("profile_list_items"):
        op.create_table(
            "profile_list_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("profile_id", sa.Integer,
                      sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("tmdb_id", sa.Integer, nullable=False),
            sa.Column("media_type", _media_type(), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=_now()),
            sa.UniqueConstraint("profile_id", "tmdb_id", "media_type"),
        )
        op.create_index("ix_profile_list_items_profile_id",
                        "profile_list_items", ["profile_id"])

    # --- Pre-Alembic installs: the old _init_db ALTER pile, verbatim. ---
    # Retire the neko-era playback_mode column and its enum type.
    op.execute("ALTER TABLE services DROP COLUMN IF EXISTS playback_mode")
    op.execute("DROP TYPE IF EXISTS playback_mode")
    for ddl in (
        "genres VARCHAR(300) NOT NULL DEFAULT ''",
        "mature BOOLEAN NOT NULL DEFAULT FALSE",
        "rating DOUBLE PRECISION",
        "vote_count INTEGER",
        "popularity DOUBLE PRECISION",
        "certification VARCHAR(20)",
        "regions TEXT",
        "imdb_id VARCHAR(20)",
        "unavailable_since TIMESTAMPTZ",
    ):
        op.execute(f"ALTER TABLE titles ADD COLUMN IF NOT EXISTS {ddl}")
    # hide_mature is retired: the age rating cap replaces it.
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS hide_mature")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
               "max_rating_level INTEGER")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
               "allowed_services VARCHAR(500) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
               "kid_mode BOOLEAN NOT NULL DEFAULT FALSE")

    # The library is shared, watch state is per profile: seed one profile,
    # move the legacy global watched flag into it, retire the old columns.
    op.execute("INSERT INTO profiles (name) SELECT 'Default' "
               "WHERE NOT EXISTS (SELECT 1 FROM profiles)")
    legacy_watched = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='titles' AND column_name='watched'")).first()
    if legacy_watched:
        op.execute(
            "INSERT INTO profile_watches (profile_id, tmdb_id, media_type, watched_at) "
            "SELECT (SELECT id FROM profiles ORDER BY id LIMIT 1), "
            "       t.tmdb_id, t.media_type, now() "
            "FROM (SELECT DISTINCT tmdb_id, media_type FROM titles WHERE watched) t "
            "ON CONFLICT DO NOTHING")
        op.execute("ALTER TABLE titles DROP COLUMN watched")
    op.execute("ALTER TABLE titles DROP COLUMN IF EXISTS last_played_at")


def downgrade() -> None:
    # Children before parents, so foreign keys don't block the drops.
    for table in ("profile_list_items", "profile_episode_watches",
                  "profile_watches", "profiles", "app_prefs",
                  "titles", "services"):
        op.drop_table(table)
    postgresql.ENUM(name="media_type").drop(op.get_bind(), checkfirst=True)
