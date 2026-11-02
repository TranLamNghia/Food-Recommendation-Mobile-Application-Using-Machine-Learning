-- ════════════════════════════════════════════════════════════════════════
-- 001 — Chỉnh lược đồ để nạp được tập dữ liệu món ăn
--
-- Ba thay đổi, đều phát hiện khi đối chiếu CSV với schema bằng
-- `tools/check_db_ready.py`. Chạy MỘT LẦN trước khi nạp dữ liệu:
--
--     mysql -u <user> -p <database> < db/migrations/001_dataset_readiness.sql
-- ════════════════════════════════════════════════════════════════════════


-- ── 1. Mở rộng vai trò món ────────────────────────────────────────────
--
-- Enum cũ gộp *món mặn* và *món rau* chung vào `side`. Bộ sinh thực đơn cần
-- tách hai thứ này: mâm cơm Việt thiếu món mặn thì không còn là bữa ăn, mà
-- với enum cũ thì bữa tối hoàn toàn có thể ra hai món rau và không có đạm
-- nào. Thêm `snack` vì món phụ (gỏi cuốn, bánh mì) không phải `side` cũng
-- không phải `dessert`.

ALTER TABLE foods
    MODIFY dish_role ENUM(
        'main',          -- món chính: cơm, phở, bún
        'side_protein',  -- món mặn: thịt, cá, trứng, đậu phụ
        'side_veg',      -- món rau: luộc, xào, nộm
        'soup',          -- món canh
        'snack',         -- món phụ, ăn vặt
        'dessert',       -- tráng miệng
        'drink'          -- đồ uống
    ) NOT NULL DEFAULT 'main';


-- ── 2. Cho phép "chưa biết" khác "bằng 0" ─────────────────────────────
--
-- Bốn cột này đang là NOT NULL DEFAULT 0, nghĩa là món chưa có số liệu sẽ
-- được ghi thành 0. Với chất xơ và đường thì chỉ sai lệch thống kê, nhưng
-- với NATRI thì đây là lỗi an toàn theo đúng hướng nguy hiểm:
--
--     Món chưa biết natri  →  ghi 0 mg  →  bộ lọc F1 thấy "ít natri nhất"
--     →  gợi ý cho người tăng huyết áp
--
-- Tức là món thiếu dữ liệu lại được ưu tiên hơn món có dữ liệu. Để NULL thì
-- truy vấn `sodium_mg > 600` bỏ qua món đó, và có thể đếm được còn bao nhiêu
-- món chưa đủ dữ liệu.

ALTER TABLE food_nutrition
    MODIFY fiber_g        DECIMAL(6,2) NULL,
    MODIFY sugar_g        DECIMAL(6,2) NULL,
    MODIFY sodium_mg      DECIMAL(7,2) NULL,
    MODIFY cholesterol_mg DECIMAL(7,2) NULL;


-- ── 3. Chỗ chứa đường dẫn nguồn ───────────────────────────────────────
--
-- `data_source` VARCHAR(150) chỉ đủ cho tên nguồn. Đường dẫn tới đúng trang
-- chứa số liệu dài hơn thế, mà đó lại là thứ hội đồng cần khi hỏi "con số
-- này ở đâu ra" — tên nguồn không kiểm chứng được, đường dẫn thì có.

ALTER TABLE food_nutrition
    ADD COLUMN source_url VARCHAR(500) NULL AFTER data_source;


-- ── 4. Nhãn giàu purin ────────────────────────────────────────────────
--
-- Quy tắc ràng buộc cho người bệnh gút dựa trên `purine_mg`, nhưng cột này
-- chỉ có số liệu ở 16 % mục của Bảng thành phần thực phẩm Việt Nam 2007, và
-- USDA FoodData Central KHÔNG công bố purin. Không nguồn uy tín nào lấp được.
--
-- Để nguyên thì quy tắc gút lặng lẽ không bao giờ kích hoạt. Thay bằng cơ
-- chế nhãn — kém chính xác hơn ngưỡng định lượng, nhưng chạy được và phủ
-- đúng nhóm thực phẩm mà y văn cảnh báo.
--
-- Ghi vào phần hạn chế của báo cáo: ràng buộc gút ở mức phân loại nhóm
-- thực phẩm, chưa ở mức định lượng.

INSERT INTO tags (code, name_vi, tag_type, description) VALUES
    ('high_purine', 'Giàu purin', 'nutrition',
     'Nội tạng, hải sản vỏ cứng, cá nhỏ nguyên con, nước dùng ninh xương lâu')
ON DUPLICATE KEY UPDATE description = VALUES(description);
