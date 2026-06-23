from config import Settings
from emailer import (
    cta_demo_request_subject,
    customer_lead_request_subject,
    demo_inquiry_body,
    demo_inquiry_subject,
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
