from __future__ import annotations

import csv
from io import StringIO
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from config import get_settings
from emailer import (
    notify_for_cta_demo_request,
    notify_for_customer_lead_request,
    notify_for_new_lead,
    send_email,
)
from lead_logic import (
    CONDITIONS,
    DEFAULT_BUSINESS_PROFILE,
    SERVICES,
    STATUSES,
    URGENCIES,
    VEHICLE_TYPES,
    priority_label,
    looks_like_email,
    slugify,
)
from storage import (
    archive_customer_form,
    business_lead_stats,
    create_business_profile,
    create_customer_form,
    create_demo_inquiry,
    create_lead,
    get_customer_form_by_slug,
    get_default_customer_form_config,
    get_form_config,
    get_business_by_slug,
    get_business_profile,
    list_customer_forms,
    list_demo_inquiries,
    list_business_profiles,
    list_leads,
    reset_sample_data,
    reset_form_config,
    restore_business_profile,
    soft_delete_business_profile,
    update_customer_form,
    update_business_profile,
    update_lead_status,
    update_owner_notes,
)


def copy_box(label: str, value: str, key: str, height: int = 150) -> None:
    st.text_area(label, value=value, height=height, key=key)


def logout_operator_session() -> None:
    st.session_state.pop("admin_authenticated", None)


def is_honeypot_filled(value: str) -> bool:
    return bool(str(value or "").strip())


def render_honeypot_field(key: str) -> str:
    st.markdown(
        """
        <style>
        div[data-testid="stTextInput"]:has(input[aria-label="Website"]) {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    return st.text_input(
        "Website",
        value="",
        key=key,
        label_visibility="collapsed",
        autocomplete="off",
    )


def inquiry_export_rows(inquiries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "submitted": inquiry.get("created_at", ""),
            "name": inquiry.get("name", ""),
            "email": inquiry.get("email", ""),
            "phone": inquiry.get("phone", ""),
            "message": inquiry.get("message", ""),
            "client_form_name": inquiry.get("customer_form_client_name") or "Legacy/default",
            "form_slug": inquiry.get("customer_form_slug") or "Unknown",
            "destination_email_used": inquiry.get("destination_email_used") or "",
        }
        for inquiry in inquiries
    ]


def inquiries_to_csv(inquiries: list[dict[str, Any]]) -> str:
    output = StringIO()
    fieldnames = [
        "submitted",
        "name",
        "email",
        "phone",
        "message",
        "client_form_name",
        "form_slug",
        "destination_email_used",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(inquiry_export_rows(inquiries))
    return output.getvalue()


def public_quote_link(settings, profile: dict[str, Any]) -> str:
    return f"{settings.app_base_url.rstrip('/')}/quote/{profile['public_slug']}"


def public_follow_up_link(settings, form_slug: str = "lead") -> str:
    base_url = settings.app_base_url.rstrip("/")
    if not settings.app_base_url_configured:
        context = getattr(st, "context", None)
        url = getattr(context, "url", "") if context else ""
        parsed = urlparse(url) if url else None
        if parsed and parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base_url}/?form={slugify(form_slug) if form_slug else 'lead'}"


def public_contact_link(settings) -> str:
    base_url = settings.app_base_url.rstrip("/")
    if not settings.app_base_url_configured:
        context = getattr(st, "context", None)
        url = getattr(context, "url", "") if context else ""
        parsed = urlparse(url) if url else None
        if parsed and parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base_url}/?contact=1"


def requested_public_slug() -> str:
    slug = st.query_params.get("slug") or st.query_params.get("business")
    if slug:
        return slugify(str(slug))
    context = getattr(st, "context", None)
    url = getattr(context, "url", "") if context else ""
    path = urlparse(url).path if url else ""
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "quote":
        return slugify(parts[1])
    return ""


def public_route_name(
    form_value: str | None,
    admin_value: str | None,
    contact_value: str | None = None,
) -> str:
    if admin_value == "1":
        return "operator"
    if contact_value == "1":
        return "contact_form"
    if form_value:
        return "customer_lead_form"
    return "homepage"


def requested_customer_form_slug() -> str:
    form_value = st.query_params.get("form")
    if not form_value or form_value == "lead":
        return ""
    return slugify(str(form_value))


def sequence_text(lead: dict[str, Any]) -> str:
    sequence = lead["follow_up_sequence"]
    return "\n\n".join(
        [
            f"Immediate reply:\n{sequence[0]}",
            f"24-hour follow-up:\n{sequence[1]}",
            f"72-hour final nudge:\n{sequence[2]}",
        ]
    )


def operator_unlocked(settings) -> bool:
    if not settings.admin_password:
        st.error("Operator area is locked.")
        st.write("Set `ADMIN_PASSWORD` before using the operator tools.")
        st.code("ADMIN_PASSWORD=choose-a-private-password", language="text")
        st.write(
            "Local: add that line to `.env`, then restart Streamlit. Hosted: add "
            "`ADMIN_PASSWORD` in Streamlit Community Cloud secrets or environment settings, then reboot the app."
        )
        return False
    if st.session_state.get("admin_authenticated"):
        return True

    with st.form("admin_login"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Open Operator Area")
    if submitted and password == settings.admin_password:
        st.session_state["admin_authenticated"] = True
        st.rerun()
    if submitted:
        st.error("Incorrect password.")
    return False


def render_form_unavailable(title: str, message: str) -> None:
    st.title(title)
    st.write(message)


def render_public_landing(settings) -> None:
    st.title("Lead Rescue")
    st.subheader("A simple follow-up link for small businesses that miss calls, messages, or quote requests.")
    st.write(
        "Lead Rescue gives small business owners one shareable form for customers who need a callback, "
        "quote, booking, or follow-up. Every request is saved so it does not disappear in DMs, voicemail, "
        "or a busy inbox."
    )

    who_col, why_col = st.columns(2)
    with who_col:
        st.markdown("**Who it is for**")
        st.write("Local service businesses that get leads from missed calls, texts, social messages, website buttons, or Google Business Profile.")
    with why_col:
        st.markdown("**What it solves**")
        st.write("Customers get one clear place to ask for help. Owners get a saved request with contact details and context for fast follow-up.")

    st.markdown("**How the demo works**")
    st.write(
        "Lead Rescue includes an editable customer-facing lead form, saved request records, email forwarding, "
        "and a protected setup area for managing form copy and destinations."
    )

    st.link_button("Request a Demo", public_contact_link(settings), type="primary")
    st.link_button("View Example Customer Form", public_follow_up_link(settings))


def render_cta_demo_request_form(settings) -> None:
    st.title("Request a Lead Rescue Demo")
    st.write("Tell me about your business and I'll follow up with next steps.")

    if st.session_state.get("cta_demo_request_submitted"):
        st.success("Thanks - your demo request was sent. I'll follow up soon.")
        for result in st.session_state.get("cta_demo_request_email_results", []):
            st.caption(result)
        if st.button("Send another demo request"):
            st.session_state.pop("cta_demo_request_submitted", None)
            st.session_state.pop("cta_demo_request_email_results", None)
            st.rerun()
        return

    with st.form("cta_demo_request_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name *")
            email = st.text_input("Email *")
            phone = st.text_input("Phone *")
        with col2:
            business_name = st.text_input("Business name *")
            business_type = st.text_input("Business type or industry")
        message = st.text_area("What do you want help with?", height=132)
        website = render_honeypot_field("cta_demo_request_website")
        submitted = st.form_submit_button("Request Demo", type="primary")

    if not submitted:
        return

    if is_honeypot_filled(website):
        st.session_state["cta_demo_request_email_results"] = []
        st.session_state["cta_demo_request_submitted"] = True
        st.rerun()

    required = {
        "Name": name,
        "Email": email,
        "Phone": phone,
        "Business name": business_name,
        "What do you want help with?": message,
    }
    missing = [label for label, value in required.items() if not value.strip()]
    if missing:
        st.error("Please complete: " + ", ".join(missing))
        return

    try:
        inquiry = create_demo_inquiry(
            settings.database_path,
            {
                "submission_type": "cta_demo_request",
                "name": name,
                "phone": phone,
                "email": email,
                "business_name": business_name,
                "service_type": business_type or "Lead Rescue demo",
                "message": message,
            },
        )
    except Exception as exc:
        st.error("We could not save your demo request. Please try again.")
        st.caption(f"Technical detail: {exc}")
        return

    st.session_state["cta_demo_request_email_results"] = notify_for_cta_demo_request(settings, inquiry)
    st.session_state["cta_demo_request_submitted"] = True
    st.rerun()


def render_customer_lead_form(settings, form_slug: str = "") -> None:
    if form_slug:
        form_config = get_customer_form_by_slug(settings.database_path, form_slug)
        if form_config is None:
            render_form_unavailable(
                "Customer form not found",
                "This customer lead form does not exist or is currently inactive. Please check the link and try again.",
            )
            return
    else:
        form_config = get_default_customer_form_config(settings.database_path)
    st.caption(form_config["business_display_name"])
    st.title(form_config["page_title"])
    if form_config.get("page_subtitle"):
        st.subheader(form_config["page_subtitle"])
    st.write(form_config["page_description"])

    section_cols = st.columns(3)
    sections = [
        ("who_header", "who_body"),
        ("problem_header", "problem_body"),
        ("process_header", "process_body"),
    ]
    for column, (header_key, body_key) in zip(section_cols, sections):
        with column:
            if form_config.get(header_key):
                st.markdown(f"**{form_config[header_key]}**")
            if form_config.get(body_key):
                st.write(form_config[body_key])
    if form_config.get("value_message"):
        st.info(form_config["value_message"])

    submitted_key = f"customer_lead_form_submitted_{form_config.get('form_slug', 'lead')}"
    results_key = f"customer_lead_email_results_{form_config.get('form_slug', 'lead')}"
    if st.session_state.get(submitted_key):
        st.success(form_config["success_title"])
        st.write(form_config["success_body"])
        for result in st.session_state.get(results_key, []):
            st.caption(result)
        if st.button("Send another request"):
            st.session_state.pop(submitted_key, None)
            st.session_state.pop(results_key, None)
            st.rerun()
        return

    with st.form("customer_lead_form"):
        if form_config.get("form_header") and form_config["form_header"] != form_config["page_title"]:
            st.markdown(f"**{form_config['form_header']}**")
        if form_config.get("form_help"):
            st.caption(form_config["form_help"])
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input(form_config["name_label"])
            phone = st.text_input(form_config["phone_label"])
            email = st.text_input(form_config["email_label"])
            business_name = st.text_input(form_config["business_label"])
        with col2:
            service_type = st.text_input(form_config["service_label"])
            message = st.text_area(
                form_config["message_label"],
                placeholder=form_config["message_placeholder"],
                height=132,
            )
        website = render_honeypot_field(f"customer_lead_website_{form_config.get('form_slug', 'lead')}")
        submitted = st.form_submit_button(form_config["cta_button_text"], type="primary")

    if not submitted:
        return

    if is_honeypot_filled(website):
        st.session_state[results_key] = []
        st.session_state[submitted_key] = True
        st.rerun()

    fields = {
        "Name": name,
        "Phone number": phone,
        "Email": email,
        "Service or request type": service_type,
        "Message": message,
    }
    missing = [label for label, value in fields.items() if not value.strip()]
    if missing:
        st.error("Please complete: " + ", ".join(missing))
        return

    destination_email = (
        form_config.get("destination_email")
        or form_config.get("destination_owner_email")
        or settings.owner_email
    ).strip()
    form_slug_for_storage = form_config.get("form_slug") or "lead"
    client_name_for_storage = (
        form_config.get("client_business_name")
        or form_config.get("business_display_name")
        or "Default"
    )

    try:
        inquiry = create_demo_inquiry(
            settings.database_path,
            {
                "name": name,
                "phone": phone,
                "email": email,
                "business_name": business_name,
                "service_type": service_type,
                "message": message,
                "submission_type": "customer_lead",
                "customer_form_id": form_config.get("id"),
                "customer_form_slug": form_slug_for_storage,
                "customer_form_client_name": client_name_for_storage,
                "destination_email_used": destination_email,
            },
        )
    except Exception as exc:
        st.error("We could not save your request. Please try again.")
        st.caption(f"Technical detail: {exc}")
        return

    if not destination_email:
        st.warning("Follow-up email not sent: this form does not have a destination email.")
        email_results = ["Follow-up email not sent: this form does not have a destination email."]
    elif not looks_like_email(destination_email):
        st.warning("Follow-up email not sent: this form destination email is invalid.")
        email_results = ["Follow-up email not sent: this form destination email is invalid."]
    else:
        email_results = notify_for_customer_lead_request(
            settings,
            inquiry,
            destination_email,
        )
    st.session_state[results_key] = email_results
    st.session_state[submitted_key] = True
    st.rerun()


def customer_form_payload_from_fields(
    client_business_name: str,
    form_slug: str,
    destination_email: str,
    business_display_name: str,
    page_title: str,
    page_subtitle: str,
    page_description: str,
    who_header: str,
    who_body: str,
    problem_header: str,
    problem_body: str,
    process_header: str,
    process_body: str,
    value_message: str,
    form_header: str,
    form_help: str,
    cta_button_text: str,
    name_label: str,
    phone_label: str,
    email_label: str,
    business_label: str,
    service_label: str,
    message_label: str,
    message_placeholder: str,
    success_title: str,
    success_body: str,
    is_active: bool,
) -> dict[str, Any]:
    return {
        "client_business_name": client_business_name.strip(),
        "form_slug": form_slug.strip() or client_business_name.strip(),
        "destination_email": destination_email.strip(),
        "business_display_name": business_display_name.strip() or client_business_name.strip(),
        "page_title": page_title.strip(),
        "page_subtitle": page_subtitle.strip(),
        "page_description": page_description.strip(),
        "who_header": who_header.strip(),
        "who_body": who_body.strip(),
        "problem_header": problem_header.strip(),
        "problem_body": problem_body.strip(),
        "process_header": process_header.strip(),
        "process_body": process_body.strip(),
        "value_message": value_message.strip(),
        "form_header": form_header.strip(),
        "form_help": form_help.strip(),
        "cta_button_text": cta_button_text.strip(),
        "name_label": name_label.strip(),
        "phone_label": phone_label.strip(),
        "email_label": email_label.strip(),
        "business_label": business_label.strip(),
        "service_label": service_label.strip(),
        "message_label": message_label.strip(),
        "message_placeholder": message_placeholder.strip(),
        "success_title": success_title.strip(),
        "success_body": success_body.strip(),
        "is_active": is_active,
    }


def render_customer_form_editor(settings, form_config: dict[str, Any] | None = None) -> None:
    is_edit = form_config is not None
    defaults = {**get_form_config(settings.database_path), **(form_config or {})}
    defaults.setdefault("client_business_name", defaults.get("business_display_name", ""))
    defaults.setdefault("form_slug", slugify(defaults.get("client_business_name", "")))
    defaults.setdefault("destination_email", defaults.get("destination_owner_email", ""))
    defaults.setdefault("is_active", True)

    with st.form(f"customer_form_record_{defaults.get('id', 'new')}"):
        st.subheader("Edit Customer-Facing Form" if is_edit else "Create Customer-Facing Form")
        meta_cols = st.columns(2)
        with meta_cols[0]:
            client_business_name = st.text_input("Client/business name *", value=defaults["client_business_name"])
            form_slug = st.text_input("Unique form slug", value=defaults["form_slug"])
            destination_email = st.text_input("Destination email *", value=defaults["destination_email"])
        with meta_cols[1]:
            business_display_name = st.text_input("Business display name", value=defaults["business_display_name"])
            is_active = st.checkbox("Active public form", value=bool(defaults.get("is_active", True)))

        page_title = st.text_input("Form title", value=defaults["page_title"])
        page_subtitle = st.text_area("Subtitle/description line", value=defaults["page_subtitle"], height=70)
        page_description = st.text_area("Intro paragraph", value=defaults["page_description"], height=90)

        section_cols = st.columns(3)
        with section_cols[0]:
            who_header = st.text_input("Section 1 header", value=defaults["who_header"])
            who_body = st.text_area("Section 1 body", value=defaults["who_body"], height=120)
        with section_cols[1]:
            problem_header = st.text_input("Section 2 header", value=defaults["problem_header"])
            problem_body = st.text_area("Section 2 body", value=defaults["problem_body"], height=120)
        with section_cols[2]:
            process_header = st.text_input("Section 3 header", value=defaults["process_header"])
            process_body = st.text_area("Section 3 body", value=defaults["process_body"], height=120)
        value_message = st.text_area("Value message", value=defaults["value_message"], height=80)

        form_header = st.text_input("Form title shown above fields", value=defaults["form_header"])
        form_help = st.text_area("Form helper text", value=defaults["form_help"], height=80)
        cta_button_text = st.text_input("CTA/button text", value=defaults["cta_button_text"])

        label_cols = st.columns(2)
        with label_cols[0]:
            name_label = st.text_input("Name field label", value=defaults["name_label"])
            phone_label = st.text_input("Phone field label", value=defaults["phone_label"])
            email_label = st.text_input("Email field label", value=defaults["email_label"])
        with label_cols[1]:
            business_label = st.text_input("Company/business field label", value=defaults["business_label"])
            service_label = st.text_input("Service/request type field label", value=defaults["service_label"])
            message_label = st.text_input("Message field label", value=defaults["message_label"])
            message_placeholder = st.text_input("Message placeholder", value=defaults["message_placeholder"])

        success_title = st.text_input("Thank-you message title", value=defaults["success_title"])
        success_body = st.text_area("Thank-you message body", value=defaults["success_body"], height=80)
        saved = st.form_submit_button("Save Customer Form", type="primary")

    if not saved:
        return

    payload = customer_form_payload_from_fields(
        client_business_name,
        form_slug,
        destination_email,
        business_display_name,
        page_title,
        page_subtitle,
        page_description,
        who_header,
        who_body,
        problem_header,
        problem_body,
        process_header,
        process_body,
        value_message,
        form_header,
        form_help,
        cta_button_text,
        name_label,
        phone_label,
        email_label,
        business_label,
        service_label,
        message_label,
        message_placeholder,
        success_title,
        success_body,
        is_active,
    )
    try:
        if is_edit:
            saved_form = update_customer_form(settings.database_path, int(form_config["id"]), payload)
        else:
            saved_form = create_customer_form(settings.database_path, payload)
        st.session_state["selected_customer_form_id"] = saved_form["id"]
        st.success(f"Saved {saved_form['client_business_name']} with slug `{saved_form['form_slug']}`.")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


def render_public_form(settings, profile: dict[str, Any] | None) -> None:
    if profile is None:
        render_form_unavailable(
            "Quote form not found",
            "This quote request form does not exist. Please check the link and try again.",
        )
        return
    if profile.get("deleted_at") or not profile["is_active"]:
        render_form_unavailable(
            "Quote form unavailable",
            "This quote request form is currently unavailable.",
        )
        return

    st.title(f"Request a Callback or Quote from {profile['business_name']}")
    st.write(
        "Tell us what you need, how to reach you, and the best time to follow up. "
        "Your request will be saved and reviewed so the business can respond with the right next step."
    )
    st.markdown(f"**Service area:** {profile['service_area']}")
    if profile.get("business_hours"):
        st.caption(f"Business hours: {profile['business_hours']}")
    if profile.get("services_offered"):
        st.info(f"Services offered: {profile['services_offered']}")
    if profile.get("starting_prices"):
        st.info(profile["starting_prices"])
    if profile.get("booking_link"):
        st.caption("After you submit, you can also open the business booking link if one is available.")

    session_key = f"submitted_lead_{profile['id']}"
    if st.session_state.get(session_key):
        lead = st.session_state[session_key]
        st.success("Your request has been received.")
        st.write(lead["customer_confirmation"])
        if profile.get("booking_link"):
            st.link_button("Open Booking Link", profile["booking_link"])
        if st.button("Submit another request"):
            st.session_state.pop(session_key, None)
            st.rerun()
        return

    with st.form(f"public_lead_form_{profile['id']}"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Customer name *")
            phone = st.text_input("Phone number *")
            email = st.text_input("Email address (optional)")
            vehicle_type = st.selectbox("Vehicle type", VEHICLE_TYPES)
            vehicle_condition = st.selectbox("Vehicle condition", CONDITIONS, index=1)
        with col2:
            desired_service = st.selectbox("Desired service", SERVICES, index=2)
            location = st.text_input("Location or service area *")
            preferred_time = st.text_input("Preferred day/time *")
            urgency = st.selectbox("Urgency", URGENCIES)
            can_send_photos = st.radio("Can send photos?", ["yes", "no"], horizontal=True)
        notes = st.text_area("Notes or special concerns")
        submitted = st.form_submit_button("Request a Follow-Up", type="primary")

    if not submitted:
        return

    missing = [
        label
        for label, value in {
            "Customer name": name,
            "Phone number": phone,
            "Location or service area": location,
            "Preferred day/time": preferred_time,
        }.items()
        if not value.strip()
    ]
    if missing:
        st.error("Please complete: " + ", ".join(missing))
        return

    try:
        lead = create_lead(
            settings.database_path,
            profile["id"],
            {
                "name": name.strip(),
                "phone": phone.strip(),
                "email": email.strip(),
                "vehicle_type": vehicle_type,
                "vehicle_condition": vehicle_condition,
                "desired_service": desired_service,
                "location": location.strip(),
                "preferred_time": preferred_time.strip(),
                "urgency": urgency,
                "can_send_photos": can_send_photos,
                "notes": notes.strip(),
            },
        )
    except Exception as exc:
        st.error("We could not submit your request. Please check the form and try again.")
        st.caption(f"Technical detail: {exc}")
        return
    st.session_state[session_key] = lead
    st.session_state["email_results"] = notify_for_new_lead(settings, lead, profile)
    st.rerun()


def render_profile_form(settings, profile: dict[str, Any] | None = None) -> None:
    is_edit = profile is not None
    defaults = {**DEFAULT_BUSINESS_PROFILE, **(profile or {})}
    title = "Edit Business Profile" if is_edit else "Create Business Profile"
    with st.form(f"profile_form_{defaults.get('id', 'new')}"):
        st.subheader(title)
        col1, col2 = st.columns(2)
        with col1:
            business_name = st.text_input("Business name", value=defaults["business_name"])
            suggested_slug = slugify(business_name) if not defaults.get("public_slug") else defaults["public_slug"]
            public_slug = st.text_input("Public slug", value=suggested_slug)
            owner_name = st.text_input("Owner name", value=defaults["owner_name"])
            owner_email = st.text_input("Owner email", value=defaults["owner_email"])
            phone = st.text_input("Business phone", value=defaults["phone"])
            booking_link = st.text_input("Booking link", value=defaults["booking_link"])
            is_active = st.checkbox("Active public form", value=bool(defaults.get("is_active", True)))
        with col2:
            service_area = st.text_area("Service area", value=defaults["service_area"], height=90)
            business_hours = st.text_area("Business hours", value=defaults["business_hours"], height=90)
            preferred_tone = st.text_area("Preferred tone", value=defaults["preferred_tone"], height=90)
        services_offered = st.text_area("Services offered", value=defaults["services_offered"], height=100)
        starting_prices = st.text_area("Starting prices", value=defaults["starting_prices"], height=100)
        photo_request_instructions = st.text_area(
            "Photo request instructions",
            value=defaults["photo_request_instructions"],
            height=100,
        )
        submitted = st.form_submit_button("Save Profile", type="primary")

    if submitted:
        if not business_name.strip():
            st.error("Business name is required.")
            return
        if not (public_slug.strip() or business_name.strip()):
            st.error("Public slug is required.")
            return
        if not owner_email.strip():
            st.error("Owner email is required for lead routing.")
            return
        payload = {
            "business_name": business_name.strip(),
            "public_slug": public_slug.strip() or business_name.strip(),
            "owner_name": owner_name.strip(),
            "owner_email": owner_email.strip(),
            "phone": phone.strip(),
            "service_area": service_area.strip(),
            "booking_link": booking_link.strip(),
            "business_hours": business_hours.strip(),
            "services_offered": services_offered.strip(),
            "starting_prices": starting_prices.strip(),
            "preferred_tone": preferred_tone.strip(),
            "photo_request_instructions": photo_request_instructions.strip(),
            "is_active": is_active,
        }
        try:
            if is_edit:
                saved = update_business_profile(settings.database_path, profile["id"], payload)
            else:
                saved = create_business_profile(settings.database_path, payload)
            st.success(f"Saved {saved['business_name']} with slug `{saved['public_slug']}`.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def render_business_manager(settings) -> None:
    st.title("Business Profile Manager")
    st.write("Create mobile detailer profiles, copy public quote links, and route leads by business.")
    if not operator_unlocked(settings):
        return

    if st.button("Reset sample businesses and leads"):
        reset_sample_data(settings.database_path)
        st.rerun()

    profiles = list_business_profiles(settings.database_path)
    deleted_profiles = list_business_profiles(settings.database_path, only_deleted=True)
    stats = business_lead_stats(settings.database_path)
    rows = []
    for profile in profiles:
        profile_stats = stats.get(profile["id"], {"total": 0, "new": 0, "booked": 0, "lost": 0})
        rows.append(
            {
                "Business": profile["business_name"],
                "Slug": profile["public_slug"],
                "Owner Email": profile["owner_email"],
                "Active": profile["is_active"],
                "Created": profile["created_at"],
                "Updated": profile["updated_at"],
                "Deleted": profile.get("deleted_at") or "",
                "Total Leads": profile_stats["total"],
                "New": profile_stats["new"],
                "Booked": profile_stats["booked"],
                "Lost": profile_stats["lost"],
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No business profiles yet. Create your first profile to generate a public quote form link.")

    if deleted_profiles:
        st.subheader("Recently Deleted")
        deleted_rows = [
            {
                "Business": profile["business_name"],
                "Slug": profile["public_slug"],
                "Owner Email": profile["owner_email"],
                "Deleted": profile.get("deleted_at") or "",
            }
            for profile in deleted_profiles
        ]
        st.dataframe(deleted_rows, use_container_width=True, hide_index=True)
        restore_id = st.selectbox(
            "Restore deleted profile",
            [profile["id"] for profile in deleted_profiles],
            format_func=lambda profile_id: next(
                f"{profile['business_name']} ({profile['public_slug']})"
                for profile in deleted_profiles
                if profile["id"] == profile_id
            ),
            key="restore_profile_id",
        )
        if st.button("Restore selected profile"):
            try:
                restored = restore_business_profile(settings.database_path, restore_id)
                st.success(f"Restored {restored['business_name']}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    if not profiles:
        render_profile_form(settings)
        return

    selected = st.selectbox(
        "Edit existing profile",
        [profile["id"] for profile in profiles],
        format_func=lambda profile_id: next(
            f"{profile['business_name']} ({profile['public_slug']})"
            for profile in profiles
            if profile["id"] == profile_id
        ),
    )
    selected_profile = next(profile for profile in profiles if profile["id"] == selected)
    link = public_quote_link(settings, selected_profile)
    st.markdown("**Public Quote Form Link**")
    st.text_input("Copy public quote link", value=link, key=f"profile_link_{selected}")
    st.link_button("Open form", link)
    copy_box(
        "Owner handoff message",
        (
            f"Your quote request form is ready: {link}. Add this to your Instagram bio, "
            "Facebook page, Google Business Profile, or website so customers can request "
            "mobile detailing quotes."
        ),
        f"handoff_{selected}",
        120,
    )
    st.caption("Where to use this link: Instagram bio, Facebook page, Google Business Profile, website, text replies, and later QR codes.")

    if st.button("Delete selected profile", type="secondary"):
        soft_delete_business_profile(settings.database_path, selected)
        st.session_state["last_deleted_profile_id"] = selected
        st.warning(f"Deleted {selected_profile['business_name']}. Existing leads were preserved.")
        st.rerun()

    last_deleted = st.session_state.get("last_deleted_profile_id")
    if last_deleted:
        if st.button("Undo last profile delete"):
            try:
                restored = restore_business_profile(settings.database_path, int(last_deleted))
                st.session_state.pop("last_deleted_profile_id", None)
                st.success(f"Restored {restored['business_name']}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    edit_tab, create_tab = st.tabs(["Edit Selected Profile", "Create New Profile"])
    with edit_tab:
        render_profile_form(settings, selected_profile)
    with create_tab:
        render_profile_form(settings)


def render_lead_details(settings, lead: dict[str, Any]) -> None:
    business = get_business_profile(settings.database_path, int(lead["business_id"]))
    if business is None:
        st.error("Associated business profile was not found.")
        return
    st.subheader(f"{lead['name']} - {lead['desired_service']}")
    st.caption(f"Business: {business['business_name']}")
    if business.get("booking_link"):
        st.link_button("Open Booking Link", business["booking_link"])

    cols = st.columns(4)
    cols[0].metric("Lead Priority", f"{lead['lead_score']}/100", priority_label(lead["lead_score"]))
    cols[1].metric("Urgency", lead["urgency"])
    cols[2].metric("Status", lead["status"])
    cols[3].metric("Photos", lead["can_send_photos"])

    st.markdown("**Next Best Action**")
    st.info(lead["next_action"])
    copy_box("Suggested Reply", lead["suggested_next_message"], f"suggested_{lead['id']}", 130)

    control_cols = st.columns([1, 2])
    with control_cols[0]:
        status = st.selectbox(
            "Update status",
            STATUSES,
            index=STATUSES.index(lead["status"]) if lead["status"] in STATUSES else 0,
            key=f"status_{lead['id']}",
        )
        if status != lead["status"]:
            update_lead_status(settings.database_path, lead["id"], status)
            st.success("Lead status updated.")
            st.rerun()
    with control_cols[1]:
        owner_notes = st.text_area(
            "Owner notes",
            value=lead.get("owner_notes", ""),
            height=120,
            key=f"owner_notes_{lead['id']}",
        )
        if st.button("Save owner notes", key=f"save_notes_{lead['id']}"):
            update_owner_notes(settings.database_path, lead["id"], owner_notes)
            st.success("Owner notes saved.")
            st.rerun()

    info_cols = st.columns(2)
    with info_cols[0]:
        st.markdown("**Customer Details**")
        st.write(f"Created: {lead['created_at']}")
        st.write(f"Name: {lead['name']}")
        st.write(f"Phone: {lead['phone']}")
        st.write(f"Email: {lead['email'] or 'Not provided'}")
        st.write(f"Location: {lead['location']}")
        st.write(f"Preferred day/time: {lead['preferred_time']}")
    with info_cols[1]:
        st.markdown("**Vehicle and Request**")
        st.write(f"Vehicle: {lead['vehicle_type']}")
        st.write(f"Condition: {lead['vehicle_condition']}")
        st.write(f"Service: {lead['desired_service']}")
        st.write(f"Urgency: {lead['urgency']}")
        st.write(f"Can send photos: {lead['can_send_photos']}")
        st.write(f"Notes: {lead['notes'] or 'None'}")

    tab1, tab2, tab3 = st.tabs(["Owner Summary", "Customer Confirmation", "Follow-Up Sequence"])
    with tab1:
        copy_box("Copy owner summary", lead["owner_summary"], f"summary_{lead['id']}", 260)
    with tab2:
        copy_box("Copy customer confirmation", lead["customer_confirmation"], f"confirmation_{lead['id']}", 180)
    with tab3:
        copy_box("Copy follow-up sequence", sequence_text(lead), f"sequence_{lead['id']}", 340)


def render_operator_dashboard(settings) -> None:
    st.title("Detailing Leads")
    st.write("Filter leads by business, review next actions, copy replies, and update status.")
    if not operator_unlocked(settings):
        return

    profiles = list_business_profiles(settings.database_path)
    if not profiles:
        st.info("No business profiles yet. Create a business profile first.")
        return
    profile_options = [0] + [profile["id"] for profile in profiles]
    selected_business_id = st.selectbox(
        "Filter by business",
        profile_options,
        format_func=lambda profile_id: "All businesses"
        if profile_id == 0
        else next(profile["business_name"] for profile in profiles if profile["id"] == profile_id),
    )
    leads = list_leads(settings.database_path, None if selected_business_id == 0 else selected_business_id)
    if not leads:
        st.info("No leads yet for this view.")
        return

    rows = [
        {
            "Business": lead["business_name"],
            "Created": lead["created_at"],
            "Name": lead["name"],
            "Phone": lead["phone"],
            "Vehicle": lead["vehicle_type"],
            "Service": lead["desired_service"],
            "Urgency": lead["urgency"],
            "Score": lead["lead_score"],
            "Status": lead["status"],
            "Next Action": lead["next_action"],
        }
        for lead in leads
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    selected_lead_id = st.selectbox(
        "View lead details",
        [lead["id"] for lead in leads],
        format_func=lambda lead_id: next(
            f"{lead['business_name']} - {lead['name']} - {lead['desired_service']}"
            for lead in leads
            if lead["id"] == lead_id
        ),
    )
    render_lead_details(settings, next(lead for lead in leads if lead["id"] == selected_lead_id))


def render_setup_checklist(settings) -> None:
    st.title("Operator Setup Checklist")
    if not operator_unlocked(settings):
        return

    profiles = list_business_profiles(settings.database_path)
    if not profiles:
        st.info("No business profiles yet. Create your first profile in Business Profiles.")
        return
    stats = business_lead_stats(settings.database_path)
    selected = st.selectbox(
        "Business",
        [profile["id"] for profile in profiles],
        format_func=lambda profile_id: next(profile["business_name"] for profile in profiles if profile["id"] == profile_id),
        key="checklist_business",
    )
    profile = next(profile for profile in profiles if profile["id"] == selected)
    profile_stats = stats.get(selected, {"total": 0})
    link = public_quote_link(settings, profile)

    checklist = [
        ("Create business profile", bool(profile)),
        ("Add owner email", bool(profile.get("owner_email"))),
        ("Add service area", bool(profile.get("service_area"))),
        ("Add services offered", bool(profile.get("services_offered"))),
        ("Add starting prices if available", bool(profile.get("starting_prices"))),
        ("Add booking link if available", bool(profile.get("booking_link"))),
        ("Review generated public quote link", bool(link)),
        ("Submit test lead through public quote link", profile_stats["total"] > 0),
        ("Confirm lead appears under correct business", profile_stats["total"] > 0),
        ("Confirm owner notification routes to profile email if email is configured", bool(profile.get("owner_email")) and settings.email_provider != "disabled"),
        ("Copy public quote link", bool(link)),
        ("Help business put link in Instagram bio, Facebook page, Google Business Profile, or website", False),
    ]
    for index, (label, done) in enumerate(checklist, start=1):
        st.checkbox(f"{index}. {label}", value=done, disabled=True, key=f"operator_check_{index}")

    st.markdown("**Public Quote Link**")
    st.text_input("Copy public quote link", value=link, key="checklist_link")
    st.link_button("Open form", link)
    copy_box(
        "Owner handoff message",
        (
            f"Your quote request form is ready: {link}. Add this to your Instagram bio, "
            "Facebook page, Google Business Profile, or website so customers can request "
            "mobile detailing quotes."
        ),
        "checklist_handoff",
        120,
    )


def render_lead_form_setup(settings) -> None:
    st.title("Customer Lead Form Setup")
    st.write("Create, edit, and manage client-specific customer lead forms.")
    if not operator_unlocked(settings):
        return

    customer_forms = list_customer_forms(settings.database_path)
    selected_form = None
    if customer_forms:
        selected_id = st.session_state.get("selected_customer_form_id", customer_forms[0]["id"])
        if selected_id not in {form["id"] for form in customer_forms}:
            selected_id = customer_forms[0]["id"]
        selected_form = next(form for form in customer_forms if form["id"] == selected_id)
        public_link = public_follow_up_link(settings, selected_form["form_slug"])

        rows = [
            {
                "Client/business": form["client_business_name"],
                "Slug": form["form_slug"],
                "Shareable URL": public_follow_up_link(settings, form["form_slug"]),
                "Destination email": form["destination_email"],
                "Active": form["is_active"],
                "Last updated": form["updated_at"],
            }
            for form in customer_forms
        ]
        st.subheader("Saved Customer Lead Forms")
        st.dataframe(rows, use_container_width=True, hide_index=True)

        selected_id = st.selectbox(
            "Edit saved form",
            [form["id"] for form in customer_forms],
            index=[form["id"] for form in customer_forms].index(selected_form["id"]),
            format_func=lambda form_id: next(
                f"{form['client_business_name']} ({form['form_slug']})"
                for form in customer_forms
                if form["id"] == form_id
            ),
        )
        st.session_state["selected_customer_form_id"] = selected_id
        selected_form = next(form for form in customer_forms if form["id"] == selected_id)
        public_link = public_follow_up_link(settings, selected_form["form_slug"])

        st.markdown("**Shareable Customer Form Link**")
        st.text_input("Copy shareable form link", value=public_link, key=f"public_follow_up_link_{selected_form['id']}")
        st.link_button("Open customer form", public_link)
        if not settings.app_base_url_configured:
            st.warning("APP_BASE_URL is not set. Set it before deploying so hosted share links use the correct public URL.")

        copy_box(
            "Client posting copy",
            (
                f"Website button: Request a Follow-Up\n\n"
                f"Instagram bio: Need service or a callback? {public_link}\n\n"
                f"Facebook or Google Business Profile: Need service, a quote, booking help, or a follow-up? "
                f"Send your details here: {public_link}\n\n"
                f"Text reply: Thanks for reaching out. Please send your details here so we can follow up: {public_link}"
            ),
            f"public_form_posting_copy_{selected_form['id']}",
            180,
        )

        if st.button("Archive selected form", type="secondary"):
            archived = archive_customer_form(settings.database_path, selected_form["id"])
            st.success(f"Archived {archived['client_business_name']}.")
            st.rerun()
    else:
        st.info("No saved customer lead forms yet. Create one below.")

    edit_tab, create_tab = st.tabs(["Edit Selected Form", "Create New Form"])
    with edit_tab:
        if selected_form:
            render_customer_form_editor(settings, selected_form)
        else:
            st.info("Create a customer form first.")
    with create_tab:
        render_customer_form_editor(settings)

    st.subheader("Email Test")
    test_recipient = (selected_form.get("destination_email", "") if selected_form else "").strip()
    st.write(f"Current recipient: `{test_recipient or 'not configured'}`")
    if st.button("Send Test Email"):
        if not test_recipient:
            st.error("Set the selected form destination email before sending a test.")
        elif not looks_like_email(test_recipient):
            st.error("The selected form destination email is invalid.")
        else:
            sent, message = send_email(
                settings,
                test_recipient,
                "Lead Rescue Email Test",
                "This is a test email from your Lead Rescue demo.",
            )
            if sent:
                st.success(message)
            else:
                st.warning(message)

    with st.expander("Legacy default form fallback"):
        st.write("The old `?form=lead` link still loads a default customer-facing form for compatibility.")
        if st.button("Reset legacy default customer lead form copy"):
            reset_form_config(settings.database_path)
            st.success("Legacy default customer lead form settings reset.")
            st.rerun()

    filter_slug = None
    if customer_forms:
        filter_options = ["All forms"] + [form["form_slug"] for form in customer_forms]
        selected_filter = st.selectbox("Filter recent requests by form", filter_options)
        if selected_filter != "All forms":
            filter_slug = selected_filter

    recent = list_demo_inquiries(settings.database_path, limit=10, customer_form_slug=filter_slug)
    st.subheader("Recent Customer Follow-Up Requests")
    if recent:
        recent_rows = [
            {
                "Submitted": inquiry["created_at"],
                "Client/form": inquiry.get("customer_form_client_name") or "Legacy/default",
                "Form slug": inquiry.get("customer_form_slug") or "Unknown",
                "Destination email used": inquiry.get("destination_email_used") or "",
                "Name": inquiry["name"],
                "Phone": inquiry["phone"],
                "Email": inquiry["email"],
                "Service/request": inquiry["service_type"],
                "Message": inquiry["message"],
            }
            for inquiry in recent
        ]
        st.dataframe(recent_rows, use_container_width=True, hide_index=True)
        st.download_button(
            "Export recent requests CSV",
            data=inquiries_to_csv(recent),
            file_name="lead-rescue-recent-requests.csv",
            mime="text/csv",
        )
    else:
        st.info("No follow-up requests submitted yet.")


def render_sidebar(settings) -> str:
    with st.sidebar:
        st.header("Lead Rescue AI")
        st.caption("Operator-managed lead form generator")
        if st.session_state.get("admin_authenticated"):
            if st.button("Log out Operator"):
                logout_operator_session()
                st.rerun()
        page = st.radio(
            "Operator View",
            ["Customer Lead Form Setup", "Business Profiles", "Detailing Leads", "Pilot Setup Checklist"],
        )
        st.header("Email")
        if settings.email_provider == "disabled":
            st.caption("Email sending is disabled.")
        else:
            st.caption(f"Provider: {settings.email_provider}")
        results = st.session_state.get("email_results")
        if results:
            st.header("Last Email Attempt")
            for result in results:
                st.caption(result)
    return page


def main() -> None:
    st.set_page_config(page_title="Lead Rescue AI", page_icon="LR", layout="wide")
    settings = get_settings()
    slug = requested_public_slug()
    if slug:
        render_public_form(settings, get_business_by_slug(settings.database_path, slug))
        return

    route = public_route_name(
        st.query_params.get("form"),
        st.query_params.get("admin"),
        st.query_params.get("contact"),
    )
    if route == "customer_lead_form":
        render_customer_lead_form(settings, requested_customer_form_slug())
        return
    if route == "contact_form":
        render_cta_demo_request_form(settings)
        return
    if route == "homepage":
        render_public_landing(settings)
        return

    page = render_sidebar(settings)
    if page == "Customer Lead Form Setup":
        render_lead_form_setup(settings)
    elif page == "Business Profiles":
        render_business_manager(settings)
    elif page == "Detailing Leads":
        render_operator_dashboard(settings)
    else:
        render_setup_checklist(settings)


if __name__ == "__main__":
    main()
