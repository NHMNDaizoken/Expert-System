# Car Diagnostic Expert System

Hệ chuyên gia chẩn đoán lỗi ô tô dạng web app. Người dùng nhập triệu chứng như `dim headlights`, `engine does not crank`, `ABS warning light on`; hệ thống chuẩn hóa input, match triệu chứng, suy luận lỗi có khả năng xảy ra, xếp hạng bằng dynamic Certainty Factor, hỏi thêm theo information gain/procedure tree nếu còn mơ hồ, rồi hiển thị kết quả cuối kèm parts và repair procedure.

## 1. Project Làm Gì?

Project mô phỏng một hệ chuyên gia cho miền chẩn đoán ô tô:

- `React + Vite`: giao diện nhập triệu chứng, xem kết quả, xem Knowledge Graph dạng focused subgraph và duyệt rule.
- `FastAPI`: backend API cho frontend.
- `Neo4j`: lưu Knowledge Graph gồm hệ thống xe, cụm con, linh kiện, lỗi, triệu chứng và cách sửa.
- `SQLite`: lưu session chẩn đoán tạm thời cho luồng hỏi thêm.
- `src/`: logic suy luận lõi gồm chuẩn hóa input, fuzzy matching, dynamic CF ranking, information gain và procedure-tree question selection.

Hệ thống có thể chạy với Neo4j đầy đủ. Một số phần inference/evaluation vẫn có thể đọc dữ liệu JSON trong `data/staging` khi cần fallback.

## 2. Cấu Trúc Thư Mục

```text
backend/       FastAPI app: routes, schemas, services, SQLite session storage
frontend/      React + Vite UI: diagnosis chat, graph viewer, expert review
src/           Core expert-system logic: KG inference, CF, importer, validator
scripts/       Script xử lý data, import Neo4j, kiểm tra dev, evaluation
data/raw/      Dữ liệu gốc
data/staging/  Ontology, dynamic CF, procedure trees, rules, aliases, test cases
tests/         Unit tests
docs/          Tài liệu map duy nhất cho hệ chuyên gia và trạng thái project
```

## 3. Xem Nhanh Phần Hệ Chuyên Gia

Nếu cần show code để giải thích "hệ chuyên gia nằm ở đâu", đọc file:

```text
docs/Project_Brief.md
docs/Expert_System_Map.md
```

Đọc `Project_Brief.md` trước nếu cần handoff nhanh cho người khác. Đọc `Expert_System_Map.md` nếu cần đi sâu vào flow hệ chuyên gia, data, API và graph.

Tóm tắt nhanh (sau refactoring):

- Luật chẩn đoán: `data/staging/kg_rules_from_dataset.json`.
- Dynamic CF: `data/staging/cf_dynamic.json`.
- Procedure tree: `data/staging/procedure_trees.json`.
- Quan hệ graph: `data/staging/ontology.json`, `backend/services/graph_service.py`.
- **Bộ suy luận chính**: `src/expert_system/engine.py` (ExpertSystemEngine).
- **Matcher triệu chứng**: `src/expert_system/matcher.py` (SymptomMatcher).
- **Procedure tree / câu hỏi**: `src/expert_system/procedure.py` và logic information gain trong `src/expert_system/engine.py`.
- **Response filtering**: `src/expert_system/policy.py` (apply_response_policy).
- API hỏi-đáp: `backend/services/diagnosis_service.py`, `backend/services/session_service.py`.
- UI show luật/quan hệ/trace: `frontend/src/pages/GraphViewer.jsx`, `frontend/src/components/ReasoningTrace.jsx`.

**Legacy modules** (không dùng nữa, lưu ở `src/legacy/` cho backward compatibility):
- `src/legacy/kg_inference.py`, `src/legacy/next_question.py`, `src/legacy/cf.py`, `src/legacy/kg_validator.py`

## 4. Yêu Cầu

Cài sẵn:

- Python 3.11+
- Node.js 20+ và npm
- Docker Desktop

Tạo file môi trường:

```powershell
Copy-Item .env.example .env
```

`.env` dùng cho chế độ chạy local. Docker Compose đã có cấu hình mặc định trong `docker-compose.yml`.

## 5. Cách 1: Chạy Local Bằng Môi Trường Ảo

Cách này dùng khi bạn muốn cập nhật thư viện Python, sửa dữ liệu, build lại rule, validate rule hoặc import thông tin mới vào Knowledge Graph.

### 5.1. Tạo môi trường ảo và cài thư viện Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Ý nghĩa:

- `python -m venv .venv`: tạo môi trường Python riêng cho project.
- `Activate.ps1`: kích hoạt môi trường ảo.
- `pip install -r requirements.txt`: cài FastAPI, Neo4j driver, pandas, RapidFuzz, dotenv, uvicorn và các thư viện cần thiết.

Nếu sau này có thay đổi trong `requirements.txt`, chỉ cần kích hoạt lại `.venv` rồi chạy:

```powershell
pip install -r requirements.txt
```

Nếu máy chưa có `python` global nhưng có `uv`, có thể chạy các lệnh Python theo dạng:

```powershell
uv run python scripts/validate_knowledge.py
```

### 5.2. Chạy Neo4j local bằng Docker

Backend local cần Neo4j để import và đọc Knowledge Graph:

```powershell
docker compose up -d neo4j
```

Đảm bảo `.env` đang trỏ tới Neo4j local:

```text
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
ADMIN_API_KEY=change_me_admin_key
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash
FRONTEND_ORIGIN=http://localhost:5173
SQLITE_DB_PATH=data/app.sqlite3
```

Mở Neo4j Browser tại:

```text
http://localhost:7474
```

Đăng nhập:

```text
Username: neo4j
Password: password123
```

### 5.3. Cập nhật dữ liệu vào Knowledge Graph

Nếu bạn sửa dataset gốc trong `data/raw/automotive_faults.json` và muốn sinh lại staging rules từ đầu, chạy một lệnh consolidate duy nhất:

```powershell
python scripts/build_knowledge.py --rebuild-from-raw
```

Lệnh này sẽ:
- Tính dynamic CF từ dataset raw (`data/raw/automotive_faults.json`)
- Build procedure tree từ diagnosis steps
- Sinh ra `data/staging/cf_dynamic.json`, `data/staging/procedure_trees.json`, `data/staging/kg_rules_from_dataset.json`, `data/staging/symptom_aliases.json`, `data/staging/expert_tree.json`

Nếu cần cập nhật nhãn tiếng Việt trước khi rebuild, chạy:

```powershell
python scripts/translate_vi.py
```

Nếu chỉ muốn sinh lại cây chuyên gia từ staging hiện có:

```powershell
python scripts/rebuild_hierarchy.py
```

Sau khi build xong, validate dữ liệu:

```powershell
python scripts/validate_knowledge.py
```

Nếu không sửa dataset raw mà chỉ muốn import staging rules vào Neo4j:

```powershell
python scripts/import_graph.py --clear
```

Ghi chú: `scripts/import_neo4j.py` vẫn tồn tại như wrapper tương thích và gọi sang `scripts/import_graph.py`. Các script cũ (`compute_cf.py`, `build_expert_tree.py`, `build_procedure.py`, `rebuild_kg.py`, `data_tools.py`) đã được gom vào `scripts/build_knowledge.py`, `scripts/rebuild_hierarchy.py`, hoặc lưu trong `scripts/legacy/` nếu cần tham khảo.

### 5.4. Chạy backend và frontend local

Chạy backend:

```powershell
python -m uvicorn backend.main:app --reload
```

Backend mặc định:

- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Mở terminal khác để chạy frontend:

```powershell
cd frontend
npm install
npm run dev
```

Frontend mặc định:

- UI: `http://localhost:5173`
- Knowledge Graph: `http://localhost:5173/graph`

## 6. Cách 2: Docker Một Lệnh Chạy Hết

Cách này dùng khi bạn muốn chạy toàn bộ hệ thống nhanh gọn sau khi đã có code và dữ liệu staging.

```powershell
docker compose up -d --build
```

Lệnh này build và chạy 3 service:

- `neo4j`: Neo4j Browser tại `http://localhost:7474`, Bolt tại `localhost:7687`.
- `backend`: FastAPI tại `http://localhost:8000`.
- `frontend`: React/Vite tại `http://localhost:5173`.

Kiểm tra trạng thái container:

```powershell
docker compose ps
```

Xem log nếu cần debug:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f neo4j
```

Nếu Docker chạy lần đầu và Neo4j còn trống, import dữ liệu vào KG bằng backend container:

```powershell
docker compose exec backend python -m scripts.import_graph --clear
```

Sau đó mở:

- App: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Neo4j Browser: `http://localhost:7474`

Dừng toàn bộ service:

```powershell
docker compose down
```

Nếu muốn xóa luôn dữ liệu Neo4j volume để làm lại từ đầu:

```powershell
docker compose down -v
```

## 7. Kiểm Tra Knowledge Graph Trong Neo4j

Vào Neo4j Browser tại `http://localhost:7474`, chạy các câu Cypher sau.

Đếm node theo label:

```cypher
MATCH (n) RETURN labels(n) AS labels, count(n) AS total ORDER BY total DESC;
```

Xem graph mẫu:

```cypher
MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 100;
```

Xem lỗi và triệu chứng:

```cypher
MATCH (f:Fault)-[r:HAS_SYMPTOM]->(s:Symptom)
RETURN f.display_name AS fault, r.cf AS cf, s.display_name AS symptom
ORDER BY fault, cf DESC;
```

Xem lỗi ảnh hưởng linh kiện nào:

```cypher
MATCH (f:Fault)-[:AFFECTS]->(c:Component)
RETURN f.display_name AS fault, c.display_name AS component;
```

Xem lỗi và hướng sửa:

```cypher
MATCH (f:Fault)-[:FIXED_BY]->(r:Repair)
RETURN f.display_name AS fault, r.display_name AS repair;
```

## 8. Lệnh Dev Và Test

Kiểm tra kết nối Neo4j:

```powershell
python scripts/dev_checks.py neo4j
```

Test chuẩn hóa input và fuzzy matching:

```powershell
python scripts/dev_checks.py normalizer "ABS warning light on"
```

Xem rule staging theo symptom id:

```powershell
python scripts/dev_checks.py rules SYM_ABS_WARNING_LIGHT_ON
```

Chạy inference thủ công:

```powershell
python scripts/dev_checks.py inference "dim headlights and clicking noise when starting"
```

Chạy unit test:

```powershell
uv run pytest
```

Chạy frontend test và build:

```powershell
cd frontend
npm run test -- --reporter=verbose
npm run build
```

Chạy evaluation:

```powershell
python scripts/evaluate_diagnosis.py
```

Baseline hiện tại: 20 test case, Top-1/Top-3/Top-5 đều 100%.

## 9. API Chính

```http
GET /health
```

Kiểm tra backend còn sống.

```http
POST /api/diagnose
```

Body mẫu:

```json
{
  "text": "clicking noise when starting and dim headlights",
  "top_k": 5
}
```

Response gồm `matched_symptoms`, `diagnoses`, `results`, `next_question`, `reasoning_trace`, `status`, `session_id`, `mode`, `step_context`, `step_progress`, `fault_preview`, `resolution`.

Diagnostic Chat là luồng từng bước. Nếu API trả `status = need_more_info`, UI chỉ hiển thị câu hỏi tiếp theo và chưa render ranking cuối; các giả thuyết tạm thời nằm trong `current_hypotheses` để lưu session/trace. Chỉ khi `status = diagnosed` và `is_final = true` thì `results` mới có ranking kết luận.

Luồng API mới cho UI:

```http
POST /session/new
GET  /session/{session_id}
POST /diagnose
```

Body tiếp tục session:

```json
{
  "session_id": "...",
  "symptom": "blue smoke from exhaust",
  "step_answer": true
}
```

`step_answer` có thể là `true`, `false` hoặc `null` để skip. Endpoint `/api/answer` vẫn được giữ để tương thích với flow cũ.

Luồng chẩn đoán ưu tiên theo thứ tự:

1. Neo4j Knowledge Graph.
2. JSON staging files trong `data/staging` nếu Neo4j lỗi/rỗng.
3. LLM fallback nếu KG không match được symptom mới. Nhánh này dùng `GEMINI_API_KEY`; nếu chưa cấu hình key, API vẫn trả một kết quả `UNMAPPED_SYMPTOM` để UI không bị trống và báo cần bổ sung rule.

```http
POST /api/answer
```

Body mẫu:

```json
{
  "session_id": "...",
  "answer": "yes"
}
```

```http
GET /api/graph
```

Lấy full Knowledge Graph để frontend hiển thị. API trả `nodes` với `id`, `label`, `type`, `status`, `metadata` và `edges` với `id`, `source`, `target`, `type`, `cf`, `confidence_label`. Backend ưu tiên đọc từ Neo4j; nếu Neo4j chưa có dữ liệu hoặc không kết nối được, backend fallback sang file trong `data/staging`.

```http
GET /api/graph/fault/{fault_id}
```

Lấy focused subgraph quanh một `Fault`: triệu chứng, component bị ảnh hưởng, subsystem/system cha, repair và relationship liên quan. Endpoint này dùng cho graph demo kiểu expert-system path: `Symptom -> Fault -> Component -> Subsystem -> VehicleSystem` và `Fault -> Repair`.

```http
GET /api/graph/search?q=battery
GET /api/graph/stats
```

`search` trả danh sách node compact theo `id/name/display_name/label_vi`; `stats` trả số lượng node theo label và tổng số relationship.

```http
GET  /api/pending-rules
POST /api/rules/{rule_id}/approve
POST /api/rules/{rule_id}/reject
```

Các API review rule yêu cầu header `X-Admin-API-Key` khớp `ADMIN_API_KEY`.

## 10. Ghi Chú Lỗi Thường Gặp

- Nếu PowerShell báo không thấy `python`, hãy kích hoạt `.venv`, dùng `py` thay cho `python`, hoặc chạy qua `uv run python ...`.
- Nếu không chạy được `Activate.ps1`, mở PowerShell bằng quyền phù hợp hoặc chạy `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- Nếu frontend lỗi thiếu `vite`, chạy lại `npm install` trong thư mục `frontend`.
- Nếu backend chạy nhưng `/api/graph` trống, hãy chạy lại `python scripts/import_graph.py --clear` hoặc `docker compose exec backend python -m scripts.import_graph --clear` để import dữ liệu vào Neo4j.
- `data/app.sqlite3` là file runtime, có thể xóa; backend sẽ tạo lại khi khởi động.
- Nếu thấy tài liệu/ảnh mở `docs/fixed.md`, file đó không còn nằm trong workspace hiện tại; dùng `docs/Project_Brief.md` và `docs/Expert_System_Map.md`.
