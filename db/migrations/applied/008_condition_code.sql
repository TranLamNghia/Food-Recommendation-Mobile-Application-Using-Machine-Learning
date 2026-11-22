-- ════════════════════════════════════════════════════════════════════════
-- 008 — `conditions.code`: khóa bền cho bệnh lý, thay vì chỉ có id tự tăng
--
-- Ba chỗ cùng cần một thứ mà bảng `conditions` không có: **một mã ổn định**.
--
-- ## 1. Đặc tả đã hứa nó
--
-- API 7.5.2 trả cảnh báo món không phù hợp với hình dạng:
--
--     { "conditionCode": "hypertension", "conditionName": "Tăng huyết áp", ... }
--
-- Không có cột `code` nên backend đang trả `conditionId` thay thế. Đó là chỗ
-- lệch đã ghi trong `DOC_DEVIATIONS.md`; migration này đóng nó lại, và trả
-- đúng chuỗi mà ví dụ trong tài liệu viết ra.
--
-- ## 2. App đã dùng chính những mã này
--
-- `mobile/lib/data/mock/mock_rules.dart` khóa toàn bộ quy tắc F1 bản ngoại
-- tuyến theo `'hypertension'`, `'gout'`, `'allergy_seafood'`… và
-- `features/onboarding/steps/conditions_step.dart` dựng danh sách câu hỏi
-- theo đúng bộ mã đó. Nghĩa là vốn từ này đã tồn tại và đang chạy — nó chỉ
-- chưa có mặt trong CSDL.
--
-- ## 3. `id` là khóa thay thế, KHÔNG dùng được để nối hai bên
--
-- `conditions.id` là `INT UNSIGNED AUTO_INCREMENT`. Dựng CSDL mới bằng
-- `schema.sql` + `seed.sql` thì thứ tự chèn quyết định id — nên một app
-- hard-code `conditionId: 2` sẽ đúng trên máy này và sai trên máy khác, mà
-- không báo gì: nó vẫn khai một bệnh, chỉ là bệnh khác. Bộ lọc F1 sau đó loại
-- nhầm nhóm món.
--
-- Mã chuỗi thì không phụ thuộc thứ tự chèn. App tra `GET /conditions` một
-- lần, ghép theo `code`, và dùng `id` cho các lần gọi sau — id vẫn là khóa
-- ngoại trong `user_conditions` và `condition_rules`, không đổi gì ở đó.
--
-- ## Vì sao không bỏ `id` và lấy `code` làm khóa chính
--
-- `code` dài 40 byte, `id` là 4. Hai bảng tham chiếu tới nó
-- (`user_conditions`, `condition_rules`) và cả hai đều có chỉ mục trên khóa
-- ngoại đó; đổi sang chuỗi là phình mọi chỉ mục để đổi lấy một tiện lợi khi
-- đọc bằng mắt. Giữ cả hai: `id` để nối bảng, `code` để nối hệ thống.
--
-- ## Vì sao điền theo `name_vi` chứ không theo `id`
--
-- Chính vì lý do ở mục 3: trên CSDL đang chạy thì id là 1..13, nhưng
-- migration này còn phải đúng với bất kỳ CSDL nào đã dựng theo thứ tự khác.
-- `name_vi` đã là `UNIQUE` nên nó là khóa tự nhiên duy nhất đang có.
-- ════════════════════════════════════════════════════════════════════════

USE nutrition_rec;

-- Cho NULL trước, điền, rồi mới siết — không thể thêm NOT NULL vào bảng đã
-- có 13 dòng mà không có giá trị mặc định nào đúng.
ALTER TABLE conditions ADD COLUMN code VARCHAR(40) NULL AFTER id;

UPDATE conditions SET code = 'diabetes'            WHERE name_vi = 'Đái tháo đường';
UPDATE conditions SET code = 'hypertension'        WHERE name_vi = 'Tăng huyết áp';
UPDATE conditions SET code = 'kidney_disease'      WHERE name_vi = 'Bệnh thận';
UPDATE conditions SET code = 'dyslipidemia'        WHERE name_vi = 'Rối loạn mỡ máu';
UPDATE conditions SET code = 'gout'                WHERE name_vi = 'Gút';
UPDATE conditions SET code = 'allergy_seafood'     WHERE name_vi = 'Dị ứng hải sản';
UPDATE conditions SET code = 'allergy_peanut'      WHERE name_vi = 'Dị ứng đậu phộng';
UPDATE conditions SET code = 'allergy_egg'         WHERE name_vi = 'Dị ứng trứng';
UPDATE conditions SET code = 'allergy_soy'         WHERE name_vi = 'Dị ứng đậu nành';
UPDATE conditions SET code = 'lactose_intolerance' WHERE name_vi = 'Không dung nạp lactose';
UPDATE conditions SET code = 'gluten_intolerance'  WHERE name_vi = 'Không dung nạp gluten';
UPDATE conditions SET code = 'vegetarian'          WHERE name_vi = 'Ăn chay';
UPDATE conditions SET code = 'vegan'               WHERE name_vi = 'Ăn thuần chay';

-- Dừng lại nếu còn dòng nào chưa có mã: siết NOT NULL khi còn NULL sẽ khiến
-- MySQL tự điền chuỗi rỗng, và bản sửa đó lặng lẽ hơn một lỗi.
SELECT COUNT(*) AS so_dong_chua_co_ma FROM conditions WHERE code IS NULL;

ALTER TABLE conditions
    MODIFY code VARCHAR(40) NOT NULL,
    ADD UNIQUE KEY uq_condition_code (code);

SELECT id, code, condition_type, name_vi FROM conditions ORDER BY id;
