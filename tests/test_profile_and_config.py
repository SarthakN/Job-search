import json

from jobapply.config import Config
from jobapply.profile import Experience, Profile


def test_profile_roundtrip(tmp_path):
    p = Profile(
        first_name="Ada",
        last_name="Lovelace",
        experience=[Experience(title="Eng", company="X")],
        skills=["Python"],
    )
    out = tmp_path / "profile.json"
    p.save(out)
    loaded = Profile.load(out)
    assert loaded.full_name == "Ada Lovelace"
    assert loaded.experience[0].company == "X"
    assert loaded.skills == ["Python"]


def test_profile_from_dict_ignores_unknown_keys():
    p = Profile.from_dict({"first_name": "Ada", "bogus": 1})
    assert p.first_name == "Ada"


def test_config_defaults():
    c = Config.from_dict({})
    assert c.auto_submit is False
    assert c.rate_limit.max_applications_per_run == 15
    assert c.search.easy_apply_only is True


def test_config_from_yaml_like_dict():
    data = {
        "auto_submit": True,
        "search": {"keywords": "Backend", "location": "Remote"},
        "rate_limit": {"between_applications": [10, 20], "max_applications_per_run": 5},
    }
    c = Config.from_dict(data)
    assert c.auto_submit is True
    assert c.search.keywords == "Backend"
    assert c.rate_limit.between_applications == (10, 20)
    assert c.rate_limit.max_applications_per_run == 5
