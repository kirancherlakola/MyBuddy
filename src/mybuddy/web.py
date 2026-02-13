from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mybuddy.db import init_db
from mybuddy.routes import actions, contacts, notes

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="MyBuddy")
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    app.state.templates = templates

    app.include_router(notes.router)
    app.include_router(actions.router)
    app.include_router(contacts.router)

    @app.get("/")
    async def index(request: Request):
        return RedirectResponse(url="/notes", status_code=302)

    return app
