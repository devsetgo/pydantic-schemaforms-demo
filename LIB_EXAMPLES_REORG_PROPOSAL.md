# Proposal: split `examples/fastapi_example.py` in the `pydantic-schemaforms` library repo

## Audience

This is written for whoever edits the **library repo** (`devsetgo/pydantic-schemaforms`,
specifically its `examples/` folder — the thing `scripts/sync-lib-examples.sh` pulls
wholesale into this demo app's `lib-examples/`). It is not a change to this demo repo;
it's the mirror-image reorg that needs to happen on the other side so that syncing
stays cheap.

## Why

Today `examples/fastapi_example.py` (2048 lines) is one file that mixes two very
different concerns:

1. **Routes and endpoints** — the actual showcase content: forms, dual-use JSON
   APIs, live validation, AI instructions, etc. This is the part the demo app wants,
   verbatim, in `src/examples_routes.py`.
2. **App bootstrapping** — `FastAPI(...)` construction, `SessionMiddleware`,
   static mount, OpenAPI tags, the `if __name__ == '__main__':` uvicorn runner.
   This part is meaningless to the demo app — it already has its own `FastAPI()`
   instance, its own middleware stack (analytics/anti-scan), its own static mount,
   in `src/main.py`.

Because these are interleaved in one file, every sync means re-deriving which lines
are "routes" (port them) vs. "app setup" (ignore them) by re-reading the whole diff.
This demo app already went through exactly this split for its own code — see
`src/main.py` (composition root) vs. `src/examples_routes.py` (routes only),
`src/app_routes.py`, `src/middleware.py`, `src/resources.py` — and it made the local
sync trivial. The library's `examples/` package should get the equivalent split
(just the two-file version — the library has no analytics/middleware/lifecycle
concerns, so it doesn't need those extra modules).

## Target structure

```
examples/
├── fastapi_example.py     # thin entrypoint — unchanged behavior, ~80 lines
├── fastapi_routes.py      # NEW — the APIRouter with everything else, ~1950 lines
├── shared_models.py       # unchanged
├── nested_forms_example.py# unchanged
└── templates/             # unchanged
```

`fastapi_routes.py` becomes the file the demo app copies over `src/examples_routes.py`.
`fastapi_example.py` stays exactly what someone runs via `python examples/fastapi_example.py`
per the README — its behavior doesn't change, only its size shrinks.

## The boundary: what goes where

Everything below is keyed to the current `examples/fastapi_example.py` (line numbers
as of the last sync) so it's a mechanical cut, not a redesign.

### Stays in `fastapi_example.py` (app bootstrap only)

| Current content | Lines (approx) |
|---|---|
| Module docstring | 1–22 |
| `sys.path.insert(...)` bootstrap for direct-script execution | ~26 |
| `_openapi_tags` list | 173–215 |
| `app = FastAPI(...)` | 216–222 |
| `app.add_middleware(SessionMiddleware, ...)` | 223–233 |
| `app.mount('/static', StaticFiles(directory=_base_dir / 'img'), ...)` — `APIRouter` has no `.mount()`, this **must** stay on the `app` object | 308 |
| `if __name__ == '__main__':` uvicorn/print block | 1996–end |

Note: `_base_dir = Path(__file__).resolve().parent` needs to be computed **independently
in both files** (each file is still in `examples/`, so it resolves to the same directory
either way) — one copy feeds `app.mount(...)` here, another feeds the router's own
`Jinja2Templates(...)` over there. This mirrors exactly what `src/main.py` and
`src/examples_routes.py` do in the demo app today: two separate `_base_dir` computations,
no sharing needed.

New content to add to `fastapi_example.py`:
```python
from examples.fastapi_routes import router

app.include_router(router)
```
(Absolute import, matching the existing `sys.path.insert` + `from examples.shared_models import ...`
style already in this file — see "Constraints" below for why this matters.)

### Moves to `fastapi_routes.py` (everything else)

| Current content | Lines (approx) |
|---|---|
| `ContactForm`, `FeedbackForm` classes + their `as_api_model()` schemas | 80–172 |
| CSRF helpers (`issue_login_csrf_token`, `verify_login_csrf_token`, `issue_register_csrf_token`, `verify_register_csrf_token`) | 234–265 |
| `templates = Jinja2Templates(...)` + `safe_json_filter` + filter registration — **this router builds its own `Jinja2Templates` instance**, pointed at the same `templates/` directory | 266–307 |
| `/vendor/bootstrap-icons.css`, `/vendor/htmx.min.js` routes | 308–324 |
| `render_self_contained_demo_page()` helper | 325–379 |
| Every `@app.get`/`@app.post` route (`home`, `login`, `register`, `user`, `showcase`, `pets`, `organization`, `organization-shared`, `layouts`, `self-contained`, `api/forms/*`, `contact`/`feedback` dual-use + their `api/*` JSON siblings, `live-validation`, `validate/{field_name}`, `ai-instructions`, `api/health`) — decorators become `@router.get`/`@router.post` | 380–1977 |
| `create_refer_path()` helper | 1978–1995 |
| `FORM_REGISTRY` (used by the generic `api/forms/{form_type}/*` routes) | inline within the route block above |

At the top of `fastapi_routes.py`:
```python
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
# ...same pydantic_schemaforms / examples.shared_models / examples.nested_forms_example
# imports the current file already has...

router = APIRouter()
```

## Constraints to preserve

1. **Direct execution must keep working.** The README says `python examples/fastapi_example.py`.
   That only works today because the file does `sys.path.insert(0, ...)` then uses
   **absolute** imports (`from examples.shared_models import ...`), not relative ones
   (`from .shared_models import ...`). A relative import breaks the moment the file is
   run directly instead of via `python -m`. Keep `fastapi_routes.py` on the same
   absolute-import style, and have `fastapi_example.py` import it the same way
   (`from examples.fastapi_routes import router`), not `from .fastapi_routes import router`.
2. **`app.mount(...)` cannot move.** `APIRouter` has no `.mount()` method — the static
   mount for `examples/img` has to stay in `fastapi_example.py` on the real `app` object.
   (This demo app hit the same constraint with its own static mount and `/vendor/*`
   asset routes — the mount stayed in `main.py`, the routes serving from it moved to
   `examples_routes.py`.)
3. **`_openapi_tags` stays put.** It's an argument to the `FastAPI(...)` constructor,
   not something a router can register on its own.
4. **No new dependency on demo-app concepts.** Don't add anything analytics/dashboard/
   middleware-shaped to `examples/` — none of that exists in the library, and it
   shouldn't. This split is purely "routes vs. app," nothing more.

## What this changes on the demo-app side (once the library lands this)

Right now `CLAUDE.md` in this repo says to diff `lib-examples/fastapi_example.py`
against `src/examples_routes.py` and manually figure out which changed lines are
routes vs. app setup. Once the library does this split, the sync source becomes
`lib-examples/fastapi_routes.py`, and the process collapses to:

```bash
diff lib-examples/fastapi_routes.py src/examples_routes.py
```

The only expected diff left is the two import lines (`examples.shared_models` →
`.models`, `examples.nested_forms_example` → `.nested_forms_models`) — already
documented in `CLAUDE.md`'s "Adjust imports when porting" note, and now the *only*
adjustment needed instead of one of several.

I'll update `CLAUDE.md`'s file-mapping table and sync instructions to point at
`fastapi_routes.py` once this lands in the library repo.
