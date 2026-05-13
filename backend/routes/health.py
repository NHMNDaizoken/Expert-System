from fastapi import APIRouter
from neo4j import GraphDatabase

from backend.core.config import settings
from backend.database import get_sqlite_connection


router = APIRouter()


@router.get("/health")
def health_check():
    sqlite_status = "connected"
    neo4j_status = "connected"

    with get_sqlite_connection() as connection:
        connection.execute("SELECT 1").fetchone()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        with driver.session() as session:
            session.run("RETURN 1").single()
    finally:
        driver.close()

    return {
        "status": "ok",
        "neo4j": neo4j_status,
        "sqlite": sqlite_status,
    }
