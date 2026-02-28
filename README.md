
# demo-pydantic-schemaforms

Demo FastAPI application showcasing `pydantic-schemaforms` form rendering and validation.

## Quick start

Prereqs:
- Python 3.14+

Install dependencies:

```bash
make install
```

Run the demo app:

```bash
make run
```

Then open:
- Home: http://localhost:5000/
- OpenAPI docs (grouped): http://localhost:5000/docs
- Health: http://localhost:5000/api/health

## What’s in the demo

- Server: FastAPI app in `src/main.py`
- Forms:
	- HTML pages (e.g. `/login`, `/register`, `/contact`, `/pets`, …)
	- JSON API endpoints:
		- `GET /api/forms/{form_type}/schema`
		- `GET /api/forms/{form_type}/render`
		- `POST /api/forms/{form_type}/submit`
- Analytics:
	- Dashboard: `GET /dashboard`
	- JSON endpoints under `/api/analytics/*`

OpenAPI tags are organized into three groups (in order): `Examples`, `Analytics`, `Health`.

## Smoke checks (recommended)

In-process integration smoke tests (fast, does not require the server to be running):

```bash
python -m pytest -q
```

Live-server smoke test (requires `make run` already running on the configured port):

```bash
make smoke-live
```

## Useful Make targets

- `make run`: run the demo server on `PORT` (default `5000`)
- `make kill`: kill any process using `PORT`
- `make test`: run lint + pytest (repo’s full test target)
- `make smoke-live`: run network smoke test against `http://localhost:${PORT}`

## Notes

- The canonical example implementation is also included under `examples/`.
- If you change `PORT`, the live smoke test will follow it automatically via the Makefile.

