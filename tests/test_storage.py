import pytest

from storage import (
    create_business_profile,
    create_demo_inquiry,
    create_lead,
    get_form_config,
    get_business_by_slug,
    get_business_profile,
    get_lead,
    list_demo_inquiries,
    list_business_profiles,
    list_leads,
    reset_sample_data,
    reset_form_config,
    restore_business_profile,
    soft_delete_business_profile,
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
