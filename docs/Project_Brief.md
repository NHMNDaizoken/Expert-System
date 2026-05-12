# Project Brief

Cập nhật: 2026-05-12

Mục tiêu của file này là handoff nhanh: đọc 10-15 phút là biết hệ thống làm gì, chạy ra sao, và cần sửa file nào cho từng loại yêu cầu.

## 1. Project Là Gì?

Đây là hệ chuyên gia chẩn đoán lỗi ô tô dạng web app.

Luồng cốt lõi:

1. Nhập triệu chứng tự do.
2. Match triệu chứng với alias/rule.
3. Xếp hạng fault bằng dynamic CF.
4. Nếu chưa đủ chắc chắn thì hỏi tiếp theo từng bước.
5. Đủ điều kiện mới trả kết luận cuối + hướng sửa chữa.

## 2. Tech Stack

```text
Backend:  FastAPI
Frontend: React + Vite
Graph:    Neo4j (phục vụ visualization/query)
Storage:  SQLite cho session
Core:     Python rule-based inference
Fallback: LLM fallback khi symptom chưa map trong tri thức
```

Fallback module layout:

- `src/llm_fallback.py`: lớp tương thích để import path cũ không bị vỡ.
- `src/expert_system/llm_fallback.py`: nơi chứa logic fallback thật.

## 3. Cấu Trúc Chính

```text
backend/       Routes, services, schemas, database
frontend/      UI diagnosis/graph/review
src/           Engine, matcher, procedure, policy
scripts/       Build/validate/import/evaluate
data/raw/      Dữ liệu nguồn
data/staging/  Tri thức đã chuẩn hóa để runtime dùng
tests/         Test backend + engine
docs/          Tài liệu
```

## 4. Các File Cần Nhớ

Inference:

- `src/expert_system/engine.py`: điều phối suy luận.
- `src/expert_system/matcher.py`: chuẩn hóa/match symptom.
- `src/expert_system/procedure.py`: hỏi đáp theo cây bước.
- `src/expert_system/policy.py`: chỉ cho phép finalization đúng điều kiện.

Backend:

- `backend/routes/diagnosis.py`: endpoints chẩn đoán + session.
- `backend/services/diagnosis_service.py`: orchestration và fallback.
- `backend/services/session_service.py`: lưu trạng thái phiên theo bước.
- `backend/services/graph_service.py`: dữ liệu graph và fallback.

Data/scripts:

- `data/staging/kg_rules_from_dataset.json`
- `data/staging/cf_dynamic.json`
- `data/staging/procedure_trees.json`
- `data/staging/symptom_aliases.json`
- `data/staging/ontology.json`
- `scripts/build_knowledge.py`
- `scripts/validate_knowledge.py`
- `scripts/import_graph.py`

UI:

- `frontend/src/pages/DiagnosticChat.jsx`
- `frontend/src/components/SymptomInput.jsx`
- `frontend/src/components/QuestioningScreen.jsx`
- `frontend/src/components/DiagnosisResult.jsx`
- `frontend/src/pages/GraphViewer.jsx`

## 5. API Quan Trọng

Diagnosis/session:

```text
POST /diagnose
POST /api/diagnose
POST /api/answer
POST /session/new
POST /api/session/new
GET  /session/{session_id}
GET  /api/session/{session_id}
```

Graph:

```text
GET /api/graph
GET /api/graph/search
GET /api/graph/faults
GET /api/graph/fault/{fault_id}
GET /api/graph/stats
```

Review:

```text
GET  /api/pending-rules
POST /api/rules/{rule_id}/approve
POST /api/rules/{rule_id}/reject
```

## 6. Trạng Thái Chẩn Đoán

- `need_more_info`: còn phải hỏi thêm.
- `diagnosed`: đủ điều kiện kết luận.
- `unknown_symptom`: không match symptom hiện có.
- `no_fault_found`: match được symptom nhưng không tạo được candidate đủ tốt.
- `llm_fallback`: đang trả gợi ý tham khảo từ LLM, chưa phải final diagnosis.

Trường response cần chú ý:

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

## 7. Ranh Giới Kiến Trúc Khi Thuyết Trình

```text
Knowledge base   -> data/staging/*.json
Rule base        -> data/staging/kg_rules_from_dataset.json
Inference engine -> src/expert_system/engine.py
Question flow    -> procedure tree + information gain
Session state    -> backend/services/session_service.py (SQLite)
Graph layer      -> Neo4j + backend/services/graph_service.py
UI layer         -> frontend/src/pages + components
```

Điểm quan trọng:

- Neo4j hữu ích cho visualize và query graph.
- Inference cốt lõi vẫn dựa vào tri thức đã staging.
- Graph không thay thế inference engine.

## 8. Chạy Nhanh

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
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

## 9. Build Lại Tri Thức

```powershell
python scripts/translate_vi.py
python scripts/build_knowledge.py --rebuild-from-raw
python scripts/validate_knowledge.py
python scripts/import_graph.py --clear
```

## 10. Khi Cần Sửa Theo Từng Loại Yêu Cầu

Sửa rule/tri thức:

- `data/staging/kg_rules_from_dataset.json`
- `data/staging/symptom_aliases.json`
- `data/staging/ontology.json`

Sửa logic suy luận:

- `src/expert_system/engine.py`
- `src/expert_system/procedure.py`
- `src/expert_system/policy.py`

Sửa session/API:

- `backend/routes/diagnosis.py`
- `backend/services/diagnosis_service.py`
- `backend/services/session_service.py`

Sửa UI:

- `frontend/src/pages/DiagnosticChat.jsx`
- `frontend/src/components/QuestioningScreen.jsx`
- `frontend/src/components/DiagnosisResult.jsx`

Sửa graph:

- `backend/services/graph_service.py`
- `frontend/src/pages/GraphViewer.jsx`
- `frontend/src/components/GraphCanvas.jsx`

## 11. Chỗ Cần Cẩn Trọng

- Không trả `results` final khi chưa đủ điều kiện chẩn đoán.
- Nhánh `llm_fallback` luôn phải giữ `is_final = false`.
- Khi tiếp tục session, giữ đúng `confirmed/rejected_symptoms` và lịch sử step.
- Tránh sửa logic làm mất backward compatibility của endpoint `/api/diagnose` và `/diagnose`.
- Nếu đổi schema staging, phải cập nhật cả build, validate, import và tests.
