"""Uvicorn entrypoint: ``uv run uvicorn vikat_hire.app.main:app``."""

from vikat_hire.app.composition import create_production_app

app = create_production_app()
