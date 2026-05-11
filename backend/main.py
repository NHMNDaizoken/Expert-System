from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import ensure_database
from backend.routes import diagnosis, graph, health, review


ensure_database()

app = FastAPI(title="Car Diagnostic Expert System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(diagnosis.router)
app.include_router(graph.router)
app.include_router(review.router)
