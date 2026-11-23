-- ════════════════════════════════════════════════════════════════════════
-- 009 — `user_food_marks`: dấu người dùng đặt lên một món
--
-- App có hai nút trong màn chi tiết món mà không bảng nào đỡ: **dấu trang**
-- (để dành xem lại) và **"Không gợi ý món này nữa"**. Cả hai chỉ sống trong
-- bộ nhớ, nên đóng app là mất — và nút thứ hai còn tệ hơn thế khi có máy
-- chủ: thực đơn do ML service dựng, nên nó **im lặng không có tác dụng**.
-- Người dùng bấm "đừng gợi ý nữa", hôm sau món đó lại hiện ra.
--
-- ## Vì sao một bảng cho cả hai, không phải hai bảng
--
-- Hai nút là hai giá trị của CÙNG một quan hệ: món này với người này đang ở
-- trạng thái nào — không dấu, dấu trang, hay bị chặn. App vốn đã tự giữ luật
-- loại trừ lẫn nhau bằng tay (`toggleLoved` gọi `neverAgainIds.remove`).
--
-- Khóa chính `(user_id, food_id)` chuyển luật đó xuống CSDL: một món **không
-- thể** vừa có dấu trang vừa bị chặn. Hai bảng riêng sẽ cần một ràng buộc
-- chéo để cấm trùng, mà MySQL không có kiểu ràng buộc đó.
--
-- `kind` là ENUM chứ không phải hai cột boolean, vì hai boolean cho phép
-- trạng thái `(true, true)` vô nghĩa tồn tại.
--
-- ## Vì sao KHÔNG có cột `id` thay thế
--
-- Cặp `(user_id, food_id)` chính là danh tính. Thêm `id` tự tăng là thêm một
-- khóa thứ hai cho cùng một thứ, và vẫn phải đặt UNIQUE lên cặp kia để cấm
-- trùng — tức hai chỉ mục thay vì một. Khóa chính tổ hợp cũng khiến câu hỏi
-- nóng nhất ("người này chặn những món nào?") đọc thẳng từ chỉ mục.
--
-- ## `blocked` là BỘ LỌC, không phải điểm số
--
-- Đây là điều quan trọng nhất của migration này. Mọi tín hiệu ưa thích trong
-- hệ thống đều **mềm**: nó dịch một con số, và Bước 4 vẫn có thể chọn món đó
-- nếu một vai trò cạn lựa chọn — đã đo được `side_protein` tụt còn 2 món khi
-- khai đủ 13 bệnh lý. Nhãn 0.0 trọng số 1.0 vẫn để món **đủ điều kiện**.
--
-- Mà nút này hứa "không bao giờ". Nên nó phải là nơi `ml/f1_filter.py`
-- đọc, cạnh Bộ lọc F1 — không phải nơi vector đọc. Khác biệt:
--
--   · ý kiến ("không thích")  -> điểm số. Đã có: vuốt trái, chấm 1 sao.
--   · câu lệnh ("đừng gợi ý") -> bộ lọc. Chưa có. Đây.
--
-- `loved` thì ngược lại: nó hiện **không ảnh hưởng gì** tới thực đơn và
-- không nên ảnh hưởng. Nó là dấu trang, nên icon trái tim cũng đổi thành
-- dấu trang: trái tim hứa một ý kiến, dấu trang chỉ hứa "để dành xem lại".
--
-- ## Vì sao chưa thành nguồn nhãn huấn luyện
--
-- `ml_training_samples.source` KHÔNG có giá trị mới nào ở migration này.
-- Thêm `user_blocked` làm nguồn thứ sáu là việc riêng: phải chọn nhãn và
-- trọng số, và nó **đổi thành phần tập huấn luyện**, tức dịch các con số
-- Chương 3 đã đo. Bộ lọc là thứ làm nút đó trung thực; nhãn huấn luyện là
-- thứ làm nó thông minh hơn. Trung thực trước.
-- ════════════════════════════════════════════════════════════════════════

USE nutrition_rec;

CREATE TABLE user_food_marks (
    user_id    CHAR(36) NOT NULL,
    food_id    CHAR(36) NOT NULL,

    -- `loved`   = dấu trang, không ảnh hưởng gợi ý.
    -- `blocked` = loại khỏi mọi thực đơn sinh sau đó, như một quy tắc cứng.
    kind       ENUM('loved','blocked') NOT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Một món chỉ mang MỘT dấu. Luật loại trừ nằm ở đây, không ở app.
    PRIMARY KEY (user_id, food_id),

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    -- Bước 2 hỏi đúng câu này mỗi lần dựng thực đơn: "người này chặn gì?"
    INDEX idx_kind (user_id, kind)
) ENGINE=InnoDB;

-- Kiểm lại: bảng có mặt, khóa chính là cặp, và ENUM đúng hai giá trị.
SELECT COUNT(*) AS so_dong FROM user_food_marks;

SELECT column_name, column_type, column_key
FROM information_schema.columns
WHERE table_schema = 'nutrition_rec'
  AND table_name   = 'user_food_marks'
ORDER BY ordinal_position;
