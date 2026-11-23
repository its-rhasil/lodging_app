# FrontdeskInn

Front-desk software for lodges: check-in and checkout, rolling 24-hour billing, payments,
room changes and a full audit trail. Multi-tenant, installable as a PWA.

## Live demo

- App: https://frontdeskinn.pages.dev
- Email: `demo.manager@example.com` · Password: `demomanager` (sample data, manager role)

## Features

- Check-in with guest lookup by phone, backdating and expected checkout
- Stay plans (full day, fresh-up, hourly) with grace periods and conversion to full day
- Append-only billing ledger: corrections are reversals and waivers, never edits
- Payments with idempotency keys; room changes; price corrections; cancel a check-in
- Roles and per-user permission overrides; audit log of every change
- Tenant isolation verified on every API route by automated tests

## Tech stack

- **Backend:** FastAPI, SQLAlchemy 2, PostgreSQL, Alembic
- **Frontend:** React, Vite, TypeScript (PWA)
- **Hosting:** Cloudflare Pages with an `/api` proxy function, Render, Supabase;
  daily encrypted backups with GitHub Actions
