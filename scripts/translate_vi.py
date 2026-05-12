from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

try:
    import _bootstrap  # type: ignore # noqa: F401
except ModuleNotFoundError:
    from scripts import _bootstrap  # type: ignore # noqa: F401

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_PATH = PROJECT_ROOT / "data" / "raw" / "automotive_faults.json"
OUT_PATH = PROJECT_ROOT / "data" / "staging" / "vi_translations.json"

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

BATCH_SIZE = 40
SLEEP_SECONDS = 10
MAX_RETRIES = 5


MANUAL_TRANSLATIONS: dict[str, str] = {
    "wheel bearing": "Ổ bi bánh xe",
    "bearing": "Ổ bi",
    "torque converter": "Bộ biến mô",
    "misfire": "Bỏ máy",
    "rough idle": "Garanti không đều",
    "engine knocking": "Gõ máy",
    "stall": "Tắt máy",
    "hard start": "Khó nổ máy",
    "no start": "Không nổ máy",
    "hesitation": "Hụt ga",
    "poor acceleration": "Tăng tốc yếu",
    "transmission slipping": "Trượt số",
    "harsh shifting": "Sang số giật",
    "fuel pump": "Bơm nhiên liệu",
    "fuel injector": "Kim phun nhiên liệu",
    "spark plug": "Bugi",
    "ignition coil": "Mobin đánh lửa",
    "check engine light": "Đèn báo lỗi động cơ",
    "abs sensor": "Cảm biến ABS",
    "suspension arm": "Càng treo",
    "brake pad": "Má phanh",
    "steering rack": "Thước lái",
    "OBD scanner": "Máy quét OBD",
    "obd scanner": "Máy quét OBD",
    "Multimeter": "Đồng hồ vạn năng",
    "multimeter": "Đồng hồ vạn năng",

    "symptoms": "Dấu hiệu",
    "fault": "Lỗi",
    "fault list": "Danh sách lỗi",
    "diagnosis steps": "Quy trình kiểm tra",
    "repair action": "Hướng xử lý",
    "repair solution": "Giải pháp sửa chữa",
    "recommendations": "Khuyến nghị",
    "causes": "Nguyên nhân",
    "related faults": "Lỗi liên quan",
    "system": "Hệ thống",
    "component": "Bộ phận",
    "affects": "Ảnh hưởng đến",
    "fixed by": "Giải pháp sửa chữa",
    "related to": "Liên quan đến",
    "part of": "Thuộc hệ thống",
    "approved": "Đã xác minh",

    "HAS_SYMPTOM": "Dấu hiệu",
    "CAUSED_BY": "Nguyên nhân",
    "AFFECTS": "Ảnh hưởng đến",
    "FIXED_BY": "Giải pháp sửa chữa",
    "RELATED_TO": "Liên quan đến",
    "PART_OF": "Thuộc hệ thống",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def slugify(text: Any) -> str:
    text = str(text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def should_translate_text(text: str) -> bool:
    text = text.strip()

    if not text:
        return False

    if len(text) <= 1:
        return False

    if text.isdigit():
        return False

    if re.fullmatch(r"[A-Z0-9_]+", text):
        return True

    return bool(re.search(r"[A-Za-z]", text))


def load_records() -> list[dict[str, Any]]:
    data = load_json(RAW_PATH)

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("records", "faults", "data", "nodes", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def collect_texts_from_any(value: Any, texts: set[str]) -> None:
    if isinstance(value, str):
        text = value.strip()
        if should_translate_text(text):
            texts.add(text)
        return

    if isinstance(value, list):
        for item in value:
            collect_texts_from_any(item, texts)
        return

    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and should_translate_text(key):
                if key.upper() in MANUAL_TRANSLATIONS:
                    texts.add(key)

            collect_texts_from_any(child, texts)


def collect_texts(records: list[dict[str, Any]]) -> list[str]:
    texts: set[str] = set()

    for record in records:
        collect_texts_from_any(record, texts)
        fault_display = str(
            record.get("subcategory")
            or record.get("fault")
            or record.get("name")
            or ""
        ).strip()
        if fault_display:
            texts.add(f"Diagnosis for {fault_display}")

    for key in MANUAL_TRANSLATIONS:
        texts.add(key)

    return sorted(texts)


def normalize_manual_key(text: str) -> str:
    stripped = text.strip()

    if stripped in MANUAL_TRANSLATIONS:
        return stripped

    lower = stripped.lower()
    if lower in MANUAL_TRANSLATIONS:
        return lower

    upper = stripped.upper()
    if upper in MANUAL_TRANSLATIONS:
        return upper

    return ""


def apply_manual_translations(texts: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}

    for text in texts:
        manual_key = normalize_manual_key(text)
        if manual_key:
            result[slugify(text)] = MANUAL_TRANSLATIONS[manual_key]

    return result


def parse_gemini_json(text: str) -> dict[str, str]:
    text = text.strip()

    if text.startswith("```json"):
        text = text.removeprefix("```json").strip()
    if text.startswith("```"):
        text = text.removeprefix("```").strip()
    if text.endswith("```"):
        text = text.removesuffix("```").strip()

    data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError("Gemini response is not a JSON object")

    return {
        str(key).strip(): str(value).strip()
        for key, value in data.items()
        if str(key).strip() and str(value).strip()
    }


def build_prompt(texts: list[str]) -> dict[str, Any]:
    return {
        "instruction": """
            You are a Vietnamese automotive diagnostic terminology localizer for an expert system and knowledge graph UI.

            Your task is NOT to literally translate English into Vietnamese.

            Your task is to localize automotive terminology into natural Vietnamese commonly used in:
            - automotive repair garages,
            - mechanic workshops,
            - automotive diagnostic software,
            - technical service manuals in Vietnam.

            The output must sound like real automotive diagnostic software used in Vietnam.

            Core translation principles:
            - Prefer practical garage terminology over textbook wording.
            - Use concise and natural Vietnamese.
            - Avoid robotic or machine-translated phrases.
            - Avoid overly academic language.
            - Use terminology understandable to both mechanics and vehicle owners.
            - Keep UI labels short and readable.
            - Preserve technical meaning accurately.

            Critical rules:
            - Never translate word-by-word.
            - Never keep awkward English-Vietnamese mixed wording.
            - Never use robotic phrases like:
            - "Được xử lý bởi"
            - "Có triệu chứng"
            - "Nút"
            - "Node"
            - "Approved"
            - Relationship labels must sound natural in Vietnamese.
            - If multiple translations exist, choose the wording most commonly used by Vietnamese mechanics.

            Preferred automotive terminology:
            - Wheel bearing → Ổ bi bánh xe
            - Bearing → Ổ bi
            - Torque converter → Bộ biến mô
            - Misfire → Bỏ máy
            - Rough idle → Garanti không đều
            - Engine knocking → Gõ máy
            - Stall → Tắt máy
            - Hard start → Khó nổ máy
            - No start → Không nổ máy
            - Hesitation → Hụt ga
            - Poor acceleration → Tăng tốc yếu
            - Transmission slipping → Trượt số
            - Harsh shifting → Sang số giật
            - Fuel pump → Bơm nhiên liệu
            - Fuel injector → Kim phun nhiên liệu
            - Spark plug → Bugi
            - Ignition coil → Mobin đánh lửa
            - Check engine light → Đèn báo lỗi động cơ
            - ABS sensor → Cảm biến ABS
            - Suspension arm → Càng treo
            - Brake pad → Má phanh
            - Steering rack → Thước lái

            Preferred UI wording:
            - Symptoms → Dấu hiệu
            - Fault → Lỗi
            - Fault list → Danh sách lỗi
            - Diagnosis steps → Quy trình kiểm tra
            - Repair action → Hướng xử lý
            - Repair solution → Giải pháp sửa chữa
            - Recommendations → Khuyến nghị
            - Causes → Nguyên nhân
            - Related faults → Lỗi liên quan
            - System → Hệ thống
            - Component → Bộ phận
            - Affects → Ảnh hưởng đến
            - Fixed by → Giải pháp sửa chữa
            - Related to → Liên quan đến
            - Part of → Thuộc hệ thống
            - Approved → Đã xác minh

            Coverage requirements:
            You MUST translate ALL automotive-related text fields, including:
            - fault names
            - symptoms
            - diagnosis questions
            - diagnosis steps
            - repair actions
            - repair recommendations
            - causes
            - relationship labels
            - graph labels
            - edge labels
            - descriptions
            - rule explanations
            - UI labels
            - nested text fields inside objects and arrays

            Output requirements:
            - Return ONLY valid JSON.
            - Do NOT add explanations.
            - Do NOT wrap output in markdown.
            - The JSON key must remain EXACTLY the original English text.
            - The JSON value must be the localized Vietnamese automotive term.
""".strip(),
        "texts": texts,
    }


def translate_batch(texts: list[str], api_key: str) -> dict[str, str]:
    prompt = build_prompt(texts)

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = httpx.post(
                GEMINI_URL,
                params={"key": api_key},
                json={
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        prompt,
                                        ensure_ascii=False,
                                    )
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                        "response_mime_type": "application/json",
                    },
                },
                timeout=120,
            )

            if response.status_code in (429, 500, 502, 503, 504):
                wait_seconds = SLEEP_SECONDS * attempt
                print(
                    f"Gemini temporary error {response.status_code}. "
                    f"Retry in {wait_seconds}s..."
                )
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()

            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return parse_gemini_json(text)

        except Exception as exc:
            last_error = exc
            wait_seconds = SLEEP_SECONDS * attempt
            print(f"Translate attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            print(f"Retry in {wait_seconds}s...")
            time.sleep(wait_seconds)

    raise RuntimeError(f"Translate failed after retries: {last_error}")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")

    records = load_records()
    texts = collect_texts(records)

    existing: dict[str, str] = {}
    if OUT_PATH.exists():
        loaded = load_json(OUT_PATH)
        if isinstance(loaded, dict):
            existing = {
                str(key): str(value)
                for key, value in loaded.items()
            }

    manual_translations = apply_manual_translations(texts)
    existing.update(manual_translations)

    pending = [
        text
        for text in texts
        if slugify(text) not in existing
    ]

    print(f"Total source texts: {len(texts)}")
    print(f"Manual translations: {len(manual_translations)}")
    print(f"Already translated: {len(existing)}")
    print(f"Pending: {len(pending)}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Sleep seconds: {SLEEP_SECONDS}")

    translations = dict(existing)

    save_json(OUT_PATH, dict(sorted(translations.items())))

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        end = start + len(batch)

        print(f"Translating {start + 1}-{end} / {len(pending)}")

        translated_batch = translate_batch(batch, api_key)

        for english_text in batch:
            key = slugify(english_text)
            manual_key = normalize_manual_key(english_text)

            if manual_key:
                translations[key] = MANUAL_TRANSLATIONS[manual_key]
            else:
                translations[key] = translated_batch.get(
                    english_text,
                    english_text,
                )

        save_json(OUT_PATH, dict(sorted(translations.items())))

        print(f"Saved progress: {len(translations)} translations")
        time.sleep(SLEEP_SECONDS)

    print(f"Done. Saved translations to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
