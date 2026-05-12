import json
from datetime import datetime, timezone
from uuid import uuid4

from backend.database import get_sqlite_connection


JSON_FIELDS = {
    "confirmed_symptoms",
    "rejected_symptoms",
    "current_hypotheses",
    "reasoning_trace",
    "answers",
    "last_question",
    "step_history",
    "branch_path",
}

NEW_SESSION_FIELDS = {
    "current_step_id": None,
    "step_history": [],
    "branch_path": [],
    "last_answer": None,
    "active_fault_id": None,
    "total_steps_est": None,
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def matched_symptom_ids(response):
    return sorted({
        symptom["symptom_id"]
        for symptom in response.get("matched_symptoms", [])
        if symptom.get("symptom_id")
    })


def hypotheses(response):
    return response.get("current_hypotheses") or response.get("results", [])


class SessionService:
    def create(self, user_input, response):
        session_id = str(uuid4())
        now = utc_now()
        last_question = response.get("next_question")
        confirmed = matched_symptom_ids(response)

        with get_sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO diagnosis_sessions (
                    session_id,
                    created_at,
                    updated_at,
                    status,
                    user_input,
                    confirmed_symptoms,
                    rejected_symptoms,
                    current_hypotheses,
                    reasoning_trace,
                    answers,
                    last_question,
                    current_step_id,
                    step_history,
                    branch_path,
                    last_answer,
                    active_fault_id,
                    total_steps_est
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    now,
                    response["status"],
                    user_input,
                    json.dumps(confirmed),
                    json.dumps([]),
                    json.dumps(hypotheses(response)),
                    json.dumps(response.get("reasoning_trace", {})),
                    json.dumps({}),
                    json.dumps(last_question),
                    (last_question or {}).get("step_id"),
                    json.dumps(
                        [(last_question or {}).get("step_id")]
                        if (last_question or {}).get("step_id")
                        else []
                    ),
                    json.dumps([]),
                    None,
                    ((last_question or {}).get("fault_preview") or {}).get("fault_id"),
                    response.get("total_steps_est"),
                ),
            )

        return session_id

    def get(self, session_id):
        with get_sqlite_connection() as connection:
            row = connection.execute(
                "SELECT * FROM diagnosis_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        data = dict(row)
        for field in JSON_FIELDS:
            if field in data and data[field]:
                data[field] = json.loads(data[field])
        for field, default in NEW_SESSION_FIELDS.items():
            data.setdefault(field, default.copy() if isinstance(default, list) else default)
        if isinstance(data.get("last_answer"), str):
            if data["last_answer"] == "true":
                data["last_answer"] = True
            elif data["last_answer"] == "false":
                data["last_answer"] = False
            elif data["last_answer"] == "null":
                data["last_answer"] = None
        return data

    def delete(self, session_id):
        with get_sqlite_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM diagnosis_sessions WHERE session_id = ?",
                (session_id,),
            )
        return cursor.rowcount > 0

    def update_from_response(self, session_id, response, answers, user_input=None):
        confirmed = list(response.get("confirmed_symptoms") or matched_symptom_ids(response))
        rejected = list(response.get("rejected_symptoms") or [])

        for symptom, answer in answers.items():
            if answer:
                confirmed.append(symptom)
            else:
                rejected.append(symptom)

        previous = self.get(session_id) or {}
        previous_question = previous.get("last_question") or {}

        next_question = response.get("next_question")

        if response.get("status") == "need_more_info":
            if not next_question:
                response["status"] = "diagnosed"
                response["is_final"] = True
                response["results"] = (
                    response.get("results")
                    or response.get("current_hypotheses")
                    or response.get("diagnoses")
                    or []
                )
                next_question = None
        else:
            next_question = None

        current_step_id = None
        if next_question:
            current_step_id = next_question.get("step_id")

        step_history = list(previous.get("step_history", [])) if previous else []
        branch_path = list(previous.get("branch_path", [])) if previous else []

        current_hypotheses = response.get("current_hypotheses") or response.get("diagnoses") or []
        detected_systems = response.get("detected_systems") or previous.get("detected_systems", [])
        primary_symptom = response.get("primary_symptom") or previous.get("primary_symptom")

        active_fault_id = None
        if next_question:
            fault_preview = next_question.get("fault_preview") or {}
            active_fault_id = fault_preview.get("fault_id")

        if not active_fault_id and current_hypotheses:
            active_fault_id = current_hypotheses[0].get("fault_id")

        with get_sqlite_connection() as connection:
            connection.execute(
                """
                UPDATE diagnosis_sessions
                SET updated_at = ?,
                    status = ?,
                    user_input = ?,
                    confirmed_symptoms = ?,
                    rejected_symptoms = ?,
                    current_hypotheses = ?,
                    reasoning_trace = ?,
                    answers = ?,
                    last_question = ?,
                    current_step_id = ?,
                    step_history = ?,
                    branch_path = ?,
                    active_fault_id = ?,
                    total_steps_est = ?
                WHERE session_id = ?
                """,
                (
                    utc_now(),
                    response["status"],
                    user_input if user_input is not None else previous.get("user_input", ""),
                    json.dumps(sorted(set(confirmed))),
                    json.dumps(sorted(set(rejected))),
                    json.dumps(current_hypotheses),
                    json.dumps(response.get("reasoning_trace", {})),
                    json.dumps(answers),
                    json.dumps(next_question),
                    current_step_id,
                    json.dumps(step_history),
                    json.dumps(branch_path),
                    active_fault_id,
                    response.get("total_steps_est"),
                    session_id,
                ),
            )

    def create_empty(self):
        session_id = str(uuid4())
        now = utc_now()
        with get_sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO diagnosis_sessions (
                    session_id, created_at, updated_at, status, user_input,
                    confirmed_symptoms, rejected_symptoms, current_hypotheses,
                    reasoning_trace, answers, last_question, current_step_id,
                    step_history, branch_path, last_answer, active_fault_id,
                    total_steps_est
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    now,
                    "new",
                    "",
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps({}),
                    json.dumps({}),
                    json.dumps(None),
                    None,
                    json.dumps([]),
                    json.dumps([]),
                    None,
                    None,
                    None,
                ),
            )
        return session_id

    def update_step_state(self, session_id, step_id, answer):
        session = self.get(session_id)
        if session is None:
            return None
        history = list(session.get("step_history", []))
        if step_id and step_id not in history:
            history.append(step_id)
        branch_path = list(session.get("branch_path", []))
        if step_id is not None:
            branch_path.append({"step_id": step_id, "answer": answer})

        with get_sqlite_connection() as connection:
            connection.execute(
                """
                UPDATE diagnosis_sessions
                SET updated_at = ?,
                    current_step_id = ?,
                    step_history = ?,
                    branch_path = ?,
                    last_answer = ?
                WHERE session_id = ?
                """,
                (
                    utc_now(),
                    step_id,
                    json.dumps(history),
                    json.dumps(branch_path),
                    "true" if answer is True else "false" if answer is False else "null",
                    session_id,
                ),
            )
        return self.get(session_id)
