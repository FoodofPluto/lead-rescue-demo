from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


VEHICLE_TYPES = ["sedan", "SUV", "truck", "van", "motorcycle", "other"]
CONDITIONS = ["light", "moderate", "heavy", "very dirty"]
SERVICES = [
    "exterior",
    "interior",
    "full detail",
    "ceramic coating inquiry",
    "maintenance wash",
    "other",
]
URGENCIES = ["today", "this week", "flexible", "just pricing"]
STATUSES = [
    "New",
    "Contacted",
    "Waiting on Photos",
    "Quote Sent",
    "Booked",
    "Lost",
    "Follow Up Later",
]


DEFAULT_BUSINESS_PROFILE: dict[str, str] = {
    "business_name": "Shine Mobile Detailing",
    "owner_name": "Jordan",
    "owner_email": "owner@example.com",
    "phone": "(555) 300-1212",
    "service_area": "Austin, Round Rock, Cedar Park, and nearby areas",
    "booking_link": "https://example.com/book",
    "business_hours": "Monday-Saturday, 8 AM-6 PM",
    "services_offered": "Exterior detail, interior detail, full detail, maintenance wash, ceramic coating inquiry",
    "starting_prices": "Maintenance washes from $75. Full details from $175. Final pricing depends on size and condition.",
    "preferred_tone": "Friendly, professional, helpful, and not pushy",
    "photo_request_instructions": "Please send clear photos of the front, back, seats, carpets, wheels, and any problem areas.",
    "public_slug": "shine-mobile-detailing",
    "is_active": "1",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalized_profile(profile: dict[str, str] | None = None) -> dict[str, str]:
    merged = DEFAULT_BUSINESS_PROFILE.copy()
    if profile:
        merged.update({key: str(value or "") for key, value in profile.items()})
    return merged


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "mobile-detailer"


def score_lead(data: dict[str, str]) -> int:
    score = 35

    urgency_scores = {
        "today": 25,
        "this week": 18,
        "flexible": 9,
        "just pricing": 2,
    }
    service_scores = {
        "ceramic coating inquiry": 18,
        "full detail": 16,
        "interior": 10,
        "exterior": 8,
        "maintenance wash": 7,
        "other": 5,
    }
    condition_scores = {
        "very dirty": 14,
        "heavy": 11,
        "moderate": 7,
        "light": 4,
    }

    score += urgency_scores.get(data.get("urgency", ""), 0)
    score += service_scores.get(data.get("desired_service", ""), 0)
    score += condition_scores.get(data.get("vehicle_condition", ""), 0)

    if data.get("name", "").strip():
        score += 4
    if data.get("phone", "").strip():
        score += 8
    if data.get("email", "").strip():
        score += 4
    if data.get("location", "").strip():
        score += 4
    if data.get("preferred_time", "").strip():
        score += 3
    if data.get("can_send_photos") == "yes":
        score += 4
    if data.get("urgency") == "just pricing":
        score -= 12

    return max(1, min(100, score))


def priority_label(score: int) -> str:
    if score >= 80:
        return "High - call or text ASAP"
    if score >= 60:
        return "Medium - follow up today"
    return "Low - nurture with quote and availability"


def first_name(name: str) -> str:
    return name.split()[0] if name.strip() else "there"


def booking_sentence(profile: dict[str, str]) -> str:
    if profile.get("booking_link", "").strip():
        return f"You can also book a time here: {profile['booking_link']}."
    return f"{profile['owner_name']} will follow up directly to confirm availability and next steps."


def generate_customer_confirmation(
    data: dict[str, str], profile: dict[str, str] | None = None
) -> str:
    business = normalized_profile(profile)
    photo_line = (
        business["photo_request_instructions"]
        if data.get("can_send_photos") == "yes"
        else "If you can send photos later, that will help us quote more accurately."
    )
    return (
        f"Thanks, {data['name']}. {business['business_name']} received your request "
        f"for a {data['desired_service']} on your {data['vehicle_type']} in "
        f"{data['location']}. We will review your details and follow up with next steps. "
        f"{photo_line} {booking_sentence(business)}"
    )


def generate_follow_up_sequence(
    data: dict[str, str], profile: dict[str, str] | None = None
) -> list[str]:
    business = normalized_profile(profile)
    name = first_name(data.get("name", ""))
    booking = booking_sentence(business)
    return [
        generate_customer_confirmation(data, business),
        (
            f"Hi {name}, this is {business['owner_name']} with {business['business_name']}. "
            f"Just checking in on your {data['vehicle_type']} {data['desired_service']} "
            f"request around {data['location']}. Are you still looking to get this handled? "
            f"{booking}"
        ),
        (
            f"Hi {name}, final quick follow-up from {business['business_name']}. "
            f"If you still want help with your {data['vehicle_type']}, send over photos "
            f"or a good time and we can help you move forward. {booking}"
        ),
    ]


def missing_contact_info(data: dict[str, str]) -> list[str]:
    missing = []
    if not data.get("phone", "").strip():
        missing.append("phone number")
    if not data.get("location", "").strip():
        missing.append("service location")
    if not data.get("preferred_time", "").strip():
        missing.append("preferred time")
    return missing


def generate_next_action(
    data: dict[str, Any], profile: dict[str, str] | None = None
) -> dict[str, str]:
    business = normalized_profile(profile)
    name = first_name(str(data.get("name", "")))
    status = str(data.get("status", "New"))
    urgency = str(data.get("urgency", ""))
    high_priority = urgency in {"today", "this week"}
    prefix = "High priority: " if high_priority and status not in {"Booked", "Lost"} else ""
    missing = missing_contact_info({key: str(data.get(key, "")) for key in data})

    if missing:
        action = f"{prefix}Collect missing {', '.join(missing)}."
        message = (
            f"Hi {name}, thanks for reaching out to {business['business_name']}. "
            f"Could you send your {', '.join(missing)} so we can prepare an accurate quote?"
        )
    elif status == "New" and data.get("can_send_photos") == "yes":
        action = f"{prefix}Ask for photos."
        message = (
            f"Hi {name}, thanks for the request. When you can, please send photos of the "
            f"vehicle so {business['business_name']} can quote your {data['desired_service']} accurately. "
            f"{business['photo_request_instructions']}"
        )
    elif status == "New":
        action = f"{prefix}Call or text customer to clarify details."
        message = (
            f"Hi {name}, this is {business['owner_name']} with {business['business_name']}. "
            f"I saw your {data['desired_service']} request for your {data['vehicle_type']}. "
            "I have a couple quick questions so I can quote it correctly."
        )
    elif status == "Contacted":
        action = f"{prefix}Send quote or ask final qualifying question."
        message = (
            f"Hi {name}, based on what you shared, I can help with the "
            f"{data['desired_service']}. {booking_sentence(business)}"
        )
    elif status == "Waiting on Photos":
        action = f"{prefix}Follow up for photos."
        message = (
            f"Hi {name}, just checking back for photos of the {data['vehicle_type']}. "
            f"Once I have those, I can confirm the best option and pricing. "
            f"{business['photo_request_instructions']}"
        )
    elif status == "Quote Sent":
        action = f"{prefix}Check if they want to book."
        message = (
            f"Hi {name}, just checking whether you would like to book the "
            f"{data['desired_service']} for your {data['vehicle_type']}. "
            f"{booking_sentence(business)}"
        )
    elif status == "Booked":
        action = "Prepare for appointment."
        message = (
            f"Hi {name}, your detailing appointment is on our schedule. "
            f"{business['business_name']} will see you at the agreed time."
        )
    elif status == "Lost":
        action = "No action needed."
        message = (
            f"Hi {name}, thanks again for considering {business['business_name']}. "
            "Reach out anytime if you need detailing help in the future."
        )
    else:
        action = f"{prefix}Follow up later."
        message = (
            f"Hi {name}, just following up on your {data['vehicle_type']} "
            f"{data['desired_service']} request. Let me know if you still want a quote or want to book."
        )

    return {"next_action": action, "suggested_next_message": message}


def generate_owner_summary(
    data: dict[str, str], lead_score: int, profile: dict[str, str] | None = None
) -> str:
    business = normalized_profile(profile)
    sequence = generate_follow_up_sequence(data, business)
    next_step = generate_next_action({**data, "status": "New"}, business)
    email = data.get("email", "").strip() or "Not provided"
    notes = data.get("notes", "").strip() or "None"
    return f"""New Detailing Lead for {business["business_name"]}
Name: {data["name"]}
Phone: {data["phone"]}
Email: {email}
Vehicle: {data["vehicle_type"]}
Condition: {data["vehicle_condition"]}
Requested Service: {data["desired_service"]}
Location: {data["location"]}
Preferred Time: {data["preferred_time"]}
Urgency: {data["urgency"]}
Photos Available: {data["can_send_photos"]}
Notes: {notes}
Lead Priority: {priority_label(lead_score)} ({lead_score}/100)
Next Best Action: {next_step["next_action"]}
Suggested Reply: {sequence[1]}"""


def prepare_lead(
    data: dict[str, str], profile: dict[str, str] | None = None
) -> dict[str, object]:
    business = normalized_profile(profile)
    lead_score = score_lead(data)
    lead = {
        **data,
        "lead_score": lead_score,
        "status": "New",
        "owner_notes": "",
        "customer_confirmation": generate_customer_confirmation(data, business),
        "owner_summary": generate_owner_summary(data, lead_score, business),
        "follow_up_sequence": generate_follow_up_sequence(data, business),
    }
    return {**lead, **generate_next_action(lead, business)}


def sample_lead_inputs() -> list[dict[str, str]]:
    return [
        {
            "name": "Marcus Rivera",
            "phone": "(555) 214-9088",
            "email": "marcus@example.com",
            "vehicle_type": "SUV",
            "vehicle_condition": "heavy",
            "desired_service": "full detail",
            "location": "North Austin",
            "preferred_time": "Friday afternoon",
            "urgency": "this week",
            "can_send_photos": "yes",
            "notes": "Dog hair in back seat and coffee spill on passenger side.",
        },
        {
            "name": "Jasmine Lee",
            "phone": "(555) 772-1440",
            "email": "",
            "vehicle_type": "sedan",
            "vehicle_condition": "moderate",
            "desired_service": "interior",
            "location": "Round Rock",
            "preferred_time": "Tomorrow morning",
            "urgency": "today",
            "can_send_photos": "no",
            "notes": "Needs seats and carpets cleaned before selling the car.",
        },
        {
            "name": "Andre Coleman",
            "phone": "(555) 619-3031",
            "email": "andre@example.com",
            "vehicle_type": "truck",
            "vehicle_condition": "light",
            "desired_service": "ceramic coating inquiry",
            "location": "Cedar Park",
            "preferred_time": "Flexible next week",
            "urgency": "just pricing",
            "can_send_photos": "yes",
            "notes": "Wants coating options for a newer black pickup.",
        },
    ]
