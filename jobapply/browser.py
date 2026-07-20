"""Chrome lifecycle management via Playwright.

Launches a real Chrome instance with a persistent user-data directory so you
log into LinkedIn once (manually, solving any CAPTCHA yourself) and the session
is reused on later runs. Nothing here bypasses authentication or bot checks.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Page, sync_playwright


@contextmanager
def launch_chrome(
    user_data_dir: str | Path,
    headless: bool = False,
    slow_mo_ms: int = 0,
) -> Iterator[BrowserContext]:
    """Yield a persistent Chrome browser context.

    Using a persistent context (rather than an incognito browser) is what keeps
    the LinkedIn login alive between runs.
    """
    user_data_dir = Path(user_data_dir)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=headless,
            channel="chrome",
            slow_mo=slow_mo_ms,
            viewport={"width": 1366, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        try:
            yield context
        finally:
            context.close()


def get_page(context: BrowserContext) -> Page:
    """Return the first open page, creating one if needed."""
    if context.pages:
        return context.pages[0]
    return context.new_page()
