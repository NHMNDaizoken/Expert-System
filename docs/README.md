# Expert System Documentation

Cập nhật: 2026-05-12

---

## Mục Lục
1. [Giới thiệu & Mục tiêu](#giới-thiệu--mục-tiêu)
2. [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
3. [Các thành phần & file chính](#các-thành-phần--file-chính)
4. [Luồng hoạt động](#luồng-hoạt-động)
5. [Lộ trình refactor & UX](#lộ-trình-refactor--ux)
6. [Hướng dẫn sử dụng nhanh](#hướng-dẫn-sử-dụng-nhanh)

---

## Giới thiệu & Mục tiêu

Hệ chuyên gia chẩn đoán lỗi ô tô dạng web app. Mục tiêu tài liệu:
- Mô tả đúng implementation hiện tại.
- Hỗ trợ chạy local, docker và debug nhanh.
- Chỉ rõ nơi chứa knowledge base, rule base, inference engine.
- Làm rõ ranh giới giữa graph visualization và core inference.

---

## Kiến trúc hệ thống

Hệ thống gồm 4 lớp:
1. Data layer: raw dataset + staging artifacts + Neo4j graph.
2. Inference layer: matcher, engine, procedure runner, response policy.
3. Service/API layer: diagnosis/session/graph/review.
4. Presentation layer: diagnostic chat, graph viewer, expert review.

Sơ đồ luồng khái quát:

User input → Symptom normalization + fuzzy matching → Hypothesis ranking (dynamic CF) → Question selection (information gain / procedure tree) → Session update (SQLite) → Response policy (final or ask-next) → Frontend rendering

### Data Artifacts (staging files dùng ở runtime):
- data/staging/kg_rules_from_dataset.json: nguồn rule theo fault
- data/staging/cf_dynamic.json: ma trận CF động symptom → fault
- data/staging/procedure_trees.json: cấu trúc cây hỏi nhị phân theo fault
- data/staging/symptom_aliases.json: từ điển chuẩn hóa symptom
- data/staging/ontology.json: phân cấp system/subsystem/component
- data/staging/expert_tree.json: cây phân cấp phục vụ UI/analysis
- data/staging/test_cases.json: bộ dữ liệu đánh giá

---

## Các thành phần & file chính

### Inference:
- src/expert_system/inference/engine.py: điều phối suy luận
- src/expert_system/inference/fuzzy.py: chuẩn hóa/match symptom
- src/expert_system/inference/procedure.py: hỏi đáp theo cây bước
- src/expert_system/inference/policy.py: chỉ cho phép finalization đúng điều kiện

### Backend:
- backend/routes/diagnosis.py: endpoints chẩn đoán + session
- backend/services/diagnosis_service.py: orchestration và fallback

### Fallback module:
- src/expert_system/llm_fallback.py: nơi chứa logic fallback thật

---

## Luồng hoạt động

1. Nhập triệu chứng tự do
2. Match triệu chứng với alias/rule
3. Xếp hạng fault bằng dynamic CF
4. Nếu chưa đủ chắc chắn thì hỏi tiếp theo từng bước
5. Đủ điều kiện mới trả kết luận cuối + hướng sửa chữa

---

## Lộ trình refactor & UX

### Final Goal
Hệ thống phải vận hành như một chuyên gia thực thụ:

User nhập triệu chứng → xác định hệ thống xe → hỏi phân biệt → thu hẹp fault → đề xuất quy trình kiểm tra → xác nhận fault → khuyến nghị sửa chữa/phụ tùng → thiếu tri thức thì gửi lên expert review.

### Vấn đề hiện tại
1. Diagnosis flow bỏ qua bước hỏi tiếp
2. Knowledge graph visualization bị vỡ
3. Expert review khó đọc
4. Reasoning trace quá kỹ thuật
5. Schema không nhất quán

### Định hướng kiến trúc đúng
- Tách biệt rõ frontend, backend, core inference, data
- Payload trả về phải human-readable, không lẫn debug
- Review chỉ hiển thị thông tin cần thiết

---

## Hướng dẫn sử dụng nhanh

### 1. Cài đặt & chạy
- Xem README.md ở thư mục gốc để setup môi trường, cài Python, Node.js, Docker nếu cần.
- Chạy backend: `uvicorn backend.main:app --reload`
- Chạy frontend: `cd frontend && npm install && npm run dev`

### 2. Kiểm thử
- Test backend: `pytest tests/`
- Test frontend: `npm run test`

### 3. Debug/Phát triển
- Sửa rule/data: cập nhật file trong data/staging, chạy lại script validate nếu cần.
- Sửa engine: thay đổi trong src/expert_system/*
- Sửa UI: frontend/src/components/*

---

## Liên hệ & đóng góp
- Đọc kỹ mục lục, commit message rõ ràng, tuân thủ cấu trúc repo.
- Mọi thắc mắc: mở issue hoặc liên hệ maintainer.
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
- Logic fallback thực tế ở `src/expert_system/llm_fallback.py`.

## 7. Build Tri Thức và Import Graph

Chuỗi chuẩn:

```powershell
python scripts/build/translate_vi.py
python scripts/build/build_knowledge.py --rebuild-from-raw
python scripts/validate/validate_knowledge.py
python scripts/graph/import_graph.py --clear
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
python scripts/evaluate/evaluate_diagnosis.py
```

Dev checks:

```powershell
python scripts/dev/dev_checks.py neo4j
python scripts/dev/dev_checks.py normalizer "ABS warning light on"
python scripts/dev/dev_checks.py rules SYM_ABS_WARNING_LIGHT_ON
python scripts/dev/dev_checks.py inference "dim headlights and clicking noise when starting"
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
