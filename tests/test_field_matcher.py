from jobapply.field_matcher import Answer, choose_option, resolve_answer
from jobapply.profile import Experience, Profile


def make_profile() -> Profile:
    return Profile(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="+15551234567",
        city="London",
        country="United Kingdom",
        years_of_experience=8,
        authorized_to_work=True,
        requires_sponsorship=False,
        willing_to_relocate=False,
        desired_salary="120000",
        experience=[Experience(title="Senior Engineer", company="Engines Ltd")],
        screening_answers={"how did you hear about": "LinkedIn"},
    )


def test_basic_contact_fields():
    p = make_profile()
    assert resolve_answer("First name", p).value == "Ada"
    assert resolve_answer("Last Name", p).value == "Lovelace"
    assert resolve_answer("Email address", p).value == "ada@example.com"
    assert resolve_answer("Mobile phone number", p).value == "+15551234567"
    assert resolve_answer("City", p).value == "London"


def test_boolean_questions():
    p = make_profile()
    assert resolve_answer("Are you legally authorized to work?", p).value == "Yes"
    assert resolve_answer("Do you require visa sponsorship?", p).value == "No"
    assert resolve_answer("Are you willing to relocate?", p).value == "No"


def test_years_of_experience():
    p = make_profile()
    ans = resolve_answer("How many years of experience do you have with Python?", p)
    assert ans.value == "8"
    assert ans.kind == "numeric"


def test_screening_override_wins():
    p = make_profile()
    ans = resolve_answer("How did you hear about this role?", p)
    assert ans.value == "LinkedIn"


def test_current_company_and_title():
    p = make_profile()
    assert resolve_answer("Current company", p).value == "Engines Ltd"
    assert resolve_answer("Current job title", p).value == "Senior Engineer"


def test_unknown_question_returns_none():
    p = make_profile()
    assert resolve_answer("What is your favourite colour?", p) is None


def test_empty_value_is_low_confidence():
    p = make_profile()
    p.desired_salary = ""
    ans = resolve_answer("Desired salary", p)
    assert ans is not None
    assert ans.confident is False


def test_choose_option_exact_and_fuzzy():
    ans = Answer("United Kingdom", kind="choice")
    options = ["United States", "United Kingdom of Great Britain", "Canada"]
    assert choose_option(ans, options) == "United Kingdom of Great Britain"


def test_choose_option_boolean_synonyms():
    ans = Answer("Yes", kind="boolean")
    assert choose_option(ans, ["True", "False"]) == "True"
