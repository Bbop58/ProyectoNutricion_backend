# Conversational Reports Implementation Plan

**Goal:** Generate reports from Spanish voice or text with reliable branch and period interpretation.

**Architecture:** A deterministic period parser and validated report intent build one query plan. Administrators report across their own company independently of their operational branch. The web retains presets, voice/text, result attributes, summary, and exports.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Angular 22.

**Scope:** No dates means January 1 through today in Bolivia. No branch means every authorized branch. Unknown scope or invalid dates require clarification. Exports reuse the interpreted query; mobile headers cannot expand authorization.

- [x] Extract Spanish period parsing and cover exact dates, relative periods and calendar quarters.
- [x] Allow company administrators to consolidate authorized branches in reporting only.
- [x] Resolve named branches against the authorized database catalog.
- [x] Remove manual date, entity and grouping controls from the web report view.
- [x] Preserve presets, spoken summaries and result attribute selection for lists and aggregates.
- [x] Verify interpretation, company isolation, result projection and PDF/Excel signatures.
- [ ] Commit and deploy backend and web; verify production queries.
