import json

from config import Settings
from emailer import (
    RESEND_API_URL,
    RESEND_USER_AGENT,
    build_resend_request,
    cta_demo_request_subject,
    customer_lead_request_subject,
    demo_inquiry_body,
    demo_inquiry_subject,
    notify_for_customer_lead_request,
    owner_email_body,
    profile_owner_email,
)


def settings(owner_email="fallback@example.com"):
    return Settings(
        app_base_url="http://localhost:8501",
        app_base_url_configured=True,
        admin_password="secret",
        owner_email=owner_email,
        email_provider="disabled",
        from_email="Lead Rescue <noreply@example.com>",
        resend_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        database_path=":memory:",
    )


def resend_settings():
    return Settings(
        app_base_url="http://localhost:8501",
        app_base_url_configured=True,
        admin_password="secret",
        owner_email="owner@example.com",
        email_provider="resend",
        from_email="Lead Rescue <leads@verified.example>",
        resend_api_key="test-api-key",
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        database_path=":memory:",
    )


def test_profile_owner_email_takes_priority_over_global_fallback():
    profile = {"owner_email": "profile@example.com"}
    assert profile_owner_email(settings(), profile) == "profile@example.com"
    assert profile_owner_email(settings(), {}) == "fallback@example.com"


def test_owner_email_body_includes_business_and_dashboard_link():
    lead = {
        "name": "Alex",
        "phone": "555",
        "email": "",
        "vehicle_type": "SUV",
        "vehicle_condition": "heavy",
        "desired_service": "full detail",
        "location": "Vinton",
        "preferred_time": "Friday",
        "urgency": "today",
        "lead_score": 91,
        "owner_summary": "summary",
        "next_action": "Ask for photos.",
        "suggested_next_message": "Please send photos.",
    }
    body = owner_email_body(
        lead,
        {"business_name": "Vinton Auto Detail"},
        "http://localhost:8501",
    )

    assert "Vinton Auto Detail" in body
    assert "Ask for photos." in body
    assert "http://localhost:8501" in body


def test_demo_inquiry_email_includes_all_submitted_details():
    inquiry = {
        "submission_type": "customer_lead",
        "name": "Morgan Owner",
        "phone": "555-200-3030",
        "email": "morgan@example.com",
        "business_name": "Morgan Mobile Detail",
        "service_type": "Estimate",
        "message": "We need a callback link.",
        "customer_form_client_name": "ABC Plumbing",
        "customer_form_slug": "abc-plumbing",
        "destination_email_used": "abc@example.com",
        "created_at": "2026-06-22T18:00:00+00:00",
    }
    body = demo_inquiry_body(inquiry, "http://localhost:8501?admin=1")

    assert demo_inquiry_subject() == "New Customer Lead Request"
    assert customer_lead_request_subject() == "New Customer Lead Request"
    assert cta_demo_request_subject() == "New Lead Rescue Demo Request"
    assert "New customer lead request received." in body
    assert "Morgan Owner" in body
    assert "555-200-3030" in body
    assert "morgan@example.com" in body
    assert "Morgan Mobile Detail" in body
    assert "Estimate" in body
    assert "We need a callback link." in body
    assert "ABC Plumbing" in body
    assert "abc-plumbing" in body
    assert "abc@example.com" in body
    assert "http://localhost:8501?admin=1" in body


def test_cta_demo_request_email_body_identifies_demo_request():
    inquiry = {
        "submission_type": "cta_demo_request",
        "name": "Morgan Owner",
        "phone": "555-200-3030",
        "email": "morgan@example.com",
        "business_name": "Morgan Mobile Detail",
        "service_type": "Mobile detailing",
        "message": "I want Lead Rescue for missed calls.",
        "created_at": "2026-06-22T18:00:00+00:00",
    }

    body = demo_inquiry_body(inquiry)

    assert "New Lead Rescue demo request received." in body
    assert "Morgan Mobile Detail" in body
    assert "I want Lead Rescue for missed calls." in body


def test_resend_request_includes_required_headers_and_payload():
    request = build_resend_request(
        resend_settings(),
        "owner@example.com",
        "New Customer Lead Request",
        "Lead details",
    )

    assert request.full_url == RESEND_API_URL
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-api-key"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("User-agent") == RESEND_USER_AGENT

    payload = json.loads(request.data.decode("utf-8"))
    assert payload == {
        "from": "Lead Rescue <leads@verified.example>",
        "to": ["owner@example.com"],
        "subject": "New Customer Lead Request",
        "text": "Lead details",
    }


def test_customer_lead_notification_uses_form_destination_email(monkeypatch):
    sent = {}

    def fake_send_email(settings, to_email, subject, body):
        sent["to_email"] = to_email
        sent["subject"] = subject
        sent["body"] = body
        return True, "sent"

    monkeypatch.setattr("emailer.send_email", fake_send_email)
    inquiry = {
        "submission_type": "customer_lead",
        "name": "Taylor",
        "phone": "555",
        "email": "taylor@example.com",
        "business_name": "",
        "service_type": "Repair",
        "message": "Need help",
        "created_at": "2026-06-22T18:00:00+00:00",
    }
    configured = resend_settings()

    result = notify_for_customer_lead_request(configured, inquiry, "abc@example.com")

    assert result == ["sent"]
    assert sent["to_email"] == "abc@example.com"
    assert sent["subject"] == "New Customer Lead Request"


def test_customer_lead_notification_rejects_missing_or_invalid_destination():
    inquiry = {
        "submission_type": "customer_lead",
        "name": "Taylor",
        "phone": "555",
        "email": "taylor@example.com",
        "business_name": "",
        "service_type": "Repair",
        "message": "Need help",
    }

    assert notify_for_customer_lead_request(resend_settings(), inquiry, "") == [
        "Follow-up email not sent: form destination email is missing."
    ]
    assert notify_for_customer_lead_request(resend_settings(), inquiry, "bad-email") == [
        "Follow-up email not sent: form destination email is invalid."
    ]
