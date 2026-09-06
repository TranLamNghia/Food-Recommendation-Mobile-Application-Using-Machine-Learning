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
INSERT INTO conditions (code, name_vi, condition_type, description) VALUES
('diabetes',            'Đái tháo đường',         'disease',     'Cần hạn chế đường và tinh bột hấp thu nhanh'),
('hypertension',        'Tăng huyết áp',          'disease',     'Cần hạn chế natri'),
('kidney_disease',      'Bệnh thận',              'disease',     'Cần hạn chế đạm và natri'),
('dyslipidemia',        'Rối loạn mỡ máu',        'disease',     'Cần hạn chế cholesterol và chất béo bão hòa'),
('gout',                'Gút',                    'disease',     'Cần hạn chế purin'),
('allergy_seafood',     'Dị ứng hải sản',         'allergy',     NULL),
('allergy_peanut',      'Dị ứng đậu phộng',       'allergy',     NULL),
('allergy_egg',         'Dị ứng trứng',           'allergy',     NULL),
('lactose_intolerance', 'Không dung nạp lactose', 'intolerance', NULL),
('gluten_intolerance',  'Không dung nạp gluten',  'intolerance', NULL),
('vegetarian',          'Ăn chay',                'diet',        'Không ăn thịt, có thể dùng trứng và sữa'),
('vegan',               'Ăn thuần chay',          'diet',        'Không dùng mọi sản phẩm từ động vật');


-- ── 2. tags ───────────────────────────────────────────────────────────────
INSERT INTO tags (code, name_vi, tag_type, description) VALUES
-- Dị nguyên: dùng thay cho bảng nguyên liệu chi tiết.
-- Đủ chính xác cho các nhóm dị ứng phổ biến, chi phí nhập liệu thấp hơn
-- nhiều lần. Hạn chế với dị ứng hiếm — đã ghi vào phần hạn chế báo cáo.
('contains_seafood', 'Có hải sản',              'allergen',  NULL),
('contains_peanut',  'Có đậu phộng',            'allergen',  NULL),
('contains_egg',     'Có trứng',                'allergen',  NULL),
('contains_dairy',   'Có sữa / chế phẩm sữa',   'allergen',  NULL),
('contains_gluten',  'Có gluten',               'allergen',  NULL),
('contains_soy',     'Có đậu nành',             'allergen',  NULL),
-- Chế độ ăn
('vegetarian',       'Món chay',                'diet',      NULL),
('vegan',            'Món thuần chay',          'diet',      NULL),
-- Dinh dưỡng — dùng cho quy tắc bệnh lý và vector đặc trưng
('low_sodium',       'Ít natri',                'nutrition', NULL),
('low_sugar',        'Ít đường',                'nutrition', NULL),
('high_protein',     'Giàu đạm',                'nutrition', NULL),
('high_fiber',       'Giàu chất xơ',            'nutrition', NULL),
-- Khẩu vị — thành phần "khẩu vị" của vector đặc trưng ML
('salty',            'Mặn',                     'taste',     NULL),
('sweet',            'Ngọt',                    'taste',     NULL),
('sour',             'Chua',                    'taste',     NULL),
('fatty',            'Béo',                     'taste',     NULL),
('light',            'Thanh đạm',               'taste',     NULL);


-- ── 3. food_categories ────────────────────────────────────────────────────
-- Giữ 12 danh mục: mã hóa one-hot cho ML, nhiều quá làm vector thưa.
INSERT INTO food_categories (code, name, description) VALUES
('mon_nuoc',    'Món nước',        'Phở, bún, miến, hủ tiếu'),
('com',         'Cơm',             'Cơm trắng, cơm tấm, cơm chiên'),
('mon_kho',     'Món kho',         'Thịt kho, cá kho'),
('mon_xao',     'Món xào',         'Rau xào, thịt xào'),
('mon_canh',    'Món canh',        'Canh chua, canh rau'),
('mon_chien',   'Món chiên rán',   'Nem rán, gà rán, cá chiên'),
('mon_nuong',   'Món nướng',       'Thịt nướng, cá nướng'),
('mon_luoc_hap','Món luộc hấp',    'Rau luộc, thịt luộc, cá hấp'),
('mon_cuon',    'Món cuốn',        'Gỏi cuốn, bánh cuốn'),
('mon_goi',     'Món gỏi / nộm',   'Gỏi, nộm, salad'),
('trang_mieng', 'Tráng miệng',     'Chè, bánh ngọt, trái cây'),
('do_uong',     'Đồ uống',         'Nước ép, sữa, trà');


-- ── 4. condition_rules — BỘ QUY TẮC F1 ────────────────────────────────────
-- Đây là bảng in vào báo cáo. Vừa là sản phẩm phải nộp theo đề cương,
-- vừa là phương án đối chứng variant='rule_based' ở Chương 3.

-- 4a. Ràng buộc theo ngưỡng dinh dưỡng
INSERT INTO condition_rules
    (condition_id, rule_type, nutrient, comparator, threshold, scope, severity_min, is_hard, penalty, note)
SELECT c.id, 'nutrient_limit', v.nutrient, v.comparator, v.threshold, v.scope,
       v.severity_min, v.is_hard, v.penalty, v.note
FROM (
    SELECT 'diabetes'     AS code, 'sugar_g'        AS nutrient, 'lte' AS comparator,   10.00 AS threshold, 'per_serving' AS scope, 'mild'     AS severity_min, 1 AS is_hard, NULL AS penalty, 'Hạn chế đường hấp thu nhanh'          AS note
    UNION ALL SELECT 'diabetes',     'carbs_g',        'lte',   60.00, 'per_meal',    'mild',     0, 0.700, 'Khuyến cáo mềm: hạn chế tinh bột mỗi bữa'
    UNION ALL SELECT 'hypertension', 'sodium_mg',      'lte',  600.00, 'per_serving', 'mild',     1, NULL,  'Ngưỡng natri mỗi khẩu phần'
    UNION ALL SELECT 'hypertension', 'sodium_mg',      'lte', 2000.00, 'per_day',     'mild',     1, NULL,  'Ngưỡng natri cả ngày — kiểm tra ở Bước 4'
    UNION ALL SELECT 'hypertension', 'sodium_mg',      'lte',  400.00, 'per_serving', 'severe',   1, NULL,  'Ngưỡng chặt hơn cho mức nặng'
    UNION ALL SELECT 'dyslipidemia', 'cholesterol_mg', 'lte',  200.00, 'per_serving', 'mild',     1, NULL,  'Ngưỡng cholesterol mỗi khẩu phần'
    UNION ALL SELECT 'dyslipidemia', 'fat_g',          'lte',   20.00, 'per_serving', 'mild',     0, 0.750, 'Khuyến cáo mềm: hạn chế chất béo'
    UNION ALL SELECT 'kidney_disease','protein_g',     'lte',   15.00, 'per_serving', 'mild',     1, NULL,  'Hạn chế đạm'
    UNION ALL SELECT 'kidney_disease','sodium_mg',     'lte',  500.00, 'per_serving', 'mild',     1, NULL,  'Hạn chế natri'
    UNION ALL SELECT 'gout',         'purine_mg',      'lte',  100.00, 'per_serving', 'mild',     1, NULL,  'Hạn chế purin'
) v
JOIN conditions c ON c.code = v.code;

-- 4b. Ràng buộc loại bỏ theo nhãn dị nguyên
INSERT INTO condition_rules (condition_id, rule_type, tag_id, severity_min, is_hard, note)
SELECT c.id, 'exclude_tag', t.id, 'mild', 1, CONCAT('Loại mọi món có nhãn ', t.code)
FROM (
    SELECT 'allergy_seafood'     AS ccode, 'contains_seafood' AS tcode
    UNION ALL SELECT 'allergy_peanut',      'contains_peanut'
    UNION ALL SELECT 'allergy_egg',         'contains_egg'
    UNION ALL SELECT 'lactose_intolerance', 'contains_dairy'
    UNION ALL SELECT 'gluten_intolerance',  'contains_gluten'
) v
JOIN conditions c ON c.code = v.ccode
JOIN tags       t ON t.code = v.tcode;

-- 4c. Ràng buộc bắt buộc theo nhãn chế độ ăn
INSERT INTO condition_rules (condition_id, rule_type, tag_id, severity_min, is_hard, note)
SELECT c.id, 'require_tag', t.id, 'mild', 1, CONCAT('Chỉ giữ món có nhãn ', t.code)
FROM (
    SELECT 'vegetarian' AS ccode, 'vegetarian' AS tcode
    UNION ALL SELECT 'vegan', 'vegan'
) v
JOIN conditions c ON c.code = v.ccode
JOIN tags       t ON t.code = v.tcode;


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


-- ── 6. Món ăn mẫu — chỉ để kiểm thử lược đồ ───────────────────────────────
INSERT INTO foods (category_id, name, origin, cooking_method, spice_level, dish_role, suitable_meals)
SELECT fc.id, v.name, v.origin, v.cooking_method, v.spice_level, v.dish_role, v.meals
FROM (
    SELECT 'mon_nuoc'     AS cat, 'Phở bò'               AS name, 'Hà Nội'   AS origin, 'nau_canh' AS cooking_method, 0 AS spice_level, 'main'    AS dish_role, 'breakfast,lunch,dinner' AS meals
    UNION ALL SELECT 'mon_nuoc',      'Bún bò Huế',        'Huế',      'nau_canh', 2, 'main',    'breakfast,lunch'
    UNION ALL SELECT 'com',           'Cơm tấm sườn nướng','Sài Gòn',  'nuong',    0, 'main',    'lunch,dinner'
    UNION ALL SELECT 'mon_kho',       'Thịt kho tàu',      NULL,       'kho',      0, 'main',    'lunch,dinner'
    UNION ALL SELECT 'mon_canh',      'Canh chua cá lóc',  'Miền Tây', 'nau_canh', 1, 'soup',    'lunch,dinner'
    UNION ALL SELECT 'mon_canh',      'Canh bí đao',       NULL,       'nau_canh', 0, 'soup',    'lunch,dinner'
    UNION ALL SELECT 'mon_chien',     'Nem rán',           'Hà Nội',   'chien',    0, 'side',    'lunch,dinner'
    UNION ALL SELECT 'mon_luoc_hap',  'Rau muống luộc',    NULL,       'luoc',     0, 'side',    'lunch,dinner'
    UNION ALL SELECT 'mon_goi',       'Gỏi ngó sen tôm thịt', NULL,    'tron',     1, 'side',    'lunch,dinner'
    UNION ALL SELECT 'trang_mieng',   'Sữa chua nếp cẩm',  NULL,       'khac',     0, 'dessert', 'snack'
) v
JOIN food_categories fc ON fc.code = v.cat;

INSERT INTO food_nutrition
    (food_id, serving_size_g, calories_kcal, protein_g, carbs_g, fat_g,
     fiber_g, sugar_g, sodium_mg, cholesterol_mg, purine_mg, data_source)
SELECT f.id, v.serving, v.kcal, v.protein, v.carbs, v.fat,
       v.fiber, v.sugar, v.sodium, v.chol, v.purine, 'Số liệu mẫu — thay bằng Bảng TPTP Việt Nam'
FROM (
    SELECT 'Phở bò'               AS name, 400 AS serving, 430.00 AS kcal, 25.00 AS protein, 55.00 AS carbs, 12.00 AS fat, 2.00 AS fiber,  3.00 AS sugar, 1200.00 AS sodium,  60.00 AS chol, 150.00 AS purine
    UNION ALL SELECT 'Bún bò Huế',            450, 520.00, 28.00, 60.00, 18.00, 2.50,  4.00, 1500.00,  75.00, 180.00
    UNION ALL SELECT 'Cơm tấm sườn nướng',    400, 620.00, 30.00, 78.00, 20.00, 2.00,  8.00,  900.00,  85.00, 120.00
    UNION ALL SELECT 'Thịt kho tàu',          150, 340.00, 22.00,  6.00, 25.00, 0.50,  5.00,  980.00, 110.00, 140.00
    UNION ALL SELECT 'Canh chua cá lóc',      250, 120.00, 14.00, 10.00,  3.00, 1.80,  6.00,  650.00,  40.00,  90.00
    UNION ALL SELECT 'Canh bí đao',           250,  45.00,  2.00,  8.00,  1.00, 1.50,  3.00,  380.00,   0.00,  10.00
    UNION ALL SELECT 'Nem rán',               100, 280.00, 12.00, 22.00, 16.00, 1.00,  2.00,  520.00,  55.00, 100.00
    UNION ALL SELECT 'Rau muống luộc',        150,  35.00,  3.00,  5.00,  0.30, 2.80,  1.00,   45.00,   0.00,  20.00
    UNION ALL SELECT 'Gỏi ngó sen tôm thịt',  180, 210.00, 15.00, 18.00,  9.00, 2.20, 10.00,  700.00,  70.00, 160.00
    UNION ALL SELECT 'Sữa chua nếp cẩm',      180, 230.00,  6.00, 40.00,  5.00, 1.20, 25.00,   80.00,  15.00,  10.00
) v
JOIN foods f ON f.name = v.name;

-- Gán nhãn cho món mẫu
INSERT INTO food_tags (food_id, tag_id)
SELECT f.id, t.id
FROM (
    SELECT 'Phở bò'                AS fname, 'salty'            AS tcode
    UNION ALL SELECT 'Phở bò',               'contains_gluten'
    UNION ALL SELECT 'Bún bò Huế',           'salty'
    UNION ALL SELECT 'Cơm tấm sườn nướng',   'fatty'
    UNION ALL SELECT 'Thịt kho tàu',         'salty'
    UNION ALL SELECT 'Thịt kho tàu',         'fatty'
    UNION ALL SELECT 'Canh chua cá lóc',     'sour'
    UNION ALL SELECT 'Canh chua cá lóc',     'light'
    UNION ALL SELECT 'Canh bí đao',          'light'
    UNION ALL SELECT 'Canh bí đao',          'low_sodium'
    UNION ALL SELECT 'Canh bí đao',          'vegetarian'
    UNION ALL SELECT 'Nem rán',              'fatty'
    UNION ALL SELECT 'Nem rán',              'contains_egg'
    UNION ALL SELECT 'Rau muống luộc',       'light'
    UNION ALL SELECT 'Rau muống luộc',       'high_fiber'
    UNION ALL SELECT 'Rau muống luộc',       'vegan'
    UNION ALL SELECT 'Rau muống luộc',       'vegetarian'
    UNION ALL SELECT 'Rau muống luộc',       'low_sodium'
    UNION ALL SELECT 'Gỏi ngó sen tôm thịt', 'contains_seafood'
    UNION ALL SELECT 'Gỏi ngó sen tôm thịt', 'sour'
    UNION ALL SELECT 'Sữa chua nếp cẩm',     'sweet'
    UNION ALL SELECT 'Sữa chua nếp cẩm',     'contains_dairy'
) v
JOIN foods f ON f.name = v.fname
JOIN tags  t ON t.code = v.tcode;
