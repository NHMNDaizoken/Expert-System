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
src/expert_system/engine.py
  Engine chính. Match symptom, tạo cf_map, rank fault bằng dynamic CF, chọn information-gain question, trả next_question, status.

src/expert_system/procedure.py
  Đi theo procedure tree của từng fault để hỏi yes/no theo bước.

src/expert_system/matcher.py
  Chuẩn hóa input người dùng và fuzzy-match với symptom aliases.

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

scripts/import_graph.py
  Import staging files vào Neo4j. Đây là lệnh import hiện tại; `scripts/import_neo4j.py` là wrapper tương thích.

scripts/rebuild_hierarchy.py
  Sinh lại `data/staging/expert_tree.json` từ staging JSON hiện có.

scripts/translate_vi.py
  Cập nhật `data/staging/vi_translations.json` từ dataset raw bằng Gemini API nếu còn text chưa dịch.

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

## Cấu Trúc Hệ Chuyên Gia Khi Bảo Vệ

```text
Knowledge base  -> data/staging/*.json chứa triệu chứng, lỗi, linh kiện, ontology và quan hệ.
Rule base       -> data/staging/kg_rules_from_dataset.json chứa luật IF symptoms THEN fault.
Inference engine-> src/expert_system/engine.py match triệu chứng, tính CF và xếp hạng lỗi.
Question flow   -> procedure tree runtime sinh câu hỏi từ symptom, không hỏi bước kỹ thuật.
Technician steps-> resolution/procedure trong rule, chỉ hiển thị sau khi đã chẩn đoán.
Graph UI        -> backend/services/graph_service.py và frontend graph pages dùng để giải thích/visualize.
Neo4j           -> hữu ích cho graph demo, nhưng không bắt buộc vì inference có thể chạy từ JSON staging.
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

Ghi chú: Response gating được áp dụng tại layer `src/expert_system/policy.py`. Chỉ khi `procedure_terminal == "DIAGNOSED"` thì `results` mới được trả về. Nếu chưa, `results = []` và `is_final = false`.

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
python scripts/import_graph.py --clear
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
python scripts/import_graph.py --clear
```

Build lại staging data từ dataset raw (consolidated script):

```powershell
uv run python scripts/translate_vi.py
uv run python scripts/build_knowledge.py --rebuild-from-raw
uv run python scripts/validate_knowledge.py
uv run python scripts/import_graph.py --clear
```

Validate staging data:

```powershell
uv run python scripts/validate_knowledge.py
```

**Legacy** (không nên dùng nữa):

```powershell
# Cách cũ - các script riêng lẻ (đã gộp vào build_knowledge.py)
# uv run python scripts/legacy/compute_cf.py
# uv run python scripts/legacy/build_procedure.py
# uv run python scripts/legacy/rebuild_kg.py
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
src/expert_system/engine.py
```

Sửa cách hỏi tiếp:

```text
src/expert_system/procedure.py
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
