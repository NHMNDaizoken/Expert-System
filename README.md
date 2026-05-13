# Car Diagnostic Expert System

Cập nhật: 2026-05-12

Ứng dụng web hệ chuyên gia chẩn đoán lỗi ô tô. Người dùng nhập triệu chứng tự do, hệ thống chuẩn hóa và fuzzy-match triệu chứng, suy luận fault bằng dynamic CF, hỏi thêm theo information gain hoặc procedure tree khi chưa chắc chắn, rồi trả kết quả cuối kèm hướng kiểm tra và sửa chữa.

## 1. Tổng Quan

Thành phần chính:

- Backend API: FastAPI.
- Frontend: React + Vite.
- Tri thức chẩn đoán: JSON trong `data/staging`.
- Graph visualization: Neo4j (có fallback từ JSON).
- Session runtime: SQLite.
- Inference engine: `src/expert_system/inference/engine.py`.

Luồng chuẩn:

1. Người dùng nhập triệu chứng.
2. `SymptomMatcher` chuẩn hóa + fuzzy-match alias.
3. `ExpertSystemEngine` xếp hạng fault bằng CF động.
4. Nếu cần thêm thông tin thì sinh `next_question`.
5. Session được lưu ở SQLite để hỏi đáp nhiều bước.
6. Khi đủ điều kiện kết luận mới trả `results` cuối.

## 2. Cấu Trúc Thư Mục

```text
backend/       FastAPI app: routes, schemas, services, SQLite session storage
frontend/      React + Vite UI: diagnosis chat, graph viewer, expert review
src/           Core expert-system logic
scripts/       Build knowledge, validate, import graph, dev checks, evaluation
data/raw/      Dataset gốc
data/staging/  Artifacts tri thức đã xử lý
tests/         Test backend và engine
docs/          Tài liệu chi tiết
```

## 3. Các File Cốt Lõi Cần Biết

Inference và policy:

- `src/expert_system/inference/engine.py`: engine chính.
- `src/expert_system/inference/fuzzy.py`: match triệu chứng.
- `src/expert_system/inference/procedure.py`: hỏi theo procedure tree.
- `src/expert_system/inference/policy.py`: gate kết quả final.

Backend orchestration:

- `backend/services/diagnosis_service.py`: luồng chẩn đoán + fallback + enrich response.
- `backend/services/session_service.py`: quản lý phiên và trạng thái bước.
- `backend/services/graph_service.py`: graph API + fallback.
- `src/expert_system/llm_fallback.py`: triển khai chính cho LLM fallback.

Tri thức staging:

- `data/staging/kg_rules_from_dataset.json`: rule chẩn đoán.
- `data/staging/cf_dynamic.json`: bản đồ CF động.
- `data/staging/procedure_trees.json`: cây câu hỏi.
- `data/staging/symptom_aliases.json`: alias triệu chứng.
- `data/staging/ontology.json`: ontology hệ thống xe.

## 4. Yêu Cầu Môi Trường

- Python 3.11+
- Node.js 20+
- Docker Desktop

Tạo `.env`:

```powershell
Copy-Item .env.example .env
```

Biến quan trọng:

```text
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
ADMIN_API_KEY=change_me_admin_key
FRONTEND_ORIGIN=http://localhost:5173
SQLITE_DB_PATH=data/app.sqlite3
GEMINI_API_KEY=
```

## 5. Chạy Local

### 5.1 Setup Python

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu dùng `uv`:

```powershell
uv run python scripts/validate/validate_knowledge.py
```

### 5.2 Setup Frontend

```powershell
cd frontend
npm install
cd ..
```

### 5.3 Chạy Neo4j

```powershell
docker compose up -d neo4j
```

### 5.4 Import Knowledge Graph

```powershell
python scripts/graph/import_graph.py --clear
```

### 5.5 Chạy Backend và Frontend

Backend:

```powershell
python -m uvicorn backend.main:app --reload
```

Frontend:

```powershell
cd frontend
npm run dev
```

URL mặc định:

```text
Frontend:      http://localhost:5173
Backend API:   http://localhost:8000
API docs:      http://localhost:8000/docs
Health check:  http://localhost:8000/health
Neo4j Browser: http://localhost:7474
```

## 6. Chạy Bằng Docker Compose

```powershell
docker compose up -d --build
```

Kiểm tra:

```powershell
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f neo4j
```

Nếu graph rỗng:

```powershell
docker compose exec backend python -m scripts.graph.import_graph --clear
```

## 7. Data Pipeline

Khi cập nhật dataset gốc `data/raw/automotive_faults.json`:

```powershell
python scripts/build/translate_vi.py
python scripts/build/build_knowledge.py --rebuild-from-raw
python scripts/validate/validate_knowledge.py
python scripts/graph/import_graph.py --clear
```

Mục đích từng script:

- `translate_vi.py`: cập nhật nhãn tiếng Việt.
- `build_knowledge.py`: sinh toàn bộ artifact staging chính.
- `validate_knowledge.py`: kiểm tra tính nhất quán dữ liệu.
- `import_graph.py`: nạp vào Neo4j.
- `rebuild_hierarchy.py`: chỉ build lại `expert_tree.json`.

Lưu ý: script cũ đã được xóa trong quá trình dọn dẹp.

## 8. API Chính

Diagnosis:

```http
POST /diagnose
POST /api/diagnose
POST /api/answer
POST /session/new
POST /api/session/new
GET  /session/{session_id}
GET  /api/session/{session_id}
```

Graph:

```http
GET /api/graph
GET /api/graph/search?q=...
GET /api/graph/faults?q=...&limit=...
GET /api/graph/fault/{fault_id}
GET /api/graph/stats
```

Review (admin key):

```http
GET  /api/pending-rules
POST /api/rules/{rule_id}/approve
POST /api/rules/{rule_id}/reject
```

Health:

```http
GET /health
```

## 9. Quy Tắc Trả Kết Quả Chẩn Đoán

- Nếu `status = need_more_info`: UI chỉ hiển thị câu hỏi tiếp theo, chưa hiển thị bảng kết luận cuối.
- Nếu `status = diagnosed`: trả `results` và `resolution` để render kết quả hoàn chỉnh.
- Nếu `status = llm_fallback`: giữ `is_final = false`, trả gợi ý tham khảo, không coi là kết luận chắc chắn.
- Nếu không match tri thức: nhánh fallback thường trả `status = unknown_symptom` và `fallback_suggestions`.

Chi tiết policy hiện tại:

- `status != diagnosed`: `results` bị clear và `is_final = false`.
- `status = diagnosed` và không còn `next_question`: hệ thống cho phép trả kết luận final.
- Nếu `procedure_terminal` không hợp lệ với trạng thái chẩn đoán: ép về `need_more_info`.

Field quan trọng trong response:

- `session_id`
- `status`
- `next_question`
- `current_hypotheses`
- `results`
- `reasoning_trace`
- `mode`
- `step_context`
- `step_progress`
- `fault_preview`
- `resolution`
- `source`

## 10. Test và Đánh Giá

Backend/core:

```powershell
pytest
```

Hoặc:

```powershell
uv run pytest
```

Frontend:

```powershell
cd frontend
npm run test -- --reporter=verbose
npm run build
```

Evaluation:

```powershell
python scripts/evaluate/evaluate_diagnosis.py
```

## 11. Lỗi Thường Gặp

- Lỗi PowerShell policy: dùng `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.
- Không thấy `python`: dùng `py` hoặc kích hoạt đúng `.venv`.
- `/api/graph` trống: import lại `scripts/graph/import_graph.py --clear`.
- Frontend thiếu package: chạy lại `npm install` trong `frontend`.
- SQLite lỗi lock file: dừng backend cũ còn treo, xóa `data/app.sqlite3` nếu cần khởi tạo lại.

## 12. Tài Liệu Bổ Sung

- `docs/README.md`: index tài liệu và luồng đọc.
- `docs/Project_Brief.md`: bản handoff ngắn.
- `docs/Expert_System_Map.md`: bản đồ kỹ thuật chi tiết.
- `docs/plan.md`: kế hoạch cleanup và trạng thái thực thi.
