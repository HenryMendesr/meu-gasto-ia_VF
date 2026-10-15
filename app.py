"""Entrada nativa do FastAPI detectada automaticamente pela Vercel."""

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.index import fastapi_app


fastapi_app.mount("/icons", StaticFiles(directory="public/icons"), name="icons")


@fastapi_app.get("/app.css", include_in_schema=False)
def app_css():
    return FileResponse("public/app.css", media_type="text/css")


@fastapi_app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse("public/service-worker.js", media_type="application/javascript", headers={"Cache-Control": "public, max-age=0, must-revalidate", "Service-Worker-Allowed": "/"})


@fastapi_app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse("public/manifest.webmanifest", media_type="application/manifest+json")


@fastapi_app.get("/offline.html", include_in_schema=False)
def offline():
    return FileResponse("public/offline.html", media_type="text/html")


app = fastapi_app
