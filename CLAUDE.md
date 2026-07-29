# Claude rules

## Git workflow

- Never commit directly to `main`. Always create a feature branch
  (short, kebab-case, named for the change), commit there, and push
  the branch.
- Merge into `main` only when explicitly asked, and delete the branch
  after merging only when asked.
- Pre-commit hooks run pylint and pytest; both must pass before a
  commit lands.
