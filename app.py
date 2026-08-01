"""Local-only HTTP entrypoint for Medical Knowledge Hub."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from routes_ext.knowledge import router as knowledge_router
from routes_ext.platforms import router as platforms_router
from routes_ext.subscriptions import router as subscriptions_router


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
APP_VERSION = "1.1.1"
ACTIVE_PAGES = {
    "admin",
    "inbox",
    "platforms",
    "review",
    "subscriptions",
    "wechat-collect",
}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}


def load_local_env(path: Path) -> None:
    load_dotenv(dotenv_path=path, override=False)


load_local_env(ROOT / ".env")


def _split_env(name: str) -> set[str]:
    return {value.strip() for value in os.getenv(name, "").split(",") if value.strip()}


def get_allowed_browser_origins() -> set[str]:
    defaults = {
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    }
    return defaults | _split_env("CONTENT_HUB_ALLOWED_ORIGINS")


def get_allowed_hosts() -> set[str]:
    return LOOPBACK_HOSTS | _split_env("CONTENT_HUB_ALLOWED_HOSTS")


def resolve_bind_host() -> str:
    requested = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    network_access = os.getenv("ALLOW_NETWORK_ACCESS", "0").strip().lower()
    if requested in LOOPBACK_HOSTS or network_access in {"1", "true", "yes"}:
        return requested
    return "127.0.0.1"


app = FastAPI(
    title="Medical Knowledge Hub",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def protect_local_boundary(request: Request, call_next):
    host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
    if host not in get_allowed_hosts():
        return JSONResponse({"detail": "Untrusted host"}, status_code=400)

    origin = request.headers.get("origin")
    if origin and origin not in get_allowed_browser_origins():
        return JSONResponse({"detail": "Untrusted browser origin"}, status_code=403)

    response = await call_next(request)
    if origin:
        response.headers["access-control-allow-origin"] = origin
        response.headers["vary"] = "Origin"
    return response


app.include_router(platforms_router, prefix="/api/ext")
app.include_router(knowledge_router, prefix="/api/ext")
app.include_router(subscriptions_router, prefix="/api/ext")
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "medical-knowledge-hub",
        "version": APP_VERSION,
    }


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC_ROOT / "admin.html")


@app.get("/{page_name}.html", include_in_schema=False)
async def page(page_name: str):
    if page_name not in ACTIVE_PAGES:
        raise HTTPException(status_code=404, detail="Page not found")
    return FileResponse(STATIC_ROOT / f"{page_name}.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=resolve_bind_host(), port=int(os.getenv("PORT", "5000")))
