"""Top-level orchestration: search -> iterate -> apply, under rate limits."""

from __future__ import annotations

import time
from typing import Callable

from .browser import launch_chrome
from .config import Config
from .linkedin import LinkedInSession
from .profile import Profile
from .rate_limiter import RateLimiter
from .tracker import Tracker
from playwright.sync_api import TimeoutError as PWTimeout


def default_confirm(prompt: str) -> bool:
    print("\n" + prompt)
    try:
        answer = input("[y = submit / n = leave for me / q = quit run]: ").strip().lower()
    except EOFError:
        return False
    if answer == "q":
        raise KeyboardInterrupt
    return answer == "y"


def run(config: Config, log: Callable[[str], None] = print) -> dict[str, int]:
    profile = Profile.load(config.profile_path)
    tracker = Tracker(config.tracker_path)
    rate_limiter = RateLimiter(
        between_applications=config.rate_limit.between_applications,
        between_actions=config.rate_limit.between_actions,
        max_per_run=config.rate_limit.max_applications_per_run,
        max_per_hour=config.rate_limit.max_applications_per_hour,
        recent_timestamps=tracker.recent_epochs_within_hour(),
    )

    stats = {"submitted": 0, "filled_awaiting_review": 0, "skipped": 0, "error": 0}
    confirm = None if config.auto_submit else default_confirm

    with launch_chrome(config.user_data_dir, headless=config.headless) as context:
        session = LinkedInSession(
            context=context,
            config=config,
            profile=profile,
            tracker=tracker,
            rate_limiter=rate_limiter,
            confirm=confirm,
            log=log,
        )
        session.open_search()
        if not session.is_logged_in():
            log("Easy Apply requires a LinkedIn sign-in.")
            try:
                session.ensure_logged_in(timeout_s=config.login_timeout_s)
            except PWTimeout:
                log(
                    "Sign-in timed out. Continuing in browse-only mode — jobs will be "
                    "listed but Easy Apply is unavailable until you sign in."
                )
                session.open_search()

        try:
            jobs = session.discover_jobs()
            log(f"Discovered {len(jobs)} job(s) to process.")
            attempted = 0
            for job in jobs:
                if attempted >= config.rate_limit.max_applications_per_run:
                    log(f"Reached per-run cap ({config.rate_limit.max_applications_per_run}). Stopping.")
                    break
                if rate_limiter.run_limit_reached():
                    log(f"Reached submission cap ({config.rate_limit.max_applications_per_run}). Stopping.")
                    break

                if config.skip_already_applied and tracker.already_applied(job.job_id):
                    log(f"Already applied, skipping: {job.title}")
                    continue

                if rate_limiter.hourly_limit_reached():
                    wait_s = rate_limiter.seconds_until_hourly_slot()
                    log(f"Hourly cap reached. Waiting {wait_s:.0f}s before continuing.")
                    time.sleep(wait_s)

                log(f"Applying: {job.title} @ {job.company} ({job.location})")
                try:
                    status = session.apply_to_job(job)
                except Exception as exc:  # keep the run alive across bad jobs
                    status = "error"
                    log(f"  Error on {job.title}: {exc}")

                tracker.record(
                    job_id=job.job_id,
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    url=job.url,
                    status=status,
                )
                stats[status] = stats.get(status, 0) + 1
                attempted += 1

                if status in {"submitted", "filled_awaiting_review"}:
                    rate_limiter.record_application()
                    rate_limiter.application_pause()
        except KeyboardInterrupt:
            log("Run stopped by user.")

    log(
        "Done. "
        f"submitted={stats['submitted']} "
        f"awaiting_review={stats['filled_awaiting_review']} "
        f"skipped={stats['skipped']} errors={stats['error']}"
    )
    return stats
