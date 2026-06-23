import sqlite3

import pytest

from storage import (
    archive_customer_form,
    create_business_profile,
    create_customer_form,
    create_demo_inquiry,
    create_lead,
    get_customer_form_by_slug,
    get_default_customer_form_config,
    get_form_config,
    get_business_by_slug,
    get_business_profile,
    get_lead,
    list_demo_inquiries,
    list_customer_forms,
    list_business_profiles,
    list_leads,
    reset_sample_data,
    reset_form_config,
    restore_business_profile,
    soft_delete_business_profile,
    unique_customer_form_slug,
    update_customer_form,
    update_form_config,
    update_business_profile,
    update_lead_status,
    update_owner_notes,
)


def lead_input():
    return {
        "name": "Taylor Smith",
        "phone": "555-444-1212",
        "email": "taylor@example.com",
        "vehicle_type": "sedan",
        "vehicle_condition": "moderate",
        "desired_service": "full detail",
        "location": "Austin",
        "preferred_time": "Tuesday morning",
        "urgency": "this week",
        "can_send_photos": "yes",
        "notes": "Needs trunk cleaned.",
    }


def test_create_demo_inquiry_requires_contact_and_business_details(tmp_path):
    db_path = str(tmp_path / "demo_inquiries.db")

    inquiry = create_demo_inquiry(
        db_path,
        {
            "name": "Morgan Owner",
            "phone": "555-200-3030",
            "email": "morgan@example.com",
            "business_name": "Morgan Mobile Detail",
            "service_type": "Callback request",
            "message": "We need one quote link for Facebook and our website.",
        },
    )

    assert inquiry["id"] > 0
    assert inquiry["submission_type"] == "customer_lead"
    assert inquiry["business_name"] == "Morgan Mobile Detail"
    assert inquiry["service_type"] == "Callback request"
    assert list_demo_inquiries(db_path, limit=5)[0]["id"] == inquiry["id"]

    with pytest.raises(ValueError):
        create_demo_inquiry(
            db_path,
            {
                "name": "",
                "phone": "555-200-3030",
                "email": "morgan@example.com",
                "business_name": "Morgan Mobile Detail",
                "service_type": "Callback request",
                "message": "Missing name should be rejected.",
            },
        )
    with pytest.raises(ValueError):
        create_demo_inquiry(
            db_path,
            {
                "name": "Morgan Owner",
                "phone": "555-200-3030",
                "email": "not-an-email",
                "business_name": "Morgan Mobile Detail",
                "service_type": "Callback request",
                "message": "Bad email should be rejected.",
            },
        )


def test_create_demo_inquiry_allows_optional_company_name(tmp_path):
    db_path = str(tmp_path / "customer_inquiries.db")

    inquiry = create_demo_inquiry(
        db_path,
        {
            "name": "Taylor Customer",
            "phone": "555-101-2020",
            "email": "taylor@example.com",
            "business_name": "",
            "service_type": "Estimate",
            "message": "Please call me about service this week.",
        },
    )

    assert inquiry["business_name"] == ""
    assert inquiry["service_type"] == "Estimate"


def test_demo_request_and_customer_lead_submissions_are_typed(tmp_path):
    db_path = str(tmp_path / "typed_inquiries.db")

    demo_request = create_demo_inquiry(
        db_path,
        {
            "submission_type": "cta_demo_request",
            "name": "Morgan Owner",
            "phone": "555-200-3030",
            "email": "morgan@example.com",
            "business_name": "Morgan Mobile Detail",
            "service_type": "Mobile detailing",
            "message": "I want Lead Rescue for my business.",
        },
    )
    customer_lead = create_demo_inquiry(
        db_path,
        {
            "submission_type": "customer_lead",
            "name": "Taylor Customer",
            "phone": "555-101-2020",
            "email": "taylor@example.com",
            "business_name": "",
            "service_type": "Estimate",
            "message": "Please call me about service.",
        },
    )

    assert demo_request["submission_type"] == "cta_demo_request"
    assert customer_lead["submission_type"] == "customer_lead"
    assert {row["submission_type"] for row in list_demo_inquiries(db_path, limit=5)} == {
        "cta_demo_request",
        "customer_lead",
    }


def test_customer_form_submission_stores_form_attribution_and_destination(tmp_path):
    db_path = str(tmp_path / "attributed_inquiries.db")
    form = create_customer_form(db_path, customer_form_input())

    inquiry = create_demo_inquiry(
        db_path,
        {
            "submission_type": "customer_lead",
            "name": "Taylor Customer",
            "phone": "555-101-2020",
            "email": "taylor@example.com",
            "business_name": "",
            "service_type": "Estimate",
            "message": "Please call me about service.",
            "customer_form_id": form["id"],
            "customer_form_slug": form["form_slug"],
            "customer_form_client_name": form["client_business_name"],
            "destination_email_used": form["destination_email"],
        },
    )

    saved = list_demo_inquiries(db_path, limit=5)[0]

    assert inquiry["customer_form_id"] == form["id"]
    assert saved["customer_form_id"] == form["id"]
    assert saved["customer_form_slug"] == "abc-plumbing"
    assert saved["customer_form_client_name"] == "ABC Plumbing"
    assert saved["destination_email_used"] == "abc@example.com"


def test_inquiry_preserves_historical_destination_after_form_edit(tmp_path):
    db_path = str(tmp_path / "historical_destination.db")
    form = create_customer_form(db_path, customer_form_input())

    create_demo_inquiry(
        db_path,
        {
            "submission_type": "customer_lead",
            "name": "Taylor Customer",
            "phone": "555-101-2020",
            "email": "taylor@example.com",
            "business_name": "",
            "service_type": "Estimate",
            "message": "Please call me.",
            "customer_form_id": form["id"],
            "customer_form_slug": form["form_slug"],
            "customer_form_client_name": form["client_business_name"],
            "destination_email_used": "abc@example.com",
        },
    )
    update_customer_form(db_path, form["id"], {"destination_email": "new-dispatch@example.com"})

    saved = list_demo_inquiries(db_path, limit=5)[0]

    assert saved["destination_email_used"] == "abc@example.com"


def test_legacy_default_inquiry_and_old_schema_rows_are_null_safe(tmp_path):
    db_path = str(tmp_path / "legacy_inquiries.db")

    legacy = create_demo_inquiry(
        db_path,
        {
            "submission_type": "customer_lead",
            "name": "Legacy Customer",
            "phone": "555-000-1111",
            "email": "legacy@example.com",
            "business_name": "",
            "service_type": "Callback",
            "message": "Old default form submission.",
            "customer_form_slug": "lead",
            "customer_form_client_name": "Default",
            "destination_email_used": "owner@example.com",
        },
    )

    assert legacy["customer_form_id"] is None
    assert legacy["customer_form_slug"] == "lead"
    assert legacy["customer_form_client_name"] == "Default"
    assert legacy["destination_email_used"] == "owner@example.com"

    old_db_path = str(tmp_path / "old_schema.db")
    with sqlite3.connect(old_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE demo_inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                submission_type TEXT NOT NULL DEFAULT 'customer_lead',
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                business_name TEXT NOT NULL,
                service_type TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO demo_inquiries (
                created_at, submission_type, name, phone, email, business_name, service_type, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-22T18:00:00+00:00",
                "customer_lead",
                "Old Customer",
                "555",
                "old@example.com",
                "",
                "Callback",
                "Before attribution columns.",
            ),
        )
        conn.commit()

    old_rows = list_demo_inquiries(old_db_path, limit=5)

    assert old_rows[0]["customer_form_id"] is None
    assert old_rows[0]["customer_form_slug"] is None
    assert old_rows[0]["customer_form_client_name"] is None
    assert old_rows[0]["destination_email_used"] is None


def test_list_demo_inquiries_can_filter_by_customer_form_slug(tmp_path):
    db_path = str(tmp_path / "filter_inquiries.db")
    first = create_customer_form(db_path, customer_form_input())
    second = create_customer_form(
        db_path,
        customer_form_input(
            client_business_name="Smith Roofing",
            form_slug="smith-roofing",
            destination_email="smith@example.com",
        ),
    )
    for form in [first, second]:
        create_demo_inquiry(
            db_path,
            {
                "submission_type": "customer_lead",
                "name": form["client_business_name"],
                "phone": "555-101-2020",
                "email": "lead@example.com",
                "business_name": "",
                "service_type": "Estimate",
                "message": "Please call me.",
                "customer_form_id": form["id"],
                "customer_form_slug": form["form_slug"],
                "customer_form_client_name": form["client_business_name"],
                "destination_email_used": form["destination_email"],
            },
        )

    filtered = list_demo_inquiries(db_path, limit=5, customer_form_slug="smith-roofing")

    assert len(filtered) == 1
    assert filtered[0]["customer_form_id"] == second["id"]
    assert filtered[0]["customer_form_slug"] == "smith-roofing"


def test_form_config_defaults_update_and_reset(tmp_path):
    db_path = str(tmp_path / "form_config.db")

    defaults = get_form_config(db_path)
    assert defaults["business_display_name"] == "Your Business"
    assert defaults["page_title"] == "Request a Follow-Up"
    assert defaults["page_description"] == "Tell us what you need and someone from our team will get back to you soon."
    assert defaults["cta_button_text"] == "Send Request"
    assert defaults["success_body"] == "Someone from our team will follow up soon."
    assert "Lead Rescue" not in defaults["page_title"]
    assert "Lead Rescue" not in defaults["page_description"]

    updated = update_form_config(
        db_path,
        {
            "page_title": "Callback Rescue",
            "cta_button_text": "Get a Callback",
            "name_label": "",
            "unknown": "ignored",
        },
    )

    assert updated["page_title"] == "Callback Rescue"
    assert updated["cta_button_text"] == "Get a Callback"
    assert updated["name_label"] == defaults["name_label"]
    assert "unknown" not in updated

    reset = reset_form_config(db_path)
    assert reset["page_title"] == "Request a Follow-Up"
    assert reset["cta_button_text"] == "Send Request"


def customer_form_input(**overrides):
    data = {
        "client_business_name": "ABC Plumbing",
        "form_slug": "",
        "destination_email": "abc@example.com",
        "business_display_name": "ABC Plumbing",
        "page_title": "Need Plumbing Help?",
        "page_subtitle": "Fast callbacks for urgent jobs.",
        "page_description": "Tell us what is going on and we will follow up.",
        "form_header": "Request plumbing help",
        "cta_button_text": "Send Plumbing Request",
        "success_title": "Request received",
        "success_body": "ABC Plumbing will follow up soon.",
    }
    data.update(overrides)
    return data


def test_create_customer_form_generates_unique_slug_and_loads_by_slug(tmp_path):
    db_path = str(tmp_path / "customer_forms.db")

    form = create_customer_form(db_path, customer_form_input())
    second = create_customer_form(
        db_path,
        customer_form_input(
            client_business_name="ABC Plumbing",
            destination_email="abc2@example.com",
        ),
    )

    assert form["id"] > 0
    assert form["form_slug"] == "abc-plumbing"
    assert second["form_slug"] == "abc-plumbing-2"
    assert form["destination_email"] == "abc@example.com"
    assert get_customer_form_by_slug(db_path, "abc-plumbing")["page_title"] == "Need Plumbing Help?"
    assert unique_customer_form_slug(db_path, "ABC Plumbing") == "abc-plumbing-3"


def test_update_customer_form_preserves_record_and_blocks_duplicate_slug(tmp_path):
    db_path = str(tmp_path / "customer_form_update.db")
    first = create_customer_form(db_path, customer_form_input())
    second = create_customer_form(
        db_path,
        customer_form_input(
            client_business_name="Smith Roofing",
            form_slug="smith-roofing",
            destination_email="smith@example.com",
            page_title="Roof repair request",
        ),
    )

    updated = update_customer_form(
        db_path,
        first["id"],
        {
            "form_slug": "abc-plumbing-pro",
            "destination_email": "dispatch@example.com",
            "page_title": "Updated Plumbing Help",
            "cta_button_text": "Get Help",
        },
    )

    assert updated["id"] == first["id"]
    assert updated["form_slug"] == "abc-plumbing-pro"
    assert updated["destination_email"] == "dispatch@example.com"
    assert updated["page_title"] == "Updated Plumbing Help"
    assert get_customer_form_by_slug(db_path, "abc-plumbing-pro")["cta_button_text"] == "Get Help"

    with pytest.raises(ValueError):
        update_customer_form(db_path, second["id"], {"form_slug": "abc-plumbing-pro"})


def test_customer_form_validation_and_inactive_lookup(tmp_path):
    db_path = str(tmp_path / "customer_form_validation.db")

    with pytest.raises(ValueError):
        create_customer_form(db_path, customer_form_input(client_business_name=""))
    with pytest.raises(ValueError):
        create_customer_form(db_path, customer_form_input(destination_email="not-an-email"))

    form = create_customer_form(db_path, customer_form_input())
    archived = archive_customer_form(db_path, form["id"])

    assert archived["is_active"] is False
    assert get_customer_form_by_slug(db_path, form["form_slug"]) is None
    assert get_customer_form_by_slug(db_path, form["form_slug"], include_inactive=True)["id"] == form["id"]


def test_default_customer_form_falls_back_when_no_records_exist(tmp_path):
    db_path = str(tmp_path / "default_customer_form.db")

    default = get_default_customer_form_config(db_path)

    assert default["form_slug"] == "lead"
    assert default["page_title"] == "Request a Follow-Up"
    assert list_customer_forms(db_path) == []


def test_default_customer_form_stays_legacy_even_when_client_forms_exist(tmp_path):
    db_path = str(tmp_path / "default_with_client_forms.db")
    create_customer_form(db_path, customer_form_input())

    default = get_default_customer_form_config(db_path)

    assert default["id"] is None
    assert default["form_slug"] == "lead"
    assert default["client_business_name"] == "Default"
    assert default["page_title"] == "Request a Follow-Up"


def test_business_profile_slug_generation_and_duplicate_prevention(tmp_path):
    db_path = str(tmp_path / "test_profiles.db")
    first = create_business_profile(
        db_path,
        {
            "business_name": "Blue Ridge Mobile Detailing!",
            "public_slug": "",
            "owner_name": "Alex",
            "owner_email": "alex@example.com",
        },
    )
    second = create_business_profile(
        db_path,
        {
            "business_name": "Blue Ridge Mobile Detailing",
            "public_slug": "blue-ridge-mobile-detailing",
            "owner_name": "Sam",
            "owner_email": "sam@example.com",
        },
    )

    assert first["public_slug"] == "blue-ridge-mobile-detailing"
    assert second["public_slug"] == "blue-ridge-mobile-detailing-2"
    assert get_business_by_slug(db_path, first["public_slug"])["id"] == first["id"]


def test_business_profile_can_be_updated_and_deactivated(tmp_path):
    db_path = str(tmp_path / "test_profile_update.db")
    profile = create_business_profile(
        db_path,
        {
            "business_name": "Original Detail Shop",
            "public_slug": "original-detail-shop",
            "owner_name": "Pilot",
            "owner_email": "pilot@example.com",
        },
    )
    updated = update_business_profile(
        db_path,
        profile["id"],
        {
            **profile,
            "business_name": "Pilot Detail Shop",
            "owner_email": "pilot@example.com",
            "booking_link": "https://book.example.com",
            "is_active": False,
        },
    )

    assert updated["business_name"] == "Pilot Detail Shop"
    assert updated["owner_email"] == "pilot@example.com"
    assert updated["is_active"] is False


def test_reads_do_not_create_profiles(tmp_path):
    db_path = str(tmp_path / "empty.db")

    assert list_business_profiles(db_path) == []
    assert get_business_by_slug(db_path, "missing") is None
    assert list_business_profiles(db_path) == []


def test_edit_slug_conflict_is_blocked(tmp_path):
    db_path = str(tmp_path / "slug_conflict.db")
    first = create_business_profile(
        db_path,
        {
            "business_name": "First Detail",
            "public_slug": "first-detail",
            "owner_name": "One",
            "owner_email": "one@example.com",
        },
    )
    second = create_business_profile(
        db_path,
        {
            "business_name": "Second Detail",
            "public_slug": "second-detail",
            "owner_name": "Two",
            "owner_email": "two@example.com",
        },
    )

    with pytest.raises(ValueError):
        update_business_profile(
            db_path,
            second["id"],
            {**second, "public_slug": first["public_slug"]},
        )


def test_create_list_get_status_and_notes_by_business(tmp_path):
    db_path = str(tmp_path / "test_leads.db")
    profile = create_business_profile(
        db_path,
        {
            "business_name": "Pilot Detail Shop",
            "public_slug": "pilot-detail-shop",
            "owner_name": "Pilot",
            "owner_email": "pilot@example.com",
            "booking_link": "https://book.example.com",
        },
    )
    lead = create_lead(db_path, profile["id"], lead_input())

    assert lead["id"] > 0
    assert lead["business_id"] == profile["id"]
    assert lead["next_action"]
    assert "Pilot Detail Shop" in lead["customer_confirmation"]
    assert "https://book.example.com" in lead["customer_confirmation"]
    assert len(list_leads(db_path, profile["id"])) == 1

    update_lead_status(db_path, lead["id"], "Quote Sent")
    update_owner_notes(db_path, lead["id"], "Customer prefers Saturday.")
    updated = get_lead(db_path, lead["id"])

    assert updated["status"] == "Quote Sent"
    assert updated["owner_notes"] == "Customer prefers Saturday."
    assert "book" in updated["next_action"].lower()
    assert updated["follow_up_sequence"][0] == updated["customer_confirmation"]


def test_soft_delete_restore_preserves_leads_and_public_lookup(tmp_path):
    db_path = str(tmp_path / "delete_restore.db")
    profile = create_business_profile(
        db_path,
        {
            "business_name": "Restore Detail",
            "public_slug": "restore-detail",
            "owner_name": "Riley",
            "owner_email": "riley@example.com",
        },
    )
    lead = create_lead(db_path, profile["id"], lead_input())

    soft_delete_business_profile(db_path, profile["id"])

    assert list_business_profiles(db_path) == []
    assert len(list_business_profiles(db_path, only_deleted=True)) == 1
    assert get_business_by_slug(db_path, "restore-detail") is None
    assert get_lead(db_path, lead["id"])["business_id"] == profile["id"]

    restored = restore_business_profile(db_path, profile["id"])

    assert restored["id"] == profile["id"]
    assert restored["deleted_at"] is None
    assert get_business_by_slug(db_path, "restore-detail")["id"] == profile["id"]
    assert len(list_leads(db_path, profile["id"])) == 1


def test_seed_demo_data_has_two_profiles_and_business_leads(tmp_path):
    db_path = str(tmp_path / "seed.db")
    reset_sample_data(db_path)

    profiles = list_business_profiles(db_path)
    assert len(profiles) == 2
    assert profiles[0]["owner_email"] != profiles[1]["owner_email"]
    for profile in profiles:
        assert len(list_leads(db_path, profile["id"])) >= 2
