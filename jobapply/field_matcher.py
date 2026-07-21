"""Pure logic that maps a form question to an answer from the profile.

Kept free of any browser dependency so it can be unit tested in isolation. The
DOM-walking code in :mod:`jobapply.form_filler` calls into here to decide what
to type or select for each field it discovers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .profile import Profile

# Ordered list of (matchers, resolver). The first group whose any keyword is a
# substring of the normalised question wins. Resolvers read from the profile.
_YES = "Yes"
_NO = "No"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


@dataclass
class Answer:
    """The desired answer for a field.

    ``value`` is the raw text to type or the option label to select. ``kind`` is
    a hint for the filler (``text``, ``choice``, ``boolean``, ``numeric``).
    ``confident`` is False when we're guessing; the filler surfaces low-confidence
    fields for human review.
    """

    value: str
    kind: str = "text"
    confident: bool = True


def _boolean_answer(flag: bool) -> Answer:
    return Answer(_YES if flag else _NO, kind="boolean")


# Each rule: list of keyword fragments -> function(profile) returning Answer|None
def _rules(profile: Profile) -> list[tuple[list[str], Optional[Answer]]]:
    p = profile
    yoe = str(p.years_of_experience) if p.years_of_experience else ""
    # Ordered specific -> generic. Yes/No and multi-word phrases come before
    # generic single words (e.g. work-authorization before "country") so a
    # question like "authorized to work in this country?" isn't captured by the
    # country rule.
    return [
        # Work authorisation / logistics (boolean) -- kept first so phrases that
        # embed generic words like "country" resolve correctly.
        (
            ["authorized to work", "legally authorized", "work authorization",
             "eligible to work", "right to work"],
            _boolean_answer(p.authorized_to_work),
        ),
        (
            ["require sponsorship", "need sponsorship", "visa sponsorship",
             "require visa", "sponsorship"],
            _boolean_answer(p.requires_sponsorship),
        ),
        (
            ["willing to relocate", "open to relocation", "relocate"],
            _boolean_answer(p.willing_to_relocate),
        ),
        (
            ["years of experience", "years experience", "how many years"],
            Answer(yoe, kind="numeric", confident=bool(yoe)),
        ),
        (["desired salary", "salary expectation", "expected salary", "compensation"], Answer(p.desired_salary, kind="numeric")),
        (["notice period", "when can you start", "availability", "start date"], Answer(p.notice_period)),
        # Identity / contact
        (["first name", "given name", "legal first"], Answer(p.first_name)),
        (["last name", "family name", "surname", "legal last"], Answer(p.last_name)),
        (["full name", "your name", "name of applicant"], Answer(p.full_name)),
        (["email"], Answer(p.email)),
        (["country code", "phone country"], Answer(p.phone_country_code, kind="choice")),
        (["mobile", "phone number", "phone", "contact number"], Answer(p.phone, kind="numeric")),
        (["current company", "employer"], Answer(p.experience[0].company if p.experience else "")),
        (["current title", "job title", "current role"], Answer(p.experience[0].title if p.experience else "")),
        (["linkedin"], Answer(p.linkedin_url)),
        (["portfolio", "website", "personal site", "github"], Answer(p.website)),
        # Address (generic single words last)
        (["street", "address line", "address"], Answer(p.address)),
        (["city", "town"], Answer(p.city)),
        (["state", "province", "region"], Answer(p.state)),
        (["zip", "postal", "postcode"], Answer(p.postal_code, kind="numeric")),
        (["country"], Answer(p.country, kind="choice")),
    ]


def resolve_answer(question: str, profile: Profile) -> Optional[Answer]:
    """Return the best answer for ``question`` or ``None`` if unknown.

    Resolution order: explicit screening_answers overrides, then the built-in
    rule table. Screening answers let you pin exact responses to recurring
    questions the rules don't cover.
    """
    q = _norm(question)
    if not q:
        return None

    # 1. User-provided explicit overrides (most specific match wins).
    best_key = None
    for key in profile.screening_answers:
        nk = _norm(key)
        if nk and nk in q:
            if best_key is None or len(nk) > len(_norm(best_key)):
                best_key = key
    if best_key is not None:
        return Answer(profile.screening_answers[best_key], confident=True)

    # 2. Built-in rules, first match wins. The table is ordered specific ->
    #    generic so multi-word phrases ("authorized to work in this country")
    #    are matched before generic single words ("country").
    for keywords, answer in _rules(profile):
        if answer is None:
            continue
        if any(kw in q for kw in keywords):
            # An empty value is not a usable answer; treat as low-confidence so
            # the field is flagged for review rather than silently blanked.
            if answer.value == "" and answer.kind != "boolean":
                return Answer("", kind=answer.kind, confident=False)
            return answer

    return None


def choose_option(answer: Answer, options: list[str]) -> Optional[str]:
    """Pick the option label from ``options`` best matching ``answer.value``.

    Handles exact match, case-insensitive match, and substring both ways so a
    profile value of "United States" matches an option like
    "United States of America".
    """
    if not options:
        return None
    target = _norm(answer.value)
    if not target:
        return None

    norm_options = [(_norm(o), o) for o in options]

    for no, orig in norm_options:
        if no == target:
            return orig
    for no, orig in norm_options:
        if target in no or no in target:
            return orig
    # For boolean answers, accept common synonyms.
    if answer.kind == "boolean":
        synonyms = {"yes": ["true", "y"], "no": ["false", "n"]}.get(target, [])
        for no, orig in norm_options:
            if no in synonyms:
                return orig
    return None
