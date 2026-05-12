# Expert System Cleanup Plan

Cập nhật: 2026-05-12

Mục tiêu của tài liệu này là theo dõi tiến độ cleanup và chuẩn hóa hệ chuyên gia theo hướng sẵn sàng demo/bảo vệ, đồng thời chỉ ra phần còn tồn đọng cần làm.

## 1. Goal Checklist

- [x] User questions symptom-based, dễ hiểu với người dùng phổ thông.
- [x] Technician diagnosis/repair steps chỉ hiển thị sau khi có kết quả.
- [x] Tài liệu kiến trúc hệ chuyên gia đã được cập nhật chi tiết.
- [x] Luồng chẩn đoán nhiều bước có session state rõ ràng.
- [x] Build pipeline tri thức đã gom về script tập trung.
- [ ] Chuẩn hóa hoàn toàn ngôn ngữ hiển thị (tránh trộn Anh-Việt ở một số label dữ liệu thô).
- [ ] Bổ sung thêm test integration cho graph APIs và multi-turn session edge cases.

## 2. Phase Status

### Phase 1 Audit Current Flow

- [x] Xác định nơi tạo procedure trees.
- [x] Xác định nơi sinh/cấu hình câu hỏi người dùng.
- [x] Xác định nơi lưu technician steps.
- [x] Xác định logic graph labels và fallback.
- [x] Xác định các điểm có khả năng rò rỉ label tiếng Anh.

Kết quả: hoàn thành, đã map rõ trách nhiệm file.

### Phase 2 Fix User Questions

- [x] Câu hỏi tập trung vào symptom xác nhận.
- [x] Câu hỏi map với symptom id/step id.
- [x] Tránh yêu cầu người dùng thao tác kỹ thuật chuyên sâu trong flow hỏi đáp.
- [x] Có fallback question để tránh dead-end flow.

Kết quả: cơ bản hoàn thành, cần tiếp tục rà wording tự nhiên theo từng nhóm symptom.

### Phase 3 Separate Technician Procedures

- [x] Tách phần hỏi đáp và phần hướng dẫn sửa chữa.
- [x] Chỉ hiển thị resolution khi status final.
- [x] Giữ procedure/resolution trong rule để render hậu chẩn đoán.

Kết quả: hoàn thành theo kiến trúc hiện tại.

### Phase 4 Fix Vietnamese Labels

- [x] Có pipeline dịch và map nhãn Việt trong data build.
- [x] Có trường label_vi ở graph import.
- [ ] Một số thuật ngữ kỹ thuật vẫn có thể giữ tiếng Anh từ raw dataset.
- [ ] Cần rà thủ công UI copywriting để đồng nhất hoàn toàn.

Kết quả: hoàn thành phần nền tảng, còn nợ polishing dữ liệu và UI text.

### Phase 5 Graph Relations

- [x] Quan hệ graph đã được chuẩn hóa ở backend graph service.
- [x] Có metadata tách riêng thay vì nhồi toàn bộ vào edge label.
- [ ] Cần thêm snapshot test cho hiển thị edge labels phía frontend.

Kết quả: hoạt động ổn, thiếu test tự động chuyên biệt.

### Phase 6 Prevent Loops

- [x] Session có lịch sử step để theo dõi traversal.
- [x] Có cơ chế fallback question khi flow thiếu thông tin.
- [ ] Cần hard guard rõ ràng hơn cho vòng lặp bất thường từ dữ liệu sai.
- [ ] Cần test riêng cho cycle/missing transition của procedure tree.

Kết quả: đã giảm rủi ro, chưa khóa hoàn toàn mọi edge case dữ liệu xấu.

### Phase 7 UI Polish

- [x] Luồng `input -> questioning -> result` đã ổn định.
- [x] Có progress/context/fault preview ở màn hình hỏi đáp.
- [ ] Cần thêm vòng polish spacing/typography thống nhất toàn app.
- [ ] Cần review giao diện trên nhiều kích thước màn hình.

Kết quả: đủ dùng cho demo kỹ thuật, còn dư địa polish presentation.

### Phase 8 Defense Documentation

- [x] Đã tài liệu hóa knowledge base/rule base/inference engine.
- [x] Đã làm rõ graph là lớp explainability, không phải engine chính.
- [x] Đã mô tả fallback và session model.

Kết quả: hoàn thành.

## 3. Remaining Work (Ưu Tiên)

1. Thêm integration test cho các API `graph/*` và flow session nhiều bước.
2. Thêm guard cycle cứng và test dữ liệu lỗi cho procedure traversal.
3. Chốt bộ guideline tiếng Việt để tránh trộn ngôn ngữ ở UI/labels.
4. Mở rộng test cases trong `data/staging/test_cases.json` khi thêm rule mới.

## 4. Validation Checklist

- [x] Chạy unit tests backend/core.
- [x] Chạy frontend test/build.
- [x] Chạy evaluation script.
- [ ] Chạy kịch bản manual đầy đủ cho ít nhất 5 flow chẩn đoán nhiều bước sau mỗi thay đổi lớn inference.
- [ ] Lưu snapshot kết quả graph rendering để so sánh regression.

## 5. Definition of Done Cho Đợt Cleanup Này

- [x] Engine, session, policy và data pipeline đã ổn định.
- [x] Tài liệu kỹ thuật đã cập nhật theo implementation.
- [ ] Bổ sung đầy đủ integration tests còn thiếu.
- [ ] Hoàn thành polishing ngôn ngữ hiển thị và UI consistency.

## 6. Rủi Ro Còn Lại

- Rủi ro lệch schema nếu data staging đổi nhưng parser không cập nhật đồng bộ.
- Rủi ro loop hoặc dead-end khi procedure tree có dữ liệu bất thường.
- Rủi ro khác biệt wording giữa source data và UI text.

## 7. Notes

- Các script legacy vẫn giữ trong `scripts/legacy/` để tham chiếu, không dùng cho flow chính.
- Tài liệu chính để trình bày: `README.md`, `docs/Project_Brief.md`, `docs/Expert_System_Map.md`.
