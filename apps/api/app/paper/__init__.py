"""Local paper trading read-only API (Prompt 65B). Default OFF."""

from apps.api.app.paper.router import router

__all__ = ["router"]
