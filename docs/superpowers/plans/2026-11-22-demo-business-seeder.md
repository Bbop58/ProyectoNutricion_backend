# Demo Business Seeder

> **For agentic workers:** Implement this plan task by task. Keep the data synthetic, repeatable, and scoped to the named demo businesses.

## Goal

Provide an explicit, idempotent backend seeder for five sample nutrition businesses with credible SaaS and clinic activity from January through November 2026. Respect the actual patient caps and prices in `SubscriptionService.PLANS`; branch counts are sample business sizes because the product currently has no branch cap. Ensure the existing `VIDASANA` sample tenant has an active primary branch so the public registration flow can offer a branch.

## Architecture

- Keep the generated dataset in a dedicated backend seeder module and expose it through a one-shot CLI command; never seed the five businesses automatically on API startup.
- Use stable tenant codes, branch codes, reserved `.example.test` emails, and deterministic IDs so re-running the command fills missing demo records without duplicating or replacing real records.
- Reuse the existing `VIDASANA` sample tenant and `PRINCIPAL` branch when present. Add only missing demo companies, branches, demo users, patient links, historical appointments, cash consultation payments, and monthly subscription periods.
- Keep synthetic subscriptions local: do not invent PayPal order/capture IDs or issue provider receipts. Model eleven consecutive 30-day periods per business, leaving one current `ACTIVE` period and marking prior periods `REPLACED`.
- Seed tenant-level recipe catalogs only when the plan metadata includes `Recetario & Macros`; seed manual self-reported food diary records for synthetic patients using the same payload and idempotency shape as the API.
- Do not seed anamneses, AI photo analyses, or approved personal meal plans. Those flows depend on user consent, a real photo/Gemini analysis, or a clinician's review and approval.
- Require an explicitly supplied seed password for newly created demo users. Require an explicit CLI production flag before adding synthetic records to a production database.

## Tech Stack

- Python 3, SQLAlchemy ORM, existing FastAPI backend models/services, pytest with in-memory SQLite.
- Existing `SubscriptionService.PLANS` is the single source of truth for company prices and patient caps.
- Bolivia location catalog codes are used for the seeded company and branch location.

## Spec

- Seed five companies in total, counting the existing `VIDASANA` sample company when present.
- Assign plans and active patient counts below the actual plan caps: two `BASICO` tenants (8 and 10 patients), two `PROFESIONAL` tenants (32 and 45 patients), and one `PREMIUM` tenant (64 patients).
- Assign uneven sample branch counts of 1, 1, 2, 3, and 5. These numbers illustrate business size and do not imply plan entitlements.
- Create valid company admin and nutritionist users, linked patient accounts, and synthetic historical clinic visits. Completed consultation charges must use the existing USD 5 fee, cash method, and no fake PayPal identifiers.
- Add generic, clearly labeled demo recipes for plans that include the recipe feature, and historical manual diary entries with no fabricated image or AI result.
- Store business/subscription/user activity within 2026-01-01 through 2026-11-22. Preserve existing unrelated tenant, branch, and user data.
- The CLI must state how many records it created and be safe to run repeatedly.
- Add tests for plan caps, branch counts, historical bounds/statuses, correct consultation pricing, idempotency, production guard, and the missing `VIDASANA` primary-branch regression.

## Global Constraints

- Do not delete or overwrite existing non-demo records.
- Do not run this seeder against Railway or another remote database as part of local implementation.
- Do not fabricate external payment credentials, PayPal IDs, receipts, or real patient identities.
- Do not fabricate patient consent, medical diagnoses, AI image analysis, or nutrition-plan approval.
- Keep the change scoped to backend seeding, the existing `VIDASANA` startup seed, documentation, and targeted tests.

## Review Focus

- Plan metadata comes from `SubscriptionService.PLANS`, not duplicated constants.
- Branch count is not presented as a subscription rule.
- All generated foreign keys, dates, status transitions, and consultation amounts match the current domain models and services.
- Re-running leaves counts stable and preserves real data.

## Implementation Tasks

- [x] Add an idempotent synthetic business dataset, recipe catalogs, and manual food-diary history.
- [x] Ensure `init_db()` creates/reuses and activates the `VIDASANA` primary branch and assigns its existing demo users.
- [x] Add an explicit CLI with password and production safeguards plus concise usage documentation.
- [x] Add focused tests for plan entitlements, food-diary history, repeatability, and branch creation.
- [x] Run focused and relevant backend tests; review the final diff for accidental changes.
