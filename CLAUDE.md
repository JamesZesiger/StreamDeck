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
  This repo is its standalone release, refreshed by copying that directory
  over (the app, tests, docs, compose file and `.env.example`).
- Only these files are this repo's own and survive a refresh: `.github/`,
  `.githooks/`, `.gitignore`, `CLAUDE.md` and `pyproject.toml` (which carries
  the lint settings homenet keeps at its root).
- There is no Alembic: tables come from `Base.metadata.create_all` at startup,
  and additive column changes go in `_init_db` in `app/main.py` as
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Databases created by the old
  Alembic-managed releases keep working; their `alembic_version` table is
  simply unused.
