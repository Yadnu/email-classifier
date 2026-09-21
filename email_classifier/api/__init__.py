"""FastAPI application with /classify and /metrics endpoints."""

from email_classifier.api.app import app as fastapi_app

__all__ = ["fastapi_app"]
