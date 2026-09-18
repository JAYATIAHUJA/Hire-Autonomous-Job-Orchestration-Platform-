import json

from app.applications.consent import (
    CONSENT_ALGORITHM,
    build_consent_payload,
    canonical_json,
    issue_consent,
    sign_payload,
    verify_payload,
)


def test_consent_payload_carries_timestamp_purpose_and_named_employer():
    payload, signature = issue_consent(
        subject="oshisharma1222",
        employer_name="Swiggy Engineering",
        job_id="blr_swig_001",
        role_title="Backend Software Engineer",
    )

    assert payload["employer_name"] == "Swiggy Engineering"
    assert payload["purpose"]
    assert payload["granted_at"].endswith("+00:00")
    assert payload["action"] == "swipe_right"
    assert payload["consent_id"].startswith("csnt_")
    assert verify_payload(payload, signature) is True


def test_signature_is_independent_of_key_order():
    payload = build_consent_payload(
        consent_id="csnt_fixed",
        subject="candidate@example.com",
        employer_name="Zepto",
        job_id="hyd_zepto_002",
        role_title="Junior Full Stack Engineer",
        granted_at="2026-09-18T10:00:00+00:00",
    )
    reordered = dict(reversed(list(payload.items())))

    assert canonical_json(payload) == canonical_json(reordered)
    assert sign_payload(payload) == sign_payload(reordered)


def test_tampering_with_the_employer_breaks_verification():
    payload, signature = issue_consent(
        subject="oshisharma1222",
        employer_name="CRED",
        job_id="pune_cred_003",
        role_title="Android Developer",
    )
    assert verify_payload(payload, signature) is True

    forged = json.loads(json.dumps(payload))
    forged["employer_name"] = "Some Other Employer"
    assert verify_payload(forged, signature) is False

    assert verify_payload(payload, signature, secret="a-different-secret") is False
    assert verify_payload(payload, "") is False


def test_algorithm_is_recorded_for_replay():
    assert CONSENT_ALGORITHM == "HMAC-SHA256"
