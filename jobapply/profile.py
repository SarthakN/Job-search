"""Structured applicant profile derived from a resume.

The profile is the single source of truth the autofill engine reads from. It is
intentionally a plain, serialisable dataclass tree so it can be stored as JSON,
hand-edited, and diffed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Experience:
    title: str = ""
    company: str = ""
    location: str = ""
    start_date: str = ""  # free-form, e.g. "2021-03" or "Mar 2021"
    end_date: str = ""     # "" or "Present"
    description: str = ""


@dataclass
class Education:
    school: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""


@dataclass
class Profile:
    # Contact / identity
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    phone_country_code: str = "United States (+1)"
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "United States"
    linkedin_url: str = ""
    website: str = ""

    # Files
    resume_path: str = ""
    cover_letter_path: str = ""

    # History
    experience: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    # Common screening answers. Keys are lowercased question fragments; values
    # are the answer to type/select. The filler does fuzzy substring matching
    # against these, so keep the keys short and distinctive.
    screening_answers: dict[str, str] = field(default_factory=dict)

    # Work authorisation / logistics flags used to answer yes/no questions.
    years_of_experience: int = 0
    authorized_to_work: bool = True
    requires_sponsorship: bool = False
    willing_to_relocate: bool = False
    desired_salary: str = ""
    notice_period: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        data = dict(data)
        data["experience"] = [Experience(**e) for e in data.get("experience", [])]
        data["education"] = [Education(**e) for e in data.get("education", [])]
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
