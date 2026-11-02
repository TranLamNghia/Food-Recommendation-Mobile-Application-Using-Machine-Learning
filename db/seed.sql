-- ═══════════════════════════════════════════════════════════════════════════
--  Dữ liệu nền — chạy SAU schema.sql
--
--  Gồm 4 bảng từ điển + BỘ QUY TẮC F1 + vài món mẫu để kiểm thử lược đồ.
--  Dữ liệu món ăn thật (300–500 món) nạp riêng bằng script đọc CSV.
--
--  ⚠ CÁC NGƯỠNG TRONG condition_rules LÀ SỐ MINH HỌA.
--    Khi triển khai thật phải tra theo tài liệu
--    "Nhu cầu dinh dưỡng khuyến nghị cho người Việt Nam" (NIN 2016)
--    và ghi nguồn của từng ngưỡng vào cột `note`.
-- ═══════════════════════════════════════════════════════════════════════════

USE nutrition_rec;


-- ── 1. conditions ─────────────────────────────────────────────────────────
INSERT INTO conditions (name_vi, condition_type, description) VALUES
('Đái tháo đường',         'disease',     'Cần hạn chế đường và tinh bột hấp thu nhanh'),
('Tăng huyết áp',          'disease',     'Cần hạn chế natri'),
('Bệnh thận',              'disease',     'Cần hạn chế đạm và natri'),
('Rối loạn mỡ máu',        'disease',     'Cần hạn chế cholesterol và chất béo bão hòa'),
('Gút',                    'disease',     'Cần hạn chế purin'),
('Dị ứng hải sản',         'allergy',     NULL),
('Dị ứng đậu phộng',       'allergy',     NULL),
('Dị ứng trứng',           'allergy',     NULL),
-- Nhãn `Có đậu nành` tồn tại từ đầu và gắn cho 13 món, nhưng trước đây không
-- bệnh nào dùng tới nó: 6 nhãn dị nguyên mà chỉ 5 bệnh. Người dị ứng đậu nành
-- vì vậy không khai được, và Bộ lọc F1 không loại gì cho họ — trong khi đậu
-- nành là một trong các dị nguyên phổ biến nhất. Phát hiện khi chạy
-- `tools/check_f1.py`.
('Dị ứng đậu nành',        'allergy',     NULL),
('Không dung nạp lactose', 'intolerance', NULL),
('Không dung nạp gluten',  'intolerance', NULL),
('Ăn chay',                'diet',        'Không ăn thịt, có thể dùng trứng và sữa'),
('Ăn thuần chay',          'diet',        'Không dùng mọi sản phẩm từ động vật');


-- ── 2. tags ───────────────────────────────────────────────────────────────
INSERT INTO tags (name_vi, tag_type, description) VALUES
-- Dị nguyên: dùng thay cho bảng nguyên liệu chi tiết.
-- Đủ chính xác cho các nhóm dị ứng phổ biến, chi phí nhập liệu thấp hơn
-- nhiều lần. Hạn chế với dị ứng hiếm — đã ghi vào phần hạn chế báo cáo.
('Có hải sản',              'allergen',  NULL),
('Có đậu phộng',            'allergen',  NULL),
('Có trứng',                'allergen',  NULL),
('Có sữa / chế phẩm sữa',   'allergen',  NULL),
('Có gluten',               'allergen',  NULL),
('Có đậu nành',             'allergen',  NULL),
-- Chế độ ăn
('Món chay',                'diet',      NULL),
('Món thuần chay',          'diet',      NULL),
-- Dinh dưỡng — dùng cho quy tắc bệnh lý và vector đặc trưng
('Ít natri',                'nutrition', NULL),
('Ít đường',                'nutrition', NULL),
('Giàu đạm',                'nutrition', NULL),
('Giàu chất xơ',            'nutrition', NULL),
-- Thay cho ngưỡng purine_mg: cột đó chỉ có số liệu ở 16 % mục của Bảng thành
-- phần thực phẩm Việt Nam 2007, còn USDA không công bố purin. Không nguồn uy
-- tín nào lấp được, nên ràng buộc cho người bệnh gút chuyển sang mức phân
-- loại nhóm thực phẩm.
('Giàu purin',              'nutrition', 'Nội tạng, hải sản vỏ cứng, cá nhỏ nguyên con, nước dùng ninh xương lâu');

-- Không còn nhãn vị. Vị mặn và vị ngọt nay là CHIỀU VECTOR tính từ
-- `sodium_mg` và `sugar_g` — số đo thay cho nhãn gán tay. Vị chua và vị đắng
-- không nguồn nào công bố nên không biểu diễn, và đó là hạn chế đã ghi trong
-- báo cáo.


-- ── 3. food_categories ────────────────────────────────────────────────────
-- Giữ 12 danh mục: mã hóa one-hot cho ML, nhiều quá làm vector thưa.
INSERT INTO food_categories (name, description) VALUES
('Món nước',        'Phở, bún, miến, hủ tiếu'),
('Cơm',             'Cơm trắng, cơm tấm, cơm chiên'),
('Món kho',         'Thịt kho, cá kho'),
('Món xào',         'Rau xào, thịt xào'),
('Món canh',        'Canh chua, canh rau'),
('Món chiên rán',   'Nem rán, gà rán, cá chiên'),
('Món nướng',       'Thịt nướng, cá nướng'),
('Món luộc hấp',    'Rau luộc, thịt luộc, cá hấp'),
('Món cuốn',        'Gỏi cuốn, bánh cuốn'),
('Món gỏi / nộm',   'Gỏi, nộm, salad'),
('Tráng miệng',     'Chè, bánh ngọt, trái cây'),
('Đồ uống',         'Nước ép, sữa, trà');


-- ── 4. condition_rules — BỘ QUY TẮC F1 ────────────────────────────────────
-- Đây là bảng in vào báo cáo. Vừa là sản phẩm phải nộp theo đề cương,
-- vừa là phương án đối chứng variant='rule_based' ở Chương 3.

-- 4a. Ràng buộc theo ngưỡng dinh dưỡng
--
-- ═══ MỌI NGƯỠNG CỨNG Ở ĐÂY ĐỀU THEO NGÀY, VÀ ĐỀU CÓ NGUỒN ═══
--
-- Bản trước đặt ngưỡng CỨNG theo từng khẩu phần với những con số tự nghĩ ra.
-- Hậu quả đo được: ngưỡng natri 600 mg mỗi suất loại **58 trong 60 món**, để
-- lại 2 món — Bước 4 không dựng nổi thực đơn bốn bữa, tức hệ thống vô dụng
-- với người tăng huyết áp.
--
-- Nguyên nhân gốc: **mọi hướng dẫn y khoa đều phát biểu theo NGÀY**, không
-- theo từng món. Chia nhỏ xuống mỗi suất là tự đặt ra một ràng buộc chặt hơn
-- nguồn, vì nó cấm cả việc ăn một món mặn rồi bù bằng các món nhạt.
--
-- Nên cấu trúc mới:
--   · ngưỡng CỨNG  → scope per_day, giá trị lấy từ hướng dẫn, Bước 4 kiểm
--   · ngưỡng MỀM   → scope per_serving, chỉ TRỪ ĐIỂM để hạ bậc món quá đậm
--
-- Quy tắc dị nguyên và chế độ ăn (mục 4b, 4c) vẫn CỨNG — dị ứng là tuyệt đối.

INSERT INTO condition_rules
    (condition_id, rule_type, nutrient, comparator, threshold, scope, severity_min, is_hard, penalty, note)
SELECT c.id, 'nutrient_limit', v.nutrient, v.comparator, v.threshold, v.scope,
       v.severity_min, v.is_hard, v.penalty, v.note
FROM (
    -- ── Tăng huyết áp ──
    SELECT 'Tăng huyết áp' AS code, 'sodium_mg' AS nutrient, 'lte' AS comparator, 2000.00 AS threshold, 'per_day' AS scope, 'mild' AS severity_min, 1 AS is_hard, NULL AS penalty, 'WHO: người lớn dưới 2000 mg natri/ngày (tương đương 5 g muối)' AS note
    UNION ALL SELECT 'Tăng huyết áp', 'sodium_mg', 'lte',  700.00, 'per_serving', 'mild',   0, 0.600, 'Ràng buộc MỀM. 2000 mg/ngày chia theo tỷ lệ năng lượng bữa lớn nhất; không phải ngưỡng của hướng dẫn nào'
    UNION ALL SELECT 'Tăng huyết áp', 'sodium_mg', 'lte',  500.00, 'per_serving', 'severe', 0, 0.400, 'Ràng buộc MỀM, phạt nặng hơn cho mức nặng. Ngưỡng theo ngày cho mức nặng CẦN TRA AHA/ESC — chưa xác minh'

    -- ── Gút ──
    UNION ALL SELECT 'Gút', 'purine_mg', 'lte', 400.00, 'per_day',     'mild', 1, NULL,  'Hướng dẫn tăng acid uric máu và gút của Nhật Bản: dưới 400 mg purin/ngày'
    UNION ALL SELECT 'Gút', 'purine_mg', 'lte', 150.00, 'per_serving', 'mild', 0, 0.500, 'Ràng buộc MỀM. 400 mg/ngày chia cho 3 bữa chính; là suy diễn, không phải ngưỡng công bố'

    -- ── Bệnh thận mạn ──
    UNION ALL SELECT 'Bệnh thận', 'protein_g', 'lte',   48.00, 'per_day', 'mild', 1, NULL, 'KDIGO 2024: 0,8 g đạm/kg/ngày. 48 g cho người 60 kg. KHẢ THI nhưng pha 5 chỉ đạt 4/12: sàn đạm của cấu trúc bữa là 34,5 g nên ngưỡng nằm trong tầm, song phép đổi một món bị kẹt ở cực trị cục bộ. Xem ML_PIPELINE mục 7.0.1'
    UNION ALL SELECT 'Bệnh thận', 'sodium_mg', 'lte', 2000.00, 'per_day', 'mild', 1, NULL, 'Áp cùng ngưỡng natri của WHO; bệnh thận cũng cần hạn chế natri'

    -- ── Rối loạn mỡ máu ──
    UNION ALL SELECT 'Rối loạn mỡ máu', 'cholesterol_mg', 'lte', 300.00, 'per_day', 'mild', 0, 0.700, 'Ràng buộc MỀM vì ngưỡng 300 mg/ngày ĐÃ BỊ RÚT khỏi Dietary Guidelines for Americans 2015 và AHA/ACC 2019. Giữ ở mức khuyến cáo, không chống chỉ định'
    UNION ALL SELECT 'Rối loạn mỡ máu', 'fat_g',          'lte',  25.00, 'per_serving', 'mild', 0, 0.750, 'Ràng buộc MỀM. Mục tiêu THẬT của AHA là béo BÃO HÒA dưới 10% năng lượng, nhưng bảng thành phần thực phẩm không tách béo bão hòa nên dùng béo tổng làm thay'

    -- ── Đái tháo đường ──
    UNION ALL SELECT 'Đái tháo đường', 'sugar_g', 'lte', 25.00, 'per_day',  'mild', 0, 0.600, 'Ràng buộc MỀM. WHO khuyến cáo đường tự do dưới 10% năng lượng, lý tưởng dưới 5% (~25 g với khẩu phần 2000 kcal). ADA không đặt mốc gam cố định'
    UNION ALL SELECT 'Đái tháo đường', 'carbs_g', 'lte', 60.00, 'per_meal', 'mild', 0, 0.700, 'Ràng buộc MỀM. ADA Standards of Care nêu rõ KHÔNG có tỷ lệ bột đường lý tưởng; 45–60 g mỗi bữa là cách làm cũ, giữ làm khuyến cáo chứ không phải ngưỡng'
) v
JOIN conditions c ON c.name_vi = v.code;

-- 4b. Ràng buộc loại bỏ theo nhãn dị nguyên
INSERT INTO condition_rules (condition_id, rule_type, tag_id, severity_min, is_hard, note)
SELECT c.id, 'exclude_tag', t.id, 'mild', 1, CONCAT('Loại mọi món có nhãn ', t.name_vi)
FROM (
    SELECT 'Dị ứng hải sản'     AS ccode, 'Có hải sản' AS tcode
    UNION ALL SELECT 'Dị ứng đậu phộng',      'Có đậu phộng'
    UNION ALL SELECT 'Dị ứng trứng',         'Có trứng'
    UNION ALL SELECT 'Dị ứng đậu nành',      'Có đậu nành'
    UNION ALL SELECT 'Không dung nạp lactose', 'Có sữa / chế phẩm sữa'
    UNION ALL SELECT 'Không dung nạp gluten',  'Có gluten'
) v
JOIN conditions c ON c.name_vi = v.ccode
JOIN tags       t ON t.name_vi = v.tcode;

-- 4b-bis. Ràng buộc gút theo nhãn, thay cho ngưỡng purin
-- Quy tắc nutrient_limit trên purine_mg ở mục 4a chỉ chạy được với khoảng
-- 6 % số món, vì bảng thành phần gốc thiếu số liệu purin và USDA không công
-- bố chất này. Quy tắc theo nhãn phủ phần còn lại ở mức phân loại nhóm thực
-- phẩm. Giữ CẢ HAI: có số đo thì dùng số, không có thì dùng nhãn.
INSERT INTO condition_rules (condition_id, rule_type, tag_id, severity_min, is_hard, note)
SELECT c.id, 'exclude_tag', t.id, 'moderate', 1,
       'Loại món giàu purin — dùng khi thiếu số liệu purine_mg'
FROM conditions c
JOIN tags t ON t.name_vi = 'Giàu purin'
WHERE c.name_vi = 'Gút';


-- 4c. Ràng buộc bắt buộc theo nhãn chế độ ăn
INSERT INTO condition_rules (condition_id, rule_type, tag_id, severity_min, is_hard, note)
SELECT c.id, 'require_tag', t.id, 'mild', 1, CONCAT('Chỉ giữ món có nhãn ', t.name_vi)
FROM (
    SELECT 'Ăn chay' AS ccode, 'Món chay' AS tcode
    UNION ALL SELECT 'Ăn thuần chay', 'Món thuần chay'
) v
JOIN conditions c ON c.name_vi = v.ccode
JOIN tags       t ON t.name_vi = v.tcode;


-- ── 5. rda_reference — mẫu tối thiểu ──────────────────────────────────────
-- Nạp đầy đủ từ NIN 2016 bằng script riêng.
INSERT INTO rda_reference (gender, age_min, age_max, nutrient, rda_value, unit) VALUES
('male',   19, 30, 'protein_g',     68.00, 'g'),
('male',   19, 30, 'calcium_mg',   800.00, 'mg'),
('male',   19, 30, 'iron_mg',       11.90, 'mg'),
('male',   19, 30, 'vitamin_c_mg',  85.00, 'mg'),
('female', 19, 30, 'protein_g',     60.00, 'g'),
('female', 19, 30, 'calcium_mg',   800.00, 'mg'),
('female', 19, 30, 'iron_mg',       26.10, 'mg'),
('female', 19, 30, 'vitamin_c_mg',  75.00, 'mg');

-- Chất xơ — nguồn WHO, không phải NIN.
--
-- Bốn dòng này là cơ sở để trả lời nhu cầu "tôi muốn ăn nhiều chất xơ".
-- Không có chúng thì nhu cầu đó không có con số nào để đối chiếu, và hệ
-- thống chỉ còn cách gắn một cái nhãn `Giàu chất xơ` mà ngưỡng "giàu" là bao
-- nhiêu thì không ai nói được.
--
-- `gender = 'all'` vì khuyến nghị của WHO **không phân biệt giới** — khác hẳn
-- sắt (nam 11,90 / nữ 26,10). Chép thành hai dòng nam và nữ sẽ ngụ ý một sự
-- phân biệt mà nguồn không hề đưa ra.
--
-- Khuyến nghị cho người lớn ở mức **mạnh**; ba mức cho trẻ em là **có điều
-- kiện** và được ngoại suy từ giá trị người lớn vì chứng cứ riêng cho trẻ em
-- chưa đủ. Ghi vào `source` để khi đọc lại còn biết độ chắc của từng dòng.
--
-- WHO, Carbohydrate intake for adults and children: WHO guideline (2023)
-- https://iris.who.int/server/api/core/bitstreams/6c31b739-c2e8-4515-970d-d9e42346c7f4/content
INSERT INTO rda_reference (gender, age_min, age_max, nutrient, rda_value, unit, source) VALUES
('all',  2,  5, 'fiber_g', 15.00, 'g', 'WHO carbohydrate guideline 2023 (khuyen nghi co dieu kien)'),
('all',  6,  9, 'fiber_g', 21.00, 'g', 'WHO carbohydrate guideline 2023 (khuyen nghi co dieu kien)'),
('all', 10, 18, 'fiber_g', 25.00, 'g', 'WHO carbohydrate guideline 2023 (khuyen nghi co dieu kien)'),
('all', 19, 120, 'fiber_g', 25.00, 'g', 'WHO carbohydrate guideline 2023 (khuyen nghi manh)');


-- ── 6. Món ăn — KHÔNG seed ở đây ─────────────────────────────────────────
--
-- Trước đây mục này chèn 9 món mẫu để kiểm thử lược đồ. Đã bỏ vì tập dữ liệu
-- thật đã có và hai bên chồng lấn nhau:
--
--   · "Phở bò" mẫu trùng khái niệm với "Phở bò tái" và "Phở bò chín" thật
--   · "Canh chua cá lóc" mẫu THIẾU nhãn contains_seafood — người dị ứng hải
--     sản sẽ được gợi ý canh cá
--   · "Phở bò" mẫu gắn contains_gluten, trong khi bánh phở làm từ gạo
--
-- Món ăn nay đi theo một đường duy nhất:
--
--   data/foods/*.csv  →  tools/load_foods.py  →  db/seed_foods.sql  →  MySQL
--
-- Tệp này chỉ seed các bảng từ điển và tham chiếu: conditions, tags,
-- food_categories, condition_rules, rda_reference. Một nguồn cho mỗi loại
-- dữ liệu, không có bản sao để lệch nhau.
