-- ════════════════════════════════════════════════════════════════════════
-- 004 — Mức tin cậy của từng ngưỡng, thành cột thay vì nằm trong văn xuôi
--
-- `condition_rules.note` đang chứa xuất xứ của mọi ngưỡng, và ba loại xuất
-- xứ rất khác nhau đang nằm chung một trường chữ:
--
--     "WHO: người lớn dưới 2000 mg natri/ngày"
--     "400 mg/ngày chia cho 3 bữa chính; là suy diễn, không phải ngưỡng
--      công bố"
--     "Ngưỡng theo ngày cho mức nặng CẦN TRA AHA/ESC — chưa xác minh"
--
-- Giao diện cần phân biệt ba thứ đó: một ứng dụng sức khỏe trình bày khuyến
-- cáo của WHO và một con số chưa ai kiểm với cùng giọng tự tin là không
-- trung thực. Nhưng lọc chúng bằng cách tìm chuỗi "chưa xác minh" trong
-- `note` thì hỏng ngay lần đầu ai sửa lại câu chữ.
--
-- ## Bốn giá trị, và vì sao không phải ba
--
--     definitional  Luật LÀ định nghĩa, không có ngưỡng nào để dẫn nguồn.
--                   "Dị ứng trứng thì loại món có trứng" không cần WHO
--                   công bố. Mọi luật `exclude_tag` và `require_tag` thuộc
--                   nhóm này — 9/20 luật. Nhồi chúng vào `published` sẽ
--                   thành khẳng định rằng có tổ chức nào đó công bố điều
--                   hiển nhiên ấy.
--     published     Con số lấy nguyên từ một nguồn đang hiệu lực. WHO
--                   2000 mg natri/ngày; hướng dẫn gút Nhật Bản 400 mg.
--     derived       Nguồn có thật nhưng con số là phép suy ra, nên nó chỉ
--                   đúng với giả thiết đi kèm. 48 g đạm của KDIGO đúng cho
--                   người 60 kg, không đúng cho người 90 kg; 25 g đường là
--                   5% của khẩu phần 2000 kcal; `fat_g` tổng thay cho béo
--                   bão hòa vì bảng thành phần không tách.
--     unsupported   Không có nguồn ĐANG HIỆU LỰC. Hai trường hợp khác
--                   nhau cùng rơi vào đây, và `note` phân biệt chúng:
--                   ngưỡng cholesterol 300 mg/ngày đã BỊ RÚT khỏi Dietary
--                   Guidelines 2015 và AHA/ACC 2019; ngưỡng natri 500 mg
--                   cho mức nặng thì CHƯA ai tra. Về mặt trình bày hai thứ
--                   như nhau — đều không được dẫn như khuyến cáo.
--
-- ## Vì sao để `derived` làm mặc định
--
-- Một luật thêm vào mà quên khai mức tin cậy thì mặc định phải là mức
-- KHÔNG cho phép dẫn nguồn, chứ không phải `published`. Chọn `published`
-- làm mặc định sẽ khiến mọi luật mới tự nhận là có nguồn.
--
-- Chạy:
--     python tools/run_sql.py db/migrations/004_evidence_level.sql --apply
-- ════════════════════════════════════════════════════════════════════════

USE nutrition_rec;

-- ── 1. Thêm cột ──────────────────────────────────────────────────────────

ALTER TABLE condition_rules
  ADD COLUMN evidence_level
      ENUM('definitional', 'published', 'derived', 'unsupported')
      NOT NULL DEFAULT 'derived'
      COMMENT 'Mức tin cậy của ngưỡng; giao diện dùng để chọn giọng trình bày'
      AFTER penalty;

-- ── 1b. Ràng buộc: `definitional` CHỈ dành cho quy tắc nhãn ─────────────
--
-- Thêm cột mà quên ràng buộc thì `schema.sql` khai 16 CHECK còn CSDL đang
-- chạy có 15 — và `test_schema_build.py` KHÔNG bắt được, vì nó dựng CSDL
-- nháp từ `schema.sql` rồi đo chính bản nháp đó, không bao giờ đối chiếu
-- với CSDL thật. Lỗi này đã xảy ra đúng một lần, ở chính tệp migration này.
--
-- Đặt ràng buộc SAU bước 2–4 thì sẽ vỡ, vì lúc đó mọi quy tắc nhãn còn
-- đang mang giá trị mặc định `derived`. Nên gán giá trị trước, ràng buộc
-- sau — xem bước 4b.

-- ── 2. Luật nhãn: định nghĩa, không có ngưỡng để dẫn nguồn ──────────────

UPDATE condition_rules
   SET evidence_level = 'definitional'
 WHERE rule_type IN ('exclude_tag', 'require_tag');

-- ── 3. Ba ngưỡng lấy nguyên từ nguồn đang hiệu lực ──────────────────────

-- WHO: người lớn dưới 2000 mg natri/ngày. Áp cho cả Tăng huyết áp và
-- Bệnh thận — cùng một con số công bố, dùng ở hai chỗ.
UPDATE condition_rules
   SET evidence_level = 'published'
 WHERE rule_type = 'nutrient_limit'
   AND nutrient = 'sodium_mg'
   AND scope = 'per_day'
   AND threshold = 2000.00;

-- Hướng dẫn tăng acid uric máu và gút của Nhật Bản: dưới 400 mg purin/ngày.
UPDATE condition_rules
   SET evidence_level = 'published'
 WHERE rule_type = 'nutrient_limit'
   AND nutrient = 'purine_mg'
   AND scope = 'per_day'
   AND threshold = 400.00;

-- ── 4. Hai ngưỡng không có nguồn đang hiệu lực ──────────────────────────

-- Ngưỡng cholesterol 300 mg/ngày đã bị RÚT khỏi Dietary Guidelines for
-- Americans 2015 và khỏi AHA/ACC 2019.
UPDATE condition_rules
   SET evidence_level = 'unsupported'
 WHERE rule_type = 'nutrient_limit'
   AND nutrient = 'cholesterol_mg'
   AND scope = 'per_day';

-- Ngưỡng natri theo suất cho mức NẶNG — chưa tra AHA/ESC.
UPDATE condition_rules
   SET evidence_level = 'unsupported'
 WHERE rule_type = 'nutrient_limit'
   AND nutrient = 'sodium_mg'
   AND scope = 'per_serving'
   AND severity_min = 'severe';

-- ── 4b. Giờ mới đặt được ràng buộc ─────────────────────────────────────

ALTER TABLE condition_rules
  ADD CONSTRAINT chk_rule_evidence CHECK (
      (rule_type IN ('exclude_tag','require_tag')
           AND evidence_level = 'definitional')
      OR
      (rule_type = 'nutrient_limit'
           AND evidence_level <> 'definitional')
  );

-- ── 5. Phần còn lại giữ `derived` theo mặc định ─────────────────────────
--
-- Sáu luật: đạm 48 g của KDIGO (giả thiết 60 kg), bột đường 60 g mỗi bữa
-- (cách làm cũ, ADA nói rõ không có tỷ lệ lý tưởng), đường 25 g (5% của
-- 2000 kcal), purin 150 mg mỗi suất (400 chia 3), béo 25 g (thay cho béo
-- bão hòa), natri 700 mg mỗi suất (chia theo tỷ lệ năng lượng).

-- ── 6. Soát lại ──────────────────────────────────────────────────────────

SELECT evidence_level, COUNT(*) AS so_luat
  FROM condition_rules
 GROUP BY evidence_level
 ORDER BY FIELD(evidence_level,
                'definitional', 'published', 'derived', 'unsupported');
