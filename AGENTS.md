# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single Python CLI package (`jobapply`): a human-in-the-loop
LinkedIn Easy Apply assistant. There is no server or web UI — the "app" is the
`python -m jobapply ...` CLI, driven by Playwright + Chrome.

### Environment
- Python 3.12. Dependencies are installed into a project-local virtualenv at
  `.venv/` (the system Python is externally managed / PEP 668). The startup
  update script creates/refreshes `.venv` and installs a Playwright browser.
- Always run tooling through the venv, e.g. `.venv/bin/python -m jobapply ...`
  and `.venv/bin/python -m pytest`.
- `browser.py` launches Chrome with `channel="chrome"` (system Google Chrome is
  already installed on the VM), not the bundled Chromium. Playwright's Chromium
  is also installed for completeness. If a fresh pod is missing browsers, run
  `.venv/bin/python -m playwright install chromium`.

### Test / lint / build / run
- Tests: `.venv/bin/python -m pytest` (config in `pytest.ini`; ~19 fast unit
  tests, no browser needed). This is the primary verification gate.
- Lint: none configured (no ruff/flake8/black/mypy). Nothing to run.
- Build: none — it's a plain package run via `python -m jobapply`.
- Run (profile build, no network/login needed):
  `.venv/bin/python -m jobapply init-profile --resume <file> --output profile.json`
  Supports `.txt`, `.pdf`, `.docx` resumes.

### Gotchas
- The `apply` command (`python -m jobapply apply`) requires a real, interactive
  LinkedIn sign-in in a visible Chrome window and is rate-limited by design; it
  cannot be exercised end-to-end headlessly/unattended and should not be
  automated against LinkedIn. Use `init-profile` and the unit tests to validate
  the environment instead.
- Local runtime files are gitignored: `config.yaml`, `profile.json`,
  `applications.csv`, `.chrome-profile/`, and any `*.pdf`/`*.docx`. Keep sample
  resumes/profiles out of the repo (e.g. under `/tmp`).
