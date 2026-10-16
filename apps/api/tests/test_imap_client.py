from email.message import EmailMessage

from app.applications.board import STAGE_INTERVIEW
from app.mail.classifier import classify_reply
from app.mail.imap_client import ImapNotConfigured, config_from_settings, parse_message


def build_raw_message(*, subject: str, body: str, html: str = "") -> bytes:
    msg = EmailMessage()
    msg["From"] = "Talent Team <careers@swiggy.com>"
    msg["To"] = "candidate@example.com"
    msg["Subject"] = subject
    msg["Date"] = "Thu, 18 Sep 2026 09:30:00 +0530"
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg.as_bytes()


def test_parse_message_extracts_headers_and_plain_text_body():
    raw = build_raw_message(
        subject="Interview invitation - Backend Engineer",
        body="Please share your availability for a technical interview.",
        html="<p>Please share your availability for a technical interview.</p>",
    )

    parsed = parse_message("42", raw)

    assert parsed["uid"] == "42"
    assert parsed["from_address"] == "Talent Team <careers@swiggy.com>"
    assert parsed["subject"] == "Interview invitation - Backend Engineer"
    assert "availability" in parsed["body"]
    assert "<p>" not in parsed["body"]  # text/plain is preferred over the HTML part
    assert parsed["received_at"].startswith("2026-09-18T09:30:00")


def test_parse_message_decodes_encoded_subject_headers():
    raw = (
        b"From: =?utf-8?q?Talent_Team?= <careers@zeptonow.com>\r\n"
        b"Subject: =?utf-8?q?Interview_invitation_=E2=80=94_Zepto?=\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Can we schedule the interview on Monday?\r\n"
    )

    parsed = parse_message("43", raw)

    assert parsed["subject"] == "Interview invitation — Zepto"
    assert classify_reply(subject=parsed["subject"], body=parsed["body"]).stage == STAGE_INTERVIEW


def test_config_from_settings_names_the_missing_credentials():
    try:
        config_from_settings()
    except ImapNotConfigured as exc:
        assert "IMAP_HOST" in str(exc)
        assert "IMAP_USER" in str(exc)
    else:  # pragma: no cover - only reached if a real mailbox is configured locally
        pass
