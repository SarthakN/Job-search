"""Resume ingestion.

Extracts raw text from PDF / DOCX / TXT resumes and does a best-effort pass at
populating a :class:`~jobapply.profile.Profile`. Parsing resumes from free text
is inherently lossy, so the goal here is to give you a filled-in starting point
that you then review and correct by hand (or via the ``--edit`` flow).
"""

from __future__ import annotations

import re
from pathlib import Path

from .profile import Profile

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Matches most international / US phone formats with 7-15 digits.
PHONE_RE = re.compile(
    r"(?<!\w)(\+?\d{1,3}[\s.-]?)?(\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\w)"
)
LINKEDIN_RE = re.compile(r"https?://(?:[\w.]*\.)?linkedin\.com/[^\s)]+", re.I)
URL_RE = re.compile(r"https?://[^\s)]+", re.I)


def extract_text(path: str | Path) -> str:
    """Return the plain text content of a resume file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Resume not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported resume format: {suffix} (use pdf, docx, txt)")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(path: Path) -> str:
    import docx  # python-docx

    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _clean_phone(raw: str) -> str:
    digits = re.sub(r"[^\d+]", "", raw)
    # Reject strings that are clearly not phone numbers (dates, ids).
    stripped = digits.lstrip("+")
    if not (7 <= len(stripped) <= 15):
        return ""
    return digits


def parse_resume(path: str | Path, base: Profile | None = None) -> Profile:
    """Best-effort extraction of contact fields from a resume file.

    ``base`` lets you layer parsed values on top of an existing profile without
    clobbering fields you have already curated.
    """
    text = extract_text(path)
    profile = base or Profile()
    profile.resume_path = str(Path(path).resolve())

    if not profile.email:
        if m := EMAIL_RE.search(text):
            profile.email = m.group(0)

    if not profile.phone:
        for m in PHONE_RE.finditer(text):
            phone = _clean_phone(m.group(0))
            if phone:
                profile.phone = phone
                break

    if not profile.linkedin_url:
        if m := LINKEDIN_RE.search(text):
            profile.linkedin_url = m.group(0).rstrip(".,);")

    if not profile.website:
        for m in URL_RE.finditer(text):
            url = m.group(0).rstrip(".,);")
            if "linkedin.com" not in url.lower():
                profile.website = url
                break

    if not (profile.first_name or profile.last_name):
        first, last = _guess_name(text, profile.email)
        profile.first_name = profile.first_name or first
        profile.last_name = profile.last_name or last

    return profile


def _guess_name(text: str, email: str) -> tuple[str, str]:
    """Guess a name from the first non-empty line of the resume.

    Resumes almost always lead with the candidate's name as a heading. We fall
    back to the local part of the email address if that fails.
    """
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if EMAIL_RE.search(line) or URL_RE.search(line) or any(c.isdigit() for c in line):
            continue
        words = line.split()
        if 1 < len(words) <= 4 and all(w[:1].isalpha() for w in words):
            return words[0], " ".join(words[1:])
        break

    if email and "@" in email:
        local = re.split(r"[._-]", email.split("@")[0])
        local = [p for p in local if p.isalpha()]
        if len(local) >= 2:
            return local[0].capitalize(), local[1].capitalize()
        if local:
            return local[0].capitalize(), ""
    return "", ""
