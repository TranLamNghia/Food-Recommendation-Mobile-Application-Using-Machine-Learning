-- ═══════════════════════════════════════════════════════════════════════════
--  CSDL — Ứng dụng khuyến nghị thực đơn dinh dưỡng cá nhân hóa
--  Đồ án tốt nghiệp — Trần Lâm Nghĩa (22115053122231)
--
--  MySQL 8.x · InnoDB · utf8mb4_unicode_ci
--  21 bảng · 28 khóa ngoại
--
--  Thiết kế chi tiết: docs/DATABASE_DESIGN.md
--  Thứ tự tạo bảng theo 4 tầng phụ thuộc (Mục 2.1)
-- ═══════════════════════════════════════════════════════════════════════════

DROP DATABASE IF EXISTS nutrition_rec;
CREATE DATABASE nutrition_rec
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
USE nutrition_rec;


-- ╔═════════════════════════════════════════════════════════════════════════╗
-- ║  TẦNG 0 — Không phụ thuộc bảng nào                                      ║
-- ╚═════════════════════════════════════════════════════════════════════════╝

-- ── users ─────────────────────────────────────────────────────────────────
-- Không có cột `role`   : hệ thống không có ứng dụng quản trị.
-- Không có cột `is_active`: không có nghiệp vụ khóa tài khoản.
CREATE TABLE users (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    password_hash           VARCHAR(255) NOT NULL,
    display_name            VARCHAR(100) NOT NULL,
    avatar_url              VARCHAR(500) NULL,
    -- NULL = chưa hoàn tất phiên vuốt thăm dò -> còn ở Giai đoạn 0
    onboarding_completed_at DATETIME     NULL,
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;


-- ── conditions ────────────────────────────────────────────────────────────
-- Từ điển bệnh lý / dị ứng / chế độ ăn. Bảng cha của condition_rules.
CREATE TABLE conditions (
    id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code           VARCHAR(50)  NOT NULL UNIQUE,
    name_vi        VARCHAR(100) NOT NULL,
    condition_type ENUM('disease','allergy','intolerance','diet') NOT NULL,
    description    VARCHAR(255) NULL
) ENGINE=InnoDB;


-- ── food_categories ───────────────────────────────────────────────────────
-- Giữ ở mức 10-15 danh mục: mã hóa one-hot cho ML, nhiều quá sẽ làm vector thưa.
CREATE TABLE food_categories (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    icon_url    VARCHAR(500) NULL
) ENGINE=InnoDB;


-- ── tags ──────────────────────────────────────────────────────────────────
-- Từ vựng có kiểm soát. Tránh 'low_sugar' / 'low-sugar' thành 2 cột one-hot.
CREATE TABLE tags (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    name_vi     VARCHAR(100) NOT NULL,
    tag_type    ENUM('allergen','diet','nutrition','taste') NOT NULL,
    description VARCHAR(255) NULL,
    INDEX idx_tag_type (tag_type)
) ENGINE=InnoDB;


-- ── rda_reference ─────────────────────────────────────────────────────────
-- Bảng tra cứu tĩnh, nạp từ NIN Vietnamese RDAs 2016.
CREATE TABLE rda_reference (
    id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    gender    ENUM('male','female','all') NOT NULL,
    age_min   TINYINT UNSIGNED NOT NULL,
    age_max   TINYINT UNSIGNED NOT NULL,
    nutrient  VARCHAR(30)  NOT NULL,
    rda_value DECIMAL(8,2) NOT NULL,
    unit      VARCHAR(10)  NOT NULL,
    source    VARCHAR(150) NOT NULL DEFAULT 'NIN Vietnamese RDAs 2016',

    UNIQUE KEY uq_rda    (gender, age_min, age_max, nutrient),
    INDEX     idx_lookup (gender, age_min, age_max)
) ENGINE=InnoDB;


-- ── ml_models ─────────────────────────────────────────────────────────────
-- Sổ đăng ký mô hình. recommendations.model_id và meal_plans.model_id trỏ vào đây.
CREATE TABLE ml_models (
    id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    version            VARCHAR(20) NOT NULL UNIQUE,
    algorithm          ENUM('logistic_regression','random_forest',
                            'gradient_boosting') NOT NULL,
    feature_version    VARCHAR(20) NOT NULL,
    dataset_version    VARCHAR(20) NOT NULL,

    hyperparams        JSON NULL,
    -- BẮT BUỘC: tham số chuẩn hóa đóng băng lúc train.
    -- Tính lại min/max lúc serving sẽ khiến mô hình dự đoán sai mà không báo lỗi.
    scaler_params      JSON NULL,
    feature_importance JSON NULL,

    n_train            INT UNSIGNED NOT NULL,
    n_test             INT UNSIGNED NOT NULL,
    -- Đường dẫn file .joblib trên đĩa. Không lưu mô hình dạng BLOB trong CSDL.
    artifact_path      VARCHAR(500) NOT NULL,
    is_active          TINYINT(1)   NOT NULL DEFAULT 0,
    trained_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note               VARCHAR(255) NULL,

    INDEX idx_active (is_active)
) ENGINE=InnoDB;


-- ╔═════════════════════════════════════════════════════════════════════════╗
-- ║  TẦNG 1                                                                 ║
-- ╚═════════════════════════════════════════════════════════════════════════╝

-- ── health_profiles ───────────────────────────────────────────────────────
CREATE TABLE health_profiles (
    id                    BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id               BIGINT UNSIGNED NOT NULL UNIQUE,
    gender                ENUM('male','female','other') NOT NULL,
    date_of_birth         DATE         NOT NULL,
    height_cm             DECIMAL(5,2) NOT NULL,
    weight_kg             DECIMAL(5,2) NOT NULL,
    bmi                   DECIMAL(5,2) GENERATED ALWAYS AS
                              (weight_kg / ((height_cm / 100) * (height_cm / 100))) STORED,
    activity_level        ENUM('sedentary','light','moderate','active','very_active')
                              NOT NULL DEFAULT 'moderate',
    goal                  ENUM('lose_weight','maintain','gain_weight','healthy_eating')
                              NOT NULL DEFAULT 'maintain',

    -- ══ Đầu ra Bước 1 — chụp lại để thực đơn cũ giữ đúng hạn mức cũ ══
    bmr_kcal              SMALLINT UNSIGNED NULL,
    tdee_kcal             SMALLINT UNSIGNED NULL,
    daily_calories_target SMALLINT UNSIGNED NULL,
    target_protein_pct    TINYINT UNSIGNED NOT NULL DEFAULT 15,
    target_carbs_pct      TINYINT UNSIGNED NOT NULL DEFAULT 60,
    target_fat_pct        TINYINT UNSIGNED NOT NULL DEFAULT 25,
    computed_at           DATETIME     NULL,

    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,

    -- chk_height chặn luôn lỗi chia cho 0 ở cột bmi
    CONSTRAINT chk_height    CHECK (height_cm BETWEEN 50 AND 250),
    CONSTRAINT chk_weight    CHECK (weight_kg BETWEEN 20 AND 300),
    CONSTRAINT chk_macro_sum CHECK (target_protein_pct + target_carbs_pct
                                    + target_fat_pct = 100),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ── user_conditions ───────────────────────────────────────────────────────
CREATE TABLE user_conditions (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id      BIGINT UNSIGNED NOT NULL,
    condition_id INT UNSIGNED    NOT NULL,
    severity     ENUM('mild','moderate','severe') NOT NULL DEFAULT 'moderate',
    note         VARCHAR(255) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)      REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (condition_id) REFERENCES conditions(id),
    UNIQUE KEY uq_user_condition (user_id, condition_id)
) ENGINE=InnoDB;


-- ── foods ─────────────────────────────────────────────────────────────────
-- is_active GIỮ LẠI (khác users.is_active): ẩn món khỏi gợi ý mà không xóa
-- dữ liệu. Xóa cứng sẽ CASCADE mất lịch sử tương tác và mẫu huấn luyện.
CREATE TABLE foods (
    id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    category_id      INT UNSIGNED NOT NULL,
    name             VARCHAR(200) NOT NULL,
    description      TEXT         NULL,
    image_url        VARCHAR(500) NULL,
    origin           VARCHAR(100) NULL,

    -- ══ Đặc trưng cho vector ML (đề cương nêu đích danh) ══
    cooking_method   ENUM('luoc','hap','xao','chien','nuong','kho',
                          'nau_canh','tron','song','khac')
                         NOT NULL DEFAULT 'khac',
    spice_level      TINYINT UNSIGNED NOT NULL DEFAULT 0,
    -- dish_role: Bước 4 dùng để bảo đảm cấu trúc bữa ăn hợp lý,
    -- tránh chọn ra 3 món tráng miệng vì cả 3 đều điểm cao.
    dish_role        ENUM('main','side','soup','dessert','drink')
                         NOT NULL DEFAULT 'main',
    suitable_meals   SET('breakfast','lunch','dinner','snack')
                         NOT NULL DEFAULT 'breakfast,lunch,dinner,snack',

    -- Bộ đệm độ phổ biến, tính lại định kỳ. Dùng chấm điểm ở Giai đoạn 0.
    popularity_score DECIMAL(5,4) NOT NULL DEFAULT 0,
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_spice CHECK (spice_level BETWEEN 0 AND 3),
    FOREIGN KEY (category_id) REFERENCES food_categories(id),
    INDEX idx_active_category (is_active, category_id),
    INDEX idx_dish_role       (dish_role)
) ENGINE=InnoDB;


-- ── condition_rules ───────────────────────────────────────────────────────
-- BỘ QUY TẮC F1 DƯỚI DẠNG DỮ LIỆU.
-- Vừa là sản phẩm phải nộp theo đề cương, vừa là phương án đối chứng
-- (variant = 'rule_based') khi so sánh với học máy ở Chương 3.
CREATE TABLE condition_rules (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    condition_id INT UNSIGNED NOT NULL,
    rule_type    ENUM('exclude_tag','require_tag','nutrient_limit') NOT NULL,

    -- rule_type = 'exclude_tag' | 'require_tag'
    tag_id       INT UNSIGNED NULL,

    -- rule_type = 'nutrient_limit'
    nutrient     ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g',
                      'sugar_g','sodium_mg','cholesterol_mg','purine_mg') NULL,
    comparator   ENUM('lte','gte') NULL,
    threshold    DECIMAL(8,2) NULL,
    -- per_serving lọc được ở Bước 2; per_meal / per_day chỉ kiểm tra được
    -- ở Bước 4 khi đã biết tổ hợp món cụ thể.
    scope        ENUM('per_serving','per_meal','per_day') NOT NULL DEFAULT 'per_serving',

    severity_min ENUM('mild','moderate','severe') NOT NULL DEFAULT 'mild',
    -- is_hard = 1 -> loại bỏ ở Bước 2;  = 0 -> trừ điểm ở Bước 3
    is_hard      TINYINT(1)   NOT NULL DEFAULT 1,
    penalty      DECIMAL(4,3) NULL,
    note         VARCHAR(255) NULL,

    FOREIGN KEY (condition_id) REFERENCES conditions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)       REFERENCES tags(id),
    INDEX idx_condition (condition_id)
) ENGINE=InnoDB;


-- ── user_preference_profiles ──────────────────────────────────────────────
-- Hồ sơ sở thích dạng vector trọng số (thuật toán Rocchio).
CREATE TABLE user_preference_profiles (
    user_id         BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    feature_version VARCHAR(20)   NOT NULL,
    -- weights = vector p_u, dạng {"protein_g":0.31,"taste_spicy":-0.44,...}
    weights         JSON          NOT NULL,
    -- sum_abs_weight = W = Σ|w|. BẮT BUỘC để cập nhật tăng dần:
    --   S_cũ = weights × W  ->  S_mới = S_cũ + w_mới·v_mới  ->  weights = S_mới / W_mới
    -- Không có W thì mỗi lượt vuốt phải quét lại toàn bộ interactions.
    sum_abs_weight  DECIMAL(10,4) NOT NULL DEFAULT 0,
    n_signals       INT UNSIGNED  NOT NULL DEFAULT 0,
    stage           ENUM('cold','content','hybrid','ml') NOT NULL DEFAULT 'cold',
    alpha           DECIMAL(4,3)  NOT NULL DEFAULT 0,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ╔═════════════════════════════════════════════════════════════════════════╗
-- ║  TẦNG 2                                                                 ║
-- ╚═════════════════════════════════════════════════════════════════════════╝

-- ── food_nutrition ────────────────────────────────────────────────────────
-- 4 trường macro BẮT BUỘC (thiếu thì Bước 4 không chạy được).
-- Vi chất cho phép NULL — trung thực với thực tế thu thập dữ liệu món Việt.
CREATE TABLE food_nutrition (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id         BIGINT UNSIGNED NOT NULL UNIQUE,
    serving_size_g  SMALLINT UNSIGNED NOT NULL DEFAULT 100,

    calories_kcal   DECIMAL(7,2) NOT NULL,
    protein_g       DECIMAL(6,2) NOT NULL DEFAULT 0,
    carbs_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    fat_g           DECIMAL(6,2) NOT NULL DEFAULT 0,

    fiber_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    sugar_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    sodium_mg       DECIMAL(7,2) NOT NULL DEFAULT 0,
    cholesterol_mg  DECIMAL(7,2) NOT NULL DEFAULT 0,
    purine_mg       DECIMAL(7,2) NULL,

    calcium_mg      DECIMAL(7,2) NULL,
    iron_mg         DECIMAL(6,2) NULL,
    zinc_mg         DECIMAL(6,2) NULL,
    vitamin_a_mcg   DECIMAL(7,2) NULL,
    vitamin_c_mg    DECIMAL(6,2) NULL,

    -- Truy xuất nguồn: hội đồng thường hỏi số liệu dinh dưỡng lấy ở đâu
    data_source     VARCHAR(150) NULL,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ── food_tags ─────────────────────────────────────────────────────────────
CREATE TABLE food_tags (
    food_id BIGINT UNSIGNED NOT NULL,
    tag_id  INT UNSIGNED    NOT NULL,

    PRIMARY KEY (food_id, tag_id),
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)  REFERENCES tags(id),
    -- idx_tag: Bộ lọc F1 truy ngược từ nhãn ra món
    INDEX idx_tag (tag_id)
) ENGINE=InnoDB;


-- ── meal_plans ────────────────────────────────────────────────────────────
CREATE TABLE meal_plans (
    id                     BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id                BIGINT UNSIGNED NOT NULL,
    plan_date              DATE NOT NULL,

    -- ══ Hạn mức từ Bước 1, chụp lại tại thời điểm sinh thực đơn ══
    target_calories_kcal   SMALLINT UNSIGNED NOT NULL,
    target_protein_g       DECIMAL(6,2) NOT NULL,
    target_carbs_g         DECIMAL(6,2) NOT NULL,
    target_fat_g           DECIMAL(6,2) NOT NULL,

    -- ══ Kết quả thực tế của tổ hợp Bước 4 ══
    -- NULL = chưa chạy xong Bước 4.
    -- TUYỆT ĐỐI KHÔNG dùng DEFAULT 0: số 0 là giá trị hợp lệ về mặt số học,
    -- sẽ khiến calorie_deviation_pct tính ra −100% ngay khi vừa tạo dòng.
    actual_calories_kcal   DECIMAL(7,2) NULL,
    actual_protein_g       DECIMAL(6,2) NULL,
    actual_carbs_g         DECIMAL(6,2) NULL,
    actual_fat_g           DECIMAL(6,2) NULL,

    -- Đề cương yêu cầu chứng minh sai lệch ≤ 10% — đây là chỗ lấy con số đó
    calorie_deviation_pct  DECIMAL(6,2) GENERATED ALWAYS AS
        (100 * (actual_calories_kcal - target_calories_kcal)
             / target_calories_kcal) STORED,

    total_preference_score DECIMAL(8,4) NULL,
    generation_source      ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id               INT UNSIGNED NULL,
    status                 ENUM('draft','active','completed') NOT NULL DEFAULT 'active',
    generated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_target_positive CHECK (target_calories_kcal > 0),
    FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ml_models(id) ON DELETE SET NULL,

    UNIQUE KEY uq_user_date (user_id, plan_date),
    INDEX     idx_source    (generation_source)
) ENGINE=InnoDB;


-- ── recommendations ───────────────────────────────────────────────────────
CREATE TABLE recommendations (
    id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    -- batch_id nhóm toàn bộ món trong MỘT lần gợi ý -> bắt buộc để tính @K
    batch_id          CHAR(36) NOT NULL,
    user_id           BIGINT UNSIGNED NOT NULL,
    food_id           BIGINT UNSIGNED NOT NULL,
    context_meal_type ENUM('breakfast','lunch','dinner','snack') NULL,

    -- Tách 3 thành phần của công thức trộn để phân tích ngược được:
    --   score = alpha * score_ml + (1 - alpha) * score_content
    score             DECIMAL(6,4) NOT NULL,
    score_content     DECIMAL(6,4) NULL,
    score_ml          DECIMAL(6,4) NULL,
    alpha             DECIMAL(4,3) NULL,

    rank_position     SMALLINT UNSIGNED NULL,
    source            ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id          INT UNSIGNED NULL,

    -- was_interacted = mỏ mẫu âm cho ML. Không có mẫu âm thì mô hình
    -- sẽ học ra "món nào cũng thích".
    was_interacted    TINYINT(1) NOT NULL DEFAULT 0,
    was_selected      TINYINT(1) NOT NULL DEFAULT 0,
    recommended_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id)  REFERENCES foods(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ml_models(id) ON DELETE SET NULL,

    INDEX idx_user_time (user_id, recommended_at),
    INDEX idx_batch     (batch_id),
    INDEX idx_source    (source)
) ENGINE=InnoDB;


-- ── food_diary ────────────────────────────────────────────────────────────
-- KHÔNG có cột meal_plan_item_id: cột đó cho phép NULL (người dùng ăn cả món
-- ngoài thực đơn) nên tạo ra đường đi vòng tới foods và users.
-- Tỷ lệ tuân thủ thực đơn tính bằng ghép khóa tự nhiên qua idx_compliance.
CREATE TABLE food_diary (
    id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT UNSIGNED NOT NULL,
    food_id        BIGINT UNSIGNED NOT NULL,
    ate_on         DATE NOT NULL,
    meal_type      ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    serving_size_g SMALLINT UNSIGNED NOT NULL DEFAULT 100,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id),

    -- Thứ tự 4 cột khớp đúng mệnh đề ON của truy vấn tỷ lệ tuân thủ (Mục 8.4)
    INDEX idx_compliance (user_id, ate_on, meal_type, food_id),
    -- Bước 2: loại món đã ăn trong N ngày gần đây
    INDEX idx_user_food  (user_id, food_id, ate_on)
) ENGINE=InnoDB;


-- ── feedbacks ─────────────────────────────────────────────────────────────
-- KHÔNG có food_diary_id (đường đi vòng) và KHÔNG có ate_at (trùng food_diary).
-- Đánh giá là ý kiến về MÓN ĂN, không phải về một LẦN ĂN cụ thể.
CREATE TABLE feedbacks (
    id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT UNSIGNED NOT NULL,
    food_id    BIGINT UNSIGNED NOT NULL,
    rating     TINYINT UNSIGNED NOT NULL,
    comment    TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_rating CHECK (rating BETWEEN 1 AND 5),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    INDEX idx_user        (user_id),
    INDEX idx_food_rating (food_id, rating)
) ENGINE=InnoDB;


-- ── ml_training_samples ───────────────────────────────────────────────────
-- Tập dữ liệu ĐÃ ĐÓNG BĂNG. Không tính nhãn trực tiếp từ bảng gốc lúc train,
-- nếu không thì mỗi lần chạy lại con số Precision@K trong báo cáo sẽ khác.
CREATE TABLE ml_training_samples (
    id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    dataset_version  VARCHAR(20) NOT NULL,
    user_id          BIGINT UNSIGNED NOT NULL,
    food_id          BIGINT UNSIGNED NOT NULL,

    label            DECIMAL(4,3) NOT NULL,
    sample_weight    DECIMAL(4,3) NOT NULL DEFAULT 1.000,
    source           ENUM('feedback','swipe_onboarding','swipe_explore','diary',
                          'plan_kept','plan_replaced','impression_neg','random_neg')
                         NOT NULL,

    context_meal_type ENUM('breakfast','lunch','dinner','snack') NULL,
    split            ENUM('train','val','test') NOT NULL,
    fold             TINYINT UNSIGNED NULL,
    -- collected_at = thời điểm tín hiệu GỐC phát sinh -> chia tập theo thời gian.
    -- Chia ngẫu nhiên gây rò rỉ dữ liệu trong hệ có vòng lặp phản hồi.
    collected_at     DATETIME NOT NULL,
    -- Chống rò rỉ: hồ sơ người dùng TẠI LÚC ĐÓ, không phải hồ sơ hôm nay
    profile_snapshot JSON NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_label  CHECK (label         BETWEEN 0 AND 1),
    CONSTRAINT chk_weight CHECK (sample_weight BETWEEN 0 AND 1),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    INDEX idx_dataset_split (dataset_version, split),
    INDEX idx_dataset_user  (dataset_version, user_id),
    INDEX idx_collected     (collected_at)
) ENGINE=InnoDB;


-- ── ml_evaluations ────────────────────────────────────────────────────────
-- Cột `variant` là chìa khóa: chạy CÙNG một tập kiểm thử qua nhiều nhánh,
-- ghi mỗi nhánh một dòng -> một câu SELECT ra thẳng bảng so sánh Chương 3.
CREATE TABLE ml_evaluations (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    model_id     INT UNSIGNED NOT NULL,
    variant      ENUM('ml','content_based','rule_based','popularity','hybrid') NOT NULL,
    metric       ENUM('precision','recall','ndcg','map','mae','rmse','f1','auc') NOT NULL,
    k_value      TINYINT UNSIGNED NULL,
    value        DECIMAL(8,5) NOT NULL,
    -- fold IS NULL = kết quả trên tập kiểm thử cuối
    fold         TINYINT UNSIGNED NULL,
    evaluated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (model_id) REFERENCES ml_models(id) ON DELETE CASCADE,
    UNIQUE KEY uq_eval (model_id, variant, metric, k_value, fold)
) ENGINE=InnoDB;


-- ╔═════════════════════════════════════════════════════════════════════════╗
-- ║  TẦNG 3                                                                 ║
-- ╚═════════════════════════════════════════════════════════════════════════╝

-- ── meal_plan_items ───────────────────────────────────────────────────────
-- food_id và replaced_by_food_id cùng trỏ foods nhưng là HAI VAI TRÒ khác
-- nhau (món gợi ý / món đổi sang), không phải dư thừa dữ liệu.
CREATE TABLE meal_plan_items (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    meal_plan_id        BIGINT UNSIGNED NOT NULL,
    food_id             BIGINT UNSIGNED NOT NULL,
    meal_type           ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    serving_size_g      SMALLINT UNSIGNED NOT NULL DEFAULT 100,

    predicted_score     DECIMAL(6,4) NULL,
    -- status = nguồn phản hồi ngầm định mà đề cương gọi là
    -- "món được chọn, món bị thay thế"
    status              ENUM('suggested','kept','replaced','eaten','skipped')
                            NOT NULL DEFAULT 'suggested',
    replaced_by_food_id BIGINT UNSIGNED NULL,
    replaced_at         DATETIME NULL,
    -- Đánh dấu món do chiến lược thăm dò ε-greedy chèn vào
    is_exploration      TINYINT(1) NOT NULL DEFAULT 0,
    position            TINYINT UNSIGNED NULL,
    note                VARCHAR(255) NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (meal_plan_id)        REFERENCES meal_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id)             REFERENCES foods(id),
    FOREIGN KEY (replaced_by_food_id) REFERENCES foods(id),

    INDEX idx_plan_meal (meal_plan_id, meal_type),
    INDEX idx_status    (status)
) ENGINE=InnoDB;


-- ── interactions ──────────────────────────────────────────────────────────
-- DƯ THỪA CÓ KIỂM SOÁT — chỗ duy nhất còn lại trong lược đồ.
-- Khi recommendation_id khác NULL, user_id/food_id lặp lại thông tin đã có
-- ở recommendations. Không bỏ được cột nào:
--   - user_id/food_id      : recommendation_id cho phép NULL (vuốt onboarding)
--   - recommendation_id    : bắt buộc để tính Precision@K và NDCG
-- Bất biến Backend phải giữ khi recommendation_id IS NOT NULL:
--   interactions.user_id = recommendations.user_id
--   interactions.food_id = recommendations.food_id
CREATE TABLE interactions (
    id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id           BIGINT UNSIGNED NOT NULL,
    food_id           BIGINT UNSIGNED NOT NULL,
    action            ENUM('like','dislike','neutral','unknown') NOT NULL,

    session_type      ENUM('onboarding','explore') NOT NULL DEFAULT 'explore',
    session_id        CHAR(36) NULL,
    context_meal_type ENUM('breakfast','lunch','dinner','snack') NULL,
    recommendation_id BIGINT UNSIGNED NULL,

    interacted_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)           REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id)           REFERENCES foods(id) ON DELETE CASCADE,
    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id) ON DELETE SET NULL,

    -- KHÔNG đặt UNIQUE (user_id, food_id): người dùng vuốt lại cùng món ở
    -- thời điểm khác, lịch sử thay đổi khẩu vị chính là dữ liệu quý.
    INDEX idx_user_time      (user_id, interacted_at),
    INDEX idx_user_food      (user_id, food_id),
    INDEX idx_food           (food_id),
    INDEX idx_session        (session_id),
    INDEX idx_recommendation (recommendation_id)
) ENGINE=InnoDB;
