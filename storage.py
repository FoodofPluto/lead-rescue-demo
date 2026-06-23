from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from lead_logic import (
    DEFAULT_BUSINESS_PROFILE,
    STATUSES,
    generate_next_action,
    normalized_profile,
    prepare_lead,
    sample_lead_inputs,
    slugify,
    utc_now_iso,
)


LEADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    vehicle_type TEXT NOT NULL,
    vehicle_condition TEXT NOT NULL,
    desired_service TEXT NOT NULL,
    location TEXT NOT NULL,
    preferred_time TEXT NOT NULL,
    urgency TEXT NOT NULL,
    can_send_photos TEXT NOT NULL,
    notes TEXT,
    owner_notes TEXT DEFAULT '',
    lead_score INTEGER NOT NULL,
    status TEXT NOT NULL,
    next_action TEXT DEFAULT '',
    suggested_next_message TEXT DEFAULT '',
    customer_confirmation TEXT NOT NULL,
    owner_summary TEXT NOT NULL,
    follow_up_sequence TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES business_profiles(id)
);
"""

PROFILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS business_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name TEXT NOT NULL,
    public_slug TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    owner_email TEXT,
    phone TEXT,
    service_area TEXT,
    booking_link TEXT,
    business_hours TEXT,
    services_offered TEXT,
    starting_prices TEXT,
    preferred_tone TEXT,
    photo_request_instructions TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
"""

DEMO_INQUIRIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    business_name TEXT NOT NULL,
    message TEXT NOT NULL
);
"""

APP_CONFIG_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_FORM_CONFIG: dict[str, str] = {
    "page_title": "Lead Rescue",
    "page_subtitle": "A simple follow-up link for small businesses that miss calls, messages, or quote requests.",
    "page_description": "Lead Rescue helps small businesses recover missed opportunities by giving customers one clear place to request a callback, quote, booking, or follow-up.",
    "who_header": "Who it is for",
    "who_body": "Service businesses that get leads from Facebook, Instagram, Google Business Profile, website buttons, texts, or missed phone calls.",
    "problem_header": "What problem it solves",
    "problem_body": "Instead of losing a customer in a message thread, the business gets the customer's contact details, request, and next step in one saved lead record.",
    "process_header": "What happens after a customer submits",
    "process_body": "1. The customer enters their contact details and what they need.\n2. The request is saved so it does not disappear in DMs or voicemail.\n3. The owner can review the lead and follow up.",
    "value_message": "For a business owner, the value is simple: fewer missed opportunities, faster follow-up, and one link they can share anywhere customers already find them.",
    "form_header": "Request a follow-up",
    "form_help": "Use this form the way a customer would: leave contact details and a short note about what you need.",
    "name_label": "Name *",
    "phone_label": "Phone number *",
    "email_label": "Email *",
    "business_label": "Business name *",
    "message_label": "Short message or problem description *",
    "message_placeholder": "Example: We miss Facebook messages and need one place for customers to request a quote or callback.",
    "cta_button_text": "Request a Follow-Up",
    "success_title": "Thanks. Your follow-up request was received.",
    "success_body": "The request was saved. The next step is to review the details and follow up.",
    "destination_owner_email": "",
}


LEAD_MIGRATIONS = {
    "business_id": "ALTER TABLE leads ADD COLUMN business_id INTEGER",
    "owner_notes": "ALTER TABLE leads ADD COLUMN owner_notes TEXT DEFAULT ''",
    "next_action": "ALTER TABLE leads ADD COLUMN next_action TEXT DEFAULT ''",
    "suggested_next_message": "ALTER TABLE leads ADD COLUMN suggested_next_message TEXT DEFAULT ''",
}

PROFILE_MIGRATIONS = {
    "deleted_at": "ALTER TABLE business_profiles ADD COLUMN deleted_at TEXT",
}


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(leads)").fetchall()
    }
    for column, statement in LEAD_MIGRATIONS.items():
        if column not in existing:
            conn.execute(statement)

    profile_existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(business_profiles)").fetchall()
    }
    for column, statement in PROFILE_MIGRATIONS.items():
        if column not in profile_existing:
            conn.execute(statement)


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.execute(PROFILES_SCHEMA)
        conn.execute(LEADS_SCHEMA)
        conn.execute(DEMO_INQUIRIES_SCHEMA)
        conn.execute(APP_CONFIG_SCHEMA)
        ensure_columns(conn)
        conn.commit()
    migrate_single_profile(db_path)
    normalize_existing_slugs(db_path)
    assign_orphan_leads_once(db_path)


def migrate_single_profile(db_path: str) -> None:
    with connect(db_path) as conn:
        old_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'business_profile'"
        ).fetchone()
        if not old_table:
            return
        old_profile = conn.execute("SELECT * FROM business_profile WHERE id = 1").fetchone()
        if not old_profile:
            return
        existing = conn.execute(
            "SELECT id FROM business_profiles WHERE public_slug = ?",
            (slugify(old_profile["public_slug"] or DEFAULT_BUSINESS_PROFILE["public_slug"]),),
        ).fetchone()
        if existing:
            return
        now = utc_now_iso()
        profile = normalized_profile(dict(old_profile))
        profile["public_slug"] = unique_slug(db_path, profile["public_slug"])
        conn.execute(
            """
            INSERT INTO business_profiles (
                business_name, public_slug, owner_name, owner_email, phone,
                service_area, booking_link, business_hours, services_offered,
                starting_prices, preferred_tone, photo_request_instructions,
                is_active, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            profile_values(profile, now, now),
        )
        conn.commit()


def profile_values(profile: dict[str, str], created_at: str, updated_at: str) -> tuple[Any, ...]:
    return (
        profile["business_name"],
        profile["public_slug"],
        profile["owner_name"],
        profile["owner_email"],
        profile["phone"],
        profile["service_area"],
        profile["booking_link"],
        profile["business_hours"],
        profile["services_offered"],
        profile["starting_prices"],
        profile["preferred_tone"],
        profile["photo_request_instructions"],
        int(str(profile.get("is_active", "1")) in {"1", "true", "True", "yes"}),
        created_at,
        updated_at,
        profile.get("deleted_at"),
    )


def row_to_profile(row: sqlite3.Row) -> dict[str, Any]:
    profile = dict(row)
    profile["is_active"] = bool(profile["is_active"])
    return profile


def slug_exists(
    db_path: str,
    slug: str,
    exclude_id: int | None = None,
    include_deleted: bool = False,
) -> bool:
    sql = "SELECT id FROM business_profiles WHERE public_slug = ?"
    params: list[Any] = [slug]
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    with connect(db_path) as conn:
        return conn.execute(sql, params).fetchone() is not None


def unique_slug(
    db_path: str,
    desired_slug: str,
    exclude_id: int | None = None,
    include_deleted: bool = False,
) -> str:
    base = slugify(desired_slug)
    slug = base
    suffix = 2
    while slug_exists(db_path, slug, exclude_id=exclude_id, include_deleted=include_deleted):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def normalize_existing_slugs(db_path: str) -> None:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, business_name, public_slug FROM business_profiles ORDER BY id"
        ).fetchall()
    for row in rows:
        clean = unique_slug(
            db_path,
            row["public_slug"] or row["business_name"],
            exclude_id=int(row["id"]),
            include_deleted=True,
        )
        if clean != row["public_slug"]:
            with connect(db_path) as conn:
                conn.execute(
                    "UPDATE business_profiles SET public_slug = ?, updated_at = ? WHERE id = ?",
                    (clean, utc_now_iso(), int(row["id"])),
                )
                conn.commit()


def assign_orphan_leads_once(db_path: str) -> None:
    with connect(db_path) as conn:
        orphan_count = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE business_id IS NULL"
        ).fetchone()[0]
        if not orphan_count:
            return
        existing = conn.execute(
            "SELECT id FROM business_profiles ORDER BY id LIMIT 1"
        ).fetchone()
        if existing is None:
            return
        conn.execute(
            "UPDATE leads SET business_id = ? WHERE business_id IS NULL",
            (int(existing["id"]),),
        )
        conn.commit()


def create_business_profile(db_path: str, profile: dict[str, str]) -> dict[str, Any]:
    init_path_only(db_path)
    now = utc_now_iso()
    merged = normalized_profile(profile)
    raw_slug = profile.get("public_slug") or merged["business_name"]
    merged["public_slug"] = unique_slug(db_path, raw_slug)
    if not merged["business_name"].strip():
        raise ValueError("Business name is required.")
    if not merged["public_slug"].strip():
        raise ValueError("Public slug is required.")
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO business_profiles (
                business_name, public_slug, owner_name, owner_email, phone,
                service_area, booking_link, business_hours, services_offered,
                starting_prices, preferred_tone, photo_request_instructions,
                is_active, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            profile_values(merged, now, now),
        )
        conn.commit()
        profile_id = int(cursor.lastrowid)
    return get_business_profile(db_path, profile_id)


def init_path_only(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.execute(PROFILES_SCHEMA)
        conn.execute(LEADS_SCHEMA)
        conn.execute(DEMO_INQUIRIES_SCHEMA)
        conn.execute(APP_CONFIG_SCHEMA)
        ensure_columns(conn)
        conn.commit()


def create_demo_inquiry(db_path: str, data: dict[str, str]) -> dict[str, Any]:
    init_path_only(db_path)
    cleaned = {
        "name": data.get("name", "").strip(),
        "phone": data.get("phone", "").strip(),
        "email": data.get("email", "").strip(),
        "business_name": data.get("business_name", "").strip(),
        "message": data.get("message", "").strip(),
    }
    missing = [label for label, value in cleaned.items() if not value]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))

    created_at = utc_now_iso()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO demo_inquiries (
                created_at, name, phone, email, business_name, message
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                cleaned["name"],
                cleaned["phone"],
                cleaned["email"],
                cleaned["business_name"],
                cleaned["message"],
            ),
        )
        conn.commit()
        inquiry_id = int(cursor.lastrowid)
    return {**cleaned, "id": inquiry_id, "created_at": created_at}


def list_demo_inquiries(db_path: str, limit: int = 20) -> list[dict[str, Any]]:
    init_path_only(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM demo_inquiries
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_form_config(db_path: str) -> dict[str, str]:
    init_path_only(db_path)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM app_config").fetchall()
    saved = {row["key"]: row["value"] for row in rows}
    config = DEFAULT_FORM_CONFIG.copy()
    for key, default in DEFAULT_FORM_CONFIG.items():
        value = str(saved.get(key, "")).strip()
        config[key] = value if value else default
    return config


def update_form_config(db_path: str, values: dict[str, str]) -> dict[str, str]:
    init_path_only(db_path)
    now = utc_now_iso()
    allowed = set(DEFAULT_FORM_CONFIG)
    with connect(db_path) as conn:
        for key, value in values.items():
            if key not in allowed:
                continue
            conn.execute(
                """
                INSERT INTO app_config (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, str(value or "").strip(), now),
            )
        conn.commit()
    return get_form_config(db_path)


def reset_form_config(db_path: str) -> dict[str, str]:
    init_path_only(db_path)
    with connect(db_path) as conn:
        placeholders = ", ".join("?" for _ in DEFAULT_FORM_CONFIG)
        conn.execute(
            f"DELETE FROM app_config WHERE key IN ({placeholders})",
            tuple(DEFAULT_FORM_CONFIG.keys()),
        )
        conn.commit()
    return get_form_config(db_path)


def update_business_profile(
    db_path: str, profile_id: int, profile: dict[str, str]
) -> dict[str, Any]:
    init_db(db_path)
    current = get_business_profile(db_path, profile_id)
    if current is None:
        raise ValueError(f"Business profile {profile_id} was not found.")
    merged = normalized_profile({**current, **profile})
    raw_slug = profile.get("public_slug") or merged["business_name"]
    desired_slug = slugify(raw_slug)
    if slug_exists(db_path, desired_slug, exclude_id=profile_id):
        raise ValueError(f"Public slug `{desired_slug}` is already in use.")
    merged["public_slug"] = desired_slug
    if not merged["business_name"].strip():
        raise ValueError("Business name is required.")
    if not merged["public_slug"].strip():
        raise ValueError("Public slug is required.")
    now = utc_now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE business_profiles SET
                business_name = ?, public_slug = ?, owner_name = ?, owner_email = ?,
                phone = ?, service_area = ?, booking_link = ?, business_hours = ?,
                services_offered = ?, starting_prices = ?, preferred_tone = ?,
                photo_request_instructions = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["business_name"],
                merged["public_slug"],
                merged["owner_name"],
                merged["owner_email"],
                merged["phone"],
                merged["service_area"],
                merged["booking_link"],
                merged["business_hours"],
                merged["services_offered"],
                merged["starting_prices"],
                merged["preferred_tone"],
                merged["photo_request_instructions"],
                int(bool(merged.get("is_active", True))),
                now,
                profile_id,
            ),
        )
        conn.commit()
    return get_business_profile(db_path, profile_id)


def list_business_profiles(
    db_path: str,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> list[dict[str, Any]]:
    init_db(db_path)
    where = ""
    if only_deleted:
        where = "WHERE deleted_at IS NOT NULL"
    elif not include_deleted:
        where = "WHERE deleted_at IS NULL"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM business_profiles {where} ORDER BY business_name"
        ).fetchall()
    return [row_to_profile(row) for row in rows]


def get_business_profile(db_path: str, profile_id: int) -> dict[str, Any] | None:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM business_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
    return row_to_profile(row) if row else None


def get_business_by_slug(
    db_path: str,
    slug: str,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    init_db(db_path)
    deleted_filter = "" if include_deleted else "AND deleted_at IS NULL"
    with connect(db_path) as conn:
        row = conn.execute(
            f"SELECT * FROM business_profiles WHERE public_slug = ? {deleted_filter}",
            (slugify(slug),),
        ).fetchone()
    return row_to_profile(row) if row else None


def business_lead_stats(db_path: str) -> dict[int, dict[str, int]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT business_id, status, COUNT(*) AS count
            FROM leads
            GROUP BY business_id, status
            """
        ).fetchall()
    stats: dict[int, dict[str, int]] = {}
    for row in rows:
        business_id = int(row["business_id"])
        stats.setdefault(business_id, {"total": 0, "new": 0, "booked": 0, "lost": 0})
        stats[business_id]["total"] += int(row["count"])
        if row["status"] == "New":
            stats[business_id]["new"] += int(row["count"])
        if row["status"] == "Booked":
            stats[business_id]["booked"] += int(row["count"])
        if row["status"] == "Lost":
            stats[business_id]["lost"] += int(row["count"])
    return stats


def create_lead(db_path: str, business_id: int, data: dict[str, str]) -> dict[str, Any]:
    init_db(db_path)
    profile = get_business_profile(db_path, business_id)
    if profile is None or profile.get("deleted_at") or not profile.get("is_active"):
        raise ValueError("Cannot create a lead for an unavailable business profile.")
    lead = prepare_lead(data, profile)
    created_at = utc_now_iso()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO leads (
                business_id, created_at, name, phone, email, vehicle_type,
                vehicle_condition, desired_service, location, preferred_time,
                urgency, can_send_photos, notes, owner_notes, lead_score, status,
                next_action, suggested_next_message, customer_confirmation,
                owner_summary, follow_up_sequence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                business_id,
                created_at,
                lead["name"],
                lead["phone"],
                lead["email"],
                lead["vehicle_type"],
                lead["vehicle_condition"],
                lead["desired_service"],
                lead["location"],
                lead["preferred_time"],
                lead["urgency"],
                lead["can_send_photos"],
                lead["notes"],
                lead["owner_notes"],
                lead["lead_score"],
                lead["status"],
                lead["next_action"],
                lead["suggested_next_message"],
                lead["customer_confirmation"],
                lead["owner_summary"],
                json.dumps(lead["follow_up_sequence"]),
            ),
        )
        conn.commit()
        lead_id = int(cursor.lastrowid)
    return get_lead(db_path, lead_id)


def row_to_lead(row: sqlite3.Row) -> dict[str, Any]:
    lead = dict(row)
    lead["follow_up_sequence"] = json.loads(lead["follow_up_sequence"])
    lead.setdefault("owner_notes", "")
    lead.setdefault("next_action", "")
    lead.setdefault("suggested_next_message", "")
    return lead


def refresh_lead_action(db_path: str, lead_id: int) -> None:
    lead = get_lead(db_path, lead_id)
    profile = get_business_profile(db_path, int(lead["business_id"]))
    if profile is None:
        return
    action = generate_next_action(lead, profile)
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE leads
            SET next_action = ?, suggested_next_message = ?
            WHERE id = ?
            """,
            (action["next_action"], action["suggested_next_message"], lead_id),
        )
        conn.commit()


def list_leads(db_path: str, business_id: int | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        if business_id:
            rows = conn.execute(
                """
                SELECT leads.*, business_profiles.business_name
                FROM leads
                JOIN business_profiles ON business_profiles.id = leads.business_id
                WHERE business_id = ?
                ORDER BY datetime(leads.created_at) DESC, leads.id DESC
                """,
                (business_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT leads.*, business_profiles.business_name
                FROM leads
                JOIN business_profiles ON business_profiles.id = leads.business_id
                ORDER BY datetime(leads.created_at) DESC, leads.id DESC
                """
            ).fetchall()
    leads = [row_to_lead(row) for row in rows]
    for lead in leads:
        if not lead.get("next_action") or not lead.get("suggested_next_message"):
            refresh_lead_action(db_path, lead["id"])
    if any(not lead.get("next_action") for lead in leads):
        return list_leads(db_path, business_id)
    return leads


def get_lead(db_path: str, lead_id: int) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT leads.*, business_profiles.business_name
            FROM leads
            JOIN business_profiles ON business_profiles.id = leads.business_id
            WHERE leads.id = ?
            """,
            (lead_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Lead {lead_id} was not found")
    return row_to_lead(row)


def soft_delete_business_profile(db_path: str, profile_id: int) -> None:
    init_db(db_path)
    now = utc_now_iso()
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE business_profiles SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (now, now, profile_id),
        )
        conn.commit()


def restore_business_profile(db_path: str, profile_id: int) -> dict[str, Any]:
    init_db(db_path)
    profile = get_business_profile(db_path, profile_id)
    if profile is None:
        raise ValueError(f"Business profile {profile_id} was not found.")
    if slug_exists(db_path, profile["public_slug"], exclude_id=profile_id):
        raise ValueError(
            f"Cannot restore profile because slug `{profile['public_slug']}` is in use."
        )
    now = utc_now_iso()
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE business_profiles SET deleted_at = NULL, updated_at = ? WHERE id = ?",
            (now, profile_id),
        )
        conn.commit()
    restored = get_business_profile(db_path, profile_id)
    if restored is None:
        raise ValueError(f"Business profile {profile_id} was not found.")
    return restored


def update_lead_status(db_path: str, lead_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unsupported lead status: {status}")
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        conn.commit()
    refresh_lead_action(db_path, lead_id)


def update_owner_notes(db_path: str, lead_id: int, owner_notes: str) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE leads SET owner_notes = ? WHERE id = ?",
            (owner_notes, lead_id),
        )
        conn.commit()


def sample_business_profiles() -> list[dict[str, str]]:
    return [
        {
            **DEFAULT_BUSINESS_PROFILE,
            "business_name": "Vinton Auto Detail",
            "public_slug": "vinton-auto-detail",
            "owner_name": "Maya",
            "owner_email": "maya@vintonautodetail.example",
            "phone": "(555) 410-1200",
            "service_area": "Vinton, Roanoke, Bonsack, and nearby neighborhoods",
            "booking_link": "https://example.com/vinton-booking",
            "starting_prices": "Maintenance washes from $80. Full details from $190.",
        },
        {
            **DEFAULT_BUSINESS_PROFILE,
            "business_name": "Roanoke Shine Detail",
            "public_slug": "roanoke-shine-detail",
            "owner_name": "Derrick",
            "owner_email": "derrick@roanokeshine.example",
            "phone": "(555) 920-3344",
            "service_area": "Roanoke, Salem, Cave Spring, and Hollins",
            "booking_link": "https://example.com/roanoke-shine-booking",
            "services_offered": "Interior reset, exterior wash, full detail, fleet maintenance",
            "starting_prices": "Interior resets from $125. Full details from $210.",
        },
    ]


def reset_sample_data(db_path: str) -> None:
    init_path_only(db_path)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM leads")
        conn.execute("DELETE FROM business_profiles")
        conn.commit()
    for index, profile in enumerate(sample_business_profiles()):
        created = create_business_profile(db_path, profile)
        samples = sample_lead_inputs()[index : index + 2]
        if len(samples) < 2:
            samples = sample_lead_inputs()[:2]
        for sample in samples:
            create_lead(db_path, created["id"], sample)


def seed_sample_data(db_path: str) -> None:
    init_db(db_path)
    profiles = list_business_profiles(db_path)
    if len(profiles) >= 2 and len(list_leads(db_path)) >= 4:
        return
    reset_sample_data(db_path)
