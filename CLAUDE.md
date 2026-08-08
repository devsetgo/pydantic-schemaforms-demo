# Demo App — AI Sync Instructions

## What this repo is

This is a **demo application** for the `pydantic-schemaforms` library. Its job is to stay in sync with the library's own examples so visitors see an up-to-date showcase.

The library's canonical examples live in `lib-examples/` (synced from the `main` branch of `devsetgo/pydantic-schemaforms` on every container start via `scripts/sync-lib-examples.sh`).

---

## File mapping: lib-examples → demo app

| lib-examples source | Demo app target | What it covers |
|---|---|---|
| `lib-examples/fastapi_routes.py` | `src/examples_routes.py` | Routes, endpoints, API handlers |
| `lib-examples/shared_models.py` | `src/models.py` | Form models, enums, organization structures |
| `lib-examples/nested_forms_example.py` | `src/nested_forms_models.py` | Deeply nested / tabbed form models |
| `lib-examples/date_time_formats_example.py` | `src/date_time_formats_models.py` | Custom date/time/datetime `ui_options` format showcase |
| `lib-examples/input_type_reference.py` | `src/input_type_reference.py` | Static `ui_element` cheatsheet data for `/input-types` |
| `lib-examples/templates/home.html` | `src/templates/home.html` | Home page |
| `lib-examples/templates/shared_base.html` | `src/templates/shared_base.html` | Base layout |
| `lib-examples/templates/form.html` | `src/templates/form.html` | Form rendering page |
| `lib-examples/templates/success.html` | `src/templates/success.html` | Form success page |
| `lib-examples/templates/404.html` | `src/templates/404.html` | 404 error page |
| `lib-examples/templates/500.html` | `src/templates/500.html` | 500 error page |
| `lib-examples/templates/ai_instructions.html` | `src/templates/ai_instructions.html` | AI assistant instructions page |
| `lib-examples/templates/live_validation.html` | `src/templates/live_validation.html` | Live HTMX validation demo |
| `lib-examples/templates/email_dns_validation.html` | `src/templates/email_dns_validation.html` | Email format vs. DNS/MX validation demo |
| `lib-examples/templates/input_type_reference.html` | `src/templates/input_type_reference.html` | Rendered `ui_element` cheatsheet page |

Note: `lib-examples/main.py` is the library's own composition root (FastAPI() construction,
session middleware, static mount, uvicorn entrypoint) — it has no sync target. The demo
app's `src/main.py` already plays that same role for this app and is demo-app-only (see
below), so `lib-examples/main.py` only needs to be read for context, never ported.

---

## Module layout (demo app only — no counterpart in lib-examples)

The demo app splits `src/main.py` into focused modules. Only `src/examples_routes.py`
is synced from lib-examples; the rest are demo-app-only composition/infrastructure:

| Module | Purpose |
|---|---|
| `src/main.py` | Composition root: creates the `FastAPI` app, wires middleware/lifespan, includes routers. Not synced from lib-examples. |
| `src/examples_routes.py` | The library showcase routes — **this is what gets synced from `lib-examples/fastapi_routes.py`.** |
| `src/app_routes.py` | Demo-app-only routes: analytics dashboard, `/robots.txt`, `/security`, error handlers. |
| `src/middleware.py` | The analytics/anti-scan HTTP middleware. |
| `src/resources.py` | Startup/shutdown lifecycle (analytics DB init, IP-geo worker). |

## How to sync

### 1. Routes and endpoints (`src/examples_routes.py`)

Compare `lib-examples/fastapi_routes.py` to `src/examples_routes.py` function by function.

**Port from lib-examples:**
- New `@app.get` / `@app.post` routes (becomes `@router.get` / `@router.post` here — this file defines an `APIRouter`, not the `FastAPI` app itself)
- Changed route paths or HTTP methods
- New or changed `FormModel` classes defined inline in the example (e.g. `ContactForm`, `FeedbackForm`)
- New API tags and their descriptions (the `_openapi_tags` list itself lives in `src/main.py`, since it's passed to the `FastAPI(...)` constructor there)
- Changes to helper functions like `render_self_contained_demo_page`

**Adjust imports when porting:** lib-examples uses `from examples.shared_models import ...` and `from examples.nested_forms_example import ...`. The demo app uses `from .models import ...` and `from .nested_forms_models import ...`.

**Do not touch:**
- `src/app_routes.py`, `src/middleware.py`, `src/resources.py` — demo-app-only, no lib-examples counterpart
- Any `from .analytics import` or `from .ip_geo_*` imports (in `app_routes.py`/`middleware.py`/`resources.py`)
- Dashboard-related routes (`/dashboard`, `/central`, etc.) — these live in `app_routes.py` and don't exist in lib-examples
- The `lifespan` context manager in `resources.py` (handles analytics DB setup and ip_geo worker)

### 2. Form models (`src/models.py` and `src/nested_forms_models.py`)

Compare `lib-examples/shared_models.py` to `src/models.py` and `lib-examples/nested_forms_example.py` to `src/nested_forms_models.py`.

**Port from lib-examples:**
- New `FormModel` subclasses or Pydantic models
- Field additions, removals, or type changes
- New enums or constants
- New utility functions like `create_sample_nested_data`
- Changes to `CompanyOrganizationForm`, `CompleteShowcaseForm`, and similar complex models

**Do not touch:**
- Any class or function that has no counterpart in lib-examples — it was added for demo-specific reasons.

### 3. UI templates (`src/templates/`)

Compare each file listed in the table above.

**Port from lib-examples:**
- New sections, cards, or feature highlights added to `home.html`
- Navigation changes in `shared_base.html` (new links to new demo routes)
- New Jinja2 blocks or macros
- CSS variable or style changes in `shared_base.html`

**Do not touch in templates:**
- The analytics nav link or dashboard link in the navbar (these are demo-app additions)
- The `ip_modal.html` template (demo-app only, not in lib-examples)
- `central_dashboard.html` and `dashboard.html` (demo-app only)

---

## Analytics layer — keep compatible, do not sync

These files are **demo-app-only** and have no counterpart in lib-examples. Never overwrite or remove them:

```
src/analytics.py          # SQLite-backed request + error logging
src/ip_geo_service.py     # IP → location HTTP fetch
src/ip_geo_store.py       # ip_geo cache / queue tables
src/ip_geo_worker.py      # background worker for geo lookups
src/templates/central_dashboard.html
src/templates/dashboard.html
src/templates/ip_modal.html
migrations/               # Alembic migrations for analytics DB schema
```

When syncing route handlers from lib-examples, **preserve any analytics calls** already present in the demo app's version of that handler (e.g. `record_request()`, `record_error()`). If a handler is new in lib-examples and has no demo-app equivalent yet, add the handler without analytics calls — analytics can be wired in separately.

---

## What changed? Diff first.

Before editing any file, diff lib-examples against the demo app to understand the delta:

```bash
diff lib-examples/fastapi_routes.py src/examples_routes.py
diff lib-examples/shared_models.py src/models.py
diff lib-examples/templates/home.html src/templates/home.html
diff lib-examples/templates/shared_base.html src/templates/shared_base.html
```

Focus on structural changes (new functions, new routes, model field changes). Ignore import path differences — those are expected.

---

## After syncing

1. Run `ruff check src/ --fix` and `ruff format src/` to keep style consistent.
2. Run `pytest` to verify nothing broke.
3. Check that existing analytics routes (`/dashboard`, `/api/health`) still respond.
