# Docs Index

Cập nhật: 2026-05-11

Tài liệu này là điểm bắt đầu khi cần hiểu, chạy và test hệ chuyên gia chẩn đoán lỗi ô tô.

## 1. Hệ Chuyên Gia Gồm Những Gì?

Project là web app hệ chuyên gia chẩn đoán lỗi ô tô. Người dùng nhập triệu chứng, hệ thống chuẩn hóa input, match triệu chứng, suy luận lỗi, hỏi thêm nếu chưa đủ chắc chắn, rồi trả kết quả cuối kèm hướng kiểm tra/sửa chữa.

Luồng chính (sau refactoring):

```text
Triệu chứng người dùng
-> ExpertSystemEngine.diagnose() -> SymptomMatcher chuẩn hóa và fuzzy-match alias
-> Suy luận lỗi từ rule/Knowledge Graph
-> Dynamic Certainty Factor xếp hạng lỗi
-> QuestionSelector chọn câu hỏi yes/no nếu còn mơ hồ
-> ResponsePolicy filter results dựa vào status và procedure_terminal
-> Backend lưu session hỏi đáp
-> Frontend hiển thị kết quả cuối và reasoning trace
```

File quan trọng:

```text
data/staging/kg_rules_from_dataset.json   Luật chẩn đoán chính
data/staging/cf_dynamic.json              Dynamic CF theo symptom/fault
data/staging/procedure_trees.json         Cây câu hỏi yes/no theo fault
data/staging/symptom_aliases.json         Alias để match triệu chứng
data/staging/ontology.json                Ontology system/subsystem/component
src/expert_system/engine.py               ExpertSystemEngine - bộ suy luận chính và information gain
src/expert_system/matcher.py              SymptomMatcher - match triệu chứng
src/expert_system/procedure.py            ProcedureRunner - đi theo cây câu hỏi yes/no
src/expert_system/policy.py               apply_response_policy - filter results
backend/services/diagnosis_service.py     Orchestrator API chẩn đoán
backend/services/session_service.py       Lưu session hỏi đáp SQLite
backend/services/graph_service.py         Đọc Neo4j hoặc fallback JSON
frontend/src/pages/DiagnosticChat.jsx     Luồng UI input -> question -> result
frontend/src/pages/GraphViewer.jsx        Xem Knowledge Graph
```

**Legacy modules** (lưu tại `src/legacy/` cho backward compatibility):
- `src/legacy/kg_inference.py` - cầu nối cũ
- `src/legacy/next_question.py` - chọn câu hỏi cũ
- `src/legacy/cf.py` - tính CF cũ
- `src/legacy/kg_validator.py` - validate knowledge graph

Đọc thêm:

```text
docs/Project_Brief.md       Bản tóm tắt nhanh để handoff/demo
docs/Expert_System_Map.md   Bản đồ chi tiết hệ chuyên gia, data, API, UI
```

## 2. Cài Đặt Lần Đầu

Yêu cầu:

```text
Python 3.11+
Node.js 20+
Docker Desktop
```

Tạo file môi trường:

```powershell
Copy-Item .env.example .env
```

Tạo môi trường Python:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu máy chưa có `python` global nhưng có `uv`, có thể chạy các script Python bằng `uv run python ...`.

Cài frontend:

```powershell
cd frontend
npm install
cd ..
```

## 3. Chạy Local

Chạy Neo4j:

```powershell
docker compose up -d neo4j
```

Nếu muốn rebuild staging rules từ dataset raw:

```powershell
python scripts/translate_vi.py
python scripts/build_knowledge.py --rebuild-from-raw
python scripts/validate_knowledge.py
```

Nếu chỉ muốn cập nhật `data/staging/expert_tree.json` từ staging hiện có:

```powershell
python scripts/rebuild_hierarchy.py
```

Nếu chỉ muốn import staging rules vào Neo4j:

```powershell
python scripts/import_graph.py --clear
```

`scripts/import_neo4j.py` vẫn là wrapper tương thích nếu tài liệu cũ hoặc IDE còn gọi tên này.

Chạy backend:

```powershell
python -m uvicorn backend.main:app --reload
```

Mở terminal khác, chạy frontend:

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

Đăng nhập Neo4j Browser:

```text
Username: neo4j
Password: password123
```

## 4. Chạy Bằng Docker Compose

Chạy toàn bộ backend, frontend, Neo4j:

```powershell
docker compose up -d --build
```

Kiểm tra container:

```powershell
docker compose ps
```

Xem log:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f neo4j
```

Nếu Neo4j trong container chưa có dữ liệu:

```powershell
docker compose exec backend python -m scripts.import_graph --clear
```

Dừng hệ thống:

```powershell
docker compose down
```

Xóa luôn volume Neo4j để import lại từ đầu:

```powershell
docker compose down -v
```

## 5. Test Và Kiểm Tra

Chạy unit test backend/core:

```powershell
pytest
```

Nếu dùng `uv`:

```powershell
uv run pytest
```

Chạy dev check nhanh:

```powershell
python scripts/dev_checks.py neo4j
python scripts/dev_checks.py normalizer "ABS warning light on"
python scripts/dev_checks.py rules SYM_ABS_WARNING_LIGHT_ON
python scripts/dev_checks.py inference "dim headlights and clicking noise when starting"
```

Chạy frontend test và build:

```powershell
cd frontend
npm run test -- --reporter=verbose
npm run build
cd ..
```

Chạy evaluation bộ test case chẩn đoán:

```powershell
python scripts/evaluate_diagnosis.py
```

Test thủ công API:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/diagnose `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"text":"clicking noise when starting and dim headlights","top_k":5}'
```

## 6. Build Lại Data/Rule

Khi sửa `data/raw/automotive_faults.json`, build lại staging data bằng consolidated script:

```powershell
python scripts/translate_vi.py
python scripts/build_knowledge.py --rebuild-from-raw
python scripts/validate_knowledge.py
python scripts/import_graph.py --clear
```

**Trước refactoring** (cách cũ - lưu ở `scripts/legacy/` nếu cần):

```powershell
# Không nên dùng nữa - đã gộp vào build_knowledge.py
# python scripts/legacy/compute_cf.py
# python scripts/legacy/build_procedure.py
# python scripts/legacy/rebuild_kg.py
```

## 7. File Thừa Có Thể Xóa

Các file/thư mục sau là dependency, cache, build output hoặc runtime state. Có thể xóa an toàn; khi chạy lại, project sẽ tự tạo hoặc cài lại:

```text
.pytest_cache/
.uv-cache/
.venv/
.venv-win/
**/__pycache__/
**/*.pyc
frontend/node_modules/
frontend/dist/
data/app.sqlite3
```

Sau khi xóa:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend
npm install
```

Không xóa các thư mục/file này vì đây là mã nguồn hoặc dữ liệu chính:

```text
backend/
frontend/src/
src/
scripts/
tests/
data/raw/
data/staging/
docs/Project_Brief.md
docs/Expert_System_Map.md
```
