# Car Diagnostic Expert System Map

Cập nhật: 2026-05-11

Tài liệu này là bản đồ chi tiết cho project: phần nào là hệ chuyên gia, phần nào là web/API hỗ trợ, dữ liệu nằm ở đâu, chạy như thế nào và bước tiếp theo là gì.

Nếu cần bản handoff ngắn cho người khác đọc nhanh, dùng `docs/Project_Brief.md` trước. Nếu cần checklist chạy/test/dọn file thừa, dùng `docs/README.md`.

## 1. Project Làm Gì?

Đây là hệ chuyên gia chẩn đoán lỗi ô tô dạng web app. Người dùng nhập mô tả triệu chứng như `dim headlights`, `engine does not crank`, `clicking noise when starting`, `ABS warning light on`; hệ thống sẽ:

1. Chuẩn hóa input và fuzzy-match triệu chứng bằng tập alias.
2. Suy luận lỗi có khả năng xảy ra từ Neo4j Knowledge Graph hoặc JSON fallback.
3. Xếp hạng lỗi bằng dynamic Certainty Factor `P(fault | symptom)` sinh từ dataset.
4. Nếu kết quả còn mơ hồ, chọn câu hỏi tiếp theo bằng information gain hoặc đi theo procedure tree của fault dẫn đầu.
5. Khi đủ ngưỡng, trả ranking cuối, reasoning trace và resolution gồm parts/tools/procedure.

Stack hiện tại:

| Phần | Công nghệ |
|------|-----------|
| Backend API | FastAPI, Pydantic |
| Frontend | React 19, Vite, React Router |
| Graph UI | ReactFlow, Dagre |
| Graph Database | Neo4j 5 |
| Session storage | SQLite |
| Core logic | Python |
| Matching text | RapidFuzz |
| Evaluation/Test | pytest, custom evaluation script |
| Runtime | Docker Compose |
| AI fallback | Gemini khi có `GEMINI_API_KEY` |

## 2. Cấu Trúc Chuẩn

```text
backend/       FastAPI app: routes, schemas, services, SQLite session storage
frontend/      React + Vite UI: diagnosis chat, graph viewer, expert review
src/           Core expert-system logic: KG inference, CF, validator, question selection
scripts/       Data/import/dev/evaluation scripts
data/raw/      Dữ liệu gốc và flowchart tham khảo
data/staging/  Ontology, dynamic CF, procedure trees, rules, aliases, test cases
tests/         Unit tests cho CF, KG inference và rule format
docs/          README chạy/test, brief handoff và map chi tiết hệ chuyên gia
```

Nếu IDE hiện quá nhiều file, `.vscode/settings.json` đã exclude `.venv`, `frontend/node_modules`, cache, build output và runtime SQLite DB.

## 3. Phần Hệ Chuyên Gia Nằm Ở Đâu?

Các file lõi cần show khi thuyết trình:

```text
data/staging/kg_rules_from_dataset.json   Luật chẩn đoán IF symptom THEN fault, kèm procedure/resolution
data/staging/cf_dynamic.json              Dynamic CF: cf_map[symptom_id][fault_id]
data/staging/procedure_trees.json         Cây diagnostic step yes/no cho từng fault
data/staging/symptom_aliases.json         Từ điển triệu chứng và alias để match input
data/staging/ontology.json                Ontology: system/subsystem/component
src/kg_inference.py                       Engine suy luận backend đang dùng
src/next_question.py                      Information gain + procedure-tree question selection
src/cf.py                                 Công thức Certainty Factor phụ trợ
backend/services/diagnosis_service.py     API gọi engine, enrich response và lưu session hỏi-đáp
backend/services/session_service.py       SQLite session, current_step_id, step_history, branch_path
backend/services/graph_service.py         Biến rule/ontology thành graph nodes/edges
frontend/src/pages/DiagnosticChat.jsx     State machine input/questioning/result
frontend/src/components/QuestioningScreen.jsx  Màn hình yes/no mobile-first
frontend/src/components/DiagnosisResult.jsx    Màn hình kết quả và resolution
frontend/src/pages/GraphViewer.jsx        Màn hình xem luật và quan hệ trên graph
```

Chỉ giữ một luồng suy luận chính: backend, evaluation và dev checks đều đi qua `src/kg_inference.py`.

## 4. Dữ Liệu Và Luật

File dữ liệu chính:

```text
data/staging/ontology.json
data/staging/cf_dynamic.json
data/staging/procedure_trees.json
data/staging/symptom_aliases.json
data/staging/kg_rules_from_dataset.json
data/staging/test_cases.json
data/raw/automotive_faults.json
```

Snapshot hiện tại:

| Hạng mục | Số lượng |
|----------|----------|
| Staging rules | 99 |
| Symptom aliases | 143 |
| Dynamic CF symptoms | 143 |
| Procedure trees | 99 |
| Evaluation test cases | 20 |
| Vehicle systems trong ontology | 9 |

Rule mẫu:

```json
{
  "fault_id": "FLT_001",
  "fault_name": "abs_control_module",
  "display_name": "ABS Control Module",
  "system_id": "SYS_ELECTRICAL",
  "affected_components": ["CMP_STARTER_MOTOR"],
  "symptoms": [
    {"symptom_id": "SYM_ABS_WARNING_LIGHT_ON", "cf": 1.0, "priority": 1}
  ],
  "procedure": {
    "entry_step": "flt_001_s1",
    "steps": {
      "flt_001_s1": {
        "question": "Check ABS fuse?",
        "yes_next": "flt_001_s2",
        "no_next": "REFUTED"
      }
    }
  },
  "resolution": {
    "parts": ["ABS Control Module"],
    "tools": ["OBD scanner", "Multimeter"],
    "procedure": "Check ABS fuse. Inspect wiring to ABS module."
  },
  "repairs": [
    {"repair_id": "REP_001", "steps": ["Check ABS fuse"]}
  ],
  "status": "approved"
}
```

Diễn giải theo hệ chuyên gia:

```text
IF SYM_ABS_WARNING_LIGHT_ON với dynamic CF = 1.0
THEN FLT_001 / ABS Control Module
AFFECTS CMP_STARTER_MOTOR
FIXED_BY REP_001
```

## 5. Knowledge Graph

Graph gồm các node chính:

```text
VehicleSystem
Subsystem
Component
Fault
Symptom
Repair
```

Quan hệ chính:

```text
Subsystem -[:PART_OF]-> VehicleSystem
Component -[:PART_OF]-> Subsystem
Fault -[:AFFECTS]-> Component
Fault -[:HAS_SYMPTOM {cf, priority}]-> Symptom
Fault -[:FIXED_BY]-> Repair
Fault -[:RELATED_TO]-> Fault
```

Các file liên quan:

```text
data/staging/ontology.json
data/staging/kg_rules_from_dataset.json
scripts/build_knowledge.py           Consolidate: tính CF, build procedure, expert tree, alias
scripts/validate_knowledge.py        Validate staging JSON consistency
scripts/import_neo4j.py              Import staging vào Neo4j
backend/services/graph_service.py
frontend/src/components/GraphCanvas.jsx
```

Lưu ý: Các script cũ (`compute_cf.py`, `build_procedure.py`, `rebuild_kg.py`, `data_tools.py`) được archive trong `scripts/legacy/`.

## 6. Suy Luận Chạy Như Thế Nào?

File chính: `src/kg_inference.py` (engine) + `src/expert_system/response_policy.py` (gating layer)

Luồng xử lý:

1. `SymptomMatcher.match()` fuzzy-match input với `symptom_aliases.json`.
2. `KGInference.diagnose()` lấy các symptom đã xác nhận.
3. Engine tạo `cf_map[symptom_id][fault_id]` từ `kg_rules_from_dataset.json`.
4. `rank_faults()` tính điểm:

```text
score(fault) =
  product(CF(confirmed_symptom -> fault))
  * product(1 - CF(rejected_symptom -> fault))

Sau đó normalize để tổng score của các fault = 1.
```

5. `check_diagnosed()` chỉ kết luận khi fault top > 0.70 và cách fault thứ hai > 0.30. Engine output `procedure_terminal` vào response.
6. **Response Policy Layer** (`src/expert_system/response_policy.py`): Áp dụng `apply_response_policy()` tại `backend/services/diagnosis_service.py` để gate finalization:
   - Nếu `procedure_terminal != "DIAGNOSED"`: set `status = need_more_info`, `results = []`, `is_final = false` (UI chỉ hiện câu hỏi tiếp theo)
   - Nếu `procedure_terminal == "DIAGNOSED"`: set `status = diagnosed`, `results = [ranking]`, `is_final = true` (UI hiện Final Ranking + resolution)

7. Nếu Neo4j lỗi/rỗng, backend fallback sang JSON rules trong `data/staging`.
8. Nếu KG vẫn không match symptom mới, backend dùng LLM fallback qua Gemini khi có `GEMINI_API_KEY`; nếu chưa có key thì trả `UNMAPPED_SYMPTOM` để UI không trống và báo cần bổ sung rule.
9. Ranking tạm thời được giữ trong `current_hypotheses` cho frontend để hiện fault preview khi còn cần xác nhận.

`reasoning_trace` có các phần:

```text
normalization          Match input thành symptom nào
hypothesis_generation  Sinh fault hypothesis từ symptom nào
backward_chaining      IF symptom THEN fault
cf_calculation_steps   Từng bước cộng CF/bonus
question_selection     Vì sao chọn câu hỏi tiếp theo
final_decision         Fault đứng đầu và final_cf
ranking                Bảng xếp hạng fault
```

## 7. Smart Questioning

File chính: `src/next_question.py`

Khi có nhiều fault gần đúng nhau, engine có 2 mode:

```text
procedure_tree
  Khi đang đi trong cây bước của fault dẫn đầu và score top đủ cao.

information_gain
  Khi chưa vào cây hoặc top fault chưa đủ rõ.
```

Với information gain, engine:

1. Lấy tối đa 3 fault top đầu.
2. Lấy symptom liên quan của các fault đó.
3. Loại symptom đã xác nhận hoặc đã bị trả lời "không".
4. Mô phỏng YES/NO cho từng symptom chưa hỏi.
5. Chọn symptom giảm entropy nhiều nhất.

API hỏi-đáp:

```text
POST /session/new   Tạo session rỗng
GET  /session/{id}  Xem session, gồm step_history/branch_path
POST /api/diagnose  Tạo hoặc tiếp tục session, nhận symptom/step_answer
POST /api/answer    Endpoint cũ, vẫn giữ tương thích
```

Trong Diagnostic Chat, hệ thống đi từng bước:

```text
Triệu chứng ban đầu -> ranking giả thuyết hiện tại -> hỏi thêm yes/no
-> cập nhật CF/ranking -> hỏi tiếp nếu còn mơ hồ
-> hết câu hỏi -> final ranking
```

Vì vậy Top/Candidate ranking ở giữa luồng chỉ dùng để giải thích hệ thống đang nghiêng về lỗi nào, không phải kết luận cuối.

## 8. Backend Và API

Entry point: `backend/main.py`

Route chính:

```http
GET  /health
POST /session/new
GET  /session/{session_id}
POST /diagnose
POST /api/diagnose
POST /api/answer
GET  /api/graph
GET  /api/graph/fault/{fault_id}
GET  /api/graph/search?q=battery
GET  /api/graph/stats
GET  /api/pending-rules
POST /api/rules/{rule_id}/approve
POST /api/rules/{rule_id}/reject
```

Service chính:

```text
backend/services/diagnosis_service.py  Gọi KGInference, enrich confidence label, session
backend/services/session_service.py    Lưu diagnosis session, answers, last_question, step state
backend/services/graph_service.py      Chuẩn hóa graph, focused graph, search, stats, fallback
backend/services/review_service.py     Expert review rule trong Neo4j
```

SQLite runtime mặc định: `data/app.sqlite3`.

## 9. Frontend

Entry point: `frontend/src/App.jsx`

Màn hình chính:

```text
/diagnosis  Diagnostic chat cho người dùng nhập triệu chứng
/graph      Xem full/focused Knowledge Graph
/review     Expert review rule
```

File chính:

```text
frontend/src/pages/DiagnosticChat.jsx
frontend/src/components/SymptomInput.jsx
frontend/src/components/QuestioningScreen.jsx
frontend/src/pages/GraphViewer.jsx
frontend/src/pages/ExpertReview.jsx
frontend/src/components/DiagnosisResult.jsx
frontend/src/components/ReasoningTrace.jsx
frontend/src/components/GraphCanvas.jsx
frontend/src/components/ChatBox.jsx
frontend/src/api/client.js
```

`DiagnosticChat` là state machine 3 màn hình:

```text
input -> questioning -> result
```

`QuestioningScreen` có progress bar, fault preview, question card, nút YES/NO lớn và skip. `DiagnosisResult` ưu tiên hiển thị lỗi top 1, confidence bar, parts cần chuẩn bị và repair procedure.

`GraphViewer` có search, stats cards, full/focused graph mode và side panel xem metadata. `GraphCanvas` dùng ReactFlow + Dagre để biểu diễn path: `Symptom -> Fault -> Component -> Subsystem -> VehicleSystem` và `Fault -> Repair`.

## 10. Chạy Project

Tạo file môi trường:

```powershell
Copy-Item .env.example .env
```

Biến môi trường quan trọng:

```text
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
ADMIN_API_KEY=change_me_admin_key
FRONTEND_ORIGIN=http://localhost:5173
SQLITE_DB_PATH=data/app.sqlite3
```

Chạy local:

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

URL mặc định:

```text
Frontend:      http://localhost:5173
Backend API:   http://localhost:8000
API docs:      http://localhost:8000/docs
Neo4j Browser: http://localhost:7474
```

Chạy toàn bộ bằng Docker Compose:

```powershell
docker compose up -d --build
```

Nếu Neo4j mới/rỗng, import data bằng:

```powershell
docker compose exec backend python scripts/data_tools.py rebuild data/staging/kg_rules_from_dataset.json --clear
```

## 11. Lệnh Data, Dev Và Test

Build staging data (consolidated scripts):

```powershell
# Build all staging artifacts from data/raw/automotive_faults.json
uv run python scripts/build_knowledge.py --rebuild-from-raw

# Validate staging artifacts
uv run python scripts/validate_knowledge.py

# Import into Neo4j
uv run python scripts/import_graph.py
```

**Legacy** (do not use - scripts consolidated into build_knowledge.py):

```powershell
# Old individual build scripts (replaced by build_knowledge.py)
# uv run python scripts/legacy/compute_cf.py
# uv run python scripts/legacy/build_procedure.py
# uv run python scripts/legacy/rebuild_kg.py
# uv run python scripts/legacy/data_tools.py
```

Dev check:

```powershell
python scripts/dev_checks.py neo4j
python scripts/dev_checks.py normalizer "ABS warning light on"
python scripts/dev_checks.py rules SYM_ABS_WARNING_LIGHT_ON
python scripts/dev_checks.py inference "dim headlights and clicking noise when starting"
```

Test/evaluation:

```powershell
pytest
cd frontend
npm run test -- --reporter=verbose
npm run build
python scripts/evaluate_diagnosis.py
```

Nếu dùng `uv`, có thể thay `pytest` bằng `uv run pytest`.

Baseline evaluation gần nhất:

```text
Cases: 12
Top-1: 100.00%
Top-3: 100.00%
Top-5: 100.00%
```

## 12. Trạng Thái Và Bước Tiếp Theo

| Phase | Nội dung | Trạng thái |
|-------|----------|------------|
| Phase 1 | Dynamic CF, procedure tree, rebuilt KG schema | Hoàn thành |
| Phase 2 | Dynamic inference + information gain/procedure tree | Hoàn thành |
| Phase 3 | Backend session/API step state + resolution response | Hoàn thành |
| Phase 4 | Mobile-first diagnosis UI input/question/result | Hoàn thành |
| Graph | Neo4j import/fallback visualization | Hoàn thành |
| Evaluation | Unit/evaluation layer | Hoàn thành |

Bước tiếp theo hợp lý:

1. Kiểm thử thủ công end-to-end luồng diagnostic chat trên browser: nhập triệu chứng, nhận `next_question`, trả lời yes/no, xem result có resolution.
2. Thêm integration tests sâu hơn cho `/api/graph`, `/api/graph/fault/{fault_id}`, `/api/graph/search`, `/api/graph/stats`.
3. Mở rộng `data/staging/test_cases.json` khi thêm rule mới.
4. Cải thiện ontology mapping trong `scripts/data_tools.py`.
5. Cải thiện câu hỏi tự nhiên theo ngôn ngữ UI, có thể hỗ trợ song ngữ Anh/Việt.
6. Bổ sung dữ liệu automotive thực tế hơn để KG phong phú hơn.

## 13. File Nên Đọc Theo Thứ Tự

Nếu cần hiểu nhanh hoặc demo code, đọc theo thứ tự này:

1. `data/staging/cf_dynamic.json`
2. `data/staging/procedure_trees.json`
3. `data/staging/kg_rules_from_dataset.json`
4. `src/kg_inference.py`
5. `src/next_question.py`
6. `backend/services/diagnosis_service.py`
7. `backend/services/session_service.py`
8. `frontend/src/pages/DiagnosticChat.jsx`
9. `frontend/src/components/QuestioningScreen.jsx`
10. `frontend/src/components/DiagnosisResult.jsx`
11. `frontend/src/pages/GraphViewer.jsx`
12. `scripts/evaluate_diagnosis.py`

Tóm lại: `data/staging` là tri thức, `src/kg_inference.py` là bộ suy luận, `src/next_question.py` là chiến lược hỏi thêm, `backend` là API/session, `frontend` là phần minh họa luật và quan hệ.
