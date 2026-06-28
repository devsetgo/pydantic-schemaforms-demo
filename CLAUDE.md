# Demo App — AI Sync Instructions

## What this repo is

This is a **demo application** for the `pydantic-schemaforms` library. Its job is to stay in sync with the library's own examples so visitors see an up-to-date showcase.

The library's canonical examples live in `lib-examples/` (synced from the `main` branch of `devsetgo/pydantic-schemaforms` on every container start via `scripts/sync-lib-examples.sh`).

---

## File mapping: lib-examples → demo app

| lib-examples source | Demo app target | What it covers |
|---|---|---|
| `lib-examples/fastapi_example.py` | `src/main.py` | Routes, endpoints, API handlers |
| `lib-examples/shared_models.py` | `src/models.py` | Form models, enums, organization structures |
| `lib-examples/nested_forms_example.py` | `src/nested_forms_models.py` | Deeply nested / tabbed form models |
| `lib-examples/templates/home.html` | `src/templates/home.html` | Home page |
| `lib-examples/templates/shared_base.html` | `src/templates/shared_base.html` | Base layout |
| `lib-examples/templates/form.html` | `src/templates/form.html` | Form rendering page |
| `lib-examples/templates/success.html` | `src/templates/success.html` | Form success page |
| `lib-examples/templates/404.html` | `src/templates/404.html` | 404 error page |
| `lib-examples/templates/500.html` | `src/templates/500.html` | 500 error page |

---

## How to sync

### 1. Routes and endpoints (`src/main.py`)

Compare `lib-examples/fastapi_example.py` to `src/main.py` function by function.

**Port from lib-examples:**
- New `@app.get` / `@app.post` routes
- Changed route paths or HTTP methods
- New or changed `FormModel` classes defined inline in the example (e.g. `ContactForm`, `FeedbackForm`)
- New API tags (`_openapi_tags`) and their descriptions
- Changes to helper functions like `render_self_contained_demo_page`

**Adjust imports when porting:** lib-examples uses `from examples.shared_models import ...` and `from examples.nested_forms_example import ...`. The demo app uses `from .models import ...` and `from .nested_forms_models import ...`.

**Do not touch in `src/main.py`:**
- The analytics middleware block (if present)
- Any `from .analytics import` or `from .ip_geo_*` imports
- Dashboard-related routes (`/dashboard`, `/central-dashboard`, etc.) — these don't exist in lib-examples
- The `lifespan` context manager (handles analytics DB setup and ip_geo worker)

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
diff lib-examples/fastapi_example.py src/main.py
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
