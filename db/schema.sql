-- ═══════════════════════════════════════════════════════════════════════════
--  CSDL — Ứng dụng khuyến nghị thực đơn dinh dưỡng cá nhân hóa
--  Đồ án tốt nghiệp — Trần Lâm Nghĩa (22115053122231)
--
--  MySQL 8.x · InnoDB · utf8mb4_unicode_ci
--  24 bảng · 32 khóa ngoại · 18 ràng buộc CHECK
--
--  LƯU Ý: trong MySQL 8, tên ràng buộc CHECK phải duy nhất trên TOÀN CSDL,
--  không phải trên từng bảng. Đặt trùng tên ở hai bảng khác nhau sẽ báo lỗi
--  "Duplicate check constraint name" ngay lúc tạo bảng.
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
-- Hệ thống có HAI giao diện: ứng dụng Android cho người dùng cuối, và trang
-- quản trị trên web. Cả hai dùng chung bảng này, phân biệt bằng `role`.
--
-- Không tách bảng `admins` riêng vì chỉ có đúng hai vai trò và không có phân
-- quyền chi tiết; tách ra sẽ sinh hai luồng xác thực, hai cơ chế đổi mật khẩu
-- và một thực thể nữa trong ERD mà không đổi lại được gì.
--
-- Tài khoản admin đơn giản là không có dòng trong health_profiles, không có
-- meal_plans, không có interactions. Mọi khóa ngoại đều cho phép điều đó.
CREATE TABLE users (
    id                      CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    role                    ENUM('user','admin') NOT NULL DEFAULT 'user',
    -- Khóa tài khoản: chỉ có nghĩa khi đã có trang quản trị để thao tác.
    -- XÓA MỀM. Đóng tài khoản thì đặt is_active = 0, KHÔNG dùng DELETE.
    --
    -- Lý do: khóa ngoại tới `users` của 11 bảng đều ON DELETE CASCADE, trong
    -- đó có `ml_training_samples`. Một lệnh DELETE sẽ gỡ mẫu huấn luyện ra
    -- khỏi một `dataset_version` ĐÃ ĐÓNG BĂNG, khiến `ml_models.n_train`
    -- không còn khớp dữ liệu và mọi kết quả trong `ml_evaluations` không tái
    -- lập được — đúng thứ Chương 3 dựa vào.
    --
    -- DELETE chỉ dành cho yêu cầu xóa dữ liệu thật sự của người dùng. Khi đó
    -- phải sinh lại một dataset_version mới, không sửa bản cũ.
    is_active               TINYINT(1)   NOT NULL DEFAULT 1,
    password_hash           VARCHAR(255) NOT NULL,
    display_name            VARCHAR(100) NOT NULL,
    avatar_url              VARCHAR(500) NULL,
    -- NULL = chưa hoàn tất phiên vuốt thăm dò -> còn ở Giai đoạn 0
    onboarding_completed_at DATETIME     NULL,
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_role (role, is_active)
) ENGINE=InnoDB;


-- ── conditions ────────────────────────────────────────────────────────────
-- Từ điển bệnh lý / dị ứng / chế độ ăn. Bảng cha của condition_rules.
CREATE TABLE conditions (
    id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name_vi        VARCHAR(100) NOT NULL UNIQUE,
    condition_type ENUM('disease','allergy','intolerance','diet') NOT NULL,
    description    VARCHAR(255) NULL
) ENGINE=InnoDB;


-- ── food_categories ───────────────────────────────────────────────────────
-- Giữ ở mức 10-15 danh mục: mã hóa one-hot cho ML, nhiều quá sẽ làm vector thưa.
CREATE TABLE food_categories (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    icon_url    VARCHAR(500) NULL
) ENGINE=InnoDB;


-- ── tags ──────────────────────────────────────────────────────────────────
-- Từ vựng có kiểm soát. Tránh 'low_sugar' / 'low-sugar' thành 2 cột one-hot.
CREATE TABLE tags (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name_vi     VARCHAR(100) NOT NULL UNIQUE,
    -- Không còn giá trị 'taste'. Vị mặn và vị ngọt nay là CHIỀU VECTOR
    -- tính từ `sodium_mg` và `sugar_g` — số đo, không phải nhãn gán tay.
    -- Vị chua và vị đắng không nguồn nào công bố nên không biểu diễn;
    -- đó là hạn chế đã ghi trong báo cáo. Giữ riêng mỗi vị chua thì
    -- trục vị khuyết, mà giữ cả nhóm thì ba nhãn đo được lại mâu thuẫn
    -- với chính số đo — nên bỏ cả nhóm.
    tag_type    ENUM('allergen','diet','nutrition') NOT NULL,
    description VARCHAR(255) NULL,
    INDEX idx_tag_type (tag_type)
) ENGINE=InnoDB;


-- ── rda_reference ─────────────────────────────────────────────────────────
-- Bảng tra cứu tĩnh, nạp từ NIN Vietnamese RDAs 2016.
CREATE TABLE rda_reference (
    id        CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    gender    ENUM('male','female','all') NOT NULL,
    age_min   TINYINT UNSIGNED NOT NULL,
    age_max   TINYINT UNSIGNED NOT NULL,
    -- Dùng CHUNG vốn từ với condition_rules.nutrient, và đúng bằng tên 14
    -- cột dinh dưỡng của food_nutrition. Để VARCHAR thì bảng tra cứu có thể
    -- chứa tên chất viết sai chính tả mà không ai phát hiện.
    nutrient  ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g',
                   'sugar_g','sodium_mg','cholesterol_mg','purine_mg',
                   'calcium_mg','iron_mg','zinc_mg','vitamin_a_mcg',
                   'vitamin_c_mg') NOT NULL,
    -- Nhãn phân nhóm của CHÍNH tài liệu nguồn, ghi nguyên văn không quy đổi.
    --
    -- Tài liệu "Nhu cầu dinh dưỡng khuyến nghị cho người Việt Nam" cho một số
    -- chất NHIỀU giá trị trên cùng một nhóm tuổi–giới, và phân theo những trục
    -- KHÁC NHAU tùy chất:
    --
    --   sắt  → giá trị sinh học khẩu phần 5% / 10% / 15%   (phần trăm)
    --   kẽm  → mức hấp thu tốt / vừa / kém                 (bậc định tính)
    --
    -- Vì hai trục khác nhau nên không ép được vào một ENUM thứ tự chung; làm
    -- vậy là tự dựng một phép quy đổi mà tài liệu không có. Cột này giữ nguyên
    -- nhãn của nguồn: 'bioavail_10pct', 'absorb_low'…
    --
    -- NULL = chất đó tài liệu không chia nhóm (đạm, canxi, vitamin C…).
    --
    -- Để VARCHAR vì chưa có tài liệu trong repo nên chưa biết đủ bộ nhãn.
    -- Khi nạp đủ bảng và biết chắc danh sách thì siết lại thành ENUM — đúng
    -- đường cột `nutrient` đã đi.
    qualifier VARCHAR(30)  NULL,
    rda_value DECIMAL(8,2) NOT NULL,
    unit      VARCHAR(10)  NOT NULL,
    source    VARCHAR(150) NOT NULL DEFAULT 'NIN Vietnamese RDAs 2016',

    -- `qualifier` nằm TRONG khóa: không có nó thì nạp đủ dữ liệu nguồn sẽ
    -- vi phạm khóa ngay ở chất sắt, vì ba mức giá trị sinh học là ba dòng
    -- cùng (giới tính, tuổi, 'iron_mg').
    --
    -- Nhưng `qualifier` để trống ở mọi chất không phân mức hấp thu (12/12
    -- dòng hiện tại), mà MySQL coi MỌI `NULL` là khác nhau — nên khóa đi
    -- thẳng qua `qualifier` sẽ không chặn trùng ở đúng những dòng đó. Phép
    -- quy đổi `NULL` -> `''` nằm ngay trong khóa, dạng khóa hàm (MySQL
    -- 8.0.13 trở lên), KHÔNG qua một cột sinh trung gian.
    --
    -- Trước đây chỗ này dùng cột sinh `qualifier_key`. Đã bỏ, cùng lý do và
    -- cùng cách làm như `foods.owner_key`: cột đó không mang ý nghĩa nghiệp
    -- vụ nào, chỉ tồn tại để phục vụ khóa, nên nó làm ERD dài thêm một dòng
    -- mà không nói thêm điều gì về bài toán. Hai chỗ trong cùng một lược đồ
    -- giải cùng một vấn đề thì nên giải giống nhau.
    UNIQUE KEY uq_rda    (gender, age_min, age_max, nutrient,
                          (COALESCE(qualifier, ''))),
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

-- ── password_resets ───────────────────────────────────────────────────────
-- Mã đặt lại mật khẩu cho luồng "Quên mật khẩu" (API 7.1.5-7.1.6).
--
-- Người quên mật khẩu không chứng minh được mình là chủ tài khoản bằng thứ
-- duy nhất hệ thống có — chính mật khẩu. Nên hệ thống tạm thay nó bằng quyền
-- đọc hộp thư đã đăng ký; mã trong bảng này là bằng chứng đó.
--
-- Một bảng riêng chứ không phải bốn cột trong `users`: mỗi lần xin mã là một
-- dòng, nên bấm "Gửi lại" không giết mã trong email trước đó, và 50 lần xin
-- mã trong một phút nhìn thấy được thay vì bị ghi đè.
--
-- LƯU MÃ ĐÃ BĂM. Ai đọc được bảng này mà mã nằm nguyên trong đó thì đổi được
-- mật khẩu của mọi tài khoản đang có mã sống.
--
-- Mã PHẢI do Backend sinh bằng `SecureRandom` (32 byte), KHÔNG bằng `UUID()`.
-- `UUID()` của MySQL là phiên bản 1 — ghép từ thời điểm và địa chỉ MAC máy
-- chủ, nên đoán được; nó chỉ đủ dùng cho cột `id`.
CREATE TABLE password_resets (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id     CHAR(36) NOT NULL,

    -- SHA-256 ở dạng hex: luôn đúng 64 ký tự, nên CHAR chứ không VARCHAR.
    -- SHA-256 chứ không BCrypt: BCrypt cố ý chậm để chống dò mật khẩu do
    -- người đặt, còn mã này là 32 byte ngẫu nhiên nên cái chậm đó vô ích.
    token_hash  CHAR(64) NOT NULL,

    expires_at  DATETIME NOT NULL,

    -- NULL = chưa dùng. Dùng rồi thì ghi thời điểm chứ không xóa dòng: một mã
    -- bị nộp hai lần là dấu hiệu liên kết đã rò ra ngoài, và xóa dòng đi thì
    -- lần thứ hai không phân biệt được với mã bịa.
    used_at     DATETIME NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_reset_window CHECK (expires_at > created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY uq_reset_token (token_hash),

    -- Đếm số lần xin mã gần đây của một tài khoản, cho mức 429 RATE_LIMITED.
    -- Giới hạn này chỉ che được email ĐÃ đăng ký: email không có trong hệ
    -- thống không sinh dòng nào — cố ý, vì lưu mọi địa chỉ người lạ nhập vào
    -- là tự dựng một danh sách email mà hệ thống không cần. Nhóm đó phải giới
    -- hạn ở tầng trước CSDL, theo địa chỉ IP.
    INDEX idx_reset_user_time (user_id, created_at)
) ENGINE=InnoDB;


-- ── refresh_tokens ────────────────────────────────────────────────────────
-- Chỗ lưu `refreshToken` (API 7.1.3). Đặc tả hứa hai điều đòi trạng thái
-- phía máy chủ: mỗi lần làm mới thì THU HỒI token cũ, và đổi mật khẩu thì
-- thu hồi MỌI token của tài khoản. Một JWT tự chứa không thu hồi được — nó
-- hợp lệ tới lúc hết hạn, nên đổi mật khẩu vì nghi bị chiếm tài khoản sẽ
-- không cắt được phiên của kẻ đó trong 30 ngày.
--
-- `replaced_by` nối các token thành chuỗi A -> B -> C. Xoay vòng mà không
-- phát hiện tái dùng thì không thêm an toàn nào: kẻ lấy được token cứ dùng,
-- hệ thống cứ cấp token mới, không ai biết. Khi một token ĐÃ thu hồi được
-- nộp lại, chỉ có hai khả năng — người dùng thật mất mạng giữa lúc xoay
-- vòng, hoặc token đã rò. Không phân biệt được, nên lần theo chuỗi và thu
-- hồi cả họ.
--
-- Lưu mã đã băm, cùng lý do như `password_resets`.
CREATE TABLE refresh_tokens (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id     CHAR(36) NOT NULL,
    token_hash  CHAR(64) NOT NULL,
    expires_at  DATETIME NOT NULL,

    -- NULL = còn sống. Thu hồi thì ghi thời điểm, KHÔNG xóa dòng: một token
    -- đã thu hồi mà được nộp lại là tín hiệu rò rỉ, và xóa dòng đi thì lần
    -- nộp đó không phân biệt được với một token bịa.
    revoked_at  DATETIME NULL,
    replaced_by CHAR(36) NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_refresh_window CHECK (expires_at > created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    -- SET NULL, không CASCADE: dọn một token hết hạn ở giữa chuỗi không được
    -- kéo theo token đang sống ở cuối chuỗi.
    FOREIGN KEY (replaced_by) REFERENCES refresh_tokens(id) ON DELETE SET NULL,

    UNIQUE KEY uq_refresh_token (token_hash),
    INDEX idx_refresh_user (user_id, revoked_at, expires_at)
) ENGINE=InnoDB;


-- ── health_profiles ───────────────────────────────────────────────────────
CREATE TABLE health_profiles (
    id                    CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id               CHAR(36) NOT NULL UNIQUE,
    gender                ENUM('male','female','other') NOT NULL,
    date_of_birth         DATE         NOT NULL,
    height_cm             DECIMAL(5,2) NOT NULL,
    weight_kg             DECIMAL(5,2) NOT NULL,
    -- Thuộc tính DẪN XUẤT, không phải dữ liệu lưu trữ. Dùng VIRTUAL nên
    -- MySQL không ghi byte nào xuống đĩa, chỉ tính lúc đọc — do đó không có
    -- dư thừa lưu trữ và không vi phạm chuẩn 3. Trong ERD vẽ bằng nét đứt.
    bmi                   DECIMAL(5,2) GENERATED ALWAYS AS
                              (weight_kg / ((height_cm / 100) * (height_cm / 100))) VIRTUAL,
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

    -- KHÔNG có cột `computed_at` ghi thời điểm tính lại hạn mức.
    --
    -- Bản thiết kế trước có cột đó, với ý định dùng `updated_at > computed_at`
    -- làm tín hiệu "hạn mức đã lạc hậu". Nhưng **cả 9 cột người dùng sửa được
    -- đều chảy vào công thức**: gender và date_of_birth vào BMR, height_cm và
    -- weight_kg vào BMR, activity_level vào TDEE, goal vào hạn mức năng lượng,
    -- ba cột target_*_pct vào phân bổ macro.
    --
    -- Không có cột nào sửa mà hạn mức giữ nguyên, nên điều kiện đó LUÔN đúng
    -- sau mọi lần sửa — nó không mang thông tin gì, và tương đương chính xác
    -- với "tính lại mỗi lần UPDATE". Vậy thì tính lại luôn là xong.
    --
    -- Cột đó còn là một cái bẫy: nếu công việc tính lại ghi `computed_at` ở
    -- một câu lệnh riêng so với ba cột hạn mức, thì `ON UPDATE
    -- CURRENT_TIMESTAMP` đẩy `updated_at` lên sau, và điều kiện lạc hậu đúng
    -- vĩnh viễn — tính lại vô hạn.
    --
    -- Dấu vết "thực đơn này dùng hạn mức nào" không mất: `meal_plans` chụp lại
    -- target_calories_kcal và ba cột macro ngay lúc sinh thực đơn.

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


-- ── body_logs ─────────────────────────────────────────────────────────────
-- Lịch sử cân nặng theo thời gian.
--
-- health_profiles chỉ giữ ĐÚNG MỘT dòng mỗi người (user_id là UNIQUE), nên
-- weight_kg ở đó bị ghi đè mỗi lần cập nhật — không vẽ được biểu đồ tiến
-- trình mà đề cương đã hứa ở sản phẩm số 4.
--
-- Phân vai rõ ràng: health_profiles.weight_kg là cân nặng HIỆN HÀNH, dùng để
-- tính hạn mức năng lượng; bảng này là LỊCH SỬ, chỉ dùng để hiển thị.
CREATE TABLE body_logs (
    id         CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id    CHAR(36) NOT NULL,
    logged_on  DATE NOT NULL,
    weight_kg  DECIMAL(5,2) NOT NULL,
    note       VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Chỉ có cân nặng, KHÔNG có chiều cao. Chiều cao của người trưởng thành
    -- gần như không đổi, nên ghi nó mỗi lần cân là lặp lại cùng một con số —
    -- `health_profiles.height_cm` giữ giá trị hiện tại là đủ.
    --
    -- Hệ quả phải biết: BMI theo thời gian được tính bằng chiều cao HIỆN TẠI
    -- áp cho mọi điểm trong quá khứ. Với người trưởng thành sai số không đáng
    -- kể; với người dùng còn đang phát triển chiều cao thì BMI cũ sẽ lệch nhẹ.
    CONSTRAINT chk_log_weight CHECK (weight_kg BETWEEN 20 AND 300),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    -- Mỗi ngày tối đa một bản ghi: cân hai lần trong ngày không được tạo ra
    -- hai điểm trên biểu đồ. Ghi lại thì cập nhật dòng cũ.
    UNIQUE KEY uq_user_day (user_id, logged_on),
    INDEX idx_user_time (user_id, logged_on)
) ENGINE=InnoDB;


-- ── user_conditions ───────────────────────────────────────────────────────
CREATE TABLE user_conditions (
    id           CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id      CHAR(36) NOT NULL,
    condition_id INT UNSIGNED    NOT NULL,
    severity     ENUM('mild','moderate','severe') NOT NULL DEFAULT 'moderate',
    note         VARCHAR(255) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)      REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (condition_id) REFERENCES conditions(id),
    UNIQUE KEY uq_user_condition (user_id, condition_id)
) ENGINE=InnoDB;


-- ── foods ─────────────────────────────────────────────────────────────────
-- is_active: ẩn món khỏi gợi ý mà không xóa dữ liệu. Xóa cứng sẽ CASCADE mất
-- lịch sử tương tác và mẫu huấn luyện.
-- owner_id: phạm vi của món. Ăn khớp với mạch truy xuất nguồn mà cả
-- tập dữ liệu đang theo (food_nutrition.data_source, source_url).
CREATE TABLE foods (
    id               CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    category_id      CHAR(36) NOT NULL,
    name             VARCHAR(200) NOT NULL,
    description      TEXT         NULL,
    image_url        VARCHAR(500) NULL,

    -- ══ Đặc trưng cho vector ML (đề cương nêu đích danh) ══
    spice_level      TINYINT UNSIGNED NOT NULL DEFAULT 0,
    -- dish_role: Bước 4 dùng để bảo đảm cấu trúc bữa ăn hợp lý,
    -- tránh chọn ra 3 món tráng miệng vì cả 3 đều điểm cao.
    -- Tách `side_protein` khỏi `side_veg`: mâm cơm Việt thiếu món mặn thì
    -- không còn là bữa ăn, mà gộp chung thì Bước 4 có thể chọn ra hai món
    -- rau và không có nguồn đạm nào.
    dish_role        ENUM('main','side_protein','side_veg','soup',
                          'snack','dessert','drink')
                         NOT NULL DEFAULT 'main',

    -- Bộ đệm độ phổ biến, tính lại định kỳ. Dùng chấm điểm ở Giai đoạn 0.
    popularity_score DECIMAL(5,4) NOT NULL DEFAULT 0,
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,

    -- Chủ sở hữu món.
    --   NULL      = món thuộc DANH MỤC CHUNG, do quản trị viên duyệt, mọi
    --               người dùng đều thấy. Chỉ những món này mới tính vào mốc
    --               300–500 món của đề cương.
    --   có giá trị = món RIÊNG của người dùng đó, tự thêm khi ăn thứ không
    --               có trong danh mục. Chỉ người đó thấy.
    --
    -- Nhờ cột này mà food_diary.food_id giữ được NOT NULL: người dùng ghi
    -- nhật ký món ngoài danh mục bằng cách tạo một món riêng, chứ không phải
    -- bằng một dòng nhật ký không trỏ tới món nào.
    owner_id         CHAR(36) NULL,
    -- Cột sinh, chỉ tồn tại để khóa UNIQUE bên dưới hoạt động được. Xem khối
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_spice CHECK (spice_level BETWEEN 0 AND 3),
    FOREIGN KEY (category_id) REFERENCES food_categories(id),
    -- SET NULL chứ không CASCADE: xóa tài khoản admin không được kéo theo
    -- món ăn do người đó nhập.
    -- CASCADE chứ không SET NULL: xóa tài khoản thì món riêng của người đó
    -- phải mất theo. Chuyển nó thành món danh mục chung là phát tán dữ liệu
    -- chưa kiểm duyệt cho mọi người dùng khác.
    --
    -- Không có cột `updated_by` riêng. Quy ước: owner_id IS NULL thì món do
    -- quản trị viên quản lý; owner_id có giá trị thì đó là món riêng của
    -- chính người dùng đó, và họ cũng là người sửa nó. Một cột mang cả hai
    -- thông tin, thay vì hai cột trùng nhau ở mọi món riêng tư.
    FOREIGN KEY (owner_id)    REFERENCES users(id) ON DELETE CASCADE,
    -- Tên món duy nhất TRONG PHẠM VI chủ sở hữu: trình nạp dữ liệu dùng
    -- ON DUPLICATE KEY UPDATE, không có ràng buộc này thì nạp lại lần hai sẽ
    -- nhân đôi toàn bộ món.
    --
    -- Gộp chủ sở hữu vào khóa vì hai người dùng khác nhau hoàn toàn có thể
    -- cùng tự thêm một món tên "Cơm gà bà Năm"; ràng buộc chỉ trên `name` sẽ
    -- chặn oan người thứ hai.
    --
    -- Khóa đi theo BIỂU THỨC `COALESCE(owner_id, '')` chứ KHÔNG theo
    -- `owner_id` trần, vì **MySQL coi mọi NULL là khác nhau trong chỉ mục
    -- UNIQUE**. Mọi món của danh mục chung đều có owner_id NULL, nên khóa
    -- (owner_id, name) không chặn một dòng nào trong số 305 món công khai:
    -- đo trên CSDL thật thì owner_id NULL ở 305/305 dòng.
    --
    -- Không phải lỗi lý thuyết. Bản trước ghi chú rằng phần chặn trùng của
    -- danh mục chung "do trình nạp và trang quản trị kiểm", và chính trình
    -- nạp là thứ vỡ: `load_foods.py --apply` chết ngay ở món đầu với
    -- (1242, 'Subquery returns more than 1 row') — ON DUPLICATE KEY UPDATE
    -- không thấy khóa trùng nên chèn thêm món, câu lệnh sau tra
    -- `SELECT id FROM foods WHERE name = …` thì nhận về hai dòng.
    --
    -- Bài học: ràng buộc toàn vẹn giao cho tầng ứng dụng chỉ đúng tới khi có
    -- tầng ứng dụng thứ hai. Ở đây tầng thứ hai là trang quản trị nhập món
    -- bằng tay. Xem db/migrations/003_null_breaks_unique.sql.
    --
    -- Trước đây phép quy đổi NULL nằm ở một cột sinh tên `owner_key`. Cột đó
    -- đã bỏ: nó không mang thông tin nào mà `owner_id` chưa có — chỉ là bản
    -- sao thay NULL bằng chuỗi rỗng — nên trên sơ đồ ERD nó là một dòng thừa
    -- phải giải thích. MySQL 8.0.13 trở lên cho đặt khóa thẳng lên biểu
    -- thức, nên phép quy đổi chuyển vào trong khóa. Hành vi y hệt: bên trong
    -- MySQL vẫn dựng một cột ảo ẩn, chỉ khác là nó không hiện ra nữa.
    UNIQUE KEY uq_food_name ((COALESCE(owner_id, '')), name),
    -- Bộ lọc F1 ở Bước 2 luôn kèm mệnh đề
    --   (owner_id IS NULL OR owner_id = :current_user)
    -- nên owner_id phải đứng đầu chỉ mục này.
    INDEX idx_active_category (owner_id, is_active, category_id),
    INDEX idx_dish_role       (dish_role)
) ENGINE=InnoDB;


-- ── condition_rules ───────────────────────────────────────────────────────
-- BỘ QUY TẮC F1 DƯỚI DẠNG DỮ LIỆU.
-- Vừa là sản phẩm phải nộp theo đề cương, vừa là phương án đối chứng
-- (variant = 'rule_based') khi so sánh với học máy ở Chương 3.
CREATE TABLE condition_rules (
    id           CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    condition_id INT UNSIGNED NOT NULL,
    rule_type    ENUM('exclude_tag','require_tag','nutrient_limit') NOT NULL,

    -- rule_type = 'exclude_tag' | 'require_tag'
    tag_id       INT UNSIGNED NULL,

    -- rule_type = 'nutrient_limit'
    nutrient     ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g',
                      'sugar_g','sodium_mg','cholesterol_mg','purine_mg',
                      'calcium_mg','iron_mg','zinc_mg','vitamin_a_mcg',
                      'vitamin_c_mg') NULL,
    comparator   ENUM('lte','gte') NULL,
    threshold    DECIMAL(8,2) NULL,
    -- per_serving lọc được ở Bước 2; per_meal / per_day chỉ kiểm tra được
    -- ở Bước 4 khi đã biết tổ hợp món cụ thể.
    scope        ENUM('per_serving','per_meal','per_day') NOT NULL DEFAULT 'per_serving',

    severity_min ENUM('mild','moderate','severe') NOT NULL DEFAULT 'mild',
    -- is_hard = 1 -> loại bỏ ở Bước 2;  = 0 -> trừ điểm ở Bước 3
    is_hard      TINYINT(1)   NOT NULL DEFAULT 1,
    penalty      DECIMAL(4,3) NULL,

    -- Mức tin cậy của NGƯỠNG, không phải của quy tắc. Giao diện dùng nó để
    -- chọn giọng trình bày: một ứng dụng sức khỏe dẫn khuyến cáo của WHO và
    -- một con số chưa ai tra bằng cùng một giọng là không trung thực.
    --   definitional  Quy tắc LÀ định nghĩa, không có ngưỡng để dẫn nguồn
    --                 ("dị ứng trứng thì loại món có trứng"). Mọi quy tắc
    --                 nhãn thuộc nhóm này.
    --   published     Con số lấy nguyên từ nguồn đang hiệu lực.
    --   derived       Nguồn có thật nhưng con số là phép suy ra, nên chỉ
    --                 đúng kèm giả thiết — 48 g đạm của KDIGO đúng cho
    --                 người 60 kg, không đúng cho người 90 kg.
    --   unsupported   Không có nguồn ĐANG hiệu lực: hoặc ngưỡng đã bị rút
    --                 (cholesterol 300 mg/ngày), hoặc chưa ai tra.
    -- Mặc định là `derived`, KHÔNG phải `published`: một quy tắc thêm vào mà
    -- quên khai thì phải mặc định ở mức không được dẫn nguồn.
    evidence_level ENUM('definitional','published','derived','unsupported')
                 NOT NULL DEFAULT 'derived',
    note         VARCHAR(255) NULL,

    -- Bảng đa hình: mỗi `rule_type` dùng một bộ cột khác nhau. Không có
    -- ràng buộc này thì một quy tắc nutrient_limit bỏ trống `threshold` vẫn
    -- chèn được, và nó sẽ LẶNG LẼ không bao giờ kích hoạt.
    CONSTRAINT chk_rule_shape CHECK (
        (rule_type IN ('exclude_tag','require_tag')
             AND tag_id IS NOT NULL
             AND nutrient IS NULL AND comparator IS NULL AND threshold IS NULL)
        OR
        (rule_type = 'nutrient_limit'
             AND tag_id IS NULL
             AND nutrient IS NOT NULL AND comparator IS NOT NULL
             AND threshold IS NOT NULL)
    ),
    -- Quy tắc mềm phải có mức phạt, quy tắc cứng thì không cần.
    CONSTRAINT chk_rule_penalty CHECK (is_hard = 1 OR penalty IS NOT NULL),

    -- `definitional` chỉ dành cho quy tắc nhãn, và mọi quy tắc nhãn phải là
    -- `definitional`. Không có ràng buộc này thì một ngưỡng dinh dưỡng có
    -- thể tự nhận là định nghĩa và thoát khỏi mọi yêu cầu dẫn nguồn.
    CONSTRAINT chk_rule_evidence CHECK (
        (rule_type IN ('exclude_tag','require_tag')
             AND evidence_level = 'definitional')
        OR
        (rule_type = 'nutrient_limit'
             AND evidence_level <> 'definitional')
    ),

    FOREIGN KEY (condition_id) REFERENCES conditions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)       REFERENCES tags(id),
    INDEX idx_condition (condition_id)
) ENGINE=InnoDB;


-- ── user_preference_profiles ──────────────────────────────────────────────
-- Hồ sơ sở thích dạng vector trọng số (thuật toán Rocchio).
CREATE TABLE user_preference_profiles (
    user_id         CHAR(36) NOT NULL PRIMARY KEY,
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
    id              CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    food_id         CHAR(36) NOT NULL UNIQUE,
    serving_size_g  SMALLINT UNSIGNED NOT NULL DEFAULT 100,

    calories_kcal   DECIMAL(7,2) NOT NULL,
    protein_g       DECIMAL(6,2) NOT NULL DEFAULT 0,
    carbs_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    fat_g           DECIMAL(6,2) NOT NULL DEFAULT 0,

    -- Bốn cột này CHO PHÉP NULL có chủ đích. `NOT NULL DEFAULT 0` sẽ biến
    -- "chưa biết" thành "bằng 0", và với natri thì đó là lỗi an toàn theo
    -- đúng hướng nguy hiểm: món thiếu số liệu được bộ lọc coi là ít natri
    -- nhất, rồi ưu tiên gợi ý cho người tăng huyết áp.
    fiber_g         DECIMAL(6,2) NULL,
    sugar_g         DECIMAL(6,2) NULL,
    sodium_mg       DECIMAL(7,2) NULL,
    cholesterol_mg  DECIMAL(7,2) NULL,
    purine_mg       DECIMAL(7,2) NULL,

    calcium_mg      DECIMAL(7,2) NULL,
    iron_mg         DECIMAL(6,2) NULL,
    zinc_mg         DECIMAL(6,2) NULL,
    vitamin_a_mcg   DECIMAL(7,2) NULL,
    vitamin_c_mg    DECIMAL(6,2) NULL,

    -- Truy xuất nguồn: hội đồng thường hỏi số liệu dinh dưỡng lấy ở đâu
    -- Đường dẫn tới đúng trang chứa số liệu. Tên nguồn không kiểm chứng
    -- được, đường dẫn thì có.
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ── food_tags ─────────────────────────────────────────────────────────────
CREATE TABLE food_tags (
    food_id CHAR(36) NOT NULL,
    tag_id  INT UNSIGNED    NOT NULL,

    PRIMARY KEY (food_id, tag_id),
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)  REFERENCES tags(id),
    -- idx_tag: Bộ lọc F1 truy ngược từ nhãn ra món
    INDEX idx_tag (tag_id)
) ENGINE=InnoDB;


-- ── meal_plans ────────────────────────────────────────────────────────────
CREATE TABLE meal_plans (
    id                     CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id                CHAR(36) NOT NULL,
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
    -- Thuộc tính DẪN XUẤT như health_profiles.bmi — dùng VIRTUAL để không
    -- lưu trữ dư thừa. Vẽ nét đứt trong ERD.
    calorie_deviation_pct  DECIMAL(6,2) GENERATED ALWAYS AS
        (100 * (actual_calories_kcal - target_calories_kcal)
             / target_calories_kcal) VIRTUAL,

    total_preference_score DECIMAL(8,4) NULL,
    -- Tỷ lệ thăm dò MỤC TIÊU dùng khi sinh thực đơn này (cơ chế 70-30).
    -- 0.300 = 30% số suất dành cho món thăm dò. Trần 0.5 vì quá nửa thực đơn
    -- là món thử nghiệm thì không còn là gợi ý cá nhân hóa nữa.
    -- Tỷ lệ THỰC TẾ đạt được tính từ meal_plan_items.exploration_delta.
    exploration_ratio      DECIMAL(4,3) NULL,
    generation_source      ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id               INT UNSIGNED NULL,
    status                 ENUM('draft','active','completed') NOT NULL DEFAULT 'active',
    generated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_target_positive CHECK (target_calories_kcal > 0),
    CONSTRAINT chk_expl_ratio      CHECK (exploration_ratio IS NULL
                                          OR exploration_ratio BETWEEN 0 AND 0.5),
    FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ml_models(id) ON DELETE SET NULL,

    UNIQUE KEY uq_user_date (user_id, plan_date),
    INDEX     idx_source    (generation_source)
) ENGINE=InnoDB;


-- ── recommendations ───────────────────────────────────────────────────────
CREATE TABLE recommendations (
    id                CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    -- batch_id nhóm toàn bộ món trong MỘT lần gợi ý -> bắt buộc để tính @K
    batch_id          CHAR(36) NOT NULL,
    user_id           CHAR(36) NOT NULL,
    food_id           CHAR(36) NOT NULL,
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

    -- was_selected = món có được Bước 4 đưa vào thực đơn cuối cùng không.
    -- Cho biết ràng buộc dinh dưỡng đã bác bỏ bao nhiêu món điểm cao.
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
    id             CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id        CHAR(36) NOT NULL,
    food_id        CHAR(36) NOT NULL,
    ate_on         DATE NOT NULL,
    meal_type      ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    -- Số suất đã ăn, KHÔNG phải số gam. Khối lượng một suất chuẩn nằm ở
    -- food_nutrition.serving_size_g; lưu lại gam ở đây là dư thừa và có thể
    -- lệch với suất chuẩn. 0.50 = nửa suất, 1.50 = suất lớn.
    -- Người dùng không biết món mình ăn nặng bao nhiêu gam, nhưng biết mình
    -- ăn hết một tô hay nửa tô.
    portion_multiplier  DECIMAL(4,2) NOT NULL DEFAULT 1.00,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_diary_portion CHECK (portion_multiplier BETWEEN 0.1 AND 5),

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
    id         CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id    CHAR(36) NOT NULL,
    food_id    CHAR(36) NOT NULL,
    rating     TINYINT UNSIGNED NOT NULL,
    comment    TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_rating CHECK (rating BETWEEN 1 AND 5),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    INDEX idx_user        (user_id),
    INDEX idx_food_rating (food_id, rating),
    -- Lấy đánh giá GẦN NHẤT của một người cho một món.
    -- Khẩu vị đổi theo thời gian: hôm nay 5 sao, tháng sau có thể 2 sao.
    INDEX idx_user_food_time (user_id, food_id, created_at)
) ENGINE=InnoDB;


-- ── ml_training_samples ───────────────────────────────────────────────────
-- Tập dữ liệu ĐÃ ĐÓNG BĂNG. Không tính nhãn trực tiếp từ bảng gốc lúc train,
-- nếu không thì mỗi lần chạy lại con số Precision@K trong báo cáo sẽ khác.
CREATE TABLE ml_training_samples (
    id               CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    dataset_version  VARCHAR(20) NOT NULL,
    user_id          CHAR(36) NOT NULL,
    food_id          CHAR(36) NOT NULL,

    label            DECIMAL(4,3) NOT NULL,
    sample_weight    DECIMAL(4,3) NOT NULL DEFAULT 1.000,
    source           ENUM('feedback','swipe','diary',
                          'plan_kept','plan_replaced','plan_skipped','random_neg')
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

    CONSTRAINT chk_label         CHECK (label         BETWEEN 0 AND 1),
    CONSTRAINT chk_sample_weight CHECK (sample_weight BETWEEN 0 AND 1),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    -- Một người dùng, một món, một nguồn tín hiệu chỉ cho đúng MỘT mẫu
    -- trong mỗi phiên bản tập dữ liệu. Không có ràng buộc này thì đóng băng
    -- lại cùng dataset_version lần thứ hai sẽ nhân đôi toàn bộ mẫu và làm
    -- sai mọi con số huấn luyện mà không có dấu hiệu gì.
    UNIQUE KEY uq_sample (dataset_version, user_id, food_id, source),

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
    -- 0 = độ đo không có @k (MAE, RMSE, AUC). Dùng 0 thay vì NULL vì NULL
    -- làm khóa uq_eval bên dưới mất tác dụng.
    k_value      TINYINT UNSIGNED NOT NULL DEFAULT 0,
    value        DECIMAL(8,5) NOT NULL,
    -- fold = 0 là kết quả trên tập kiểm thử cuối, không phải một fold.
    -- Cũng không để NULL: một dòng đánh giá bị chèn hai lần sẽ làm mọi phép
    -- trung bình giữa các variant lệch âm thầm, mà số liệu đánh giá là thứ
    -- đi thẳng vào báo cáo.
    fold         TINYINT UNSIGNED NOT NULL DEFAULT 0,
    evaluated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (model_id) REFERENCES ml_models(id) ON DELETE CASCADE,
    UNIQUE KEY uq_eval (model_id, variant, metric, k_value, fold)
) ENGINE=InnoDB;


-- ╔═════════════════════════════════════════════════════════════════════════╗
-- ║  TẦNG 3 — chỉ còn meal_plan_items phụ thuộc meal_plans                  ║
-- ╚═════════════════════════════════════════════════════════════════════════╝

-- ── meal_plan_items ───────────────────────────────────────────────────────
-- food_id và replaced_by_food_id cùng trỏ foods nhưng là HAI VAI TRÒ khác
-- nhau (món gợi ý / món đổi sang), không phải dư thừa dữ liệu.
CREATE TABLE meal_plan_items (
    id                  CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    meal_plan_id        CHAR(36) NOT NULL,
    food_id             CHAR(36) NOT NULL,
    meal_type           ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    -- Số suất được gợi ý, như food_diary.portion_multiplier.
    portion_multiplier       DECIMAL(4,2) NOT NULL DEFAULT 1.00,

    predicted_score     DECIMAL(6,4) NULL,
    -- status = nguồn phản hồi ngầm định mà đề cương gọi là
    -- "món được chọn, món bị thay thế"
    status              ENUM('suggested','kept','replaced','eaten','skipped')
                            NOT NULL DEFAULT 'suggested',
    replaced_by_food_id CHAR(36) NULL,
    replaced_at         DATETIME NULL,
    -- Biên độ nhiễu δ đã dùng khi chọn món này theo cơ chế 70-30.
    --   NULL       = nhóm KHAI THÁC, chọn theo vector sở thích p_u
    --   có giá trị = nhóm THĂM DÒ,  chọn theo p_u' = chuẩn_hóa(p_u + δ·n)
    -- Không cần thêm cột cờ is_exploration: (exploration_delta IS NOT NULL)
    -- đã trả lời được câu hỏi đó.
    exploration_delta   DECIMAL(4,3) NULL,
    position            TINYINT UNSIGNED NULL,
    note                VARCHAR(255) NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (meal_plan_id)        REFERENCES meal_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id)             REFERENCES foods(id),
    FOREIGN KEY (replaced_by_food_id) REFERENCES foods(id),

    CONSTRAINT chk_expl_delta CHECK (exploration_delta IS NULL
                                     OR exploration_delta BETWEEN 0 AND 1),
    CONSTRAINT chk_item_portion CHECK (portion_multiplier BETWEEN 0.1 AND 5),

    INDEX idx_plan_meal (meal_plan_id, meal_type),
    INDEX idx_status    (status),
    -- Kiểm tra "món này từng nằm trong thực đơn của user chưa"
    -- -> điều kiện bắt buộc để được đánh giá
    INDEX idx_food      (food_id)
) ENGINE=InnoDB;


-- ── interactions ──────────────────────────────────────────────────────────
-- Chỉ chứa kết quả PHIÊN KHẢO SÁT KHẨU VỊ lúc tạo tài khoản.
-- Cơ chế vuốt chạy đúng một lần trong đời tài khoản, nên bảng này không có
-- session_type, context_meal_type hay recommendation_id — cả ba sẽ là hằng số.
-- Sau khảo sát, tín hiệu sở thích đến từ meal_plan_items, food_diary, feedbacks.
CREATE TABLE interactions (
    id            CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id       CHAR(36) NOT NULL,
    food_id       CHAR(36) NOT NULL,
    action        ENUM('like','dislike','neutral','unknown') NOT NULL,
    -- Mã phiên khảo sát. Cả gói vuốt được ghi trong một giao dịch,
    -- nên mọi dòng của một người dùng chia sẻ cùng một session_id.
    session_id    CHAR(36) NOT NULL,
    interacted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    -- KHÔNG đặt UNIQUE (user_id, food_id): nếu người dùng đặt lại hồ sơ và
    -- làm lại phiên khảo sát, cả hai lần vuốt đều được giữ. So sánh hai lần
    -- cho biết khẩu vị đã đổi thế nào.
    INDEX idx_user_time (user_id, interacted_at),
    INDEX idx_user_food (user_id, food_id),
    INDEX idx_food      (food_id),
    INDEX idx_session   (session_id)
) ENGINE=InnoDB;
