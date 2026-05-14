import re
from fastapi import HTTPException, status

from backend.services.diagnosis_normalizer import normalize_diagnosis_response
from backend.services.session_service import SessionService
from backend.core.dependencies import get_engine
from src.expert_system.inference.engine import ExpertSystemEngine
from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.inference.policy import apply_response_policy
from src.expert_system.llm_fallback import diagnose_with_llm, enqueue_llm_suggestion
from src.expert_system.utils.scoring import confidence_label


MIN_CHAT_STEPS = 1

MEANINGFUL_QUESTION_FALLBACK_VI = "Bạn có thể mô tả chi tiết hơn về triệu chứng không?"


def next_question_has_substance(nq) -> bool:
    if nq is None:
        return False
    if isinstance(nq, str):
        return bool(str(nq).strip())
    if isinstance(nq, dict):
        if str(nq.get("question") or "").strip():
            return True
        if str(nq.get("label") or "").strip():
            return True
        if nq.get("step_id") or nq.get("symptom_id"):
            return True
    return bool(nq)


def _extract_patch_next_question(patch: dict) -> dict | None:
    """Build a yes/no next_question dict from llm_kb_patch procedure_trees (legacy / tests)."""
    trees = (patch or {}).get("procedure_trees") or {}
    faults = (patch or {}).get("candidate_faults") or []
    if not trees or not faults:
        return None
    fault_id = faults[0].get("fault_id")
    tree = trees.get(fault_id) if fault_id else None
    if not tree:
        return None
    entry = tree.get("entry_step")
    steps = tree.get("steps") or {}
    step = steps.get(entry) if entry else None
    if not step or not step.get("question"):
        return None
    return {
        "question": step.get("question"),
        "answer_type": "yes_no",
        "source": "llm_fallback_procedure_tree",
        "fault_id": fault_id,
        "step_id": step.get("id") or entry,
    }


def parse_answer(answer):
    normalized = str(answer).strip().lower()
    if normalized in {"yes", "y", "true", "1", "co", "có"}:
        return True
    if normalized in {"no", "n", "false", "0", "khong", "không"}:
        return False
    # If it's a text response, just return it as is or handle it
    return answer

def build_repair_plan(top_result, top_rule, resolution):
    if not top_result or not resolution:
        return None
        
    procedure_text = resolution.get("procedure", "")
    parts_to_inspect = resolution.get("parts", [])
    
    checks = []
    current_action = None
    
    sentences = [s.strip() for s in re.split(r'[\.\n]', procedure_text) if s.strip()]
    
    for sentence in sentences:
        lower_sentence = sentence.lower()
        if lower_sentence.startswith("kết quả có thể:"):
            res = sentence.split(":", 1)[1].strip()
            if current_action:
                meaning = "Cần kiểm tra thêm hoặc thay thế nếu hỏng"
                recommended_fix = "Thực hiện sửa chữa hoặc thay thế linh kiện liên quan"
                
                if any(word in res.lower() for word in ["nguyên vẹn", "tốt", "bình thường", "sạch", "không rò rỉ", "đạt", "phẳng", "chắc chắn", "đủ"]):
                    meaning = "Hệ thống/linh kiện hoạt động bình thường"
                    recommended_fix = "Chuyển sang bước kiểm tra tiếp theo"
                elif any(word in res.lower() for word in ["lỏng", "cháy", "thổi", "lỗi", "hỏng", "bẩn", "rò rỉ", "kẹt", "mòn", "thấp", "xước", "vênh", "không đạt", "đứt"]):
                    meaning = "Phát hiện dấu hiệu bất thường hoặc hư hỏng"
                    recommended_fix = "Thay thế hoặc sửa chữa theo tiêu chuẩn của nhà sản xuất"
                
                checks.append({
                    "action": current_action,
                    "possible_result": res,
                    "meaning": meaning,
                    "recommended_fix": recommended_fix
                })
        else:
            current_action = sentence
            
    if not checks and current_action:
        checks.append({
            "action": current_action,
            "possible_result": "Không xác định",
            "meaning": "Quan sát và đánh giá tình trạng thực tế",
            "recommended_fix": "Xử lý theo tình trạng thực tế"
        })
        
    return {
        "fault": top_result.get("fault_label_vi") or top_result.get("fault_label") or top_result.get("fault_name") or top_result.get("fault_id"),
        "confidence": round(float(top_result.get("final_cf", 0)) * 100),
        "affected_area": top_rule.get("system") or top_rule.get("subsystem") if top_rule else "",
        "inspect_or_replace": parts_to_inspect,
        "checks": checks
    }

def enrich_response(response):
    for result in response.get("results", []):
        cf = float(result.get("final_cf", 0))
        result["confidence_label"] = confidence_label(cf)
    return response

def question_key(question):
    if not question:
        return None
    return question.get("step_id") or question.get("symptom_id") or question.get("symptom") or question.get("mode")

def answered_step_count(session):
    if not session:
        return 0
    return len(session.get("asked_questions", []))

def estimate_step_progress(session, response):
    current = answered_step_count(session)
    if response.get("status") == "need_more_info" and response.get("next_question"):
        current += 1
    return str(current) if current > 0 else None

def should_use_llm_fallback(response):
    if response is None:
        return True
    status = response.get("status")
    if status in {"need_more_info", "collecting_context"} and next_question_has_substance(
        response.get("next_question")
    ):
        return False
    if status == "diagnosed":
        return False
    candidates = response.get("diagnoses") or response.get("current_hypotheses") or []
    if response.get("status") in {"unknown_symptom", "no_fault_found", "llm_fallback"}:
        return True
    return not candidates

def filter_rejected_faults(response, rejected_faults):
    rejected_faults = set(rejected_faults or [])
    if not rejected_faults:
        return response

    for key in ["diagnoses", "results", "current_hypotheses", "candidate_faults"]:
        response[key] = [
            item for item in response.get(key, [])
            if item.get("fault_id") not in rejected_faults
        ]

    response["rejected_faults"] = sorted(rejected_faults)

    if not response.get("diagnoses") and not response.get("current_hypotheses"):
        response["status"] = "no_fault_found"
        response["is_final"] = False
        response["next_question"] = None
        response["results"] = []

    return response

def _public_llm_need_more_from_candidate(
    user_input: str,
    candidate: dict,
    session: dict | None,
    reason: str,
) -> dict:
    session = session or {}
    nodes = _node_map(candidate)
    tree = (candidate or {}).get("tree") or {}
    root_id = tree.get("root_node_id")
    root = nodes.get(root_id) if root_id else None
    qtext = (root or {}).get("question") if root else None
    if not str(qtext or "").strip():
        qtext = MEANINGFUL_QUESTION_FALLBACK_VI
    next_q = {
        "step_id": root_id,
        "symptom_id": root_id,
        "question": str(qtext).strip(),
        "mode": "llm_tree",
        "type": "yes_no",
    }
    return {
        "status": "need_more_info",
        "is_final": False,
        "source": "llm_fallback",
        "fallback_reason": reason,
        "next_question": next_q,
        "asked_questions": list(session.get("asked_questions", [])),
        "llm_candidate_generated": bool(candidate),
        "candidate_faults": [],
        "current_hypotheses": [],
        "diagnoses": [],
        "results": [],
    }


def _strip_internal_diagnose_fields(response: dict) -> dict:
    out = dict(response)
    for k in ("decision_tree", "llm_patch_suggestion", "candidate_id", "_llm_review_candidate", "_llm_tree_update"):
        out.pop(k, None)
    if out.get("type") == "diagnostic_decision_tree":
        out.pop("type", None)
    out.pop("current_node", None)
    return out


def _session_has_navigable_llm_tree(session: dict | None) -> bool:
    if not session:
        return False
    nodes = ((session.get("decision_tree") or {}).get("tree") or {}).get("nodes") or []
    return bool(nodes) and bool(session.get("current_node_id"))


def _normalize_llm_tree_step_answer(step_answer) -> str:
    if step_answer is True:
        return "yes"
    if step_answer is False:
        return "no"
    if isinstance(step_answer, str):
        s = step_answer.strip().lower()
        if s in {"yes", "y", "true", "1", "co", "có"}:
            return "yes"
        if s in {"no", "n", "false", "0", "khong", "không"}:
            return "no"
        if s in {"unknown", "unsure", "khong_ro", "không rõ", "khong ro"}:
            return "unknown"
    if step_answer is None:
        return "unknown"
    return "unknown"


def _result_node_to_diagnoses(result_node: dict) -> list[dict]:
    fault = (result_node or {}).get("fault") or {}
    cf = float(fault.get("confidence", 0) or 0)
    label = fault.get("fault_name") or fault.get("fault_label_vi") or fault.get("fault_label") or fault.get("fault_id")
    resolution = {
        "parts": [c.get("name_vi") or c.get("component_id") for c in (result_node.get("components") or []) if c],
        "procedure": "\n".join(result_node.get("repair_steps") or []),
    }
    row = {
        "fault_id": fault.get("fault_id"),
        "fault_name": label,
        "fault_label_vi": fault.get("fault_name") or fault.get("fault_label_vi") or label,
        "fault_label": fault.get("fault_label") or label,
        "final_cf": cf,
        "confidence": cf,
        "system": fault.get("system"),
        "severity": fault.get("severity"),
        "resolution": resolution,
        "symptoms": fault.get("symptoms") or [],
        "components": result_node.get("components") or [],
        "causes": result_node.get("causes") or [],
        "diagnostic_steps": result_node.get("diagnostic_steps") or [],
        "repair_steps": result_node.get("repair_steps") or [],
        "safety_notes": result_node.get("safety_notes") or [],
    }
    return [row]


def _continue_llm_decision_tree(
    session_id: str,
    session: dict,
    step_answer,
    user_input: str,
) -> dict:
    candidate = session.get("decision_tree") or {}
    nodes = _node_map(candidate)
    node_id = session.get("current_node_id")
    node = nodes.get(node_id)
    if not node or node.get("type") != "question":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phiên LLM không ở trạng thái câu hỏi hợp lệ.",
        )
    answer_key = _normalize_llm_tree_step_answer(step_answer)
    branch = {"yes": "yes_next", "no": "no_next", "unknown": "unknown_next"}[answer_key]
    next_node_id = node.get(branch)
    next_node = nodes.get(next_node_id)
    if not next_node:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cây chẩn đoán bị thiếu node đích: {next_node_id}",
        )

    selected_path = list(session.get("selected_path") or [])
    selected_path.append(
        {
            "node_id": node_id,
            "question": node.get("question"),
            "answer": answer_key,
            "next_node_id": next_node_id,
        }
    )

    if next_node.get("type") == "result":
        review_candidate = dict(candidate)
        review_candidate["selected_path"] = selected_path
        review_candidate["selected_result_node_id"] = next_node_id
        review_candidate["expert_review"] = {"candidate_ready": True, "status": "pending_expert_review"}
        enqueue_llm_suggestion(session.get("user_input", user_input), review_candidate)
        rows = _result_node_to_diagnoses(next_node)
        return {
            "status": "diagnosed",
            "source": "llm_fallback",
            "is_final": True,
            "next_question": None,
            "diagnoses": rows,
            "results": rows,
            "current_hypotheses": rows,
            "candidate_faults": [],
            "expert_review": {"candidate_ready": False},
            "llm_candidate_generated": True,
            "_llm_tree_update": {
                "current_node_id": next_node_id,
                "selected_path": selected_path,
                "selected_result_node_id": next_node_id,
            },
        }

    qtext = next_node.get("question") or ""
    if not str(qtext).strip():
        qtext = MEANINGFUL_QUESTION_FALLBACK_VI
    next_q = {
        "step_id": next_node_id,
        "symptom_id": next_node_id,
        "question": str(qtext).strip(),
        "mode": "llm_tree",
        "type": "yes_no",
    }
    return {
        "status": "need_more_info",
        "source": "llm_fallback",
        "is_final": False,
        "next_question": next_q,
        "diagnoses": [],
        "results": [],
        "current_hypotheses": [],
        "candidate_faults": [],
        "llm_candidate_generated": True,
        "_llm_tree_update": {
            "current_node_id": next_node_id,
            "selected_path": selected_path,
        },
    }


def llm_response(user_input, session=None, reason="kg_no_match", candidate=None):
    session = session or {}
    if candidate is None:
        fallback = diagnose_with_llm(user_input, session)
        candidate = fallback.get("candidate")
    if not candidate or not (candidate.get("tree") or {}).get("nodes"):
        return {
            "status": "need_more_info",
            "is_final": False,
            "source": "llm_fallback",
            "fallback_reason": reason,
            "next_question": {
                "question": MEANINGFUL_QUESTION_FALLBACK_VI,
                "mode": "llm_tree",
                "type": "yes_no",
            },
            "asked_questions": list(session.get("asked_questions", [])),
            "llm_candidate_generated": False,
            "candidate_faults": [],
            "current_hypotheses": [],
            "diagnoses": [],
            "results": [],
        }
    return _public_llm_need_more_from_candidate(user_input, candidate, session, reason)


def _llm_resume_question_response(session: dict, user_input: str) -> dict:
    """Same need_more_info shape while user adds free-text context (no tree step consumed)."""
    cand = session.get("decision_tree") or {}
    nodes = _node_map(cand)
    nid = session.get("current_node_id")
    node = nodes.get(nid) or {}
    qtext = node.get("question") or MEANINGFUL_QUESTION_FALLBACK_VI
    next_q = {
        "step_id": nid,
        "symptom_id": nid,
        "question": str(qtext).strip(),
        "mode": "llm_tree",
        "type": "yes_no",
    }
    return {
        "status": "need_more_info",
        "is_final": False,
        "source": "llm_fallback",
        "next_question": next_q,
        "diagnoses": [],
        "results": [],
        "current_hypotheses": [],
        "candidate_faults": [],
        "llm_candidate_generated": True,
    }


def _node_map(candidate):
    return {
        node.get("node_id"): node
        for node in ((candidate or {}).get("tree") or {}).get("nodes", [])
        if isinstance(node, dict) and node.get("node_id")
    }

def _public_question_node(node):
    if not node:
        return None
    return {
        "node_id": node.get("node_id"),
        "type": node.get("type"),
        "question": node.get("question"),
        "answer_type": node.get("answer_type", "yes_no"),
        "purpose": node.get("purpose"),
    }

def _estimate_tree_depth(candidate):
    tree = (candidate or {}).get("tree") or {}
    nodes = _node_map(candidate)
    root = tree.get("root_node_id")
    seen = set()
    def walk(node_id, depth):
        if not node_id or node_id in seen or node_id not in nodes:
            return depth
        node = nodes[node_id]
        if node.get("type") == "result":
            return depth
        seen.add(node_id)
        values = [
            walk(node.get(branch), depth + 1)
            for branch in ("yes_next", "no_next", "unknown_next")
        ]
        seen.discard(node_id)
        return max(values or [depth])
    return max(1, walk(root, 1))

class DiagnosisService:
    def __init__(self):
        self.sessions = SessionService()

    def diagnose(
        self,
        user_input=None,
        top_k=5,
        session_id=None,
        step_answer=None,
        step_answer_provided=False,
    ):
        if session_id:
            return self.continue_session(
                session_id,
                symptom=user_input,
                step_answer=step_answer,
                step_answer_provided=step_answer_provided,
                top_k=top_k,
            )

        reason = "kg_no_match"
        try:
            response = get_engine().diagnose(user_input, top_k=top_k)
            response = apply_response_policy(response)
            response = enrich_response(response)
            response["source"] = "knowledge_graph"
        except Exception as exc:
            response = None
            reason = f"staging_kg_unavailable: {exc}"

        if should_use_llm_fallback(response):
            fb = diagnose_with_llm(user_input, session={})
            cand = fb.get("candidate")
            response = llm_response(user_input, session={}, reason=reason, candidate=cand)
            response = apply_response_policy(response)
            response = self._add_response_context(response, None)
            session_id = self.sessions.create(user_input, response)
            if cand and (cand.get("tree") or {}).get("nodes"):
                self.sessions.attach_decision_tree(session_id, cand, session_status=response.get("status"))
            response["session_id"] = session_id
            return _strip_internal_diagnose_fields(response)

        response = self._add_response_context(response, None)
        session_id = self.sessions.create(user_input, response)
        response["session_id"] = session_id
        return response

    def _diagnose_with_available_engine(
        self,
        user_input,
        confirmed_symptoms,
        rejected_symptoms,
        rejected_faults=None,
        session=None,
        top_k=5,
    ):
        session_for_engine = dict(session or {})
        session_for_engine["rejected_faults"] = sorted(rejected_faults or [])

        response = enrich_response(
            get_engine().diagnose(
                user_input,
                top_k=top_k,
                confirmed_symptoms=sorted(confirmed_symptoms),
                rejected_symptoms=sorted(rejected_symptoms),
                session=session_for_engine,
            )
        )
        response["source"] = "knowledge_graph"
        response["rejected_faults"] = sorted(rejected_faults or [])
        return filter_rejected_faults(response, rejected_faults)

    def _rule_for_fault(self, fault_id):
        try:
            return KnowledgeBase.from_staging().get_fault(fault_id)
        except Exception:
            return None

    def _add_response_context(self, response, session):
        nq = response.get("next_question")
        if isinstance(nq, str):
            text = nq.strip() or MEANINGFUL_QUESTION_FALLBACK_VI
            response["next_question"] = {
                "question": text,
                "mode": "llm_tree",
                "type": "yes_no",
            }
            nq = response["next_question"]
        elif response.get("status") in {"need_more_info", "collecting_context"} and not next_question_has_substance(nq):
            base = nq if isinstance(nq, dict) else {}
            response["next_question"] = {**base, "question": MEANINGFUL_QUESTION_FALLBACK_VI}
        next_question = response.get("next_question") or {}
        hypotheses = response.get("current_hypotheses") or response.get("diagnoses") or []
        top = hypotheses[0] if hypotheses else None
        top_rule = self._rule_for_fault(top.get("fault_id")) if top else None
        progress = estimate_step_progress(session or {}, response)
        mode = next_question.get("mode") or "information_gain"

        response.setdefault("mode", mode)
        response.setdefault("step_context", None)
        response.setdefault("step_progress", progress)
        response.setdefault("fault_preview", next_question.get("fault_preview"))
        response.setdefault("resolution", None)
        response["total_steps_est"] = None

        if progress:
            response["step_context"] = f"Hội thoại chẩn đoán · bước {progress}"
        
        if response.get("status") == "diagnosed":
            response["results"] = response.get("results") or hypotheses
            if top_rule:
                res = top_rule.get("resolution")
                response["resolution"] = res
                response["repair_plan"] = build_repair_plan(top, top_rule, res)
        else:
            response.setdefault("results", [])

        response["normalized"] = normalize_diagnosis_response(response)
        return response

    def continue_session(
        self,
        session_id,
        symptom=None,
        step_answer=None,
        step_answer_provided=False,
        top_k=5,
    ):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy phiên chẩn đoán.",
            )

        user_input = session.get("user_input", "")
        if symptom:
            user_input = f"{user_input} {symptom}".strip()

        confirmed_symptoms = set(session.get("confirmed_symptoms", []))
        rejected_symptoms = set(session.get("rejected_symptoms", []))
        rejected_faults = set(session.get("rejected_faults", []))
        answers = dict(session.get("answers", {}))
        last_question = session.get("last_question") or {}

        if _session_has_navigable_llm_tree(session):
            if not step_answer_provided:
                response = _llm_resume_question_response(session, user_input)
            else:
                response = _continue_llm_decision_tree(session_id, session, step_answer, user_input)
                tu = response.pop("_llm_tree_update", None)
                if tu:
                    self.sessions.update_decision_tree_state(
                        session_id,
                        tu["current_node_id"],
                        tu["selected_path"],
                        tu.get("selected_result_node_id"),
                    )
            response = self._add_response_context(response, session)
            self.sessions.update_from_response(
                session_id,
                response,
                dict(session.get("answers", {})),
                user_input=user_input,
            )
            response["session_id"] = session_id
            return _strip_internal_diagnose_fields(response)

        if step_answer_provided:
            symptom_id = (
                last_question.get("symptom_id")
                or last_question.get("step_id")
                or last_question.get("question")
            )
            if symptom_id:
                answers[symptom_id] = step_answer
                if isinstance(step_answer, bool):
                    if step_answer:
                        confirmed_symptoms.add(symptom_id)
                    else:
                        rejected_symptoms.add(symptom_id)

        response = self._diagnose_with_available_engine(
            user_input,
            confirmed_symptoms,
            rejected_symptoms,
            rejected_faults=rejected_faults,
            session=session,
            top_k=top_k,
        )
        response = apply_response_policy(response)

        if should_use_llm_fallback(response):
            session["answers"] = answers
            session["user_input"] = user_input
            fb = diagnose_with_llm(user_input, session=session)
            cand = fb.get("candidate")
            response = llm_response(user_input, session=session, reason="kg_no_match_after_answer", candidate=cand)
            response = apply_response_policy(response)
            if cand and (cand.get("tree") or {}).get("nodes"):
                self.sessions.attach_decision_tree(session_id, cand, session_status=response.get("status"))

        response = self._add_response_context(response, session)
        self.sessions.update_from_response(session_id, response, answers, user_input=user_input)
        response["session_id"] = session_id
        return _strip_internal_diagnose_fields(response)

    def answer(self, session_id, answer):
        return self.continue_session(session_id, step_answer=answer, step_answer_provided=True)

    def start_decision_tree(self, description, top_k=5):
        reason = "kg_no_match"
        try:
            kg_response = get_engine().diagnose(description, top_k=top_k)
            kg_response = apply_response_policy(enrich_response(kg_response))
            kg_response["source"] = "knowledge_graph"
        except Exception as exc:
            kg_response = None
            reason = f"staging_kg_unavailable: {exc}"

        if kg_response is not None and not should_use_llm_fallback(kg_response):
            kg_response = self._add_response_context(kg_response, None)
            session_id = self.sessions.create(description, kg_response)
            kg_response["session_id"] = session_id
            return kg_response

        fb = diagnose_with_llm(description, session={})
        candidate = fb.get("candidate")
        if not candidate or not (candidate.get("tree") or {}).get("nodes"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Không tạo được cây chẩn đoán từ LLM fallback.",
            )

        fallback_response = llm_response(description, session={}, reason=reason, candidate=candidate)
        fallback_response = apply_response_policy(fallback_response)
        fallback_response = self._add_response_context(fallback_response, None)
        session_id = self.sessions.create(description, fallback_response)
        self.sessions.attach_decision_tree(session_id, candidate)
        nodes = _node_map(candidate)
        root_node = nodes.get((candidate.get("tree") or {}).get("root_node_id"))
        return {
            "type": "diagnostic_decision_tree",
            "session_id": session_id,
            "candidate_id": candidate.get("candidate_id"),
            "root_symptom": candidate.get("root_symptom"),
            "current_node": _public_question_node(root_node),
            "progress": {
                "current_depth": 1,
                "estimated_max_depth": _estimate_tree_depth(candidate),
            },
            "decision_tree": candidate,
            "source": "llm_fallback",
        }

    def answer_decision_tree(self, session_id, node_id, answer):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy phiên chẩn đoán.",
            )
        candidate = session.get("decision_tree") or {}
        nodes = _node_map(candidate)
        node = nodes.get(node_id)
        if not node or node.get("type") != "question":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Node câu hỏi không hợp lệ.",
            )
        normalized_answer = str(answer or "").strip().lower()
        if normalized_answer in {"yes", "y", "true", "1", "co", "có"}:
            answer_key = "yes"
            branch = "yes_next"
        elif normalized_answer in {"no", "n", "false", "0", "khong", "không"}:
            answer_key = "no"
            branch = "no_next"
        elif normalized_answer in {"unknown", "khong_ro", "không rõ", "khong ro", "unsure"}:
            answer_key = "unknown"
            branch = "unknown_next"
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="answer phải là yes, no hoặc unknown.",
            )
        next_node_id = node.get(branch)
        next_node = nodes.get(next_node_id)
        if not next_node:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cây chẩn đoán bị thiếu node đích: {next_node_id}",
            )

        selected_path = list(session.get("selected_path") or [])
        selected_path.append(
            {
                "node_id": node_id,
                "question": node.get("question"),
                "answer": answer_key,
                "next_node_id": next_node_id,
            }
        )

        if next_node.get("type") == "result":
            review_candidate = dict(candidate)
            review_candidate["selected_path"] = selected_path
            review_candidate["selected_result_node_id"] = next_node_id
            review_candidate["expert_review"] = {"candidate_ready": True, "status": "pending_expert_review"}
            enqueue_llm_suggestion(session.get("user_input", ""), review_candidate)
            self.sessions.update_decision_tree_state(
                session_id,
                next_node_id,
                selected_path,
                selected_result_node_id=next_node_id,
            )
            return {
                "type": "result",
                "session_id": session_id,
                "candidate_id": candidate.get("candidate_id"),
                "root_symptom": candidate.get("root_symptom"),
                "selected_path": selected_path,
                "result_node": next_node,
                "full_tree": candidate.get("tree"),
                "expert_review": {"candidate_ready": True},
                "decision_tree": candidate,
                "source": "llm_fallback",
            }

        self.sessions.update_decision_tree_state(session_id, next_node_id, selected_path)
        return {
            "type": "question",
            "session_id": session_id,
            "current_node": _public_question_node(next_node),
            "answers": selected_path,
            "progress": {
                "current_depth": len(selected_path) + 1,
                "estimated_max_depth": _estimate_tree_depth(candidate),
            },
            "decision_tree": candidate,
            "source": "llm_fallback",
        }
