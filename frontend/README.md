# Frontend — Phase 2 (Next.js 14, App Router, RTL)

Planned structure:

```
frontend/
  app/
    layout.tsx          RTL, Readex Pro, theme tokens
    page.tsx            input (text / link) + results
    api/verify/route.ts proxy to FastAPI (hides backend URL)
  components/
    ClaimCard.tsx       verdict badge, source text, grade, diff, notes
    DiffView.tsx        word-level diff (equal / added / missing / changed)
    VerdictSummary.tsx  counts of the 7 verdicts
    Disclaimer.tsx
  lib/
    api.ts              typed client for POST /verify
    types.ts            mirrors backend/app/schemas.py
  public/logo.svg
```
