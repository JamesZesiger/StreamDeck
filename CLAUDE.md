# Claude rules

## Git workflow

- Never commit directly to `main`. Always create a feature branch
  (short, kebab-case, named for the change), commit there, and push
  the branch.
- Merge into `main` only when explicitly asked, and delete the branch
  after merging only when asked.
- Pre-commit hooks run pylint and pytest; both must pass before a
  commit lands.

## Where development happens

- streamDeck is developed in the homenet monorepo, at `apps/streamdeck/`.
  This repo is its standalone release. The monorepo is never changed to suit
  this repo — standalone-only adjustments live here and nowhere else.
- To refresh from homenet: copy `apps/streamdeck/` over this repo, then put
  back the standalone changes listed below (e.g. review `git diff` and restore
  those hunks), run pylint and pytest, and commit on a branch.
- Files that are this repo's own: `.github/`, `.githooks/`, `.gitignore`,
  `CLAUDE.md`, and `pyproject.toml` (which carries the lint settings homenet
  keeps at its root). homenet's `apps/streamdeck/` has its own pytest-only
  `pyproject.toml`, so a copy overwrites this one — restore it afterwards
  (`git checkout -- pyproject.toml`).

### Standalone-only changes to re-apply after a refresh

homenet's streamDeck assumes its dashBoard and its stack; standalone
streamDeck doesn't have them. These edits exist only here:

- `app/config.py` — `dashboard_port: int | None = None` (homenet defaults to
  8080), so the Dashboard button is off unless `DASHBOARD_PORT` is set.
- `app/routers/pages.py` — `dashboard_url()` returns `None` when
  `dashboard_port` is unset.
- `app/templates/base.html` — the nav's Dashboard link is wrapped in
  `{% set dash = dashboard_url(request) %}{% if dash %} … {% endif %}`.
- `tests/test_dashboard_link.py` — an autouse fixture sets the port to 8080,
  plus `test_hidden_without_a_dashboard`.
- `.env.example` — `DASHBOARD_PORT` is commented out, described as optional.
- `README.md` — the install step clones this repo, not the monorepo.
- `docs/TMDB-PROVIDERS.md` — the regenerate command uses
  `docker compose exec -T app python -` (homenet's uses its container name).

## Database

- There is no Alembic: tables come from `Base.metadata.create_all` at startup,
  and additive column changes go in `_init_db` in `app/main.py` as
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Databases created by the old
  Alembic-managed releases keep working; their `alembic_version` table is
  simply unused.
