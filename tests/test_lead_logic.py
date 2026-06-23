from lead_logic import (
    DEFAULT_BUSINESS_PROFILE,
    generate_customer_confirmation,
    generate_follow_up_sequence,
    generate_next_action,
    prepare_lead,
    score_lead,
    slugify,
)


def lead_input(**overrides):
    lead = {
        "name": "Alex Customer",
        "phone": "555-123-0000",
        "email": "alex@example.com",
        "vehicle_type": "SUV",
        "vehicle_condition": "very dirty",
        "desired_service": "full detail",
        "location": "Austin",
        "preferred_time": "today after 3",
        "urgency": "today",
        "can_send_photos": "yes",
        "notes": "",
    }
    lead.update(overrides)
    return lead


def test_slugify_creates_url_safe_slug():
    assert slugify("Vinton Auto Detail!") == "vinton-auto-detail"
    assert slugify("  Blue   Ridge Mobile Detailing  ") == "blue-ridge-mobile-detailing"


def test_hot_complete_lead_scores_higher_than_pricing_lead():
    hot = lead_input()
    pricing = lead_input(
        email="",
        vehicle_condition="light",
        desired_service="maintenance wash",
        urgency="just pricing",
        can_send_photos="no",
    )

    assert score_lead(hot) > score_lead(pricing)
    assert 1 <= score_lead(pricing) <= 100


def test_message_generation_uses_business_profile_and_booking_link():
    profile = {
        **DEFAULT_BUSINESS_PROFILE,
        "business_name": "Elite Detail Co",
        "owner_name": "Sam",
        "booking_link": "https://booking.example.com/elite",
    }
    lead = lead_input(vehicle_type="truck", desired_service="interior")

    confirmation = generate_customer_confirmation(lead, profile)
    sequence = generate_follow_up_sequence(lead, profile)
    prepared = prepare_lead(lead, profile)

    assert "Elite Detail Co" in confirmation
    assert "https://booking.example.com/elite" in confirmation
    assert "truck" in confirmation
    assert len(sequence) == 3
    assert prepared["status"] == "New"
    assert "New Detailing Lead for Elite Detail Co" in prepared["owner_summary"]


def test_next_action_changes_by_status_and_missing_info():
    profile = DEFAULT_BUSINESS_PROFILE.copy()

    new_with_photos = generate_next_action({**lead_input(), "status": "New"}, profile)
    waiting = generate_next_action(
        {**lead_input(), "status": "Waiting on Photos"}, profile
    )
    booked = generate_next_action({**lead_input(), "status": "Booked"}, profile)
    missing = generate_next_action(
        {**lead_input(phone="", preferred_time=""), "status": "New"}, profile
    )

    assert "Ask for photos" in new_with_photos["next_action"]
    assert "Follow up for photos" in waiting["next_action"]
    assert booked["next_action"] == "Prepare for appointment."
    assert "Collect missing" in missing["next_action"]
    assert missing["suggested_next_message"]
