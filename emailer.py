from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any

from config import Settings


def profile_owner_email(settings: Settings, profile: dict[str, str] | None = None) -> str:
    if profile and profile.get("owner_email", "").strip():
        return profile["owner_email"].strip()
    return settings.owner_email


def email_enabled(settings: Settings, profile: dict[str, str] | None = None) -> bool:
    owner_email = profile_owner_email(settings, profile)
    if settings.email_provider == "resend":
        return bool(owner_email and settings.resend_api_key)
    if settings.email_provider == "smtp":
        return bool(
            owner_email
            and settings.smtp_host
            and settings.smtp_username
            and settings.smtp_password
        )
    return False


def owner_email_subject(lead: dict[str, Any]) -> str:
    return (
        f"New Detailing Lead: {lead['desired_service']} / "
        f"{lead['vehicle_type']} / {lead['urgency']}"
    )


def owner_email_body(
    lead: dict[str, Any],
    profile: dict[str, str] | None = None,
    dashboard_link: str = "",
) -> str:
    business_name = profile.get("business_name", "Lead Rescue AI") if profile else "Lead Rescue AI"
    return f"""New detailing lead received for {business_name}.

Customer name: {lead["name"]}
Phone: {lead["phone"]}
Email: {lead["email"] or "Not provided"}
Vehicle: {lead["vehicle_type"]}
Service: {lead["desired_service"]}
Condition: {lead["vehicle_condition"]}
Location: {lead["location"]}
Preferred time: {lead["preferred_time"]}
Urgency: {lead["urgency"]}
Lead score: {lead["lead_score"]}/100

Owner summary:
{lead["owner_summary"]}

Suggested next action:
{lead["next_action"]}

Suggested next message:
{lead["suggested_next_message"]}

Dashboard:
{dashboard_link or "Open the Lead Rescue AI dashboard to manage this lead."}
"""


def customer_email_subject(profile: dict[str, str] | None = None) -> str:
    if profile and profile.get("business_name"):
        return f"{profile['business_name']} received your detailing request"
    return "We received your mobile detailing quote request"


def demo_inquiry_subject() -> str:
    return customer_lead_request_subject()


def customer_lead_request_subject() -> str:
    return "New Customer Lead Request"


def cta_demo_request_subject() -> str:
    return "New Lead Rescue Demo Request"


def demo_inquiry_body(inquiry: dict[str, Any], dashboard_link: str = "") -> str:
    intro = "New customer lead request received."
    if inquiry.get("submission_type") == "cta_demo_request":
        intro = "New Lead Rescue demo request received."
    return f"""{intro}

Name: {inquiry["name"]}
Phone: {inquiry["phone"]}
Email: {inquiry["email"]}
Company/business: {inquiry.get("business_name") or "Not provided"}
Service/request type: {inquiry.get("service_type", "Not provided")}
Message:
{inquiry["message"]}

Created: {inquiry.get("created_at", "Not recorded")}

Dashboard:
{dashboard_link or "Open the Lead Rescue operator area to review this request."}
"""


def send_email(
    settings: Settings,
    to_email: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    if not to_email:
        return False, "Missing recipient email."
    if settings.email_provider == "resend":
        return send_resend_email(settings, to_email, subject, body)
    if settings.email_provider == "smtp":
        return send_smtp_email(settings, to_email, subject, body)
    return False, "Email sending disabled. Set EMAIL_PROVIDER to resend or smtp."


def send_resend_email(
    settings: Settings,
    to_email: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    if not settings.resend_api_key:
        return False, "RESEND_API_KEY is missing."

    payload = json.dumps(
        {
            "from": settings.from_email,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 200 <= response.status < 300:
                return True, "Email sent with Resend."
            return False, f"Resend returned status {response.status}."
    except urllib.error.URLError as exc:
        return False, f"Resend email failed: {exc}"


def send_smtp_email(
    settings: Settings,
    to_email: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    message = EmailMessage()
    message["From"] = settings.from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(context=context)
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return True, "Email sent with SMTP."
    except OSError as exc:
        return False, f"SMTP email failed: {exc}"


def notify_for_new_lead(
    settings: Settings,
    lead: dict[str, Any],
    profile: dict[str, str] | None = None,
) -> list[str]:
    results: list[str] = []
    owner_email = profile_owner_email(settings, profile)
    if not owner_email:
        return ["Owner email not sent: no owner_email exists on this business profile."]
    if not email_enabled(settings, profile):
        return ["Email sending disabled or not fully configured."]

    owner_sent, owner_message = send_email(
        settings,
        owner_email,
        owner_email_subject(lead),
        owner_email_body(lead, profile, f"{settings.app_base_url.rstrip('/')}?admin=1"),
    )
    results.append(owner_message if owner_sent else f"Owner email not sent: {owner_message}")

    if lead.get("email"):
        customer_sent, customer_message = send_email(
            settings,
            lead["email"],
            customer_email_subject(profile),
            lead["customer_confirmation"],
        )
        results.append(
            customer_message
            if customer_sent
            else f"Customer email not sent: {customer_message}"
        )
    return results


def notify_for_demo_inquiry(
    settings: Settings,
    inquiry: dict[str, Any],
    destination_email: str = "",
) -> list[str]:
    return notify_for_customer_lead_request(settings, inquiry, destination_email)


def notify_for_customer_lead_request(
    settings: Settings,
    inquiry: dict[str, Any],
    destination_email: str = "",
) -> list[str]:
    to_email = destination_email.strip() or settings.owner_email
    if not to_email:
        return ["Follow-up email not sent: OWNER_EMAIL or form destination email is missing."]
    if not email_enabled_for_recipient(settings, to_email):
        return ["Follow-up email not sent: email delivery is disabled or not fully configured."]
    sent, message = send_email(
        settings,
        to_email,
        customer_lead_request_subject(),
        demo_inquiry_body(inquiry, f"{settings.app_base_url.rstrip('/')}?admin=1"),
    )
    return [message if sent else f"Follow-up email not sent: {message}"]


def notify_for_cta_demo_request(
    settings: Settings,
    inquiry: dict[str, Any],
) -> list[str]:
    if not settings.owner_email:
        return ["Demo request email not sent: OWNER_EMAIL is missing."]
    if not email_enabled_for_recipient(settings, settings.owner_email):
        return ["Demo request email not sent: email delivery is disabled or not fully configured."]
    sent, message = send_email(
        settings,
        settings.owner_email,
        cta_demo_request_subject(),
        demo_inquiry_body(inquiry),
    )
    return [message if sent else f"Demo request email not sent: {message}"]


def email_enabled_for_recipient(settings: Settings, to_email: str) -> bool:
    if not to_email:
        return False
    if settings.email_provider == "resend":
        return bool(settings.resend_api_key)
    if settings.email_provider == "smtp":
        return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)
    return False
