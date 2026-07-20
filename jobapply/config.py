"""Runtime configuration.

Values come from (in increasing priority): built-in defaults, the YAML config
file, then CLI overrides applied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SearchConfig:
    # Either provide a full LinkedIn jobs search URL, or keywords + location.
    url: str = ""
    keywords: str = ""
    location: str = ""
    remote: bool = False
    easy_apply_only: bool = True
    date_posted: str = ""  # "", "past-24h", "past-week", "past-month"
    experience_levels: list[str] = field(default_factory=list)


@dataclass
class RateLimitConfig:
    # Seconds to wait between whole applications (min, max) -> randomised.
    between_applications: tuple[float, float] = (25.0, 55.0)
    # Delay between individual field interactions to mimic human pace.
    between_actions: tuple[float, float] = (0.4, 1.4)
    # Hard cap on applications submitted in a single run.
    max_applications_per_run: int = 15
    # Hard cap per rolling hour (persisted in the tracker).
    max_applications_per_hour: int = 20


@dataclass
class Config:
    profile_path: str = "profile.json"
    tracker_path: str = "applications.csv"
    # Where Chrome stores the persistent profile (cookies/login).
    user_data_dir: str = ".chrome-profile"
    headless: bool = False
    # If False (default), the tool fills the form and waits for you to submit.
    auto_submit: bool = False
    # Skip jobs already present in the tracker.
    skip_already_applied: bool = True

    search: SearchConfig = field(default_factory=SearchConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    @classmethod
    def load(cls, path: str | Path | None) -> "Config":
        data: dict[str, Any] = {}
        if path and Path(path).exists():
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        data = dict(data or {})
        search = SearchConfig(**(data.pop("search", {}) or {}))
        rl_data = data.pop("rate_limit", {}) or {}
        for key in ("between_applications", "between_actions"):
            if key in rl_data and isinstance(rl_data[key], list):
                rl_data[key] = tuple(rl_data[key])
        rate_limit = RateLimitConfig(**rl_data)
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(search=search, rate_limit=rate_limit, **filtered)
