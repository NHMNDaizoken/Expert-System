# Docs Index

Cập nhật: 2026-05-12

Tài liệu này là điểm vào chính để đọc nhanh và điều hướng toàn bộ tài liệu trong dự án.

## 1. Nên Đọc Theo Thứ Tự Nào?

Nếu là người mới vào dự án:

1. `README.md`: setup và chạy dự án.
2. `docs/Project_Brief.md`: handoff nhanh, biết file nào cần chỉnh.
3. `docs/Expert_System_Map.md`: hiểu sâu kiến trúc suy luận và dữ liệu.
4. `docs/plan.md`: trạng thái cleanup và backlog.

## 2. Mục Tiêu Tài Liệu

- Mô tả đúng implementation hiện tại.
- Hỗ trợ chạy local, docker và debug nhanh.
- Chỉ rõ nơi chứa knowledge base, rule base, inference engine.
- Làm rõ ranh giới giữa graph visualization và core inference.

## 3. Chỉ Mục Theo Chủ Đề

### 3.1 Chạy Nhanh

Xem `README.md`.

### 3.2 Kiến Trúc Tổng Quan

Xem `docs/Project_Brief.md`.

### 3.3 Chi Tiết Kỹ Thuật

Xem `docs/Expert_System_Map.md`.

### 3.4 Kế Hoạch và Trạng Thái

Xem `docs/plan.md`.

## 4. Các File Kỹ Thuật Quan Trọng

```text
src/expert_system/engine.py
src/expert_system/matcher.py
src/expert_system/procedure.py
src/expert_system/policy.py
src/expert_system/llm_fallback.py
src/llm_fallback.py
backend/services/diagnosis_service.py
backend/services/session_service.py
backend/services/graph_service.py
```

Artifacts tri thức:

```text
data/staging/kg_rules_from_dataset.json
data/staging/cf_dynamic.json
data/staging/procedure_trees.json
data/staging/symptom_aliases.json
data/staging/ontology.json
```

## 5. API Surface Hiện Tại

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

Health:

```text
GET /health
```

## 6. Quy Ước Status Trong Luồng Chẩn Đoán

- `need_more_info`: còn phải hỏi thêm.
- `diagnosed`: đã đủ điều kiện kết luận.
- `unknown_symptom`: không match được tri thức hiện có.
- `no_fault_found`: match symptom nhưng không đủ tạo candidate đáng tin cậy.
- `llm_fallback`: dùng gợi ý LLM tham khảo, chưa phải chẩn đoán cuối.

Lưu ý:

- `results` chỉ nên dùng khi final.
- `current_hypotheses` dùng cho trạng thái trung gian.
- `next_question` điều khiển màn hình hỏi đáp.
- `src/llm_fallback.py` là wrapper; logic fallback thực tế ở `src/expert_system/llm_fallback.py`.

## 7. Build Tri Thức và Import Graph

Chuỗi chuẩn:

```powershell
python scripts/translate_vi.py
python scripts/build_knowledge.py --rebuild-from-raw
python scripts/validate_knowledge.py
python scripts/import_graph.py --clear
```

Mô tả ngắn:

- `build_knowledge.py`: script tổng hợp sinh artifact chính.
- `validate_knowledge.py`: phát hiện lỗi dữ liệu trước khi chạy app.
- `import_graph.py`: đồng bộ staging sang Neo4j.
- `rebuild_hierarchy.py`: tái tạo `expert_tree.json` khi cần.

## 8. Test Matrix

Backend/core:

```powershell
pytest
```

Frontend:

```powershell
cd frontend
npm run test -- --reporter=verbose
npm run build
```

Evaluation:

```powershell
python scripts/evaluate_diagnosis.py
```

Dev checks:

```powershell
python scripts/dev_checks.py neo4j
python scripts/dev_checks.py normalizer "ABS warning light on"
python scripts/dev_checks.py rules SYM_ABS_WARNING_LIGHT_ON
python scripts/dev_checks.py inference "dim headlights and clicking noise when starting"
```

## 9. Ghi Chú Vận Hành

- Session runtime nằm ở `data/app.sqlite3`.
- Nếu file SQLite lỗi trạng thái: dừng backend cũ, xóa file DB, khởi động lại.
- Neo4j chỉ bắt buộc cho visualization/query graph; inference vẫn có thể dùng staging JSON.
- Fallback LLM chỉ kích hoạt khi có cấu hình API key hợp lệ.

## 10. Khi Cập Nhật Tài Liệu

Checklist ngắn trước khi commit:

1. Đảm bảo endpoint trong docs khớp file route hiện tại.
2. Đảm bảo tên script khớp file thực tế trong `scripts/`.
3. Đảm bảo thuật ngữ status đồng bộ backend/frontend.
4. Cập nhật ngày ở đầu file.
