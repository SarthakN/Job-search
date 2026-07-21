from jobapply.rate_limiter import RateLimiter
from jobapply.resume import parse_resume
from jobapply.tracker import Tracker


RESUME_TEXT = """Ada Lovelace
Senior Software Engineer
ada.lovelace@example.com | +1 (555) 123-4567
https://www.linkedin.com/in/ada-lovelace
https://ada.example.com

Experience
Analytical Engines Ltd - Senior Engineer (2021 - Present)
"""


def test_parse_resume_txt(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text(RESUME_TEXT, encoding="utf-8")
    p = parse_resume(resume)
    assert p.email == "ada.lovelace@example.com"
    assert p.phone.startswith("+1") or p.phone.replace("+", "").isdigit()
    assert "linkedin.com/in/ada-lovelace" in p.linkedin_url
    assert p.website == "https://ada.example.com"
    assert p.first_name == "Ada"
    assert p.last_name == "Lovelace"
    assert p.resume_path.endswith("resume.txt")


def test_tracker_dedup_and_recording(tmp_path):
    path = tmp_path / "apps.csv"
    t = Tracker(path)
    assert not t.already_applied("123")
    t.record(
        job_id="123",
        title="Eng",
        company="X",
        location="Remote",
        url="http://x",
        status="submitted",
    )
    t2 = Tracker(path)
    assert t2.already_applied("123")
    assert len(t2.recent_epochs_within_hour()) == 1


def test_rate_limiter_run_cap():
    rl = RateLimiter((0, 0), (0, 0), max_per_run=2, max_per_hour=100)
    assert not rl.run_limit_reached()
    rl.record_application()
    rl.record_application()
    assert rl.run_limit_reached()


def test_rate_limiter_hourly_cap():
    rl = RateLimiter((0, 0), (0, 0), max_per_run=100, max_per_hour=2)
    assert not rl.hourly_limit_reached()
    rl.record_application()
    rl.record_application()
    assert rl.hourly_limit_reached()
    assert rl.seconds_until_hourly_slot() > 0
