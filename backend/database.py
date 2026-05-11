import sqlite3

from backend.config import settings


def get_sqlite_connection():
    settings.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.sqlite_db_path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_database():
    with get_sqlite_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnosis_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                user_input TEXT NOT NULL,
                confirmed_symptoms TEXT NOT NULL,
                rejected_symptoms TEXT NOT NULL,
                current_hypotheses TEXT NOT NULL,
                reasoning_trace TEXT NOT NULL,
                answers TEXT NOT NULL,
                last_question TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(diagnosis_sessions)").fetchall()
        }
        migrations = {
            "current_step_id": "TEXT",
            "step_history": "TEXT DEFAULT '[]'",
            "branch_path": "TEXT DEFAULT '[]'",
            "last_answer": "TEXT",
            "active_fault_id": "TEXT",
            "total_steps_est": "INTEGER",
        }
        for column, ddl in migrations.items():
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE diagnosis_sessions ADD COLUMN {column} {ddl}")
