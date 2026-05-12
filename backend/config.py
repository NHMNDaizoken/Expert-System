import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    admin_api_key = os.getenv("ADMIN_API_KEY")
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    frontend_origins = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            ",".join(
                [
                    frontend_origin,
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                ]
            ),
        ).split(",")
        if origin.strip()
    ]
    sqlite_db_path = PROJECT_ROOT / os.getenv(
        "SQLITE_DB_PATH",
        "data/app.sqlite3",
    )


settings = Settings()
