"""LinkedIn Easy Apply automation.

Builds/loads a jobs search, walks the result list, and drives the Easy Apply
modal to completion using the profile-backed :class:`FormFiller`. Submission is
gated by config (review-first by default). This respects LinkedIn's own login
and does not attempt to defeat any bot detection or CAPTCHA.

Selectors reflect LinkedIn's DOM as of writing; LinkedIn changes their markup
frequently, so selectors are centralised here for easy maintenance.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Iterator

from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PWTimeout

from .config import Config
from .form_filler import FillResult, FormFiller
from .profile import Profile
from .rate_limiter import RateLimiter
from .tracker import Tracker

JOBS_SEARCH = "https://www.linkedin.com/jobs/search/"
FEED_URL = "https://www.linkedin.com/feed/"
LOGIN_HINTS = ("/login", "/checkpoint", "/uas/login")

DATE_POSTED_MAP = {
    "past-24h": "r86400",
    "past-week": "r604800",
    "past-month": "r2592000",
}

# Logged-in and public/guest search pages use different card markup.
JOB_CARD_SELECTOR = (
    "li[data-occludable-job-id], "
    "div.job-card-container, "
    "ul.jobs-search__results-list li"
)
RESULT_LIST_SELECTOR = (
    "div.jobs-search-results-list, .scaffold-layout__list, ul.jobs-search__results-list"
)


@dataclass
class Job:
    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""


class LinkedInSession:
    def __init__(
        self,
        context: BrowserContext,
        config: Config,
        profile: Profile,
        tracker: Tracker,
        rate_limiter: RateLimiter,
        confirm: Callable[[str], bool] | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.context = context
        self.config = config
        self.profile = profile
        self.tracker = tracker
        self.rl = rate_limiter
        self.filler = FormFiller(profile, rate_limiter)
        # confirm(prompt) -> True to submit. Only used in review mode.
        self.confirm = confirm
        self.log = log
        self.page: Page = context.pages[0] if context.pages else context.new_page()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def is_logged_in(self) -> bool:
        """Best-effort check without blocking for manual sign-in."""
        if self._on_login_page():
            return False
        # Authenticated nav shows a profile/me control; guest pages do not.
        try:
            return self.page.locator(
                "img.global-nav__me-photo, button.global-nav__primary-link--me, .global-nav__me"
            ).count() > 0
        except Exception:
            return False

    def ensure_logged_in(self, timeout_s: int = 300) -> None:
        """Make sure we have an authenticated session.

        We navigate to the feed; if redirected to a login/checkpoint page we
        hand control to the human to sign in (and clear any CAPTCHA) and wait.
        """
        self.page.goto(FEED_URL, wait_until="domcontentloaded")
        if not self._on_login_page():
            self.log("LinkedIn session active.")
            return

        self.log(
            "Not logged in. Please sign in to LinkedIn in the opened Chrome "
            "window (complete any verification yourself). Waiting..."
        )
        self.page.wait_for_url(
            lambda url: not any(h in url for h in LOGIN_HINTS),
            timeout=timeout_s * 1000,
        )
        self.log("Login detected. Continuing.")

    def _on_login_page(self) -> bool:
        return any(h in self.page.url for h in LOGIN_HINTS)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def build_search_url(self) -> str:
        s = self.config.search
        if s.url:
            return s.url
        params: dict[str, str] = {}
        if s.keywords:
            params["keywords"] = s.keywords
        if s.location:
            params["location"] = s.location
        if s.easy_apply_only:
            params["f_AL"] = "true"
        if s.remote:
            params["f_WT"] = "2"  # remote work type
        if s.date_posted in DATE_POSTED_MAP:
            params["f_TPR"] = DATE_POSTED_MAP[s.date_posted]
        query = urllib.parse.urlencode(params)
        return f"{JOBS_SEARCH}?{query}" if query else JOBS_SEARCH

    def open_search(self) -> None:
        url = self.build_search_url()
        self.log(f"Opening search: {url}")
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Results render asynchronously on both guest and logged-in pages.
        try:
            self.page.locator(JOB_CARD_SELECTOR).first.wait_for(state="attached", timeout=30000)
        except PWTimeout:
            self.log("Search page loaded but no job cards appeared yet.")
        self.rl.action_pause()

    # ------------------------------------------------------------------
    # Result iteration
    # ------------------------------------------------------------------
    def discover_jobs(self, max_pages: int = 10) -> list[Job]:
        """Collect job metadata from search results before navigating away."""
        jobs: list[Job] = []
        seen: set[str] = set()
        for page_num in range(max_pages):
            self._scroll_result_list()
            cards = self.page.locator(JOB_CARD_SELECTOR)
            count = cards.count()
            if count == 0:
                self.log("No job cards found on this page.")
                break
            self.log(f"Found {count} job card(s) on page {page_num + 1}.")
            for i in range(count):
                job = self._read_card(cards.nth(i))
                if not job or job.job_id in seen:
                    continue
                seen.add(job.job_id)
                jobs.append(job)
            if not self._go_to_next_results_page(page_num + 2):
                break
        return jobs

    def iter_jobs(self, max_pages: int = 10) -> Iterator[Job]:
        """Yield jobs across result pages (snapshot collected up front)."""
        yield from self.discover_jobs(max_pages=max_pages)

    def _read_card(self, card: Locator) -> Job | None:
        try:
            job_id = self._job_id_from_card(card)
            if not job_id:
                return None
            title = self._safe_text(
                card.locator(
                    "a.job-card-list__title, a.job-card-container__link, h3, .base-search-card__title"
                ).first
            )
            company = self._safe_text(
                card.locator(
                    ".job-card-container__primary-description, "
                    ".artdeco-entity-lockup__subtitle, "
                    ".base-search-card__subtitle, h4"
                ).first
            )
            location = self._safe_text(
                card.locator(
                    ".job-card-container__metadata-item, .job-search-card__location"
                ).first
            )
            return Job(
                job_id=job_id,
                title=title,
                company=company,
                location=location,
                url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            )
        except Exception:
            return None

    def _job_id_from_card(self, card: Locator) -> str:
        job_id = card.get_attribute("data-occludable-job-id") or ""
        if job_id:
            return job_id
        urn = card.get_attribute("data-entity-urn") or ""
        if m := re.search(r"jobPosting:(\d+)", urn):
            return m.group(1)
        # Public cards nest the urn on an inner div.
        try:
            inner_urn = card.locator("[data-entity-urn*='jobPosting']").first.get_attribute(
                "data-entity-urn"
            )
            if inner_urn and (m := re.search(r"jobPosting:(\d+)", inner_urn)):
                return m.group(1)
        except Exception:
            pass
        link = card.locator("a[href*='/jobs/view/']").first
        href = link.get_attribute("href") if link.count() else ""
        if m := re.search(r"/jobs/view/[^/]*-(\d+)", href or ""):
            return m.group(1)
        if m := re.search(r"/jobs/view/(\d+)", href or ""):
            return m.group(1)
        return ""

    def _scroll_result_list(self) -> None:
        try:
            container = self.page.locator(RESULT_LIST_SELECTOR).first
            for _ in range(6):
                container.evaluate("el => el.scrollBy(0, el.clientHeight)")
                self.rl.action_pause()
        except Exception:
            pass

    def _go_to_next_results_page(self, page_number: int) -> bool:
        try:
            btn = self.page.locator(f"button[aria-label='Page {page_number}']")
            if btn.count() and btn.first.is_enabled():
                btn.first.click()
                self.rl.application_pause()
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Apply flow
    # ------------------------------------------------------------------
    def apply_to_job(self, job: Job) -> str:
        """Open a job and run the Easy Apply flow. Returns a status string."""
        self.page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
        self.rl.action_pause()

        easy_apply = self.page.locator(
            "button.jobs-apply-button, button[aria-label*='Easy Apply']"
        ).first
        if easy_apply.count() == 0 or not self._is_easy_apply(easy_apply):
            self.log(f"  Skipping (no Easy Apply): {job.title}")
            return "skipped"

        easy_apply.click()
        self.rl.action_pause()

        return self._run_modal(job)

    def _is_easy_apply(self, button: Locator) -> bool:
        try:
            text = (button.inner_text() or "").lower()
            return "easy apply" in text
        except Exception:
            return False

    def _run_modal(self, job: Job) -> str:
        modal = self.page.locator("div.jobs-easy-apply-modal, div[role='dialog']").first
        try:
            modal.wait_for(state="visible", timeout=10000)
        except PWTimeout:
            return "error"

        overall = FillResult()
        submit_selector = "button[aria-label='Submit application']"
        for step in range(40):  # generous cap; each step is one modal page
            self.rl.action_pause()
            step_result = self.filler.fill_container(modal)
            overall.merge(step_result)

            # Detect the submit button by presence, never by clicking it —
            # submission must only happen through the gated _finalise_submit.
            if self._is_visible(modal, submit_selector):
                return self._finalise_submit(job, modal, overall)

            # A review step often precedes submit; advancing to it may reveal
            # the submit button.
            self._click_if_present(modal, "button[aria-label='Review your application']", "Review")
            if self._is_visible(modal, submit_selector):
                return self._finalise_submit(job, modal, overall)

            # Continue to next step
            advanced = self._click_if_present(
                modal, "button[aria-label='Continue to next step']", "Next"
            ) or self._click_if_present(modal, "button:has-text('Next')", "Next")

            if not advanced:
                break

            if self._has_error(modal):
                self.log("  Form reports validation errors that need attention.")
                break

        # Reached here without submitting -> needs human help.
        self._pause_for_review(job, overall, reason="incomplete")
        return "filled_awaiting_review"

    def _finalise_submit(self, job: Job, modal: Locator, result: FillResult) -> str:
        """Decide whether to actually submit based on config + review state."""
        if self.config.auto_submit and not result.needs_review:
            self._confirm_submit_click(modal)
            self.log(f"  Submitted: {job.title} @ {job.company}")
            return "submitted"

        if self.config.auto_submit and result.needs_review:
            self.log("  Auto-submit skipped: fields need review.")

        approved = False
        if self.confirm is not None:
            summary = self._review_summary(job, result)
            approved = self.confirm(summary)
        if approved:
            self._confirm_submit_click(modal)
            self.log(f"  Submitted after review: {job.title}")
            return "submitted"

        self._pause_for_review(job, result, reason="awaiting-confirm")
        return "filled_awaiting_review"

    def _confirm_submit_click(self, modal: Locator) -> None:
        submit = modal.locator("button[aria-label='Submit application']").first
        if submit.count():
            submit.click()
            self.rl.action_pause()
        self._dismiss_post_submit()

    def _dismiss_post_submit(self) -> None:
        try:
            done = self.page.locator("button[aria-label='Dismiss'], button:has-text('Done')").first
            if done.count():
                done.click()
        except Exception:
            pass

    def _pause_for_review(self, job: Job, result: FillResult, reason: str) -> None:
        self.log(f"  Left filled for review ({reason}): {job.title}")
        if result.unmapped:
            self.log(f"    Unmapped fields: {', '.join(result.unmapped[:8])}")
        if result.low_confidence:
            self.log(f"    Low-confidence: {', '.join(result.low_confidence[:8])}")

    def _review_summary(self, job: Job, result: FillResult) -> str:
        lines = [
            f"Ready to submit: {job.title} @ {job.company} ({job.location})",
            f"  Filled {len(result.filled)} field(s).",
        ]
        if result.low_confidence:
            lines.append(f"  Review these: {', '.join(result.low_confidence[:10])}")
        if result.unmapped:
            lines.append(f"  Unmapped: {', '.join(result.unmapped[:10])}")
        lines.append("Submit this application?")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Modal helpers
    # ------------------------------------------------------------------
    def _click_if_present(self, scope: Locator, selector: str, label: str) -> bool:
        try:
            btn = scope.locator(selector).first
            if btn.count() and btn.is_visible() and btn.is_enabled():
                btn.click()
                self.rl.action_pause()
                return True
        except Exception:
            pass
        return False

    def _is_visible(self, scope: Locator, selector: str) -> bool:
        try:
            el = scope.locator(selector).first
            return bool(el.count()) and el.is_visible()
        except Exception:
            return False

    def _has_error(self, modal: Locator) -> bool:
        try:
            return modal.locator(".artdeco-inline-feedback--error, [role='alert']").count() > 0
        except Exception:
            return False

    def _safe_text(self, loc: Locator) -> str:
        try:
            if loc.count():
                return (loc.inner_text() or "").strip()
        except Exception:
            pass
        return ""
