# Lead Rescue AI / FollowUpKit for Mobile Detailers

Operator-managed lead form generator for mobile detailers.

This app is not a self-serve SaaS. It is an internal/operator tool for creating mobile detailer business profiles, generating unique public quote-request links, routing submitted leads to each profile's owner email, and managing leads by business.

The root page is a public Lead Rescue demo inquiry page. The operator tools are available at `?admin=1`.

## Stack

- Python
- Streamlit
- SQLite
- Optional email via Resend or SMTP
- Pytest

No Stripe, subscriptions, Twilio, social API integrations, CRM sync, AI agents, or complex multi-tenant auth are included.

## Run Locally

```bash
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

Before opening the operator area, edit `.env` and set:

```text
ADMIN_PASSWORD=choose-a-private-password
OWNER_EMAIL=you@example.com
```

If Windows refuses the browser connection even though Streamlit starts, run the local server with an explicit loopback address:

```bash
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

On macOS/Linux:

```bash
cp .env.example .env
```

Open:

```text
http://localhost:8501
```

Operator area:

```text
http://localhost:8501?admin=1
```

Public client quote links look like:

```text
http://localhost:8501/quote/shine-mobile-detailing
```

## Environment Variables

```text
APP_BASE_URL=http://localhost:8501
DATABASE_PATH=leads.db
ADMIN_PASSWORD=change-me
OWNER_EMAIL=owner@example.com
FROM_EMAIL=Lead Rescue AI <noreply@example.com>
EMAIL_PROVIDER=disabled
RESEND_API_KEY=
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
```

`OWNER_EMAIL` receives public Lead Rescue follow-up requests unless the destination email is overridden in **Lead Form Setup**. For business profile quote forms, owner notifications route to the `owner_email` stored on the matching business profile first and fall back to `OWNER_EMAIL`.

`ADMIN_PASSWORD` is required to open the operator area. If it is missing, public pages still work but dashboard/profile pages remain locked.

For Streamlit Community Cloud, set the same names in app secrets or environment settings:

```toml
APP_BASE_URL = "https://your-app.streamlit.app"
DATABASE_PATH = "leads.db"
ADMIN_PASSWORD = "choose-a-private-password"
OWNER_EMAIL = "you@example.com"
FROM_EMAIL = "Lead Rescue <onboarding@resend.dev>"
EMAIL_PROVIDER = "disabled"
RESEND_API_KEY = ""
SMTP_HOST = ""
SMTP_PORT = "587"
SMTP_USERNAME = ""
SMTP_PASSWORD = ""
```

## Create A Business Profile

1. Open **Business Profiles**.
2. Enter business name, owner name, owner email, service area, services, pricing, booking link, business hours, tone, photo instructions, and active status.
3. Leave slug blank to auto-generate one from the business name, or edit it before saving.
4. Slugs are normalized to URL-safe values and kept unique.

Profiles are created only when the operator submits the create form. Browsing, refreshing, opening dashboards, viewing quote pages, and listing profiles do not create profiles.

Each profile has:

- `id`
- `business_name`
- `public_slug`
- `owner_name`
- `owner_email`
- `phone`
- `service_area`
- `booking_link`
- `business_hours`
- `services_offered`
- `starting_prices`
- `preferred_tone`
- `photo_request_instructions`
- `is_active`
- `created_at`
- `updated_at`

## Public Quote Links

Each business gets a link like:

```text
http://localhost:8501/quote/vinton-auto-detail
```

The Business Profile Manager shows:

- Full public quote form URL
- Open form button
- Copy-ready owner handoff message
- Suggested placements

Use the link in:

- Instagram bio
- Facebook page
- Google Business Profile
- Website
- Text message replies
- QR code later

## Public Lead Rescue Form

The main public form is available at:

```text
http://localhost:8501/?form=lead
```

Open `http://localhost:8501?admin=1`, enter the operator password, then use **Lead Form Setup** to:

- Edit the public page copy, section headers, field labels, CTA button, thank-you message, and destination email.
- Copy the public Lead Rescue form link.
- Send a test email to verify email forwarding.
- Review recent public follow-up requests.

If `APP_BASE_URL` is set, the share link uses that hosted URL. If it is missing, the app tries to infer the current Streamlit URL and warns you to set `APP_BASE_URL` before deployment.

## Client Posting Instructions

After deployment, open the operator area at `https://your-app-url?admin=1`, create or select the client's business profile, and copy the **Public Quote Form Link**.

Give the client one short instruction: use that exact link anywhere customers already find them.

Example copy:

- Facebook or Google Business Profile: `Need a mobile detailing quote? Request one here: https://your-app-url/quote/client-slug`
- Instagram bio: `Mobile detailing quotes: https://your-app-url/quote/client-slug`
- Website button: `Request a Detailing Quote`
- Text reply: `Thanks for reaching out. Please send your vehicle details here so we can quote you accurately: https://your-app-url/quote/client-slug`

Before giving the link to the client, submit one test lead through the public form and confirm it appears in **Detailing Leads**.

## Deploy

The intended deployment platform for this stack is Streamlit Community Cloud because the app is a Streamlit app with `requirements.txt`.

There is no separate frontend build, backend service, or serverless/API route to configure. Streamlit runs `app.py` as the web server and the form handlers run inside the Streamlit app process.

1. Push this folder to a GitHub repository.
2. In Streamlit Community Cloud, create a new app from that repository.
3. Set the main file path to `app.py`.
4. Add secrets or environment variables matching `.env.example`.
5. Set `APP_BASE_URL` to the deployed app URL, for example `https://lead-rescue-demo.streamlit.app`.
6. Set `ADMIN_PASSWORD` before sharing the hosted operator area.
7. Deploy the app.

The generated Streamlit app URL is the public demo link. Use `https://your-app-url?admin=1` for setup and `https://your-app-url/quote/client-slug` for the client-shareable quote form.

SQLite is enough for a short demo, but hosted Streamlit storage may reset when the app is rebuilt or redeployed. For a production pilot, connect a persistent database and update `DATABASE_PATH` or replace the storage layer.

Do not commit `.env`, `leads.db`, or local cache folders. They are ignored by `.gitignore`.

## Test The Form

1. Run the app locally.
2. Open `http://localhost:8501?admin=1`.
3. Create a business profile or use **Reset sample businesses and leads**.
4. Copy the public quote form link.
5. Open the public link in a new tab.
6. Submit a lead with name, phone, location, preferred time, and request details.
7. Return to **Detailing Leads** and confirm the lead is saved.

## Lead Routing

When a customer submits `/quote/{public_slug}`:

1. The app loads the matching active business profile.
2. The lead is saved with that `business_id`.
3. Messages and summaries use that business profile.
4. Owner email routes to that profile's `owner_email` when email is configured.
5. Customer confirmation email sends only if the customer provided an email.

Inactive profiles show a clean unavailable page. Missing slugs show a clean not-found page.

Soft-deleted profiles also show as unavailable and cannot accept new submissions.

## Edit, Delete, And Restore Profiles

Editing:

- Open **Business Profiles**.
- Select a profile.
- Use **Edit Selected Profile**.
- Saving updates the same profile `id`; it does not create a duplicate.
- Changing `public_slug` keeps old leads attached to the same business profile.
- If the new slug conflicts with another active/non-deleted profile, the app shows an error.

Deleting:

- Use **Delete selected profile**.
- The app soft deletes the profile by setting `deleted_at`.
- Existing leads are preserved.
- The profile disappears from the default active profile list.
- Its public quote form no longer accepts submissions.

Restoring:

- Use **Undo last profile delete** immediately after deletion, or restore from **Recently Deleted**.
- Restoring clears `deleted_at`.
- The original business `id` and leads are preserved.
- If another active profile is using the same slug, restore is blocked with a clear error.

## Manage Leads By Business

Open **Detailing Leads**.

You can:

- Filter leads by business
- See latest leads
- View associated business name
- Review lead priority score
- See next recommended action
- Copy suggested reply
- Update status
- Save owner notes
- Copy owner summary, customer confirmation, and follow-up sequence

Statuses:

- New
- Contacted
- Waiting on Photos
- Quote Sent
- Booked
- Lost
- Follow Up Later

## Email Behavior

Email is safe by default.

Disabled mode:

```text
EMAIL_PROVIDER=disabled
```

Submissions still save and the app reports that email is disabled.

Resend mode:

```text
EMAIL_PROVIDER=resend
RESEND_API_KEY=...
FROM_EMAIL=...
```

SMTP mode:

```text
EMAIL_PROVIDER=smtp
SMTP_HOST=...
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
FROM_EMAIL=...
```

Owner email includes business name, customer details, lead score, owner summary, next recommended action, suggested next message, and dashboard link.

Public Lead Rescue form emails use the subject `New Lead Rescue Follow-Up Request` and include name, phone, email, business name, message, created time, and operator dashboard link.

To test email forwarding without submitting a real lead, open **Lead Form Setup** and click **Send Test Email**. If email delivery is disabled or credentials are missing, the app shows a warning but form submissions still save.

## Seed/Demo Data

The app includes sample data utilities with two mobile detailer profiles and at least two leads per profile. In **Business Profiles**, use **Reset sample businesses and leads** to load the sample operator workflow.

Seeding does not run during ordinary app startup, page render, dashboard load, profile listing, or public quote form browsing. The reset button is explicit and destructive for demo data: it clears current profiles/leads and recreates the sample set.

Sample profiles demonstrate:

- Unique slugs
- Different owner emails
- Different service areas
- Different services/prices
- Leads tied to the correct business

## Tests

```bash
python -m pytest
```

Tests cover slug generation, duplicate slug prevention, business profile persistence, lookup by slug, lead persistence with `business_id`, lead scoring, deterministic messages, next-action logic, and email recipient selection.

## Manual Verification Checklist

1. Create a new business profile.
2. Confirm a unique slug is generated.
3. Copy public quote form link.
4. Open public quote form link.
5. Submit test lead.
6. Confirm lead is saved under the correct business.
7. Confirm owner email recipient matches the business profile `owner_email`.
8. Create a second business profile.
9. Submit a lead through the second public form.
10. Confirm the second lead routes to the second profile's `owner_email`.
11. Confirm dashboard can filter leads by business.
12. Confirm inactive profile public form is unavailable.
13. Confirm missing email credentials do not crash the app.
14. Count profiles, then navigate between dashboard, profile manager, setup checklist, and public quote page.
15. Confirm the profile count does not increase.
16. Edit a profile and confirm the same profile updates instead of creating a duplicate.
17. Try to edit another profile to use the same slug and confirm the conflict is blocked.
18. Delete a profile and confirm it appears in **Recently Deleted**.
19. Confirm its leads still exist.
20. Restore the profile and confirm the same profile `id` is available again.

## Intentionally Not Built Yet

- Stripe
- Paid subscriptions
- Self-serve customer accounts
- Complex authentication
- Twilio or real SMS
- Instagram/Facebook API integrations
- ManyChat/BotBuilders webhooks
- CRM integrations
- AI agent orchestration
- Complex multi-tenant SaaS architecture

## Recommended Next Phase

Run several operator-managed pilots. After the workflow is validated, add photo upload, simple lead export, quote range estimates, optional SMS sending, and eventually a proper admin/auth model if operational usage justifies it.
