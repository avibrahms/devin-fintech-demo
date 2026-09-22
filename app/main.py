"""
Hosting adapter for Devin's FastAPI/Fly.io deployer. It wraps the Django WSGI
application in a FastAPI app named `app`; the portal itself is unchanged.

On start it points the data directory at the mounted volume (if any), runs
migrations and the idempotent demo seed, and marks the process as served over
HTTPS so cookies are Secure. `make run` / runserver do not use this module.
"""
import os
from pathlib import Path

VOLUME = Path("/data")
if VOLUME.is_dir() and os.access(VOLUME, os.W_OK):
    os.environ.setdefault("PORTAL_DATA_DIR", str(VOLUME))
os.environ.setdefault("PORTAL_HTTPS_PROXY", "1")
os.environ.setdefault("PORTAL_DEMO_MODE", "1")  # hosted demo only; never set in production
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", interactive=False, verbosity=0)
call_command("seed_demo", verbosity=0)

from a2wsgi import WSGIMiddleware  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from portal.wsgi import application as django_app  # noqa: E402

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/", WSGIMiddleware(django_app))
