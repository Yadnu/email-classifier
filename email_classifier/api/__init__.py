"""FastAPI application with /classify (metrics land in Stage 4)."""

from email_classifier.api.app import app as fastapi_app

__all__ = ["fastapi_app"]
