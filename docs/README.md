# Docs Index

Cập nhật: 2026-05-11

Tài liệu này là điểm bắt đầu khi cần hiểu, chạy và test hệ chuyên gia chẩn đoán lỗi ô tô.

## 1. Hệ Chuyên Gia Gồm Những Gì?

Project là web app hệ chuyên gia chẩn đoán lỗi ô tô. Người dùng nhập triệu chứng, hệ thống chuẩn hóa input, match triệu chứng, suy luận lỗi, hỏi thêm nếu chưa đủ chắc chắn, rồi trả kết quả cuối kèm hướng kiểm tra/sửa chữa.

Luồng chính:

```text
Triệu chứng người dùng
-> SymptomMatcher chuẩn hóa và fuzzy-match alias
-> KGInference tạo giả thuyết lỗi từ rule/Knowledge Graph
-> Dynamic Certainty Factor xếp hạng lỗi
-> NextQuestion chọn câu hỏi yes/no nếu còn mơ hồ
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
src/kg_inference.py                       Bộ suy luận chính
src/next_question.py                      Chọn câu hỏi tiếp theo
backend/services/diagnosis_service.py     Orchestrator API chẩn đoán
backend/services/session_service.py       Lưu session hỏi đáp SQLite
backend/services/graph_service.py         Đọc Neo4j hoặc fallback JSON
frontend/src/pages/DiagnosticChat.jsx     Luồng UI input -> question -> result
frontend/src/pages/GraphViewer.jsx        Xem Knowledge Graph
```

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

Import lại Knowledge Graph nếu Neo4j mới/rỗng:

```powershell
python scripts/data_tools.py validate data/staging/kg_rules_from_dataset.json
python scripts/data_tools.py rebuild data/staging/kg_rules_from_dataset.json --clear
```

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
docker compose exec backend python scripts/data_tools.py rebuild data/staging/kg_rules_from_dataset.json --clear
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

Khi sửa `data/raw/automotive_faults.json`, build lại staging data:

```powershell
python scripts/compute_cf.py
python scripts/build_procedure.py
python scripts/rebuild_kg.py
python scripts/data_tools.py validate data/staging/kg_rules_from_dataset.json
python scripts/data_tools.py rebuild data/staging/kg_rules_from_dataset.json --clear
```

Các lệnh xem dữ liệu:

```powershell
python scripts/data_tools.py inspect
python scripts/data_tools.py categories
python scripts/data_tools.py generate-related
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
