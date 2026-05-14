import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.container import container
from backend.database import ensure_database
from backend.routes import diagnosis, expert_review, graph, health, review, debug


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Expert System Engine and Knowledge Base...")
    ensure_database()
    engine = container.get_engine()
    logger.info("Engine initialized successfully.")
    yield
    logger.info("Shutting down Expert System...")
    container.reset_engine()


app = FastAPI(title="Car Diagnostic Expert System API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(diagnosis.router)
app.include_router(graph.router)
app.include_router(review.router)
app.include_router(expert_review.router)
app.include_router(debug.router)
