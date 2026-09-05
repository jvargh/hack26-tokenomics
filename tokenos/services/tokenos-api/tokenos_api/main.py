"""Entry point: `python -m uvicorn tokenos_api.main:app --port 8000`."""

from .app import app

__all__ = ["app"]
