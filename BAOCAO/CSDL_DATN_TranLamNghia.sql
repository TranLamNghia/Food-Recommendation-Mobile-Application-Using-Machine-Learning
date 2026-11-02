-- ════════════════════════════════════════════════════════════════
-- Cơ sở dữ liệu `nutrition_rec`
-- Ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa
-- Sinh viên: Trần Lâm Nghĩa — 22115053122231
--
-- Tệp này được SINH TỰ ĐỘNG từ mô hình ERD trong BAOCAO/Diagram.mdj
-- bằng tools/baocao/xuat_sql_tu_erd.py. Sửa sơ đồ rồi chạy lại,
-- đừng sửa tay vào đây.
-- Ngày sinh tệp: 02/11/2026
--
-- 22 bảng · 211 cột · 29 khóa ngoại · 0 dòng dữ liệu
-- Trong đó 2 cột là cột DẪN XUẤT, không lưu dữ liệu:
--   health_profiles.bmi              = cân nặng / bình phương chiều cao
--   meal_plans.calorie_deviation_pct = % lệch so với hạn mức năng lượng
-- Cả hai khai VIRTUAL: MySQL không ghi byte nào xuống đĩa, chỉ tính
-- lại lúc đọc. Không có dư thừa lưu trữ nên không sinh dị thường
-- cập nhật — thứ mà dạng chuẩn 3 đặt ra để ngăn.
--
-- Khóa `rda_reference.uq_rda` đi qua COALESCE ngay trong khóa (khóa
-- hàm, MySQL 8.0.13+): MySQL coi mọi NULL là khác nhau, nên khóa đi
-- thẳng qua `qualifier` sẽ không chặn trùng ở những dòng để trống.
--
-- Quy ước bù cho những gì sơ đồ ERD không ghi được:
--   CHAR -> CHAR(36) · VARCHAR -> VARCHAR(255)
--   DECIMAL -> DECIMAL(10,2) · BIT -> BIT(1)
--   Khóa chính: bảng danh mục dùng INT AUTO_INCREMENT cho dễ đọc,
--   các bảng còn lại dùng CHAR(36) DEFAULT (UUID()).
-- ════════════════════════════════════════════════════════════════

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP DATABASE IF EXISTS nutrition_rec;
CREATE DATABASE nutrition_rec
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;
USE nutrition_rec;

-- ──────────────────────────────────────────────────────────────────────
-- conditions  (bảng gốc)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE conditions (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name_vi         VARCHAR(255) NOT NULL,
    condition_type  ENUM('disease','allergy','intolerance','diet') NOT NULL,
    description     VARCHAR(255) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_conditions_name_vi (name_vi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- food_categories  (bảng gốc)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE food_categories (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name         VARCHAR(255) NOT NULL,
    description  VARCHAR(255) NULL,
    icon_url     VARCHAR(255) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_food_categories_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- ml_models  (bảng gốc)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE ml_models (
    id                  CHAR(36) NOT NULL DEFAULT (UUID()),
    version             VARCHAR(255) NOT NULL,
    algorithm           ENUM('logistic_regression','random_forest','gradient_boosting') NOT NULL,
    feature_version     VARCHAR(255) NOT NULL,
    dataset_version     VARCHAR(255) NOT NULL,
    hyperparams         JSON NULL,
    scaler_params       JSON NULL,
    feature_importance  JSON NULL,
    n_train             INT NOT NULL,
    n_test              INT NOT NULL,
    artifact_path       VARCHAR(255) NOT NULL,
    is_active           BIT(1) NOT NULL,
    trained_at          DATETIME NOT NULL,
    note                VARCHAR(255) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ml_models_version (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- rda_reference  (bảng gốc)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE rda_reference (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    gender     ENUM('male','female','all') NOT NULL,
    age_min    TINYINT NOT NULL,
    age_max    TINYINT NOT NULL,
    nutrient   ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g','sugar_g','sodium_mg','cholesterol_mg','purine_mg','calcium_mg','iron_mg','zinc_mg','vitamin_a_mcg','vitamin_c_mg') NOT NULL,
    qualifier  VARCHAR(255) NULL,
    rda_value  DECIMAL(10,2) NOT NULL,
    unit       VARCHAR(255) NOT NULL,
    source     VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_rda (gender, age_min, age_max, nutrient, (COALESCE(qualifier, '')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- tags  (bảng gốc)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE tags (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name_vi      VARCHAR(255) NOT NULL,
    tag_type     ENUM('allergen','diet','nutrition') NOT NULL,
    description  VARCHAR(255) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tags_name_vi (name_vi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- users  (bảng gốc)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id                       CHAR(36) NOT NULL DEFAULT (UUID()),
    email                    VARCHAR(255) NOT NULL,
    role                     ENUM('user','admin') NOT NULL,
    is_active                BIT(1) NOT NULL,
    password_hash            VARCHAR(255) NOT NULL,
    display_name             VARCHAR(255) NOT NULL,
    avatar_url               VARCHAR(255) NULL,
    onboarding_completed_at  DATETIME NULL,
    created_at               DATETIME NOT NULL,
    updated_at               DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- body_logs  (phụ thuộc: users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE body_logs (
    id          CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id     CHAR(36) NOT NULL,
    logged_on   DATE NOT NULL,
    weight_kg   DECIMAL(10,2) NOT NULL,
    note        VARCHAR(255) NULL,
    created_at  DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- condition_rules  (phụ thuộc: conditions, tags)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE condition_rules (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    condition_id  INT UNSIGNED NOT NULL,
    rule_type     ENUM('exclude_tag','require_tag','nutrient_limit') NOT NULL,
    tag_id        INT UNSIGNED NULL,
    nutrient      ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g','sugar_g','sodium_mg','cholesterol_mg','purine_mg','calcium_mg','iron_mg','zinc_mg','vitamin_a_mcg','vitamin_c_mg') NULL,
    comparator    ENUM('lte','gte') NULL,
    threshold     DECIMAL(10,2) NULL,
    scope         ENUM('per_serving','per_meal','per_day') NOT NULL,
    severity_min  ENUM('mild','moderate','severe') NOT NULL,
    is_hard       BIT(1) NOT NULL,
    penalty       DECIMAL(10,2) NULL,
    note          VARCHAR(255) NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (condition_id) REFERENCES conditions(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- foods  (phụ thuộc: food_categories, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE foods (
    id                CHAR(36) NOT NULL DEFAULT (UUID()),
    category_id       INT UNSIGNED NOT NULL,
    name              VARCHAR(255) NOT NULL,
    description       TEXT NULL,
    image_url         VARCHAR(255) NULL,
    spice_level       TINYINT NOT NULL,
    dish_role         ENUM('main','side_protein','side_veg','soup','snack','dessert','drink') NOT NULL,
    popularity_score  DECIMAL(10,2) NOT NULL,
    is_active         BIT(1) NOT NULL,
    owner_id          CHAR(36) NULL,
    created_at        DATETIME NOT NULL,
    updated_at        DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (category_id) REFERENCES food_categories(id),
    FOREIGN KEY (owner_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- health_profiles  (phụ thuộc: users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE health_profiles (
    id                     CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id                CHAR(36) NOT NULL,
    gender                 ENUM('male','female','other') NOT NULL,
    date_of_birth          DATE NOT NULL,
    height_cm              DECIMAL(10,2) NOT NULL,
    weight_kg              DECIMAL(10,2) NOT NULL,
    bmi                    DECIMAL(10,2) GENERATED ALWAYS AS (weight_kg / ((height_cm / 100) * (height_cm / 100))) VIRTUAL NULL,
    activity_level         ENUM('sedentary','light','moderate','active','very_active') NOT NULL,
    goal                   ENUM('lose_weight','maintain','gain_weight','healthy_eating') NOT NULL,
    bmr_kcal               SMALLINT NULL,
    tdee_kcal              SMALLINT NULL,
    daily_calories_target  SMALLINT NULL,
    target_protein_pct     TINYINT NOT NULL,
    target_carbs_pct       TINYINT NOT NULL,
    target_fat_pct         TINYINT NOT NULL,
    created_at             DATETIME NOT NULL,
    updated_at             DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_health_profiles_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- meal_plans  (phụ thuộc: ml_models, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE meal_plans (
    id                      CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id                 CHAR(36) NOT NULL,
    plan_date               DATE NOT NULL,
    target_calories_kcal    SMALLINT NOT NULL,
    target_protein_g        DECIMAL(10,2) NOT NULL,
    target_carbs_g          DECIMAL(10,2) NOT NULL,
    target_fat_g            DECIMAL(10,2) NOT NULL,
    actual_calories_kcal    DECIMAL(10,2) NULL,
    actual_protein_g        DECIMAL(10,2) NULL,
    actual_carbs_g          DECIMAL(10,2) NULL,
    actual_fat_g            DECIMAL(10,2) NULL,
    calorie_deviation_pct   DECIMAL(10,2) GENERATED ALWAYS AS (100 * (actual_calories_kcal - target_calories_kcal) / target_calories_kcal) VIRTUAL NULL,
    total_preference_score  DECIMAL(10,2) NULL,
    exploration_ratio       DECIMAL(10,2) NULL,
    generation_source       ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id                CHAR(36) NULL,
    status                  ENUM('draft','active','completed') NOT NULL,
    generated_at            DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (model_id) REFERENCES ml_models(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- ml_evaluations  (phụ thuộc: ml_models)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE ml_evaluations (
    id            CHAR(36) NOT NULL DEFAULT (UUID()),
    model_id      CHAR(36) NOT NULL,
    variant       ENUM('ml','content_based','rule_based','popularity','hybrid') NOT NULL,
    metric        ENUM('precision','recall','ndcg','map','mae','rmse','f1','auc') NOT NULL,
    k_value       TINYINT NOT NULL,
    value         DECIMAL(10,2) NOT NULL,
    fold          TINYINT NOT NULL,
    evaluated_at  DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (model_id) REFERENCES ml_models(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- user_conditions  (phụ thuộc: conditions, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE user_conditions (
    id            CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id       CHAR(36) NOT NULL,
    condition_id  INT UNSIGNED NOT NULL,
    severity      ENUM('mild','moderate','severe') NOT NULL,
    note          VARCHAR(255) NULL,
    created_at    DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (condition_id) REFERENCES conditions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- user_preference_profiles  (phụ thuộc: users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE user_preference_profiles (
    user_id          CHAR(36) NOT NULL,
    feature_version  VARCHAR(255) NOT NULL,
    weights          JSON NOT NULL,
    sum_abs_weight   DECIMAL(10,2) NOT NULL,
    n_signals        INT NOT NULL,
    stage            ENUM('cold','content','hybrid','ml') NOT NULL,
    alpha            DECIMAL(10,2) NOT NULL,
    updated_at       DATETIME NOT NULL,
    PRIMARY KEY (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- feedbacks  (phụ thuộc: foods, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE feedbacks (
    id          CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id     CHAR(36) NOT NULL,
    food_id     CHAR(36) NOT NULL,
    rating      TINYINT NOT NULL,
    comment     TEXT NULL,
    created_at  DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (food_id) REFERENCES foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- food_diary  (phụ thuộc: foods, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE food_diary (
    id                  CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id             CHAR(36) NOT NULL,
    food_id             CHAR(36) NOT NULL,
    ate_on              DATE NOT NULL,
    meal_type           ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    portion_multiplier  DECIMAL(10,2) NOT NULL,
    created_at          DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (food_id) REFERENCES foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- food_nutrition  (phụ thuộc: foods)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE food_nutrition (
    id              CHAR(36) NOT NULL DEFAULT (UUID()),
    food_id         CHAR(36) NOT NULL,
    serving_size_g  SMALLINT NOT NULL,
    calories_kcal   DECIMAL(10,2) NOT NULL,
    protein_g       DECIMAL(10,2) NOT NULL,
    carbs_g         DECIMAL(10,2) NOT NULL,
    fat_g           DECIMAL(10,2) NOT NULL,
    fiber_g         DECIMAL(10,2) NULL,
    sugar_g         DECIMAL(10,2) NULL,
    sodium_mg       DECIMAL(10,2) NULL,
    cholesterol_mg  DECIMAL(10,2) NULL,
    purine_mg       DECIMAL(10,2) NULL,
    calcium_mg      DECIMAL(10,2) NULL,
    iron_mg         DECIMAL(10,2) NULL,
    zinc_mg         DECIMAL(10,2) NULL,
    vitamin_a_mcg   DECIMAL(10,2) NULL,
    vitamin_c_mg    DECIMAL(10,2) NULL,
    updated_at      DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_food_nutrition_food_id (food_id),
    FOREIGN KEY (food_id) REFERENCES foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- food_tags  (phụ thuộc: foods, tags)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE food_tags (
    food_id  CHAR(36) NOT NULL,
    tag_id   INT UNSIGNED NOT NULL,
    PRIMARY KEY (food_id, tag_id),
    FOREIGN KEY (food_id) REFERENCES foods(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- interactions  (phụ thuộc: foods, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE interactions (
    id             CHAR(36) NOT NULL DEFAULT (UUID()),
    user_id        CHAR(36) NOT NULL,
    food_id        CHAR(36) NOT NULL,
    action         ENUM('like','dislike','neutral','unknown') NOT NULL,
    session_id     CHAR(36) NOT NULL,
    interacted_at  DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (food_id) REFERENCES foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- meal_plan_items  (phụ thuộc: foods, meal_plans)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE meal_plan_items (
    id                   CHAR(36) NOT NULL DEFAULT (UUID()),
    meal_plan_id         CHAR(36) NOT NULL,
    food_id              CHAR(36) NOT NULL,
    meal_type            ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    portion_multiplier   DECIMAL(10,2) NOT NULL,
    predicted_score      DECIMAL(10,2) NULL,
    status               ENUM('suggested','kept','replaced','eaten','skipped') NOT NULL,
    replaced_by_food_id  CHAR(36) NULL,
    replaced_at          DATETIME NULL,
    exploration_delta    DECIMAL(10,2) NULL,
    position             TINYINT NULL,
    note                 VARCHAR(255) NULL,
    created_at           DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id),
    FOREIGN KEY (food_id) REFERENCES foods(id),
    FOREIGN KEY (replaced_by_food_id) REFERENCES foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- ml_training_samples  (phụ thuộc: foods, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE ml_training_samples (
    id                 CHAR(36) NOT NULL DEFAULT (UUID()),
    dataset_version    VARCHAR(255) NOT NULL,
    user_id            CHAR(36) NOT NULL,
    food_id            CHAR(36) NOT NULL,
    label              DECIMAL(10,2) NOT NULL,
    sample_weight      DECIMAL(10,2) NOT NULL,
    source             ENUM('feedback','swipe','diary','plan_kept','plan_replaced','plan_skipped','random_neg') NOT NULL,
    context_meal_type  ENUM('breakfast','lunch','dinner','snack') NULL,
    split              ENUM('train','val','test') NOT NULL,
    fold               TINYINT NULL,
    collected_at       DATETIME NOT NULL,
    profile_snapshot   JSON NULL,
    created_at         DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (food_id) REFERENCES foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ──────────────────────────────────────────────────────────────────────
-- recommendations  (phụ thuộc: foods, ml_models, users)
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE recommendations (
    id                 CHAR(36) NOT NULL DEFAULT (UUID()),
    batch_id           CHAR(36) NOT NULL,
    user_id            CHAR(36) NOT NULL,
    food_id            CHAR(36) NOT NULL,
    context_meal_type  ENUM('breakfast','lunch','dinner','snack') NULL,
    score              DECIMAL(10,2) NOT NULL,
    score_content      DECIMAL(10,2) NULL,
    score_ml           DECIMAL(10,2) NULL,
    alpha              DECIMAL(10,2) NULL,
    rank_position      SMALLINT NULL,
    source             ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id           CHAR(36) NULL,
    was_selected       TINYINT NOT NULL,
    recommended_at     DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (food_id) REFERENCES foods(id),
    FOREIGN KEY (model_id) REFERENCES ml_models(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
