from app.applications.board import STAGE_INTERVIEW, STAGE_REJECTED
from app.mail.classifier import classify_reply
from app.mail.sync import company_tokens, match_application, sender_domain


class FakeApplication:
    def __init__(self, application_id, employer_name, employer_domain, stage="applied"):
        self.application_id = application_id
        self.employer_name = employer_name
        self.employer_domain = employer_domain
        self.stage = stage


def test_interview_invitation_is_classified():
    result = classify_reply(
        subject="Interview invitation - Backend Engineer at Swiggy",
        body="Hi, we would like to invite you to a technical interview. Please share your availability.",
    )
    assert result.stage == STAGE_INTERVIEW
    assert result.is_decision is True
    assert result.confidence > 0.5


def test_rejection_is_classified():
    result = classify_reply(
        subject="Update on your application",
        body="We regret to inform you that we have decided to move forward with other candidates.",
    )
    assert result.stage == STAGE_REJECTED
    assert result.confidence > 0.5


def test_rejection_wins_even_when_it_mentions_the_interview():
    result = classify_reply(
        subject="Your application at Zepto",
        body=(
            "Thank you for taking the time to interview with us. "
            "Unfortunately we will not be moving forward with your application at this time."
        ),
    )
    assert result.stage == STAGE_REJECTED


def test_polite_apology_inside_a_scheduling_mail_still_reads_as_interview():
    result = classify_reply(
        subject="Scheduling your technical round",
        body=(
            "Unfortunately the 10am slot is taken. Can we schedule the interview at 11am instead? "
            "A calendar invite will follow."
        ),
    )
    assert result.stage == STAGE_INTERVIEW


def test_neutral_mail_is_not_a_decision():
    result = classify_reply(
        subject="Thanks for applying",
        body="We have received your application and our team will review it shortly.",
    )
    assert result.stage is None
    assert result.is_decision is False


def test_sender_domain_ignores_generic_mailboxes():
    assert sender_domain("Recruiter <talent@swiggy.com>") == "swiggy.com"
    assert sender_domain("someone@gmail.com") is None
    assert sender_domain("no address here") is None


def test_company_tokens_drop_boilerplate():
    assert company_tokens("Swiggy Engineering") == ["swiggy"]
    assert "technologies" not in company_tokens("Acme Technologies Pvt Ltd")


def test_match_prefers_application_id_then_domain_then_name():
    swiggy = FakeApplication("app_aaaaaaaaaaaaaaaa", "Swiggy Engineering", "swiggy.com")
    zepto = FakeApplication("app_bbbbbbbbbbbbbbbb", "Zepto", "zeptonow.com")
    apps = [swiggy, zepto]

    quoted, how = match_application(
        {"subject": "Re: ref app_bbbbbbbbbbbbbbbb", "body": "", "from_address": "hr@swiggy.com"}, apps
    )
    assert quoted is zepto and "application id" in how

    by_domain, how = match_application(
        {"subject": "Next steps", "body": "", "from_address": "Talent <careers@swiggy.com>"}, apps
    )
    assert by_domain is swiggy and "sender domain" in how

    by_name, how = match_application(
        {"subject": "Your Zepto application", "body": "", "from_address": "recruiter@gmail.com"}, apps
    )
    assert by_name is zepto and "employer name" in how

    none_match, how = match_application(
        {"subject": "Newsletter", "body": "weekly digest", "from_address": "news@unrelated.io"}, apps
    )
    assert none_match is None
