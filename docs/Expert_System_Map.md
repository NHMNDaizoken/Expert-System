# Car Diagnostic Expert System Map

Cập nhật: 2026-05-12

File này mô tả kiến trúc kỹ thuật chi tiết: dữ liệu ở đâu, engine suy luận thế nào, API trả gì, UI dùng gì, và các điểm cần chú ý khi mở rộng hệ thống.

## 1. Mô Hình Hệ Thống

Hệ thống gồm 4 lớp:

1. Data layer: raw dataset + staging artifacts + Neo4j graph.
2. Inference layer: matcher, engine, procedure runner, response policy.
3. Service/API layer: diagnosis/session/graph/review.
4. Presentation layer: diagnostic chat, graph viewer, expert review.

Sơ đồ luồng khái quát:

```text
User input
-> Symptom normalization + fuzzy matching
-> Hypothesis ranking (dynamic CF)
-> Question selection (information gain / procedure tree)
-> Session update (SQLite)
-> Response policy (final or ask-next)
-> Frontend rendering
```

## 2. Data Artifacts

Staging files dùng ở runtime:

```text
data/staging/kg_rules_from_dataset.json
data/staging/cf_dynamic.json
data/staging/procedure_trees.json
data/staging/symptom_aliases.json
data/staging/ontology.json
data/staging/expert_tree.json
data/staging/test_cases.json
```

Ý nghĩa:

- `kg_rules_from_dataset.json`: nguồn rule theo fault.
- `cf_dynamic.json`: ma trận CF động symptom -> fault.
- `procedure_trees.json`: cấu trúc câu hỏi nhị phân theo fault.
- `symptom_aliases.json`: từ điển chuẩn hóa symptom.
- `ontology.json`: phân cấp system/subsystem/component.
- `expert_tree.json`: cây phân cấp phục vụ UI/analysis.
- `test_cases.json`: bộ dữ liệu đánh giá.

## 3. Inference Layer

Core modules:

```text
src/expert_system/matcher.py
src/expert_system/engine.py
src/expert_system/procedure.py
src/expert_system/policy.py
src/expert_system/knowledge_base.py
src/expert_system/llm_fallback.py
src/llm_fallback.py
```

Ghi chú về fallback module:

- `src/llm_fallback.py` chỉ là re-export wrapper để giữ tương thích import.
- Logic fallback thực thi nằm trong `src/expert_system/llm_fallback.py`.

### 3.1 Symptom Matching

- Input text được normalize.
- Fuzzy matching dựa trên alias.
- Output gồm matched symptoms và confidence nội bộ.

### 3.2 Fault Ranking

Engine tạo candidate faults và tính score từ symptom xác nhận và symptom bị bác bỏ.

Mô hình tổng quát:

$$
score(f)=\prod_{s \in confirmed} CF(s,f) \times \prod_{r \in rejected}(1-CF(r,f))
$$

Sau đó chuẩn hóa để so sánh giữa các fault.

### 3.3 Question Selection

Hai chế độ:

- `procedure_tree`: đi theo cây bước fault top.
- `information_gain`: chọn symptom có entropy reduction cao nhất trong tập candidate.

### 3.4 Response Policy

`apply_response_policy` đảm bảo:

- `status = llm_fallback`: giữ `is_final = false`, chỉ trả dữ liệu tham khảo.
- Chưa đủ điều kiện final: status phải là `need_more_info`, chưa trả ranking kết luận.
- Đủ điều kiện: status `diagnosed`, trả `results` final và `resolution`.
- Nếu engine đã diagnosed nhưng không còn `next_question`: cho phép kết luận ngay.
- Nếu `procedure_terminal` không hợp lệ: ép flow quay về `need_more_info`.

## 4. Service/API Layer

Entry:

- `backend/main.py`.

Routes:

```text
backend/routes/health.py
backend/routes/diagnosis.py
backend/routes/graph.py
backend/routes/review.py
```

Services:

```text
backend/services/diagnosis_service.py
backend/services/session_service.py
backend/services/graph_service.py
backend/services/review_service.py
```

### 4.1 Diagnosis and Session Endpoints

```http
POST /diagnose
POST /api/diagnose
POST /api/answer
POST /session/new
POST /api/session/new
GET  /session/{session_id}
GET  /api/session/{session_id}
```

### 4.2 Graph Endpoints

```http
GET /api/graph
GET /api/graph/search
GET /api/graph/faults
GET /api/graph/fault/{fault_id}
GET /api/graph/stats
```

### 4.3 Review Endpoints

```http
GET  /api/pending-rules
POST /api/rules/{rule_id}/approve
POST /api/rules/{rule_id}/reject
```

Review API cần `X-Admin-API-Key` hợp lệ.

## 5. Session State Model

SQLite runtime: `data/app.sqlite3`.

Session giữ các trường quan trọng:

- `confirmed_symptoms`
- `rejected_symptoms`
- `current_hypotheses`
- `last_question`
- `current_step_id`
- `step_history`
- `branch_path`
- `last_answer`
- `active_fault_id`
- `total_steps_est`

Điểm chính:

- Session được tạo ngay sau lượt chẩn đoán đầu.
- Mỗi câu trả lời tiếp theo cập nhật trạng thái step.
- Dữ liệu được lưu JSON trong một số cột để giữ cấu trúc linh hoạt.

## 6. Fallback Strategy

Thứ tự xử lý:

1. Inference từ tri thức staging.
2. Nếu không có candidate hoặc unknown: fallback LLM.

Kết quả fallback:

- Không được xem là chẩn đoán chắc chắn.
- Trả `fallback_suggestions` để tham khảo.
- `status` thuộc nhóm chưa final (`unknown_symptom` hoặc `llm_fallback`).

## 7. Graph Layer

Graph data model chính:

```text
VehicleSystem
Subsystem
Component
Fault
Symptom
Repair
```

Relations:

```text
Subsystem -[:PART_OF]-> VehicleSystem
Component -[:PART_OF]-> Subsystem
Fault -[:AFFECTS]-> Component
Fault -[:HAS_SYMPTOM {cf, priority}]-> Symptom
Fault -[:FIXED_BY]-> Repair
Fault -[:RELATED_TO]-> Fault
```

Graph được dùng cho:

- Explainability.
- Search tri thức.
- Review rule.

Không dùng graph query trực tiếp làm engine chính cho mọi lượt chẩn đoán.

## 8. Frontend Layer

Màn hình chính:

```text
/diagnosis
/graph
/review
```

Tổ chức component đáng chú ý:

- `SymptomInput`: nhập triệu chứng ban đầu.
- `QuestioningScreen`: hỏi yes/no theo step.
- `DiagnosisResult`: kết quả cuối.
- `ReasoningTrace`: giải thích suy luận.
- `GraphCanvas`: dựng graph bằng ReactFlow.

State machine chẩn đoán:

```text
input -> questioning -> result
```

## 9. Data Pipeline Scripts

Chuỗi chuẩn:

```powershell
python scripts/translate_vi.py
python scripts/build_knowledge.py --rebuild-from-raw
python scripts/validate_knowledge.py
python scripts/import_graph.py --clear
```

Vai trò:

- `build_knowledge.py`: build artifact tập trung.
- `validate_knowledge.py`: fail-fast khi artifact sai định dạng/logic.
- `import_graph.py`: load vào Neo4j.
- `rebuild_hierarchy.py`: tái tạo hierarchy riêng.

## 10. Test and Verification

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

Gợi ý kiểm chứng tối thiểu sau mỗi thay đổi inference:

1. Chạy unit tests.
2. Chạy evaluation test cases.
3. Chạy manual 1-2 phiên chẩn đoán end-to-end.

## 11. Rủi Ro Kỹ Thuật Cần Theo Dõi

- Drift giữa schema staging và parser runtime.
- Hỏi đáp lặp nếu procedure tree data lỗi.
- Khác biệt ngôn ngữ giữa symptom alias và UI text.
- Sai lệch giữa trạng thái session ở frontend và backend khi retry network.
- Graph data stale nếu quên import lại sau khi rebuild knowledge.

## 12. Đề Xuất Mở Rộng

1. Thêm integration test cho toàn bộ flow session multi-turn.
2. Thêm guard cycle rõ ràng hơn trong procedure traversal.
3. Chuẩn hóa confidence messaging theo ngữ cảnh người dùng.
4. Mở rộng dataset và test cases theo hệ thống xe/phân khúc xe.
