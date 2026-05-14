from fastapi import APIRouter
from fastapi import HTTPException, status

from backend.schemas import AnswerRequest, DiagnoseRequest, DiagnosisStartRequest, DiagnosisTreeAnswerRequest
from backend.services.diagnosis_service import DiagnosisService
from backend.services.session_service import SessionService


router = APIRouter(tags=["diagnosis"])


def _input_text(payload: DiagnoseRequest):
    user_input = payload.symptom or payload.user_input or payload.text
    if not user_input:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either user_input or text.",
        )
    return user_input


@router.post("/api/diagnose")
@router.post("/diagnose")
def diagnose(payload: DiagnoseRequest):
    if payload.session_id:
        if hasattr(payload, "model_fields_set"):
            fields_set = payload.model_fields_set
        else:
            fields_set = getattr(payload, "__fields_set__", set())
        return DiagnosisService().diagnose(
            payload.symptom or payload.user_input or payload.text,
            payload.top_k,
            session_id=payload.session_id,
            step_answer=payload.step_answer,
            step_answer_provided="step_answer" in fields_set,
        )
    return DiagnosisService().diagnose(_input_text(payload), payload.top_k)


@router.post("/api/answer")
def answer(payload: AnswerRequest):
    return DiagnosisService().answer(payload.session_id, payload.answer)


@router.post("/api/diagnosis/start")
def start_diagnosis(payload: DiagnosisStartRequest):
    return DiagnosisService().start_decision_tree(payload.description, payload.top_k)


@router.post("/api/diagnosis/answer")
def answer_diagnosis_tree(payload: DiagnosisTreeAnswerRequest):
    return DiagnosisService().answer_decision_tree(
        payload.session_id,
        payload.node_id,
        payload.answer,
    )


@router.post("/session/new")
@router.post("/api/session/new")
def new_session():
    return {"session_id": SessionService().create_empty()}


@router.get("/session/{session_id}")
@router.get("/api/session/{session_id}")
def get_session(session_id: str):
    session = SessionService().get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnosis session was not found.",
        )
    return session


@router.delete("/session/{session_id}")
@router.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    deleted = SessionService().delete(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnosis session was not found.",
        )
    return {"deleted": True, "session_id": session_id}
