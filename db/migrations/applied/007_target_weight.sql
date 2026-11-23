-- ════════════════════════════════════════════════════════════════════════
-- 007 — `health_profiles.target_weight_kg`: cân nặng người dùng muốn đạt
--
-- App Flutter hỏi con số này ngay trong luồng onboarding
-- (`features/onboarding/steps/target_weight_step.dart`), hiển thị nó ở màn
-- tài khoản, và dùng nó cho dòng "còn bao nhiêu kg nữa"
-- (`HealthProfile.weightDelta`). Nhưng **không bảng nào, không endpoint nào
-- mang nó**: nó chỉ sống trong bộ nhớ của app và biến mất khi đóng app.
--
-- Phát hiện lúc nối tầng mạng của app (`mobile/lib/data/api/`): `PUT /profile`
-- gửi sáu trường mà máy chủ có cột, và trường thứ bảy mà app đã hỏi người
-- dùng thì không có chỗ đi. Hỏi một người cân nặng mục tiêu rồi quên mất là
-- điều tệ hơn cả không hỏi.
--
-- ## Vì sao cho NULL
--
-- Chỉ hai trong bốn mục tiêu cần nó: `lose_weight` và `gain_weight`. Người
-- chọn `maintain` hay `healthy_eating` không có đích nào để nhắm, nên app
-- cũng không hỏi (`HealthGoal.needsTargetWeight`). NOT NULL sẽ buộc bịa ra
-- một con số cho hai nửa còn lại — thường là chính `weight_kg`, tức một giá
-- trị trông như người dùng đã khai.
--
-- ## Vì sao KHÔNG đưa vào công thức Bước 1
--
-- Đây là điều quan trọng nhất của migration này. Hạn mức năng lượng đi từ
-- `weight_kg` **hiện tại** qua Mifflin-St Jeor, rồi cộng/trừ 500 kcal theo
-- `goal`. Cân nặng mục tiêu **không** vào đó, và không được vào:
--
--   · Bước 1 có BA bản cài đặt được giữ ngang bằng bằng fixture — Python,
--     C#, Dart. Thêm một biến vào công thức là đổi cả ba, đổi toàn bộ
--     fixture, và dịch mọi con số Chương 3 đã đo.
--   · Giảm cân bằng cách tính TDEE theo cân nặng mục tiêu là cách làm sai về
--     dinh dưỡng: nó cho ra hạn mức của một cơ thể chưa tồn tại, và càng xa
--     đích thì càng nguy hiểm. Mức trừ 500 kcal/ngày (≈ 0,5 kg/tuần) cùng
--     sàn an toàn ở BMR là cơ chế đề cương đã chọn, và nó đúng.
--
-- Nên cột này là **dữ liệu để hiển thị và theo dõi tiến độ**, không phải đầu
-- vào của thuật toán. Đặt cạnh `weight_kg` chứ không nằm trong khối "Đầu ra
-- Bước 1" cũng vì vậy: nó là thứ người dùng khai, không phải thứ hệ thống
-- tính.
--
-- ## Vì sao không có CHECK đối chiếu với `goal`
--
-- Một ràng buộc kiểu "giảm cân thì mục tiêu phải nhỏ hơn cân hiện tại"
-- nghe hợp lý và sẽ chặn người dùng thật: ai đã giảm quá đích rồi sửa lại
-- cân nặng hiện tại sẽ bị CSDL từ chối giữa luồng. Khoảng hợp lệ giữ đúng
-- bằng `chk_weight`, vì nó cũng là một cân nặng; phần nhắc nhở để app làm.
-- ════════════════════════════════════════════════════════════════════════

USE nutrition_rec;

ALTER TABLE health_profiles
    ADD COLUMN target_weight_kg DECIMAL(5,2) NULL AFTER weight_kg,
    ADD CONSTRAINT chk_target_weight
        CHECK (target_weight_kg IS NULL
               OR target_weight_kg BETWEEN 20 AND 300);

-- Kiểm lại: cột có mặt, cho NULL, và ràng buộc đã gắn.
SELECT column_name, column_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'nutrition_rec'
  AND table_name   = 'health_profiles'
  AND column_name  = 'target_weight_kg';

SELECT constraint_name
FROM information_schema.check_constraints
WHERE constraint_schema = 'nutrition_rec'
  AND constraint_name   = 'chk_target_weight';
