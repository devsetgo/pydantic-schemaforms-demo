"""
Pydantic SchemaForms Demo - FastAPI Application

A comprehensive demonstration of pydantic-schemaforms capabilities
with all endpoints and models from the examples consolidated.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
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

# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="Pydantic SchemaForms Demo",
    description="Comprehensive showcase of pydantic-schemaforms capabilities in FastAPI",
    version="26.1.1b0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

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
        elif hasattr(o, '__class__') and 'Layout' in o.__class__.__name__:
            return {
                "type": o.__class__.__name__,
                "description": f"Layout object: {o.__class__.__name__}"
            }
        elif hasattr(o, '__dict__'):
            return str(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, indent=2, default=json_serial)


templates.env.filters['safe_json'] = safe_json_filter

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
            "lib_version": pydantic_schemaforms.__version__
        }
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
        form_data = {
            "username": "demo_user",
            "password": "demo_pass",
            "remember_me": True
        }

    form_html = render_form_html(
        MinimalLoginForm,
        framework=style,
        form_data=form_data,
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
            "form_method": "post"
        }
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Login form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(MinimalLoginForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Login Successful",
                "message": f"Welcome {result['data']['username']}!",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        form_html = render_form_html(
            MinimalLoginForm,
            framework=style,
            form_data=form_dict,
            errors=result['errors'],
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
                "errors": result['errors'],
                "form_action": "/login",
                "form_method": "post"
            }
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
            "role": "user"
        }

    form_html = render_form_html(
        UserRegistrationForm,
        framework=style,
        form_data=form_data,
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
            "form_method": "post"
        }
    )


@app.post("/register", response_class=HTMLResponse)
async def register_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """User registration form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(UserRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Successful",
                "message": f"Welcome {result['data']['username']}! Your account has been created.",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        form_html = render_form_html(
            UserRegistrationForm,
            framework=style,
            form_data=form_dict,
            errors=result['errors'],
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
                "errors": result['errors'],
                "form_action": "/register",
                "form_method": "post"
            }
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
            "role": "user"
        }

    form_html = render_form_html(
        UserRegistrationForm,
        framework=style,
        form_data=form_data,
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
            "form_method": "post"
        }
    )


@app.post("/user", response_class=HTMLResponse)
async def user_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Alias for user registration form submission."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(UserRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Successful",
                "message": f"Welcome {result['data']['username']}! Your account has been created.",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        form_html = render_form_html(
            UserRegistrationForm,
            framework=style,
            form_data=form_dict,
            errors=result['errors'],
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
                "errors": result['errors'],
                "form_action": "/user",
                "form_method": "post"
            }
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
            "name": "Demo User",
            "email": "demo@example.com",
            "subject": "Demo Inquiry",
            "priority": "medium",
            "message": "This is a demo message about pydantic-schemaforms capabilities."
        }

    form_html = render_form_html(
        ContactForm,
        framework=style,
        form_data=form_data,
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
            "form_method": "post"
        }
    )


@app.post("/contact", response_class=HTMLResponse)
async def contact_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Contact form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(ContactForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Message Sent",
                "message": "Thank you for contacting us! We'll get back to you soon.",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        form_html = render_form_html(
            ContactForm,
            framework=style,
            form_data=form_dict,
            errors=result['errors'],
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
                "errors": result['errors'],
                "form_action": "/contact",
                "form_method": "post"
            }
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
            "owner_name": "Pet Owner",
            "email": "pet.owner@example.com",
            "pets": []
        }

    form_html = render_form_html(
        PetRegistrationForm,
        framework=style,
        form_data=form_data,
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
            "form_method": "post"
        }
    )


@app.post("/pets", response_class=HTMLResponse)
async def pets_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Pet registration form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(PetRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Complete",
                "message": f"Thank you {result['data']['owner_name']}! Your pets have been registered.",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        form_html = render_form_html(
            PetRegistrationForm,
            framework=style,
            form_data=form_dict,
            errors=result['errors'],
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
                "errors": result['errors'],
                "form_action": "/pets",
                "form_method": "post"
            }
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
            "age": 28,
            "experience_level": "intermediate"
        }

    form_html = render_form_html(
        CompleteShowcaseForm,
        framework=style,
        form_data=form_data,
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
            "form_method": "post"
        }
    )


@app.post("/showcase", response_class=HTMLResponse)
async def showcase_post(request: Request, style: str = "bootstrap", debug: bool = False):
    """Complete showcase form submission (POST)."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(CompleteShowcaseForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Showcase Form Submitted Successfully",
                "message": "All form data processed successfully!",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        form_html = render_form_html(
            CompleteShowcaseForm,
            framework=style,
            form_data=form_dict,
            errors=result['errors'],
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
                "errors": result['errors'],
                "form_action": "/showcase",
                "form_method": "post"
            }
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
                "birth_date": "1990-05-15"
            },
            "horizontal_tab": {
                "phone": "+1 (555) 987-6543",
                "address": "456 Demo Street",
                "city": "San Francisco",
                "postal_code": "94102"
            },
            "tabbed_tab": {
                "notification_email": True,
                "notification_sms": False,
                "theme": "dark",
                "language": "en"
            },
            "list_tab": {
                "project_name": "Demo Project",
                "tasks": [
                    {
                        "task_name": "Complete project setup",
                        "priority": "high",
                        "due_date": "2024-12-01"
                    }
                ]
            }
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
            "form_html": form_html
        }
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
                "try_again_url": full_referer_path
            }
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
                "errors": {"form": str(e)}
            }
        )


# ============================================================================
# SELF-CONTAINED FORM DEMO
# ============================================================================

@app.get("/self-contained", response_class=HTMLResponse)
async def self_contained(demo: bool = True, debug: bool = True):
    """Self-contained form demo - zero external dependencies."""
    form_data = {}
    if demo:
        form_data = {
            "username": "self_contained_user",
            "email": "selfcontained@example.com",
            "password": "DemoPass123!",
            "confirm_password": "DemoPass123!",
        }

    renderer = SimpleMaterialRenderer()
    form_html = renderer.render_form_from_model(
        UserRegistrationForm, 
        data=form_data, 
        submit_url="/self-contained",
        include_submit_button=True,
        debug=debug
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Self-Contained Form Demo</title>
</head>
<body style="max-width: 600px; margin: 50px auto; padding: 20px; font-family: system-ui;">
    <h1>🎯 Self-Contained Form Demo (FastAPI)</h1>
    <p><strong>This form includes ZERO external dependencies!</strong></p>
    <p>Everything needed is embedded in the form HTML below:</p>

    <div style="border: 2px solid #dee2e6; border-radius: 8px; padding: 20px; background: #f8f9fa;">
        {form_html}
    </div>

    <div style="margin-top: 30px; padding: 20px; background: #e7f3ff; border-radius: 8px;">
        <h3>🔧 What's Included:</h3>
        <ul>
            <li>✅ Complete Material Design 3 CSS</li>
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


@app.post("/self-contained", response_class=HTMLResponse)
async def self_contained_post(request: Request, debug: bool = False):
    """Handle self-contained form submission."""
    form_data = await request.form()
    form_dict = dict(form_data)

    result = handle_form_submission(UserRegistrationForm, form_dict)
    full_referer_path = get_referer_path(request)

    if result['success']:
        return templates.TemplateResponse(
            request,
            "success.html",
            {
                "request": request,
                "title": "Registration Successful",
                "message": f"Welcome {result['data']['username']}! Your self-contained form submission was successful.",
                "data": result['data'],
                "framework": "fastapi",
                "framework_name": "FastAPI (Async)",
                "try_again_url": full_referer_path
            }
        )
    else:
        renderer = SimpleMaterialRenderer()
        form_html = renderer.render_form_from_model(
            UserRegistrationForm, 
            data=form_dict, 
            errors=result['errors'],
            submit_url="/self-contained",
            include_submit_button=True,
            debug=debug
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Self-Contained Form Demo</title>
</head>
<body style="max-width: 600px; margin: 50px auto; padding: 20px; font-family: system-ui;">
    <h1>🎯 Self-Contained Form Demo (FastAPI)</h1>
    <p><strong>This form includes ZERO external dependencies!</strong></p>
    
    {"<div style='background: #fee; padding: 15px; border-radius: 8px; margin-bottom: 20px;'><strong>⚠️ Validation Errors:</strong><ul>" + "".join([f"<li>{err}</li>" for err in result['errors']]) + "</ul></div>" if result['errors'] else ""}

    <div style="border: 2px solid #dee2e6; border-radius: 8px; padding: 20px; background: #f8f9fa;">
        {form_html}
    </div>

    <div style="text-align: center; margin-top: 30px;">
        <a href="/" style="color: #0066cc; text-decoration: none;">← Back to FastAPI Examples</a>
    </div>
</body>
</html>"""


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors."""
    return templates.TemplateResponse(
        request,
        "404.html",
        {"request": request},
        status_code=404
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Handle 500 errors."""
    return templates.TemplateResponse(
        request,
        "500.html",
        {"request": request, "error": str(exc)},
        status_code=500
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
