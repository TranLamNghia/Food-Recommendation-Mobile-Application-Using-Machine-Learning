-- ════════════════════════════════════════════════════════════════════════
-- 003 — Vá ba khóa UNIQUE không hề chặn trùng vì có cột NULL
--
-- MySQL coi **mọi NULL là khác nhau** trong chỉ mục UNIQUE. Hệ quả: một khóa
-- UNIQUE có cột cho phép NULL thì không chặn gì ở những dòng để trống cột đó.
--
-- Đo được trên CSDL thật, ba khóa bị ảnh hưởng — và ở hai khóa thì **100%
-- số dòng** đang để NULL, tức khóa chưa từng bảo vệ một dòng nào:
--
--     foods.uq_food_name      (owner_id, name)        owner_id NULL ở 305/305
--     rda_reference.uq_rda    (…, qualifier)          qualifier NULL ở 8/8
--     ml_evaluations.uq_eval  (…, k_value, fold)      bảng còn rỗng
--
-- Chứng minh bằng thực nghiệm (đã hoàn tác):
--
--     SELECT COUNT(*) FROM foods WHERE name='Cơm trắng';          -- 1
--     INSERT INTO foods (…, owner_id, name, …)
--     VALUES (…, NULL, 'Cơm trắng', …)
--     ON DUPLICATE KEY UPDATE spice_level = VALUES(spice_level);
--     SELECT COUNT(*) FROM foods WHERE name='Cơm trắng';          -- 2
--
-- `ON DUPLICATE KEY UPDATE` không thấy khóa nào trùng nên **chèn thêm dòng**
-- thay vì cập nhật. Đây không phải lỗi lý thuyết: chính nó làm
-- `tools/load_foods.py --apply` chết ngay ở món thứ nhất với
-- `(1242, 'Subquery returns more than 1 row')` — câu lệnh đầu nhân đôi món,
-- câu lệnh sau tra `SELECT id FROM foods WHERE name = …` thì được 2 dòng.
--
-- Bản schema cũ ĐÃ BIẾT lỗ hổng này và ghi chú rằng phần chặn trùng "do
-- trình nạp và trang quản trị kiểm". Chính trình nạp là thứ vỡ. Giao một
-- ràng buộc toàn vẹn cho tầng ứng dụng thì nó chỉ đúng tới khi có tầng ứng
-- dụng thứ hai — ở đây là trang quản trị sắp viết, nhập món bằng tay.
--
-- Cách vá: thêm **cột sinh (generated column) STORED** quy NULL về một giá
-- trị thật, rồi đặt UNIQUE lên cột đó. Khóa ngoại vẫn giữ trên `owner_id`
-- nên quy ước `owner_id IS NULL` = món của admin không thay đổi.
--
--     mysql -u <user> -p <database> < db/migrations/003_null_breaks_unique.sql
-- ════════════════════════════════════════════════════════════════════════


-- ── 1. foods — trùng tên trong danh mục chung ─────────────────────────
--
-- `owner_key` = 0 nghĩa là món của admin. Không dùng 0 trực tiếp cho
-- `owner_id` được vì `owner_id` có khóa ngoại sang `users(id)` và không có
-- người dùng id = 0; cột sinh tránh được chuyện đó.
--
-- VIRTUAL chứ không STORED, vì hai lẽ:
--
-- 1. Cột sinh STORED buộc MySQL **dựng lại cả bảng** (ALGORITHM=COPY). Trên
--    `foods` việc đó thất bại thẳng với lỗi
--        (1215, 'Cannot add foreign key constraint')
--    vì `foods` là bảng cha của sáu khóa ngoại (food_nutrition, food_tags,
--    meal_plan_items, food_ratings, …) và bản dựng lại không tạo lại được
--    chúng. Cột VIRTUAL thì thêm tức thì, không chạm vào dữ liệu.
-- 2. Không tốn chỗ lưu: giá trị tính lúc đọc. Chỉ mục UNIQUE trên cột sinh
--    VIRTUAL **vẫn chặn trùng thật** — MySQL 8.0 cho phép, và mục kiểm ở
--    cuối tệp này chứng minh nó chặn.
--
-- Thứ tự từ khóa của cột sinh là  <kiểu> AS (<biểu thức>) VIRTUAL NOT NULL  —
-- đặt NOT NULL trước AS sẽ lỗi cú pháp 1064.
--
-- Lưu ý khi chạy bằng script Python tự tách câu lệnh: chuỗi COMMENT dưới đây
-- có chứa dấu ';', nên phép tách phải tôn trọng dấu nháy. Tách thô theo ';'
-- sẽ cắt giữa chuỗi và báo lỗi 1064 ở một chỗ trông vô lý.

ALTER TABLE foods
    ADD COLUMN owner_key BIGINT UNSIGNED
        GENERATED ALWAYS AS (COALESCE(owner_id, 0)) VIRTUAL NOT NULL
        COMMENT '0 = món do admin quản lý; khác 0 = id chủ sở hữu. Chỉ để khóa UNIQUE hoạt động khi owner_id NULL';

ALTER TABLE foods
    DROP INDEX uq_food_name,
    ADD UNIQUE KEY uq_food_name (owner_key, name);


-- ── 2. rda_reference — trùng dòng nhu cầu dinh dưỡng ──────────────────
--
-- `qualifier` để trống ở chất không có nhiều mức hấp thu (phần lớn các
-- chất), nên khóa cũ không chặn gì ở đúng những dòng đó. Chuỗi rỗng là giá
-- trị quy về tự nhiên vì cột đã là VARCHAR.

ALTER TABLE rda_reference
    ADD COLUMN qualifier_key VARCHAR(30)
        GENERATED ALWAYS AS (COALESCE(qualifier, '')) VIRTUAL NOT NULL
        COMMENT 'Chuỗi rỗng = chất không phân mức hấp thu. Chỉ để khóa UNIQUE hoạt động khi qualifier NULL';

ALTER TABLE rda_reference
    DROP INDEX uq_rda,
    ADD UNIQUE KEY uq_rda (gender, age_min, age_max, nutrient, qualifier_key);


-- ── 3. ml_evaluations — trùng dòng kết quả đánh giá ───────────────────
--
-- Hai cột này là số nguyên nhỏ và bảng còn rỗng, nên không cần cột sinh:
-- đổi thẳng sang NOT NULL DEFAULT 0 và quy ước 0 là "không áp dụng".
--
--     k_value = 0  → độ đo không có @k (MAE, RMSE, AUC)
--     fold    = 0  → kết quả trên tập kiểm thử cuối, không phải một fold
--
-- Quan trọng với bảng này hơn hai bảng trên: một dòng đánh giá bị chèn hai
-- lần sẽ làm mọi phép tính trung bình giữa các variant lệch âm thầm, mà số
-- liệu đánh giá là thứ đi thẳng vào báo cáo.

ALTER TABLE ml_evaluations
    MODIFY k_value TINYINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '0 = độ đo không có @k',
    MODIFY fold    TINYINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '0 = kết quả trên tập kiểm thử cuối, không phải một fold';


-- ── Kiểm lại sau khi chạy ─────────────────────────────────────────────
--
-- Truy vấn này liệt kê MỌI khóa UNIQUE còn chứa cột cho phép NULL, trong cả
-- CSDL. Sau migration nó phải trả về **0 dòng**. Giữ lại ở đây để chạy lại
-- mỗi khi thêm bảng mới — lỗi này rất dễ lặp vì nhìn vào DDL thì khóa trông
-- hoàn toàn bình thường.

SELECT s.TABLE_NAME                       AS bang,
       s.INDEX_NAME                       AS khoa,
       GROUP_CONCAT(s.COLUMN_NAME
                    ORDER BY s.SEQ_IN_INDEX) AS cac_cot,
       GROUP_CONCAT(CASE WHEN s.NULLABLE = 'YES' THEN s.COLUMN_NAME END
                    ORDER BY s.SEQ_IN_INDEX) AS cot_null_duoc
FROM information_schema.STATISTICS s
WHERE s.TABLE_SCHEMA = DATABASE()
  AND s.NON_UNIQUE = 0
GROUP BY s.TABLE_NAME, s.INDEX_NAME
HAVING cot_null_duoc IS NOT NULL
ORDER BY s.TABLE_NAME;

-- Và ba phép thử phải đều báo lỗi 1062 / 1048 (đã chạy, kết quả thực tế):
--
--   foods           → 1062 Duplicate entry '0-Cơm trắng' for key 'uq_food_name'
--   rda_reference   → 1062 Duplicate entry 'male-19-30-protein_g-' for key 'uq_rda'
--   ml_evaluations  → 1048 Column 'k_value' cannot be null
