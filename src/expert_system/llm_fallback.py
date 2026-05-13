from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.expert_system.config import ENV_PATH


load_dotenv(ENV_PATH)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PLACEHOLDER_KEYS = {"", "your_gemini_api_key", "change_me", "changeme"}
LLM_SUGGESTION_QUEUE = Path("data/staging/llm_suggestions.jsonl")
MAX_LLM_CONFIDENCE = 0.55

DECISION_NEEDS_REVIEW = "Cần chuyên gia xác nhận"
SOURCE_LLM_FALLBACK = "fallback_llm_ngoai_kb"
SOURCE_OFFLINE_FALLBACK = "fallback_offline_ngoai_kb"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGING_DIR = PROJECT_ROOT / "data" / "staging"
ALIASES_PATH = STAGING_DIR / "symptom_aliases.json"
RULES_PATH = STAGING_DIR / "kg_rules_from_dataset.json"
PROCEDURES_PATH = STAGING_DIR / "procedure_trees.json"
EXPERT_TREE_PATH = STAGING_DIR / "expert_tree.json"

SYSTEM_CANDIDATES = [
    "Engine",
    "Brake",
    "Electrical",
    "Transmission",
    "Cooling System",
    "Fuel System",
    "Suspension",
    "Steering",
    "Exhaust",
    "HVAC",
    "Tire/Wheel",
    "Unknown",
]

SYSTEM_LABELS_VI = {
    "Engine": "Hệ thống động cơ",
    "Brake": "Hệ thống phanh",
    "Electrical": "Hệ thống điện",
    "Transmission": "Hệ thống hộp số",
    "Cooling System": "Hệ thống làm mát",
    "Fuel System": "Hệ thống nhiên liệu",
    "Suspension": "Hệ thống treo",
    "Steering": "Hệ thống lái",
    "Exhaust": "Hệ thống xả",
    "HVAC": "Hệ thống điều hòa",
    "Tire/Wheel": "Lốp và bánh xe",
    "Unknown": "Chưa xác định",
}

SOURCE_LABELS_VI = {
    "llm_fallback": SOURCE_LLM_FALLBACK,
    "offline_fallback": SOURCE_OFFLINE_FALLBACK,
    SOURCE_LLM_FALLBACK: SOURCE_LLM_FALLBACK,
    SOURCE_OFFLINE_FALLBACK: SOURCE_OFFLINE_FALLBACK,
}

DECISION_LABELS_VI = {
    "Needs expert review": DECISION_NEEDS_REVIEW,
    "need expert review": DECISION_NEEDS_REVIEW,
    "needs_review": DECISION_NEEDS_REVIEW,
    "Cần chuyên gia xác nhận": DECISION_NEEDS_REVIEW,
}

SYSTEM_KEYWORDS = {
    "Fuel System": ["hao xăng", "tốn xăng", "mùi xăng", "xăng", "nhiên liệu", "fuel"],
    "Cooling System": ["nóng máy", "quá nhiệt", "nhiệt cao", "két nước", "nước làm mát", "coolant"],
    "Brake": ["phanh", "thắng", "brake"],
    "Electrical": ["đèn báo", "đèn lỗi", "ắc quy", "acquy", "điện", "battery", "check engine"],
    "Transmission": ["hộp số", "sang số", "trượt số", "transmission"],
    "Suspension": ["giảm xóc", "xóc", "treo", "suspension"],
    "Steering": ["lái", "vô lăng", "steering"],
    "Exhaust": ["khói", "ống xả", "exhaust"],
    "Engine": ["động cơ", "rung", "giật", "khó nổ", "máy", "engine"],
    "Tire/Wheel": ["lốp", "bánh", "mâm", "tire", "wheel"],
    "HVAC": ["điều hòa", "máy lạnh", "ac", "hvac"],
}

PROCEDURE_TERMINALS = {"DIAGNOSED", "REFUTED", "END"}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _slugify(value: str, default: str = "unknown") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return value or default


def _has_api_key() -> bool:
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip() not in PLACEHOLDER_KEYS)


def _infer_system(user_input: str) -> str:
    text = user_input.strip().lower()
    for system, keywords in SYSTEM_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return system
    return "Unknown"


def _system_label_vi(system: str | None) -> str:
    if not system:
        return SYSTEM_LABELS_VI["Unknown"]
    return SYSTEM_LABELS_VI.get(system, system)


def _source_vi(source: str | None) -> str:
    return SOURCE_LABELS_VI.get(source or "", source or SOURCE_OFFLINE_FALLBACK)


def _decision_vi(decision: str | None) -> str:
    return DECISION_LABELS_VI.get(decision or "", decision or DECISION_NEEDS_REVIEW)


def _level_id(prefix: str, label: str) -> str:
    return f"{prefix}_{_slugify(label).upper()}"


def _load_json_safe(path: Path, default: Any = None) -> Any:
    """Load JSON file, return *default* on any failure."""
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _clamp_cf(value: Any, cap: float = MAX_LLM_CONFIDENCE) -> float:
    try:
        cf = float(value)
    except (TypeError, ValueError):
        cf = 0.35
    return round(max(0.0, min(cf, cap)), 4)


# ---------------------------------------------------------------------------
# KB context loader  (Plan step 3)
# ---------------------------------------------------------------------------

def build_kb_context(user_input: str) -> dict[str, Any]:
    """Load existing staging data and find nearby aliases / faults by keyword.

    Purpose: give the LLM prompt context so it extends the *current* tree
    style instead of inventing unrelated IDs/schema.
    """
    text = user_input.strip().lower()
    context: dict[str, Any] = {
        "existing_symptom_ids": [],
        "existing_fault_ids": [],
        "nearby_aliases": [],
        "inferred_system": _infer_system(user_input),
        "sample_procedure_tree": None,
    }

    # --- symptom aliases ---
    aliases = _load_json_safe(ALIASES_PATH, {})
    for sym_id, entry in aliases.items():
        if not isinstance(entry, dict):
            continue
        alias_list = entry.get("aliases", [])
        name = (entry.get("display_name") or entry.get("label_vi") or "").lower()
        if any(kw in text for kw in [name] + [a.lower() for a in alias_list if isinstance(a, str)] if kw):
            context["nearby_aliases"].append({
                "symptom_id": sym_id,
                "display_name": entry.get("display_name") or entry.get("label_vi"),
                "aliases": alias_list[:5],
            })
        if len(context["nearby_aliases"]) >= 5:
            break

    # --- existing fault/symptom IDs for reference ---
    rules_doc = _load_json_safe(RULES_PATH, {"rules": []})
    rules = rules_doc.get("rules", []) if isinstance(rules_doc, dict) else []
    seen_faults: set[str] = set()
    for rule in rules[:200]:
        if not isinstance(rule, dict):
            continue
        fid = rule.get("fault_id", "")
        if fid and fid not in seen_faults:
            context["existing_fault_ids"].append(fid)
            seen_faults.add(fid)
        sid = rule.get("primary_symptom") or rule.get("symptom")
        if sid and sid not in context["existing_symptom_ids"]:
            context["existing_symptom_ids"].append(sid)

    context["existing_fault_ids"] = context["existing_fault_ids"][:20]
    context["existing_symptom_ids"] = context["existing_symptom_ids"][:20]

    # --- sample procedure tree so LLM can mimic structure ---
    procedures = _load_json_safe(PROCEDURES_PATH, {})
    if isinstance(procedures, dict):
        for _fid, tree in list(procedures.items())[:1]:
            context["sample_procedure_tree"] = tree
            break

    return context


# ---------------------------------------------------------------------------
# Validation helpers  (Plan step 2)
# ---------------------------------------------------------------------------

def validate_procedure_tree(tree: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a single procedure tree dict.  Returns (ok, errors)."""
    errors: list[str] = []
    if not isinstance(tree, dict):
        return False, ["procedure_tree is not a dict"]

    entry = tree.get("entry_step")
    if not entry:
        errors.append("procedure_tree missing entry_step")

    steps = tree.get("steps")
    if not isinstance(steps, dict) or not steps:
        errors.append("procedure_tree missing or empty steps")
        return False, errors

    if entry and entry not in steps:
        errors.append(f"entry_step '{entry}' not found in steps")

    for step_id, step in steps.items():
        if not isinstance(step, dict):
            errors.append(f"step '{step_id}' is not a dict")
            continue
        if not step.get("question"):
            errors.append(f"step '{step_id}' missing question")
        for branch in ("yes_next", "no_next"):
            target = step.get(branch)
            if target is None:
                errors.append(f"step '{step_id}' missing {branch}")
            elif target not in PROCEDURE_TERMINALS and target not in steps:
                errors.append(f"step '{step_id}' {branch}='{target}' is neither a terminal nor a valid step")

    return len(errors) == 0, errors


def validate_llm_kb_patch(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate an llm_kb_patch payload.  Returns (ok, errors)."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        return False, ["payload is not a dict"]

    if payload.get("review_type") != "llm_kb_patch":
        errors.append("review_type must be 'llm_kb_patch'")

    if payload.get("needs_expert_review") is not True:
        errors.append("needs_expert_review must be true")

    # suggested_mapping
    mapping = payload.get("suggested_mapping")
    if not isinstance(mapping, dict):
        errors.append("missing suggested_mapping")
    else:
        if not mapping.get("primary_symptom_id"):
            errors.append("suggested_mapping missing primary_symptom_id")

    # candidate_faults
    faults = payload.get("candidate_faults")
    if not isinstance(faults, list) or not faults:
        errors.append("missing or empty candidate_faults")
    else:
        for i, fault in enumerate(faults):
            if not isinstance(fault, dict):
                errors.append(f"candidate_faults[{i}] is not a dict")
                continue
            cf = fault.get("cf", 0)
            try:
                if float(cf) > MAX_LLM_CONFIDENCE:
                    errors.append(f"candidate_faults[{i}] cf={cf} exceeds {MAX_LLM_CONFIDENCE}")
            except (TypeError, ValueError):
                errors.append(f"candidate_faults[{i}] cf is not a number")

    # procedure_trees
    trees = payload.get("procedure_trees")
    if not isinstance(trees, dict) or not trees:
        errors.append("missing or empty procedure_trees")
    else:
        for fault_id, tree in trees.items():
            ok, tree_errors = validate_procedure_tree(tree)
            if not ok:
                errors.extend(f"procedure_trees[{fault_id}]: {e}" for e in tree_errors)

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Suggestion queue
# ---------------------------------------------------------------------------

def enqueue_llm_suggestion(
    user_input: str,
    llm_output: dict[str, Any],
    reason: str = "trieu_chung_chua_duoc_mapping",
) -> None:
    LLM_SUGGESTION_QUEUE.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "user_input": user_input,
        "llm_output": llm_output,
        "reviewed": False,
        "promoted_to_kb": False,
    }

    with LLM_SUGGESTION_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Prompt — outputs llm_kb_patch JSON  (Plan step 1)
# ---------------------------------------------------------------------------

def _prompt(user_input: str, top_k: int, kb_context: dict[str, Any]) -> str:
    systems = ", ".join(SYSTEM_CANDIDATES)
    inferred = kb_context.get("inferred_system", "Unknown")
    nearby = json.dumps(kb_context.get("nearby_aliases", [])[:3], ensure_ascii=False)
    sample_tree = json.dumps(kb_context.get("sample_procedure_tree") or {}, ensure_ascii=False, indent=2)

    return f"""
Bạn là trợ lý chẩn đoán ô tô thận trọng, chỉ dùng làm fallback khi
Knowledge Graph dạng rule-based chưa có symptom khớp.

Chỉ trả về JSON hợp lệ. Không dùng markdown. Không giải thích ngoài JSON.

Triệu chứng người dùng nhập:
{user_input}

Hệ thống suy luận từ keyword: {inferred}
Alias gần nhất trong KB hiện tại: {nearby}

Tham khảo cấu trúc procedure tree hiện có (mẫu):
{sample_tree}

Hệ thống xe hợp lệ: {systems}

Quy tắc bắt buộc:
- Confidence tối đa là {MAX_LLM_CONFIDENCE}.
- needs_expert_review luôn là true.
- Tạo tối đa {top_k} candidate_faults.
- procedure_trees phải có entry_step, steps, mỗi step có question, yes_next, no_next.
- yes_next/no_next chỉ trỏ đến step_id khác hoặc terminal: DIAGNOSED, REFUTED, END.
- Giá trị hiển thị bằng tiếng Việt, key JSON giữ nguyên tiếng Anh.

JSON shape bắt buộc:
{{
  "review_type": "llm_kb_patch",
  "needs_expert_review": true,
  "source": "llm_fallback",
  "user_input": "{user_input}",
  "suggested_mapping": {{
    "system_id": "SYS_<SYSTEM>",
    "primary_symptom_id": "SYM_<SNAKE_CASE>",
    "primary_symptom_label": "Tên triệu chứng tiếng Việt",
    "aliases": ["alias tiếng Việt 1", "alias tiếng Việt 2"]
  }},
  "candidate_faults": [
    {{
      "fault_id": "FAULT_<SNAKE_CASE>",
      "fault_name": "snake_case_name",
      "fault_label": "Tên lỗi tiếng Việt",
      "cf": 0.35,
      "symptoms": [
        {{"symptom_id": "SYM_...", "cf": 0.35, "priority": 1}}
      ],
      "resolution": {{
        "parts": ["linh kiện"],
        "tools": [],
        "procedure": "Mô tả quy trình kiểm tra",
        "difficulty": "expert_review_required",
        "labor_hours": null
      }}
    }}
  ],
  "procedure_trees": {{
    "FAULT_<ID>": {{
      "fault_id": "FAULT_<ID>",
      "fault_name": "snake_case_name",
      "entry_step": "<fault_slug>_s1",
      "steps": {{
        "<fault_slug>_s1": {{
          "id": "<fault_slug>_s1",
          "symptom_id": "SYM_...",
          "symptom_label": "Tên triệu chứng",
          "question": "Câu hỏi kiểm tra bước 1?",
          "is_question": true,
          "yes_next": "<fault_slug>_s2",
          "no_next": "REFUTED",
          "results": []
        }},
        "<fault_slug>_s2": {{
          "id": "<fault_slug>_s2",
          "symptom_id": "SYM_...",
          "symptom_label": "Tên triệu chứng",
          "question": "Câu hỏi kiểm tra bước 2?",
          "is_question": true,
          "yes_next": "DIAGNOSED",
          "no_next": "REFUTED",
          "results": []
        }}
      }}
    }}
  }},
  "review_notes": {{
    "reason": "Lý do tạo patch",
    "confidence_limit": "LLM suggestion only; not official diagnosis."
  }}
}}
""".strip()


# ---------------------------------------------------------------------------
# Safe JSON parser
# ---------------------------------------------------------------------------

def _safe_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Offline fallback — generates llm_kb_patch shape without LLM
# ---------------------------------------------------------------------------

def _offline_response(user_input: str) -> dict[str, Any]:
    system = _infer_system(user_input)
    system_id = _level_id("SYS", system)
    symptom_name = _slugify(user_input, default="user_reported_symptom")
    symptom_id = _level_id("SYM", user_input)
    fault_id = f"FAULT_{_slugify(user_input, default='unknown').upper()}"
    fault_name = _slugify(user_input, default="unknown_fault")
    step_base = _slugify(fault_name, default="offline")

    return {
        "review_type": "llm_kb_patch",
        "needs_expert_review": True,
        "source": "llm_fallback",
        "user_input": user_input,
        "suggested_mapping": {
            "system_id": system_id,
            "primary_symptom_id": symptom_id,
            "primary_symptom_label": user_input,
            "aliases": [user_input],
        },
        "candidate_faults": [
            {
                "fault_id": fault_id,
                "fault_name": fault_name,
                "fault_label": f"Triệu chứng chưa có trong Knowledge Graph: {user_input}",
                "cf": 0.2,
                "symptoms": [
                    {"symptom_id": symptom_id, "cf": 0.2, "priority": 1}
                ],
                "resolution": {
                    "parts": [],
                    "tools": [],
                    "procedure": "Chưa xác định — cần chuyên gia kiểm tra và xác nhận.",
                    "difficulty": "expert_review_required",
                    "labor_hours": None,
                },
            }
        ],
        "procedure_trees": {
            fault_id: {
                "fault_id": fault_id,
                "fault_name": fault_name,
                "entry_step": f"{step_base}_s1",
                "steps": {
                    f"{step_base}_s1": {
                        "id": f"{step_base}_s1",
                        "symptom_id": symptom_id,
                        "symptom_label": user_input,
                        "question": "Triệu chứng xuất hiện khi nào: lúc khởi động, chạy chậm, tăng tốc hay chạy đường dài?",
                        "is_question": True,
                        "yes_next": f"{step_base}_s2",
                        "no_next": "REFUTED",
                        "results": [],
                    },
                    f"{step_base}_s2": {
                        "id": f"{step_base}_s2",
                        "symptom_id": symptom_id,
                        "symptom_label": user_input,
                        "question": "Có đèn cảnh báo hoặc đèn check engine sáng không?",
                        "is_question": True,
                        "yes_next": "DIAGNOSED",
                        "no_next": "REFUTED",
                        "results": [],
                    },
                },
            }
        },
        "review_notes": {
            "reason": "Chưa cấu hình GEMINI_API_KEY nên hệ thống dùng fallback offline.",
            "confidence_limit": "LLM suggestion only; not official diagnosis.",
        },
    }


# ---------------------------------------------------------------------------
# Normalise LLM raw output into valid llm_kb_patch shape
# ---------------------------------------------------------------------------

def _normalize_llm_patch(raw: dict[str, Any], user_input: str, source: str) -> dict[str, Any]:
    """Take raw LLM JSON and ensure it conforms to llm_kb_patch schema."""

    # If the LLM already returned valid llm_kb_patch, just clamp confidence
    if raw.get("review_type") == "llm_kb_patch" and raw.get("candidate_faults"):
        patch = dict(raw)
    else:
        # Legacy / malformed — wrap into the new shape
        patch = _offline_response(user_input)
        patch["review_notes"] = {
            "reason": "LLM trả kết quả không đúng schema llm_kb_patch, dùng offline fallback.",
            "confidence_limit": "LLM suggestion only; not official diagnosis.",
        }
        return patch

    # Force safety invariants
    patch["review_type"] = "llm_kb_patch"
    patch["needs_expert_review"] = True
    patch["source"] = source
    patch.setdefault("user_input", user_input)

    # Clamp all cf values
    for fault in patch.get("candidate_faults", []):
        if isinstance(fault, dict):
            fault["cf"] = _clamp_cf(fault.get("cf", 0.35))
            for sym in fault.get("symptoms", []):
                if isinstance(sym, dict):
                    sym["cf"] = _clamp_cf(sym.get("cf", 0.35))

    return patch


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def diagnose_with_llm(user_input: str, top_k: int = 5) -> dict[str, Any]:
    source = SOURCE_LLM_FALLBACK
    queue_reason = "trieu_chung_chua_duoc_mapping"

    # Build KB context for prompt enrichment
    kb_context = build_kb_context(user_input)

    if not _has_api_key():
        patch = _offline_response(user_input)
        source = SOURCE_OFFLINE_FALLBACK
        queue_reason = "offline_trieu_chung_chua_duoc_mapping"
    else:
        try:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(DEFAULT_MODEL)
            response = model.generate_content(_prompt(user_input, top_k, kb_context))
            raw = _safe_json(response.text)
            patch = _normalize_llm_patch(raw, user_input, source)
        except Exception as exc:
            patch = _offline_response(user_input)
            patch.setdefault("review_notes", {})["llm_error"] = str(exc)
            source = SOURCE_OFFLINE_FALLBACK
            queue_reason = "offline_trieu_chung_chua_duoc_mapping"

    # Validate
    ok, validation_errors = validate_llm_kb_patch(patch)
    if not ok:
        patch.setdefault("review_notes", {})["validation_errors"] = validation_errors

    # Enqueue for expert review
    patch["queued_for_review"] = False
    try:
        enqueue_llm_suggestion(user_input, patch, reason=queue_reason)
        patch["queued_for_review"] = True
    except Exception as exc:
        patch.setdefault("review_notes", {})["queue_error"] = str(exc)

    # Always enforce source
    patch["source"] = source

    return patch
