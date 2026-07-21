"""Command-line interface.

Subcommands:
  init-profile   Build/refresh profile.json from a resume file.
  apply          Run the search + Easy Apply flow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .profile import Profile
from .resume import parse_resume


def _prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{text}{suffix}: ").strip()
    except EOFError:
        return default
    return val or default


def cmd_init_profile(args: argparse.Namespace) -> int:
    out = Path(args.output)
    base = Profile.load(out) if out.exists() and not args.overwrite else Profile()

    if args.resume:
        print(f"Parsing resume: {args.resume}")
        base = parse_resume(args.resume, base=base)
        print("Parsed contact details (please review/edit the JSON afterwards):")
        for f in ("first_name", "last_name", "email", "phone", "linkedin_url"):
            print(f"  {f}: {getattr(base, f) or '(empty)'}")

    if args.interactive:
        base.first_name = _prompt("First name", base.first_name)
        base.last_name = _prompt("Last name", base.last_name)
        base.email = _prompt("Email", base.email)
        base.phone = _prompt("Phone", base.phone)
        base.city = _prompt("City", base.city)
        base.state = _prompt("State/Province", base.state)
        base.country = _prompt("Country", base.country)
        yoe = _prompt("Years of experience", str(base.years_of_experience or ""))
        base.years_of_experience = int(yoe) if yoe.isdigit() else base.years_of_experience

    if args.resume and not base.resume_path:
        base.resume_path = str(Path(args.resume).resolve())

    base.save(out)
    print(f"Wrote profile to {out.resolve()}")
    print("Open it and fill in experience, education, and screening_answers before applying.")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    config = Config.load(args.config)

    # CLI overrides
    if args.url:
        config.search.url = args.url
    if args.keywords:
        config.search.keywords = args.keywords
    if args.location:
        config.search.location = args.location
    if args.profile:
        config.profile_path = args.profile
    if args.tracker:
        config.tracker_path = args.tracker
    if args.max is not None:
        config.rate_limit.max_applications_per_run = args.max
    if args.auto_submit:
        config.auto_submit = True
    if args.headless:
        config.headless = True
    if args.login_timeout is not None:
        config.login_timeout_s = args.login_timeout

    if not Path(config.profile_path).exists():
        print(
            f"Profile not found at {config.profile_path}. "
            "Run `python -m jobapply init-profile --resume <file>` first.",
            file=sys.stderr,
        )
        return 2

    # Interactive prompt for search params if none provided anywhere.
    if not (config.search.url or config.search.keywords):
        print("No search provided. Enter LinkedIn search parameters (or a full URL).")
        url = _prompt("LinkedIn jobs search URL (leave blank to use keywords)")
        if url:
            config.search.url = url
        else:
            config.search.keywords = _prompt("Keywords (e.g. 'Backend Engineer')")
            config.search.location = _prompt("Location (e.g. 'Berlin' or 'Remote')")

    if config.auto_submit:
        print(
            "\n*** AUTO-SUBMIT is ON: applications will be submitted without a "
            "per-job confirmation (still rate limited, still skips fields it "
            "can't confidently fill). Ctrl-C to abort. ***\n"
        )

    # Import here so `init-profile` works without Playwright installed.
    from .runner import run

    run(config)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobapply",
        description="Human-in-the-loop LinkedIn Easy Apply assistant.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-profile", help="Create/refresh profile.json from a resume")
    p_init.add_argument("--resume", help="Path to resume (pdf/docx/txt)")
    p_init.add_argument("--output", default="profile.json", help="Where to write the profile")
    p_init.add_argument("--interactive", action="store_true", help="Prompt for core fields")
    p_init.add_argument("--overwrite", action="store_true", help="Ignore any existing profile")
    p_init.set_defaults(func=cmd_init_profile)

    p_apply = sub.add_parser("apply", help="Run the search + Easy Apply flow")
    p_apply.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    p_apply.add_argument("--url", help="Full LinkedIn jobs search URL")
    p_apply.add_argument("--keywords", help="Search keywords")
    p_apply.add_argument("--location", help="Search location")
    p_apply.add_argument("--profile", help="Path to profile.json")
    p_apply.add_argument("--tracker", help="Path to applications.csv")
    p_apply.add_argument("--max", type=int, help="Max applications this run")
    p_apply.add_argument(
        "--auto-submit",
        action="store_true",
        help="Submit without per-job confirmation (opt-in; rate limited)",
    )
    p_apply.add_argument("--headless", action="store_true", help="Run Chrome headless")
    p_apply.add_argument(
        "--login-timeout",
        type=int,
        metavar="SECONDS",
        help="How long to wait for manual LinkedIn sign-in (default: 300)",
    )
    p_apply.set_defaults(func=cmd_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
