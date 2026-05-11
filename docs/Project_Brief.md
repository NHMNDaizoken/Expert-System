# Project Brief

Cập nhật: 2026-05-11

Đây là bản tóm tắt ngắn để đưa cho người khác đọc nhanh, hiểu project đang làm gì và biết nên sửa file nào. Nếu cần hướng dẫn chạy/test/dọn file thừa, đọc `docs/README.md`.

## Project Là Gì?

Project là web app hệ chuyên gia chẩn đoán lỗi ô tô. Người dùng nhập triệu chứng, hệ thống match triệu chứng với Knowledge Graph/rule, tính xác suất động `P(fault | symptom)`, hỏi thêm từng bước nếu chưa đủ rõ, rồi mới đưa ra ranking lỗi cuối cùng và hướng kiểm tra/sửa chữa.

Luồng hiện tại:

```text
Nhập triệu chứng
-> match symptom trong KG/rule
-> rank fault bằng dynamic CF
-> nếu còn mơ hồ: hỏi yes/no bằng information gain hoặc procedure tree
-> cập nhật confirmed/rejected symptoms
-> đủ ngưỡng chẩn đoán
-> trả Final Ranking + resolution
```

Khi đang hỏi thêm, UI không hiện ranking cuối. Ranking tạm chỉ nằm trong `current_hypotheses` để backend/session dùng nội bộ.

## Stack Chính

```text
Backend:  FastAPI
Frontend: React + Vite
Graph:    Neo4j
Runtime:  SQLite session + Docker Compose
Core:     Python rule-based inference
Fallback: Gemini LLM nếu KG không có symptom mới
```

## Cấu Trúc Cần Biết

```text
backend/       API routes, services, SQLite session
frontend/      UI diagnostic chat, graph viewer, expert review
src/           Core inference, validator, next-question logic
scripts/       Data build/import/dev/evaluation tools
data/raw/      Dataset gốc
data/staging/  Ontology, dynamic CF, procedure trees, rules, aliases, test cases
docs/          Tài liệu project
```

## File Quan Trọng

```text
src/kg_inference.py
  Engine chính. Match symptom, tạo cf_map, rank fault bằng dynamic CF, trả next_question, status.

src/next_question.py
  Chọn câu hỏi yes/no tiếp theo bằng information gain hoặc đi theo procedure tree.

src/llm_fallback.py
  Nhánh fallback khi KG không match được symptom mới.

backend/services/diagnosis_service.py
  Orchestrator API: Neo4j KG -> staging JSON -> LLM fallback.

backend/services/session_service.py
  Lưu session hỏi đáp, confirmed/rejected symptoms, last_question, current_step_id, step_history, branch_path.

backend/services/graph_service.py
  Trả graph cho frontend, ưu tiên Neo4j và fallback sang data/staging.

frontend/src/pages/DiagnosticChat.jsx
  State machine 3 màn hình: input -> questioning -> result.

frontend/src/components/ChatBox.jsx
  Compatibility export sang QuestioningScreen.

frontend/src/components/SymptomInput.jsx
  Màn hình nhập triệu chứng ban đầu với textarea và common symptom chips.

frontend/src/components/QuestioningScreen.jsx
  Màn hình hỏi yes/no lớn cho thợ sửa xe, có progress và fault preview.

frontend/src/components/DiagnosisResult.jsx
  Hiển thị Final Ranking, parts cần chuẩn bị và repair procedure.

scripts/build_knowledge.py
  Consolidate knowledge pipeline: tính dynamic CF, build procedure tree, sinh expert tree, extract alias. Output tất cả staging artifacts. Thay thế compute_cf.py, build_procedure.py, rebuild_kg.py, build_expert_tree.py.

scripts/validate_knowledge.py
  Validate staging JSON consistency (ontology, rules, symptoms). Thay thế data_tools.py validate + rebuild.

scripts/import_neo4j.py
  Import staging files vào Neo4j. Thay thế data_tools.py rebuild.

scripts/legacy/
  Archive của các script cũ: compute_cf.py, build_procedure.py, rebuild_kg.py, build_expert_tree.py, data_tools.py.

data/staging/kg_rules_from_dataset.json
  Rule chẩn đoán chính, giữ field cũ và bổ sung symptoms/procedure/resolution.

data/staging/cf_dynamic.json
  Bảng dynamic CF: cf_map[symptom_id][fault_id].

data/staging/procedure_trees.json
  Cây bước chẩn đoán theo từng fault.

data/staging/symptom_aliases.json
  Alias để fuzzy-match input.

data/staging/ontology.json
  Ontology system/subsystem/component.
```

## Trạng Thái Chẩn Đoán

Backend trả các trạng thái chính:

```text
unknown_symptom
  Không match symptom trong KG/rule.

need_more_info
  Có giả thuyết nhưng cần hỏi thêm. Procedure tree chưa đi tới DIAGNOSED. UI chỉ hiện câu hỏi tiếp theo, chưa hiện Final Ranking.

diagnosed
  Procedure tree đã đi tới DIAGNOSED terminal. UI hiện Final Ranking + resolution.

llm_fallback
  KG không có symptom phù hợp, dùng Gemini hoặc offline fallback.
```

Ghi chú: Response gating được áp dụng tại layer `src/expert_system/response_policy.py`. Chỉ khi `procedure_terminal == "DIAGNOSED"` thì `results` mới được trả về. Nếu chưa, `results = []` và `is_final = false`.

Trường response quan trọng:

```text
next_question         Câu hỏi yes/no tiếp theo
current_hypotheses    Ranking tạm, dùng nội bộ khi need_more_info
results               Ranking cuối, chỉ dùng khi diagnosed/final
mode                  information_gain / procedure_tree
step_context          Mô tả ngắn ngữ cảnh bước hiện tại
step_progress         Tiến độ dạng 1/3 để UI vẽ progress
fault_preview         Fault đang nghi ngờ cao nhất khi còn cần xác nhận
resolution            Parts/tools/procedure khi diagnosed
reasoning_trace       Giải thích match, hypothesis, CF, question selection
source                neo4j_kg / staging_files_kg / llm_fallback
```

## Cách Chạy Nhanh

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d neo4j
python scripts/data_tools.py rebuild data/staging/kg_rules_from_dataset.json --clear
python -m uvicorn backend.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Docker full stack:

```powershell
docker compose up -d --build
```

Import lại Neo4j nếu graph rỗng:

```powershell
python scripts/data_tools.py rebuild data/staging/kg_rules_from_dataset.json --clear
```

Build lại staging data từ dataset raw:

```powershell
uv run python scripts\compute_cf.py
uv run python scripts\build_procedure.py
uv run python scripts\rebuild_kg.py
```

## Test

```powershell
pytest
cd frontend
npm run test -- --reporter=verbose
npm run build
```

Nếu dùng `uv`, có thể thay `pytest` bằng `uv run pytest`.

## Khi Muốn Sửa

Thêm/sửa rule:

```text
data/staging/kg_rules_from_dataset.json
data/staging/symptom_aliases.json
data/staging/ontology.json
```

Sửa cách rank/chẩn đoán:

```text
src/kg_inference.py
```

Sửa cách hỏi tiếp:

```text
src/next_question.py
```

Sửa flow API/session:

```text
backend/services/diagnosis_service.py
backend/services/session_service.py
```

Sửa UI hỏi đáp:

```text
frontend/src/pages/DiagnosticChat.jsx
frontend/src/components/SymptomInput.jsx
frontend/src/components/QuestioningScreen.jsx
frontend/src/components/DiagnosisResult.jsx
frontend/src/styles.css
```

Sửa graph viewer:

```text
backend/services/graph_service.py
frontend/src/pages/GraphViewer.jsx
frontend/src/components/GraphCanvas.jsx
```

## Ghi Chú Quan Trọng

- CF cũ `0.7` đã được thay bằng dynamic CF sinh từ dataset raw.
- Diagnostic Chat được thiết kế hỏi từng bước và chỉ hiện kết quả cuối khi `status = diagnosed`.
- `step_answer: null` là skip: backend không tính là confirmed/rejected symptom.
- Neo4j không bắt buộc cho demo cơ bản vì backend fallback sang `data/staging`.
- LLM fallback chỉ chạy thật khi `.env` có `GEMINI_API_KEY`; nếu không, hệ thống trả `UNMAPPED_SYMPTOM` để báo cần bổ sung rule.
- Tài liệu chạy/test/dọn file thừa nằm ở `docs/README.md`; tài liệu chi tiết hơn nằm ở `docs/Expert_System_Map.md`.
