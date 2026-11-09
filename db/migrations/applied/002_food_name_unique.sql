-- ════════════════════════════════════════════════════════════════════════
-- 002 — Tên món là duy nhất
--
-- `foods.name` hiện không có ràng buộc duy nhất, nên chạy lại trình nạp lần
-- thứ hai sẽ sinh ra bản sao của toàn bộ 60 món thay vì cập nhật chúng. Với
-- một tập dữ liệu còn đang xây và sẽ nạp lại nhiều lần, đó là cách chắc chắn
-- nhất để hỏng dữ liệu mà không ai nhận ra.
--
-- Có ràng buộc này thì trình nạp dùng được `INSERT ... ON DUPLICATE KEY
-- UPDATE`, tức nạp bao nhiêu lần cũng cho cùng một kết quả.
--
-- Chạy SAU 001:
--     mysql -u <user> -p <database> < db/migrations/002_food_name_unique.sql
-- ════════════════════════════════════════════════════════════════════════

-- Kiểm tra trùng trước khi thêm ràng buộc. Câu này phải trả về 0 dòng;
-- nếu không, phải xử lý trùng lặp trước rồi mới chạy ALTER bên dưới.
SELECT name, COUNT(*) AS so_ban_sao
FROM foods
GROUP BY name
HAVING COUNT(*) > 1;

ALTER TABLE foods
    ADD CONSTRAINT uq_food_name UNIQUE (name);
