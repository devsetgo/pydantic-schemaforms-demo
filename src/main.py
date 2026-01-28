"""
Pydantic SchemaForms Demo - FastAPI Application

A comprehensive demonstration of pydantic-schemaforms capabilities
with all endpoints and models from the examples consolidated.
"""

import json
import os
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import pydantic_schemaforms
from pydantic_schemaforms.enhanced_renderer import render_form_html, EnhancedFormRenderer
from pydantic_schemaforms.simple_material_renderer import SimpleMaterialRenderer

from .models import (
    CompleteShowcaseForm,
    ContactForm,
    ContactInfoForm,
    Country,
    EmergencyContactModel,
    LayoutDemonstrationForm,
    MinimalLoginForm,
    PersonalInfoForm,
    PetModel,
    PetRegistrationForm,
    PreferencesForm,
    Priority,
    TaskItem,
    TaskListForm,
    UserRegistrationForm,
    handle_form_submission,
    parse_nested_form_data,
)

from .analytics import (
    extract_client_ip,
    extract_country,
    get_recent_errors,
    get_recent_requests,
    get_summary,
    init_db,
    purge_all,
    record_error,
    record_request,
)

# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="Pydantic SchemaForms Demo",
    description="Comprehensive showcase of pydantic-schemaforms capabilities in FastAPI",
    version="26.1.1b0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


def _load_dotenv_if_present() -> None:
    """Load a local .env file if present.

    This demo intentionally avoids adding dependencies. We only set env vars that
    are not already set in the process environment.
    """

    # Repo root is one level above the `src/` package.
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        # Never fail app startup for a bad .env.
        return


_load_dotenv_if_present()


@app.on_event("startup")
async def _startup_init_analytics() -> None:
    try:
        init_db()
    except Exception:
        # Analytics must never prevent the app from starting.
        return


def _dashboard_token_required() -> str | None:
    token = os.environ.get("DASHBOARD_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None


def _dashboard_cookie_name() -> str:
    return "schemaforms_dashboard_token"


def _dashboard_cookie_ttl_seconds() -> int:
    # Default to 30 minutes; can be overridden if desired.
    raw = os.environ.get("DASHBOARD_COOKIE_TTL_SECONDS")
    try:
        if raw is None:
            return 30 * 60
        return max(60, int(raw))
    except Exception:
        return 30 * 60


def _request_is_https(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if xf_proto:
        return xf_proto == "https"
    return (request.url.scheme or "").lower() == "https"


def _token_from_request(request: Request) -> str:
    header_token = (request.headers.get("x-dashboard-token") or "").strip()
    if header_token:
        return header_token
    return (request.query_params.get("token") or "").strip()


def _maybe_set_dashboard_cookie_from_token(request: Request, response: Response) -> None:
    required = _dashboard_token_required()
    if not required:
        return

    presented = _token_from_request(request)
    if not presented:
        return

    if presented != required:
        return

    response.set_cookie(
        key=_dashboard_cookie_name(),
        value=required,
        max_age=_dashboard_cookie_ttl_seconds(),
        httponly=True,
        samesite="lax",
        secure=_request_is_https(request),
        path="/",
    )


def _require_dashboard_auth(request: Request) -> None:
    required = _dashboard_token_required()
    if not required:
        return

    # Allow either header auth, query param, or an HttpOnly cookie.
    presented = _token_from_request(request)
    if presented == required:
        return

    cookie_val = (request.cookies.get(_dashboard_cookie_name()) or "").strip()
    if cookie_val == required:
        return
    raise HTTPException(status_code=401, detail="Dashboard token required")


@app.middleware("http")
async def analytics_middleware(request: Request, call_next):
    start = time.perf_counter()

    path = request.url.path
    # Keep noise down.
    if path.startswith("/static") or path in {"/favicon.ico"}:
        return await call_next(request)

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        client_ip = extract_client_ip(dict(request.headers), getattr(request.client, "host", None))
        country = extract_country(dict(request.headers))

        record_request(
            method=request.method,
            path=path,
            status_code=500,
            duration_ms=duration_ms,
            client_ip=client_ip,
            country=country,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
        )
        raise

    duration_ms = int((time.perf_counter() - start) * 1000)
    client_ip = extract_client_ip(dict(request.headers), getattr(request.client, "host", None))
    country = extract_country(dict(request.headers))

    record_request(
        method=request.method,
        path=path,
        status_code=getattr(response, "status_code", 200),
        duration_ms=duration_ms,
        client_ip=client_ip,
        country=country,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )
    return response


def _normalize_asset_mode(asset_mode: str) -> str:
    """Normalize asset mode values to the library's expected vocabulary."""
    normalized = (asset_mode or "").strip().lower()
    if normalized in {"vendored", "cdn", "none"}:
        return normalized
    # Back-compat / forgiving parsing
    if normalized in {"vendor", "embedded", "inline"}:
        return "vendored"
    return "vendored"


def _form_mapping():
    """Central mapping for both HTML routes and JSON API endpoints."""
    return {
        "login": MinimalLoginForm,
        "register": UserRegistrationForm,
        "user": UserRegistrationForm,  # alias route in this demo
        "contact": ContactForm,
        "pets": PetRegistrationForm,
        "showcase": CompleteShowcaseForm,
        "layouts": LayoutDemonstrationForm,
        "self-contained": UserRegistrationForm,
    }


# Setup directories
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Setup templating
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Custom JSON filter for templates
def safe_json_filter(obj):
    """Custom JSON filter that handles date/datetime objects."""
    from datetime import date, datetime

    def json_serial(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        elif hasattr(o, "__class__") and "Layout" in o.__class__.__name__:
            return {
                "type": o.__class__.__name__,
                "description": f"Layout object: {o.__class__.__name__}",
            }
        elif hasattr(o, "__dict__"):
            return str(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, indent=2, default=json_serial)


templates.env.filters["safe_json"] = safe_json_filter

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_referer_path(request: Request) -> str:
    """Get referer path from request."""
    referer = request.headers.get("referer", "/")
    if referer:
        parsed_referer = urlparse(referer)
        referer_path = parsed_referer.path
        referer_query = parsed_referer.query
        full_referer_path = f"{referer_path}?{referer_query}" if referer_query else referer_path
        return full_referer_path
    return "/"


# ============================================================================
# HOME PAGE
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page showcasing all form examples."""
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "request": request,
            "framework": "fastapi",
            "framework_name": "FastAPI",
            "framework_type": "async",
            "lib_version": pydantic_schemaforms.__version__,
        },
    )


# ============================================================================
# LOGIN FORM - SIMPLE
# ============================================================================


@app.get("/login", response_class=HTMLResponse)
async def login_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """Login form page (GET)."""
    form_data = {}
    if demo:
        form_data = {"username": "demo_user", "password": "demo_pass", "remember_me": True}

    form_html = render_form_html(
        MinimalLoginForm,
        framework=style,
        form_data=form_data,
        submit_url="/login",
        debug=debug,
    )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "Login - Simple Form",
            "description": "Demonstrates basic form fields and validation",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
            "form_action": "/login",
            "form_method": "post",
        },
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Login form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(MinimalLoginForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Login Successful",
                "message": f"Welcome {result['data']['username']}!",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        form_html = render_form_html(
            MinimalLoginForm,
            framework=style,
            form_data=form_dict,
            errors=result["errors"],
            submit_url="/login",
            debug=debug,
        )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "Login - Simple Form",
                "description": "Demonstrates basic form fields and validation",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": result["errors"],
                "form_action": "/login",
                "form_method": "post",
            },
        )


# ============================================================================
# REGISTRATION FORM - MEDIUM
# ============================================================================


@app.get("/register", response_class=HTMLResponse)
async def register_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """User registration form page (GET)."""
    form_data = {}
    if demo:
        form_data = {
            "username": "alex_johnson",
            "email": "alex.johnson@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "age": 28,
            "role": "user",
        }

    form_html = render_form_html(
        UserRegistrationForm,
        framework=style,
        form_data=form_data,
        submit_url="/register",
        debug=debug,
    )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "User Registration - Medium Form",
            "description": "Demonstrates multiple field types and validation",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
            "form_action": "/register",
            "form_method": "post",
        },
    )


@app.post("/register", response_class=HTMLResponse)
async def register_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """User registration form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(UserRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Successful",
                "message": f"Welcome {result['data']['username']}! Your account has been created.",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        form_html = render_form_html(
            UserRegistrationForm,
            framework=style,
            form_data=form_dict,
            errors=result["errors"],
            submit_url="/register",
            debug=debug,
        )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "User Registration - Medium Form",
                "description": "Demonstrates multiple field types and validation",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": result["errors"],
                "form_action": "/register",
                "form_method": "post",
            },
        )


# ============================================================================
# USER ENDPOINT - ALIAS FOR REGISTRATION
# ============================================================================


@app.get("/user", response_class=HTMLResponse)
async def user_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """Alias for user registration form."""
    form_data = {}
    if demo:
        form_data = {
            "username": "alex_johnson",
            "email": "alex.johnson@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "age": 28,
            "role": "user",
        }

    form_html = render_form_html(
        UserRegistrationForm,
        framework=style,
        form_data=form_data,
        submit_url="/user",
        debug=debug,
    )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "User Registration - Medium Form",
            "description": "Demonstrates multiple field types and validation",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
            "form_action": "/user",
            "form_method": "post",
        },
    )


@app.post("/user", response_class=HTMLResponse)
async def user_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Alias for user registration form submission."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(UserRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Successful",
                "message": f"Welcome {result['data']['username']}! Your account has been created.",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        form_html = render_form_html(
            UserRegistrationForm,
            framework=style,
            form_data=form_dict,
            errors=result["errors"],
            submit_url="/user",
            debug=debug,
        )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "User Registration - Medium Form",
                "description": "Demonstrates multiple field types and validation",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": result["errors"],
                "form_action": "/user",
                "form_method": "post",
            },
        )


# ============================================================================
# CONTACT FORM
# ============================================================================


@app.get("/contact", response_class=HTMLResponse)
async def contact_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """Contact form page (GET)."""
    form_data = {}
    if demo:
        form_data = {
            "name": "Jordan Smith",
            "email": "jordan.smith@example.com",
            "subject": "Product Inquiry - Premium Features",
            "priority": "medium",
            "message": "Hello! I'm interested in learning more about your premium features and pricing options. Could you please provide detailed information about the enterprise plan and any volume discounts available? Thank you!",
        }

    form_html = render_form_html(
        ContactForm,
        framework=style,
        form_data=form_data,
        submit_url="/contact",
        debug=debug,
    )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "Contact Us",
            "description": "Get in touch with us about pydantic-schemaforms",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
            "form_action": "/contact",
            "form_method": "post",
        },
    )


@app.post("/contact", response_class=HTMLResponse)
async def contact_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Contact form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(ContactForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Message Sent",
                "message": "Thank you for contacting us! We'll get back to you soon.",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        form_html = render_form_html(
            ContactForm,
            framework=style,
            form_data=form_dict,
            errors=result["errors"],
            submit_url="/contact",
            debug=debug,
        )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "Contact Us",
                "description": "Get in touch with us about pydantic-schemaforms",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": result["errors"],
                "form_action": "/contact",
                "form_method": "post",
            },
        )


# ============================================================================
# PET REGISTRATION FORM - COMPLEX
# ============================================================================


@app.get("/pets", response_class=HTMLResponse)
async def pets_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """Pet registration form page (GET)."""
    form_data = {}
    if demo:
        form_data = {
            "owner_name": "Sarah Mitchell",
            "email": "sarah.mitchell@example.com",
            "address": "123 Main Street\r\nApt 4B\r\nSpringfield, IL 62701",
            "emergency_contact": "John Mitchell - (555) 123-4567",
            "pets": [
                {
                    "name": "Max",
                    "species": "Dog",
                    "age": 3,
                    "weight": 65.5,
                    "is_vaccinated": False,
                    "microchipped": True,
                    "breed": "Golden Retriever",
                    "color": "#000000",
                    "last_vet_visit": "2026-01-03",
                    "special_needs": "Allergic to chicken-based foods",
                },
                {
                    "name": "Luna",
                    "species": "Dog",
                    "age": 2,
                    "weight": 8.5,
                    "is_vaccinated": False,
                    "microchipped": True,
                    "breed": "Siamese",
                    "color": "#000000",
                    "last_vet_visit": "2026-01-04",
                    "special_needs": "Indoor only, needs daily medication for thyroid",
                },
            ],
        }

    form_html = render_form_html(
        PetRegistrationForm,
        framework=style,
        form_data=form_data,
        submit_url="/pets",
        debug=debug,
    )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "Pet Registration - Complex Form",
            "description": "Demonstrates model lists and nested forms",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
            "form_action": "/pets",
            "form_method": "post",
        },
    )


@app.post("/pets", response_class=HTMLResponse)
async def pets_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Pet registration form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(PetRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Complete",
                "message": f"Thank you {result['data']['owner_name']}! Your pets have been registered.",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        form_html = render_form_html(
            PetRegistrationForm,
            framework=style,
            form_data=form_dict,
            errors=result["errors"],
            submit_url="/pets",
            debug=debug,
        )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "Pet Registration - Complex Form",
                "description": "Demonstrates model lists and nested forms",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": result["errors"],
                "form_action": "/pets",
                "form_method": "post",
            },
        )


# ============================================================================
# COMPLETE SHOWCASE FORM
# ============================================================================


@app.get("/showcase", response_class=HTMLResponse)
async def showcase_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """Complete showcase form page (GET)."""
    form_data = {}
    if demo:
        form_data = {
            "first_name": "Alex",
            "last_name": "Johnson",
            "email": "alex.johnson@example.com",
            "phone": "+1 (555) 234-5678",
            "birth_date": "1995-06-15",
            "age": 28,
            "favorite_color": "#3498db",
            "experience_level": "intermediate",
            "newsletter_subscription": True,
            "rating": 8,
            "address": "456 Oak Avenue\nUnit 12\nDowntown District",
            "country": "US",
            "pets": [
                {
                    "name": "Buddy",
                    "species": "dog",
                    "breed": "Labrador",
                    "age": 4,
                    "weight": 70.0,
                    "microchipped": True,
                    "vaccination_date": "2024-03-10",
                    "special_needs": "Needs hip medication twice daily",
                },
                {
                    "name": "Whiskers",
                    "species": "cat",
                    "breed": "Maine Coon",
                    "age": 5,
                    "weight": 12.5,
                    "microchipped": True,
                    "vaccination_date": "2024-04-05",
                    "special_needs": "Requires grain-free diet",
                },
            ],
            "emergency_contacts": [
                {
                    "name": "Emma Johnson",
                    "relationship": "spouse",
                    "phone": "+1 (555) 345-6789",
                    "email": "emma.johnson@example.com",
                    "available_24_7": True,
                },
                {
                    "name": "Robert Johnson",
                    "relationship": "parent",
                    "phone": "+1 (555) 456-7890",
                    "email": "robert.johnson@example.com",
                    "available_24_7": False,
                },
            ],
            "special_requests": "Please contact me via email for all communications. I work night shifts and may not be available by phone during the day.",
            "terms_accepted": True,
        }

    form_html = render_form_html(
        CompleteShowcaseForm,
        framework=style,
        form_data=form_data,
        submit_url="/showcase",
        debug=debug,
    )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "Complete Showcase - Complex Form",
            "description": "Demonstrates ALL library features: model lists, sections, all input types",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
            "form_action": "/showcase",
            "form_method": "post",
        },
    )


@app.post("/showcase", response_class=HTMLResponse)
async def showcase_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Complete showcase form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(CompleteShowcaseForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Showcase Form Submitted Successfully",
                "message": "All form data processed successfully!",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        form_html = render_form_html(
            CompleteShowcaseForm,
            framework=style,
            form_data=form_dict,
            errors=result["errors"],
            submit_url="/showcase",
            debug=debug,
        )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "Complete Showcase - Complex Form",
                "description": "Demonstrates ALL library features: model lists, sections, all input types",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": result["errors"],
                "form_action": "/showcase",
                "form_method": "post",
            },
        )


# ============================================================================
# LAYOUT DEMONSTRATION FORM
# ============================================================================


@app.get("/layouts", response_class=HTMLResponse)
async def layouts_get(
    request: Request,
    style: str = "bootstrap",
    demo: bool = True,
    debug: bool = False,
):
    """Layout demonstration form page (GET)."""
    form_data = {}
    if demo:
        form_data = {
            "vertical_tab": {
                "first_name": "Alex",
                "last_name": "Johnson",
                "email": "alex.johnson@example.com",
                "birth_date": "1990-05-15",
            },
            "horizontal_tab": {
                "phone": "+1 (555) 987-6543",
                "address": "456 Demo Street",
                "city": "San Francisco",
                "postal_code": "94102",
            },
            "tabbed_tab": {
                "notification_email": True,
                "notification_sms": False,
                "theme": "dark",
                "language": "en",
            },
            "list_tab": {
                "project_name": "Website Redesign Project",
                "tasks": [
                    {
                        "task_name": "Complete project setup and requirements gathering",
                        "priority": "high",
                        "due_date": "2024-12-01",
                        "completed": False,
                    },
                    {
                        "task_name": "Design mockups and wireframes",
                        "priority": "medium",
                        "due_date": "2024-12-15",
                        "completed": False,
                    },
                ],
            },
        }

    if style == "material":
        renderer = SimpleMaterialRenderer()
        form_html = renderer.render_form_from_model(
            LayoutDemonstrationForm,
            data=form_data,
            errors={},
            submit_url=f"/layouts?style={style}",
            include_submit_button=True,
            debug=debug,
        )
    else:
        renderer = EnhancedFormRenderer(framework=style)
        form_html = renderer.render_form_from_model(
            LayoutDemonstrationForm,
            data=form_data,
            errors={},
            submit_url=f"/layouts?style={style}",
            include_submit_button=True,
            debug=debug,
        )

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "request": request,
            "title": "Layout Demonstration - All Types",
            "description": "Single form showcasing Vertical, Horizontal, Tabbed, and List layouts",
            "framework": "fastapi",
            "framework_name": "FastAPI (Async)",
            "framework_type": style,
            "form_html": form_html,
        },
    )


@app.post("/layouts", response_class=HTMLResponse)
async def layouts_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Layout demonstration form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)
    full_referer_path = get_referer_path(request)

    try:
        parsed_data = parse_nested_form_data(form_dict)

        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Layout Demo Submitted Successfully",
                "message": "All layout types processed successfully!",
                "data": parsed_data,
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    except Exception as e:
        if style == "material":
            renderer = SimpleMaterialRenderer()
            form_html = renderer.render_form_from_model(
                LayoutDemonstrationForm,
                data={},
                errors={"form": str(e)},
                submit_url=f"/layouts?style={style}",
                include_submit_button=True,
                debug=debug,
            )
        else:
            renderer = EnhancedFormRenderer(framework=style)
            form_html = renderer.render_form_from_model(
                LayoutDemonstrationForm,
                data={},
                errors={"form": str(e)},
                submit_url=f"/layouts?style={style}",
                include_submit_button=True,
                debug=debug,
            )

        return templates.TemplateResponse(
            request,
            "form.html",
            {
                "request": request,
                "title": "Layout Demonstration - Error",
                "description": "Form submission failed",
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "framework_type": style,
                "form_html": form_html,
                "errors": {"form": str(e)},
            },
        )


# ============================================================================
# SELF-CONTAINED FORM DEMO
# ============================================================================


@app.get("/self-contained", response_class=HTMLResponse)
async def self_contained(style: str = "material", demo: bool = True, debug: bool = True):
    """Self-contained form demo - zero external dependencies."""

    def _build_self_contained_page(
        *,
        style: str,
        demo: bool,
        debug: bool,
        form_data: dict | None = None,
        errors: dict | None = None,
    ) -> str:
        style = (style or "").strip().lower()
        if style not in {"bootstrap", "material"}:
            raise HTTPException(status_code=400, detail="style must be 'bootstrap' or 'material'")

        if form_data is None:
            form_data = {}
            if demo:
                form_data = {
                    "username": "alex_demo_user",
                    "email": "alex.demo@example.com",
                    "password": "SecurePass123!",
                    "confirm_password": "SecurePass123!",
                    "age": 28,
                    "role": "user",
                }

        # Render with vendored (inlined) assets for a truly self-contained page.
        # - Bootstrap: inlines vendored Bootstrap CSS/JS.
        # - Material: renderer already embeds its required assets.
        form_html = render_form_html(
            UserRegistrationForm,
            framework=style,
            form_data=form_data,
            errors=errors or {},
            submit_url=f"/self-contained?style={style}&demo={str(bool(demo)).lower()}&debug={str(bool(debug)).lower()}",
            debug=debug,
            self_contained=True,
        )

        style_name = "Material Design 3" if style == "material" else "Bootstrap 5"
        source_url = f"/self-contained/source?style={style}&demo={str(bool(demo)).lower()}&debug={str(bool(debug)).lower()}"

        error_html = ""
        if errors:
            error_items = "".join(f"<li>{k}: {v}</li>" for k, v in errors.items())
            error_html = (
                "<div style='background: #fee; padding: 15px; border-radius: 8px; margin-bottom: 20px;'>"
                "<strong>⚠️ Validation Errors:</strong><ul>"
                f"{error_items}"
                "</ul></div>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Self-Contained Form Demo - {style_name}</title>
</head>
<body style="max-width: 600px; margin: 50px auto; padding: 20px; font-family: system-ui;">
    <h1>🎯 Self-Contained Form Demo (FastAPI)</h1>
    <p><strong>This form includes ZERO external dependencies!</strong></p>
    <p>Current style: <strong>{style_name}</strong></p>
    <p>Everything needed is embedded in the form HTML below:</p>

    <div style="margin: 10px 0 20px; text-align: center;">
        <a href="{source_url}" style="display: inline-block; padding: 8px 16px; margin: 0 5px; background: #111827; color: white; text-decoration: none; border-radius: 4px;">
            View Source
        </a>
    </div>

    {error_html}

    <div style="margin-bottom: 20px; text-align: center;">
        <a href="/self-contained?style=bootstrap&demo=true&debug=true" 
           style="display: inline-block; padding: 8px 16px; margin: 0 5px; background: {'#0d6efd' if style == 'bootstrap' else '#6c757d'}; color: white; text-decoration: none; border-radius: 4px;">
            Bootstrap
        </a>
        <a href="/self-contained?style=material&demo=true&debug=true" 
           style="display: inline-block; padding: 8px 16px; margin: 0 5px; background: {'#1976d2' if style == 'material' else '#6c757d'}; color: white; text-decoration: none; border-radius: 4px;">
            Material
        </a>
    </div>

    <div style="border: 2px solid #dee2e6; border-radius: 8px; padding: 20px; background: #f8f9fa;">
        {form_html}
    </div>

    <div style="margin-top: 30px; padding: 20px; background: #e7f3ff; border-radius: 8px;">
        <h3>🔧 What's Included:</h3>
        <ul>
            <li>✅ Complete {style_name} CSS</li>
            <li>✅ JavaScript for interactions</li>
            <li>✅ Icons (inline SVG)</li>
            <li>✅ Form validation and styling</li>
            <li>✅ No external CDN dependencies</li>
        </ul>
        <p><strong>Template Usage:</strong> <code>&lt;div&gt;{{{{ form_html | safe }}}}&lt;/div&gt;</code></p>
    </div>

    <div style="text-align: center; margin-top: 30px;">
        <a href="/" style="color: #0066cc; text-decoration: none;">← Back to FastAPI Examples</a>
    </div>
</body>
</html>"""

    return _build_self_contained_page(style=style, demo=demo, debug=debug)


@app.get("/self-contained/source", response_class=PlainTextResponse)
async def self_contained_source(style: str = "material", demo: bool = True, debug: bool = True):
    """Return the self-contained HTML page as plain text (easy to copy/paste)."""
    # Reuse the same HTML that /self-contained returns, but return it as text.
    page_html = await self_contained(style=style, demo=demo, debug=debug)
    return PlainTextResponse(page_html)


@app.post("/self-contained", response_class=HTMLResponse)
async def self_contained_post(request: Request, style: str = "material", debug: bool = False):
    """Handle self-contained form submission."""
    style = (style or "").strip().lower()
    if style not in {"bootstrap", "material"}:
        raise HTTPException(status_code=400, detail="style must be 'bootstrap' or 'material'")

    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(UserRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result["success"]:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Successful",
                "message": f"Welcome {result['data']['username']}! Your self-contained form submission was successful.",
                "data": result["data"],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path,
            },
        )
    else:
        # Re-render as a self-contained page including the validation errors.
        # Note: demo=False because user supplied real values.
        return await self_contained(style=style, demo=False, debug=debug)


# =========================================================================
# API ENDPOINTS (JSON RESPONSES)
# =========================================================================


@app.get("/api/forms/{form_type}/schema")
async def api_form_schema(form_type: str):
    """API endpoint to get a form schema as JSON."""
    mapping = _form_mapping()
    if form_type not in mapping:
        raise HTTPException(status_code=404, detail="Form type not found")

    form_class = mapping[form_type]
    schema = form_class.model_json_schema()

    return {
        "form_type": form_type,
        "schema": schema,
        "framework": "fastapi",
    }


@app.post("/api/forms/{form_type}/submit")
async def api_submit_form(form_type: str, request: Request):
    """API endpoint for JSON form submissions."""
    mapping = _form_mapping()
    if form_type not in mapping:
        raise HTTPException(status_code=404, detail="Form type not found")

    form_class = mapping[form_type]
    json_data = await request.json()
    result = handle_form_submission(form_class, json_data)

    return {
        "success": result["success"],
        "data": result["data"] if result["success"] else None,
        "errors": result["errors"],
        "framework": "fastapi",
    }


@app.get("/api/forms/{form_type}/render")
async def api_render_form(
    form_type: str,
    style: str = "bootstrap",
    debug: bool = False,
    include_assets: bool = True,
    asset_mode: str = "vendored",
):
    """API endpoint to render form HTML."""
    mapping = _form_mapping()
    if form_type not in mapping:
        raise HTTPException(status_code=404, detail="Form type not found")

    style = (style or "").strip().lower()
    if style not in {"bootstrap", "material", "none"}:
        raise HTTPException(
            status_code=400, detail="style must be 'bootstrap', 'material', or 'none'"
        )

    form_class = mapping[form_type]
    html = render_form_html(
        form_class,
        framework=style,
        debug=debug,
        include_framework_assets=include_assets,
        asset_mode=_normalize_asset_mode(asset_mode),
    )

    return {
        "form_type": form_type,
        "style": style,
        "html": html,
        "framework": "fastapi",
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": pydantic_schemaforms.__version__,
    }


# =========================================================================
# ANALYTICS DASHBOARD
# =========================================================================


@app.get("/api/analytics/summary")
async def api_analytics_summary(request: Request, days: int = 1, top_n: int = 10):
    _require_dashboard_auth(request)
    summary = get_summary(days=days, top_n=top_n)
    return {
        "since": summary.since_iso,
        "total_requests": summary.total_requests,
        "unique_ips": summary.unique_ips,
        "avg_duration_ms": summary.avg_duration_ms,
        "top_paths": summary.top_paths,
        "status_counts": summary.status_counts,
        "browser_counts": summary.browser_counts,
    }


@app.get("/api/analytics/requests")
async def api_analytics_requests(request: Request, limit: int = 200):
    _require_dashboard_auth(request)
    return {"requests": get_recent_requests(limit=min(max(limit, 1), 1000))}


@app.get("/api/analytics/errors")
async def api_analytics_errors(request: Request, limit: int = 200):
    _require_dashboard_auth(request)
    return {"errors": get_recent_errors(limit=min(max(limit, 1), 1000))}


@app.post("/api/analytics/purge")
async def api_analytics_purge(request: Request):
    _require_dashboard_auth(request)
    purge_all()
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, days: int = 1, limit: int = 50):
    # If a valid token is presented, set/refresh a 30-min cookie and redirect
    # to a clean URL (so the token doesn't stay in the address bar).
    required = _dashboard_token_required()
    presented = _token_from_request(request)
    if required and presented:
        if presented != required:
            raise HTTPException(status_code=401, detail="Dashboard token required")

        params = dict(request.query_params)
        params.pop("token", None)
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None and v != "")
        url = "/dashboard" + (f"?{query}" if query else "")

        resp = RedirectResponse(url=url, status_code=303)
        _maybe_set_dashboard_cookie_from_token(request, resp)
        return resp

    _require_dashboard_auth(request)

    summary = get_summary(days=days, top_n=10)
    recent = get_recent_requests(limit=min(max(limit, 1), 500))
    recent_errors = get_recent_errors(limit=50)

    token_required = _dashboard_token_required() is not None
    ttl_min = int(_dashboard_cookie_ttl_seconds() / 60)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "summary": summary,
            "recent": recent,
            "recent_errors": recent_errors,
            "token_required": token_required,
            "ttl_min": ttl_min,
        },
    )


@app.get("/dashboard/logout")
async def dashboard_logout(request: Request):
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(key=_dashboard_cookie_name(), path="/")
    return resp


# ============================================================================
# ERROR HANDLERS
# ============================================================================


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors."""
    return templates.TemplateResponse(request, "404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Handle 500 errors."""
    return templates.TemplateResponse(
        request, "500.html", {"request": request, "error": str(exc)}, status_code=500
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Capture unhandled exceptions for the dashboard."""
    client_ip = extract_client_ip(dict(request.headers), getattr(request.client, "host", None))
    record_error(
        kind=exc.__class__.__name__,
        message=str(exc) or exc.__class__.__name__,
        detail=traceback.format_exc(),
        path=request.url.path,
        method=request.method,
        status_code=500,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )

    return templates.TemplateResponse(
        request,
        "500.html",
        {"request": request, "error": str(exc)},
        status_code=500,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
