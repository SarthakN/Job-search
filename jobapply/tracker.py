"""Persistent record of what we've applied to.

Backed by a simple CSV so it's trivially inspectable in a spreadsheet. Used to
skip duplicates and to seed the rolling-hour rate limit on startup.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

FIELDNAMES = [
    "timestamp",
    "epoch",
    "job_id",
    "title",
    "company",
    "location",
    "url",
    "status",  # submitted | filled_awaiting_review | skipped | error
    "note",
]


class Tracker:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._applied_ids: set[str] = set()
        self._recent_epochs: list[float] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                job_id = (row.get("job_id") or "").strip()
                if job_id and row.get("status") in {"submitted", "filled_awaiting_review"}:
                    self._applied_ids.add(job_id)
                try:
                    self._recent_epochs.append(float(row.get("epoch") or 0))
                except ValueError:
                    continue

    def already_applied(self, job_id: str) -> bool:
        return bool(job_id) and job_id in self._applied_ids

    def recent_epochs_within_hour(self) -> list[float]:
        cutoff = time.time() - 3600.0
        return [e for e in self._recent_epochs if e >= cutoff]

    def record(
        self,
        *,
        job_id: str,
        title: str,
        company: str,
        location: str,
        url: str,
        status: str,
        note: str = "",
    ) -> None:
        now = time.time()
        exists = self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "epoch": f"{now:.0f}",
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "status": status,
                    "note": note,
                }
            )
        if status in {"submitted", "filled_awaiting_review"} and job_id:
            self._applied_ids.add(job_id)
        self._recent_epochs.append(now)
