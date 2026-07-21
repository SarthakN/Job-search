"""Human-in-the-loop job application assistant.

Opens a real Chrome browser via Playwright, signs in with your own LinkedIn
session, searches for jobs, and autofills Easy Apply forms from a structured
profile derived from your resume. Rate limited by design, and by default it
pauses for you to review before an application is submitted.

This tool does not defeat CAPTCHAs, bot-detection, or any site validation.
"""

__version__ = "0.1.0"
