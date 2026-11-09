# Migration đã hợp nhất

Các tệp trong thư mục này **đã được gộp thẳng vào `db/schema.sql`**. Giữ lại
làm lịch sử thay đổi, không chạy nữa — chạy lại sẽ báo lỗi vì cấu trúc đích
đã có sẵn.

| Tệp | Nội dung đã gộp |
|---|---|
| `001_dataset_readiness.sql` | `dish_role` 5→7 giá trị · 4 cột dinh dưỡng cho NULL · thêm `source_url` · nhãn `high_purine` |
| `002_food_name_unique.sql` | `UNIQUE (foods.name)` |
| `003_null_breaks_unique.sql` | Ba khóa `UNIQUE` không chặn trùng vì có cột `NULL` — thêm cột sinh `foods.owner_key`, `rda_reference.qualifier_key`; `ml_evaluations.k_value`/`fold` thành `NOT NULL DEFAULT 0` |
| `004_evidence_level.sql` | `condition_rules.evidence_level` 4 giá trị + `chk_rule_evidence` |
| `005_password_resets.sql` | Bảng `password_resets` cho luồng Quên mật khẩu — lược đồ 22 → 23 bảng |
| `006_refresh_tokens.sql` | Bảng `refresh_tokens` cho xoay vòng token và phát hiện tái dùng — lược đồ 23 → 24 bảng |

Nguyên tắc từ nay: **`db/schema.sql` luôn là trạng thái hiện hành**. Dựng CSDL
mới thì chạy `schema.sql` rồi `seed.sql`, không cần đụng tới thư mục này.

## Kiểm lại `schema.sql` mà không xóa CSDL đang dùng

`db/schema.sql` mở đầu bằng `DROP DATABASE IF EXISTS nutrition_rec`, nên
**không chạy nó để thử**. Dùng:

    python tools/test_schema_build.py

Công cụ đó đổi tên CSDL sang một tên dùng một lần, dựng lại toàn bộ lược đồ và
seed vào đó, đối chiếu quy mô, rồi xóa. Nó cũng kiểm lại rằng kết nối thật sự
đang ở CSDL nháp trước khi đo — vì nếu phép đổi tên không ăn thì mọi con số
vẫn đúng, chỉ là đang đo CSDL thật, và bài kiểm trở thành vô nghĩa mà trông
như đã đạt.
