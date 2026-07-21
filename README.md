# Job-Apply Assistant

A human-in-the-loop LinkedIn **Easy Apply** assistant. It opens a real Chrome
browser, uses **your own** LinkedIn login, searches for jobs, and **autofills**
application forms from a structured profile built from your resume. It is rate
limited by design, and by default it fills each application and **pauses for you
to confirm before submitting**.

## What it does / doesn't do

- **Does:** open Chrome via Playwright, reuse your logged-in session, run a jobs
  search (URL or keywords), step through Easy Apply forms, map fields to your
  resume-derived profile, upload your resume, rate limit itself, track what it
  applied to, and skip duplicates.
- **Doesn't:** solve CAPTCHAs, defeat bot detection, or bypass any site
  validation. If a site presents a verification challenge, you handle it. If a
  required field can't be answered confidently, it stops for you rather than
  guessing.

> LinkedIn's User Agreement restricts automation. Use this on your own account,
> at a modest pace, and prefer the default review-before-submit mode. You are
> responsible for how you use it.

## Install

```bash
python -m pip install -r requirements.txt
python -m playwright install chrome    # or: playwright install chromium
```

## 1. Build your profile from a resume

```bash
python -m jobapply init-profile --resume /path/to/resume.pdf --interactive
```

This writes `profile.json` (see `profile.example.json`). Open it and fill in
`experience`, `education`, `skills`, and especially `screening_answers` — the
last one is how you pin exact responses to recurring questions (e.g. "Why do you
want to work here?"). Make sure `resume_path` points at the file to upload.

## 2. Configure

```bash
cp config.example.yaml config.yaml
```

Key options:

- `auto_submit` — `false` (default) fills and waits for your confirmation;
  `true` submits automatically **only** for applications where every field was
  filled confidently.
- `rate_limit` — delays between actions/applications and hard caps per run and
  per rolling hour.
- `search` — either a full `url`, or `keywords` + `location`.

## 3. Apply

Interactive (prompts for search params if none set):

```bash
python -m jobapply apply
```

With a search URL:

```bash
python -m jobapply apply --url "https://www.linkedin.com/jobs/search/?keywords=backend%20engineer&f_AL=true"
```

With keywords and a per-run cap:

```bash
python -m jobapply apply --keywords "Data Engineer" --location "Remote" --max 10
```

Opt into auto-submit (still rate limited, still skips uncertain fields):

```bash
python -m jobapply apply --auto-submit
```

On first run, if you're not logged in, sign in to LinkedIn in the Chrome window
(complete any verification yourself). The session is saved in
`.chrome-profile/` and reused next time.

In review mode, for each job you'll get a summary and a prompt:
`y` submit · `n` leave it filled for you to finish · `q` quit the run.

## Applications log

Every action is appended to `applications.csv` (`submitted`,
`filled_awaiting_review`, `skipped`, `error`) with title, company, location and
URL. This also drives duplicate-skipping and the hourly rate limit.

## How field matching works

`jobapply/field_matcher.py` maps a form question to an answer:

1. `screening_answers` overrides (longest matching key wins), then
2. a built-in rule table (name, contact, work authorisation, years of
   experience, salary, etc.).

Unknown or empty-valued fields are flagged for review instead of being guessed.

## Development

```bash
python -m pip install -r requirements-dev.txt
pytest
```

The form-matching and profile/resume/tracker/rate-limit logic are covered by
unit tests that don't require a browser.

## Project layout

```
jobapply/
  cli.py            CLI (init-profile, apply)
  runner.py         orchestration (search -> iterate -> apply)
  linkedin.py       search + Easy Apply modal automation
  form_filler.py    DOM-aware autofill engine
  field_matcher.py  pure question -> answer logic (unit tested)
  resume.py         resume text extraction + best-effort parsing
  profile.py        Profile data model
  config.py         config loading
  rate_limiter.py   pacing + per-run / per-hour caps
  tracker.py        applications.csv log + dedup
  browser.py        Playwright Chrome (persistent login)
```
