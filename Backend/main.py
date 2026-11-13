"""Run locally: python -m uvicorn main:app --reload"""
from api.application import create_app

app = create_app()
