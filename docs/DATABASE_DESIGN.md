# Thiết kế cơ sở dữ liệu — Hệ thống khuyến nghị thực đơn dinh dưỡng cá nhân hóa

## 1. Tổng quan

**Hệ quản trị CSDL:** MySQL 8.x
**Storage engine:** InnoDB
**Charset:** `utf8mb4` — **Collation:** `utf8mb4_unicode_ci`

Cơ sở dữ liệu gồm **21 bảng**, chia thành 6 nhóm chức năng:

| Nhóm | Số bảng | Bảng |
|---|---|---|
| 👤 Người dùng | 4 | `users`, `health_profiles`, `conditions`, `user_conditions` |
| 🍜 Món ăn | 5 | `food_categories`, `foods`, `food_nutrition`, `tags`, `food_tags` |
| 📏 Quy tắc dinh dưỡng | 2 | `condition_rules`, `rda_reference` |
| 🤝 Tương tác & Phản hồi | 4 | `interactions`, `food_diary`, `feedbacks`, `recommendations` |
| 📋 Thực đơn | 2 | `meal_plans`, `meal_plan_items` |
| 🤖 Machine Learning | 4 | `user_preference_profiles`, `ml_models`, `ml_evaluations`, `ml_training_samples` |

### Ba nguyên tắc chi phối thiết kế

**1. Quy tắc là dữ liệu, không phải mã nguồn.** Bộ quy tắc ràng buộc dinh dưỡng nằm trong bảng `condition_rules`, không hard-code trong C#. Đề cương liệt kê "bộ quy tắc ràng buộc dinh dưỡng" là sản phẩm phải nộp, nên nó cần trình bày được thành bảng trong báo cáo. Đồng thời đây chính là **phương án đối chứng** khi so sánh với mô hình học máy ở Chương 3.

**2. Từ vựng có kiểm soát.** Nhãn món ăn và tên bệnh lý đều tra qua bảng từ điển (`tags`, `conditions`), không lưu chuỗi tự do. Lý do kỹ thuật: bước mã hóa one-hot của ML sẽ sinh ra hai cột khác nhau nếu cùng một khái niệm bị gõ thành `low_sugar` ở chỗ này và `low-sugar` ở chỗ khác.

**3. Số liệu báo cáo phải truy vấn được, không tính tay.** Độ lệch năng lượng, kết quả Precision@K, tỷ lệ tuân thủ thực đơn — tất cả đều lưu sẵn dưới dạng cột hoặc bảng để `SELECT` ra là có số cho Chương 3. Xem Mục 8.

---

## 2. Sơ đồ quan hệ (ERD)

```
╔═ NGƯỜI DÙNG ═══════════════════════════════════════════════════════════════╗
║                                                                            ║
║   users ──1:1──► health_profiles                                           ║
║     │                                                                      ║
║     ├──1:N──► user_conditions ──N:1──► conditions                          ║
║     │                                      │                               ║
║     └──1:1──► user_preference_profiles     │ 1:N                           ║
║                                            ▼                               ║
╚════════════════════════════════════ condition_rules ═══════════════════════╝
                                            │ N:1
╔═ MÓN ĂN ═══════════════════════════════════▼═══════════════════════════════╗
║                                                                            ║
║   food_categories ──1:N──► foods ──1:1──► food_nutrition                   ║
║                              │                                             ║
║                              └──N:M──► tags        (qua food_tags)         ║
║                                                                            ║
║   rda_reference   (bảng tra cứu độc lập, không có khóa ngoại)              ║
╚════════════════════════════════════════════════════════════════════════════╝

╔═ TƯƠNG TÁC & THỰC ĐƠN ═════════════════════════════════════════════════════╗
║                                                                            ║
║   users ──┬──1:N──► interactions ──N:1──► recommendations                  ║
║           │              │                      │                          ║
║           │              └──────N:1──────► foods ◄──────┐                  ║
║           │                                      ▲      │                  ║
║           ├──1:N──► meal_plans ──1:N──► meal_plan_items─┘                  ║
║           │                                      │                         ║
║           ├──1:N──► food_diary ──────N:1──────────┤                         ║
║           │                                      │                         ║
║           └──1:N──► feedbacks ───────N:1──────────┘                         ║
║                                                                            ║
║   Không có khóa ngoại giữa food_diary / feedbacks / meal_plan_items —      ║
║   liên kết giữa chúng lấy bằng ghép khóa tự nhiên (xem Mục 6.2, 6.3)       ║
╚════════════════════════════════════════════════════════════════════════════╝

╔═ MACHINE LEARNING ═════════════════════════════════════════════════════════╗
║                                                                            ║
║   ml_models ──1:N──► ml_evaluations                                        ║
║       ▲                                                                    ║
║       └──── recommendations.model_id , meal_plans.model_id                 ║
║                                                                            ║
║   ml_training_samples ──N:1──► users , foods                               ║
║   user_preference_profiles ──1:1──► users                                  ║
╚════════════════════════════════════════════════════════════════════════════╝
```

---

## 2.1 Thứ tự tạo bảng

Tài liệu này trình bày các bảng theo **nhóm chức năng** để dễ đọc, nhưng đó **không phải** thứ tự tạo bảng. Chỉ có duy nhất một chỗ khóa ngoại trỏ ngược lại nhóm khác:

- `interactions` → `recommendations`

Đồ thị phụ thuộc không có chu trình, nên chỉ cần tạo theo thứ tự sau:

```text
Tầng 0 — không phụ thuộc bảng nào
    users, conditions, food_categories, tags, rda_reference, ml_models

Tầng 1
    health_profiles, user_conditions, foods, condition_rules,
    user_preference_profiles

Tầng 2
    food_nutrition, food_tags, meal_plans, recommendations,
    food_diary, feedbacks, ml_training_samples, ml_evaluations

Tầng 3
    meal_plan_items, interactions
```

> Khi viết `schema.sql`, đặt các câu `CREATE TABLE` theo đúng thứ tự này. Nếu dùng Entity Framework Core Migrations thì công cụ tự sắp xếp, không cần quan tâm.

---

# 3. Nhóm Người dùng

## 3.1 `users` — Tài khoản

```sql
CREATE TABLE users (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    password_hash           VARCHAR(255) NOT NULL,
    display_name            VARCHAR(100) NOT NULL,
    avatar_url              VARCHAR(500) NULL,
    onboarding_completed_at DATETIME     NULL,
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
```

| Cột | Mô tả |
|---|---|
| `onboarding_completed_at` | Mốc hoàn tất phiên vuốt thăm dò. `NULL` nghĩa là người dùng còn ở **Giai đoạn 0** |

> `onboarding_completed_at` là cột đánh dấu ranh giới Giai đoạn 0 → Giai đoạn 1. Backend dựa vào cột này để quyết định có cần đẩy người dùng vào màn hình vuốt thăm dò hay không.

**Không có cột `role`.** Hệ thống hướng hoàn toàn tới người dùng cuối, không có ứng dụng quản trị. Việc nhập 300–500 món ăn, nạp bộ quy tắc và từ điển nhãn đều làm bằng **script seed**; việc xem kết quả huấn luyện làm bằng **truy vấn SQL** trên các bảng `ml_models` và `ml_evaluations`. Không thao tác nào cần tài khoản quyền cao.

**Không có cột `is_active`.** Không có nghiệp vụ khóa tài khoản. Khi cần xóa tài khoản thì `DELETE` trực tiếp, các khóa ngoại `ON DELETE CASCADE` sẽ dọn dữ liệu liên quan.

> **Lưu ý phân biệt:** `foods.is_active` vẫn được giữ và mang vai trò hoàn toàn khác — ẩn một món khỏi danh sách gợi ý **mà không xóa dữ liệu**. Xóa cứng một món sẽ `CASCADE` xóa luôn lịch sử tương tác, nhật ký ăn uống và mẫu huấn luyện liên quan, làm hỏng tập dữ liệu ML.

---

## 3.2 `health_profiles` — Hồ sơ sức khỏe và hạn mức dinh dưỡng

```sql
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

    -- ══ Đầu ra Bước 1 của thuật toán khuyến nghị ══
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

    CONSTRAINT chk_height    CHECK (height_cm BETWEEN 50 AND 250),
    CONSTRAINT chk_weight    CHECK (weight_kg BETWEEN 20 AND 300),
    CONSTRAINT chk_macro_sum CHECK (target_protein_pct + target_carbs_pct
                                    + target_fat_pct = 100),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
```

| Cột | Mô tả |
|---|---|
| `bmi` | **Cột tính tự động** từ chiều cao và cân nặng |
| `bmr_kcal` | Chuyển hóa cơ bản, tính theo Mifflin-St Jeor |
| `tdee_kcal` | Tổng năng lượng tiêu hao ngày = BMR × hệ số vận động |
| `daily_calories_target` | Hạn mức năng lượng theo mục tiêu (TDEE ± 500) |
| `target_*_pct` | Tỷ lệ phân bổ ba chất sinh năng lượng, tổng luôn bằng 100 |
| `computed_at` | Thời điểm tính lại hạn mức — dùng để phát hiện hồ sơ đã cũ |

**Vì sao lưu BMR/TDEE thay vì tính mỗi lần cần?**

Ba lý do. Thứ nhất, người dùng thay đổi cân nặng theo thời gian, và ta cần biết **hạn mức tại thời điểm sinh thực đơn** chứ không phải hạn mức hôm nay. Thứ hai, `chk_macro_sum` bảo đảm tỷ lệ macro luôn hợp lệ ở tầng CSDL. Thứ ba, đây là đầu ra của Bước 1 — lưu lại thì Bước 4 và ML Service đọc trực tiếp, không phải tính lặp.

> `CHECK` ràng buộc `height_cm ≥ 50` cũng chặn luôn lỗi chia cho 0 ở cột `bmi`.

---

## 3.3 `conditions` — Từ điển bệnh lý, dị ứng, chế độ ăn

```sql
CREATE TABLE conditions (
    id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code           VARCHAR(50)  NOT NULL UNIQUE,
    name_vi        VARCHAR(100) NOT NULL,
    condition_type ENUM('disease','allergy','intolerance','diet') NOT NULL,
    description    VARCHAR(255) NULL
) ENGINE=InnoDB;
```

**Dữ liệu mẫu:**

| code | name_vi | condition_type |
|---|---|---|
| `diabetes` | Đái tháo đường | `disease` |
| `hypertension` | Tăng huyết áp | `disease` |
| `kidney_disease` | Bệnh thận | `disease` |
| `dyslipidemia` | Rối loạn mỡ máu | `disease` |
| `gout` | Gút | `disease` |
| `allergy_seafood` | Dị ứng hải sản | `allergy` |
| `allergy_peanut` | Dị ứng đậu phộng | `allergy` |
| `allergy_egg` | Dị ứng trứng | `allergy` |
| `lactose_intolerance` | Không dung nạp lactose | `intolerance` |
| `gluten_intolerance` | Không dung nạp gluten | `intolerance` |
| `vegetarian` | Ăn chay | `diet` |
| `vegan` | Ăn thuần chay | `diet` |

> Loại `diet` cũng nằm ở đây vì về mặt thuật toán, chế độ ăn bắt buộc là **ràng buộc cứng** giống hệt dị ứng — cùng đi qua Bộ lọc F1.

---

## 3.4 `user_conditions` — Bệnh lý của từng người dùng

```sql
CREATE TABLE user_conditions (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id      BIGINT UNSIGNED NOT NULL,
    condition_id INT UNSIGNED    NOT NULL,
    severity     ENUM('mild','moderate','severe') NOT NULL DEFAULT 'moderate',
    note         VARCHAR(255) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)      REFERENCES users(id)      ON DELETE CASCADE,
    FOREIGN KEY (condition_id) REFERENCES conditions(id),
    UNIQUE KEY uq_user_condition (user_id, condition_id)
) ENGINE=InnoDB;
```

| Cột | Mô tả |
|---|---|
| `severity` | Mức độ — cho phép áp quy tắc chặt hay lỏng tùy tình trạng |

> `severity` kết hợp với `condition_rules.severity_min`: một người tăng huyết áp mức nhẹ và một người mức nặng sẽ chịu ngưỡng natri khác nhau.

---

# 4. Nhóm Món ăn

## 4.1 `food_categories` — Danh mục

```sql
CREATE TABLE food_categories (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    icon_url    VARCHAR(500) NULL
) ENGINE=InnoDB;
```

> Ví dụ: món nước, món kho, món xào, món canh, món cuốn, cơm, bún phở, tráng miệng, đồ uống.

**Lưu ý cho ML:** danh mục được mã hóa one-hot trong vector đặc trưng, nên số lượng danh mục nên giữ ở mức **10–15**. Quá nhiều sẽ làm vector thưa và mô hình khó học.

---

## 4.2 `foods` — Món ăn

```sql
CREATE TABLE foods (
    id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    category_id      INT UNSIGNED NOT NULL,
    name             VARCHAR(200) NOT NULL,
    description      TEXT         NULL,
    image_url        VARCHAR(500) NULL,
    origin           VARCHAR(100) NULL,

    -- ══ Đặc trưng phục vụ vector ML (theo đề cương) ══
    cooking_method   ENUM('luoc','hap','xao','chien','nuong','kho',
                          'nau_canh','tron','song','khac')
                         NOT NULL DEFAULT 'khac',
    spice_level      TINYINT UNSIGNED NOT NULL DEFAULT 0,
    dish_role        ENUM('main','side','soup','dessert','drink')
                         NOT NULL DEFAULT 'main',
    suitable_meals   SET('breakfast','lunch','dinner','snack')
                         NOT NULL DEFAULT 'breakfast,lunch,dinner,snack',

    popularity_score DECIMAL(5,4) NOT NULL DEFAULT 0,
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_spice CHECK (spice_level BETWEEN 0 AND 3),
    FOREIGN KEY (category_id) REFERENCES food_categories(id),
    INDEX idx_active_category (is_active, category_id),
    INDEX idx_dish_role (dish_role)
) ENGINE=InnoDB;
```

| Cột | Mô tả | Dùng ở đâu |
|---|---|---|
| `cooking_method` | Phương pháp chế biến | **Vector đặc trưng ML** — đề cương nêu đích danh |
| `spice_level` | Độ cay 0–3 | Vector đặc trưng ML |
| `dish_role` | Vai trò trong bữa: món chính / món phụ / canh / tráng miệng / đồ uống | **Bước 4** — ràng buộc cấu trúc bữa ăn |
| `suitable_meals` | Bữa ăn phù hợp | **Bước 2** — lọc món không hợp bữa |
| `popularity_score` | Độ phổ biến chung, tính từ tỷ lệ thích toàn hệ thống | **Giai đoạn 0** — chấm điểm khi chưa biết gì về người dùng |

**Vì sao cần `dish_role`.** Bước 4 phải bảo đảm mỗi bữa có cấu trúc hợp lý — một món chính, một món canh, có thể thêm món phụ. Không có cột này thì thuật toán tham lam có thể chọn ra ba món tráng miệng vì cả ba đều điểm cao.

**Vì sao dùng `SET` cho `suitable_meals`.** Đây là tập cố định 4 giá trị, mỗi món có thể hợp nhiều bữa. Dùng `SET` giữ được tính đọc-hiểu (`FIND_IN_SET('breakfast', suitable_meals)`) mà không cần thêm một bảng phụ.

---

## 4.3 `food_nutrition` — Thành phần dinh dưỡng

```sql
CREATE TABLE food_nutrition (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id         BIGINT UNSIGNED NOT NULL UNIQUE,
    serving_size_g  SMALLINT UNSIGNED NOT NULL DEFAULT 100,

    -- ══ Năng lượng và ba chất sinh năng lượng ══
    calories_kcal   DECIMAL(7,2) NOT NULL,
    protein_g       DECIMAL(6,2) NOT NULL DEFAULT 0,
    carbs_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    fat_g           DECIMAL(6,2) NOT NULL DEFAULT 0,

    -- ══ Thành phần liên quan ràng buộc bệnh lý ══
    fiber_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    sugar_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    sodium_mg       DECIMAL(7,2) NOT NULL DEFAULT 0,
    cholesterol_mg  DECIMAL(7,2) NOT NULL DEFAULT 0,
    purine_mg       DECIMAL(7,2) NULL,

    -- ══ Vi chất ══
    calcium_mg      DECIMAL(7,2) NULL,
    iron_mg         DECIMAL(6,2) NULL,
    zinc_mg         DECIMAL(6,2) NULL,
    vitamin_a_mcg   DECIMAL(7,2) NULL,
    vitamin_c_mg    DECIMAL(6,2) NULL,

    data_source     VARCHAR(150) NULL,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
) ENGINE=InnoDB;
```

| Nhóm | Cột | Ghi chú |
|---|---|---|
| Bắt buộc | `calories_kcal`, `protein_g`, `carbs_g`, `fat_g` | Đề cương yêu cầu 300–500 món có đủ 4 trường này |
| Ràng buộc bệnh lý | `sugar_g`, `sodium_mg`, `cholesterol_mg`, `purine_mg` | Đầu vào cho `condition_rules` |
| Vi chất | `calcium_mg` → `vitamin_c_mg` | Cho phép `NULL` — không phải món nào cũng có số liệu |
| Truy xuất nguồn | `data_source` | Ghi rõ nguồn: Bảng thành phần thực phẩm Việt Nam, USDA... |

> **Vì sao vi chất cho phép NULL còn macro thì không.** Mục tiêu đề tài nêu "calo, protein, vi chất", nhưng thực tế thu thập dữ liệu 300–500 món Việt Nam thì số liệu vi chất khuyết khá nhiều. Cho `NULL` là trung thực; bước tiền xử lý của ML sẽ xử lý dữ liệu khuyết theo phương pháp đã trình bày ở Chương 1. Ngược lại 4 trường macro là bắt buộc vì thiếu chúng thì Bước 4 không chạy được.

> `data_source` là cột nhỏ nhưng đắt giá khi bảo vệ — hội đồng thường hỏi "số liệu dinh dưỡng em lấy ở đâu".

---

## 4.4 `tags` — Từ điển nhãn món ăn

```sql
CREATE TABLE tags (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(50)  NOT NULL UNIQUE,
    name_vi     VARCHAR(100) NOT NULL,
    tag_type    ENUM('allergen','diet','nutrition','taste') NOT NULL,
    description VARCHAR(255) NULL,
    INDEX idx_tag_type (tag_type)
) ENGINE=InnoDB;
```

**Dữ liệu mẫu theo từng loại:**

| tag_type | code | name_vi | Dùng làm gì |
|---|---|---|---|
| `allergen` | `contains_seafood` | Có hải sản | Ràng buộc cứng — dị ứng |
| `allergen` | `contains_peanut` | Có đậu phộng | Ràng buộc cứng |
| `allergen` | `contains_egg` | Có trứng | Ràng buộc cứng |
| `allergen` | `contains_dairy` | Có sữa / chế phẩm sữa | Ràng buộc cứng |
| `allergen` | `contains_gluten` | Có gluten | Ràng buộc cứng |
| `allergen` | `contains_soy` | Có đậu nành | Ràng buộc cứng |
| `diet` | `vegetarian` | Món chay | Ràng buộc cứng |
| `diet` | `vegan` | Món thuần chay | Ràng buộc cứng |
| `nutrition` | `low_sodium` | Ít natri | Quy tắc bệnh lý |
| `nutrition` | `low_sugar` | Ít đường | Quy tắc bệnh lý |
| `nutrition` | `high_protein` | Giàu đạm | Vector đặc trưng ML |
| `nutrition` | `high_fiber` | Giàu chất xơ | Vector đặc trưng ML |
| `taste` | `salty` | Mặn | **Vector đặc trưng ML — khẩu vị** |
| `taste` | `sweet` | Ngọt | Vector đặc trưng ML |
| `taste` | `sour` | Chua | Vector đặc trưng ML |
| `taste` | `fatty` | Béo | Vector đặc trưng ML |
| `taste` | `light` | Thanh đạm | Vector đặc trưng ML |

**Vì sao dùng nhãn dị ứng thay vì bảng nguyên liệu chi tiết.**

Phương án chính xác nhất là dựng bảng `ingredients` + `food_ingredients`, rồi truy dị ứng đến từng nguyên liệu. Nhưng với 300–500 món, đó là khối lượng nhập liệu rất lớn và nằm ngoài phạm vi khả thi của đồ án.

Phương án đã chọn: khoảng 6–8 nhãn dị nguyên phổ biến gắn trực tiếp lên món. Đủ chính xác cho các nhóm dị ứng thường gặp, chi phí nhập liệu chỉ bằng một phần nhỏ.

Cái mất là độ chi tiết với các dị ứng hiếm. **Ghi nhận thẳng vào phần hạn chế của báo cáo**, và đề xuất bảng nguyên liệu như hướng phát triển — như vậy vừa trung thực vừa cho thấy đã cân nhắc phương án.

---

## 4.5 `food_tags` — Gán nhãn cho món

```sql
CREATE TABLE food_tags (
    food_id BIGINT UNSIGNED NOT NULL,
    tag_id  INT UNSIGNED    NOT NULL,
    PRIMARY KEY (food_id, tag_id),
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)  REFERENCES tags(id),
    INDEX idx_tag (tag_id)
) ENGINE=InnoDB;
```

> Dùng khóa chính phức hợp `(food_id, tag_id)` thay cho cột `id` tự tăng — bảng thuần quan hệ N:M, không cần khóa thay thế. Chỉ mục `idx_tag` phục vụ Bộ lọc F1 truy vấn ngược từ nhãn ra món.

---

# 5. Nhóm Quy tắc dinh dưỡng

## 5.1 `condition_rules` — Bộ quy tắc ràng buộc (Bộ lọc F1)

Đây là bảng quan trọng nhất về mặt học thuật — nó **là** sản phẩm "bộ quy tắc ràng buộc dinh dưỡng" mà đề cương yêu cầu nộp.

```sql
CREATE TABLE condition_rules (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    condition_id INT UNSIGNED NOT NULL,
    rule_type    ENUM('exclude_tag','require_tag','nutrient_limit') NOT NULL,

    -- Dùng khi rule_type = 'exclude_tag' hoặc 'require_tag'
    tag_id       INT UNSIGNED NULL,

    -- Dùng khi rule_type = 'nutrient_limit'
    nutrient     ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g',
                      'sugar_g','sodium_mg','cholesterol_mg','purine_mg') NULL,
    comparator   ENUM('lte','gte') NULL,
    threshold    DECIMAL(8,2) NULL,
    scope        ENUM('per_serving','per_meal','per_day') NOT NULL DEFAULT 'per_serving',

    severity_min ENUM('mild','moderate','severe') NOT NULL DEFAULT 'mild',
    is_hard      TINYINT(1)   NOT NULL DEFAULT 1,
    penalty      DECIMAL(4,3) NULL,
    note         VARCHAR(255) NULL,

    FOREIGN KEY (condition_id) REFERENCES conditions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)       REFERENCES tags(id),
    INDEX idx_condition (condition_id)
) ENGINE=InnoDB;
```

| Cột | Mô tả |
|---|---|
| `rule_type` | Ba dạng quy tắc: loại món có nhãn / chỉ giữ món có nhãn / áp ngưỡng dinh dưỡng |
| `scope` | Ngưỡng áp cho một khẩu phần, một bữa, hay cả ngày |
| `severity_min` | Quy tắc chỉ kích hoạt khi mức độ bệnh của người dùng đạt từ mức này trở lên |
| `is_hard` | `1` = ràng buộc cứng, loại bỏ ở **Bước 2**. `0` = ràng buộc mềm, trừ điểm ở **Bước 3** |
| `penalty` | Hệ số trừ điểm khi `is_hard = 0` |

**Dữ liệu mẫu — đây chính là bảng sẽ in vào báo cáo:**

| Bệnh lý | rule_type | Nhãn / Chất | So sánh | Ngưỡng | scope | is_hard |
|---|---|---|---|---|---|---|
| Đái tháo đường | `nutrient_limit` | `sugar_g` | `lte` | 10.00 | per_serving | 1 |
| Đái tháo đường | `nutrient_limit` | `carbs_g` | `lte` | 60.00 | per_meal | 0 |
| Tăng huyết áp | `nutrient_limit` | `sodium_mg` | `lte` | 600.00 | per_serving | 1 |
| Tăng huyết áp | `nutrient_limit` | `sodium_mg` | `lte` | 2000.00 | per_day | 1 |
| Rối loạn mỡ máu | `nutrient_limit` | `cholesterol_mg` | `lte` | 200.00 | per_serving | 1 |
| Rối loạn mỡ máu | `nutrient_limit` | `fat_g` | `lte` | 20.00 | per_serving | 0 |
| Bệnh thận | `nutrient_limit` | `protein_g` | `lte` | 15.00 | per_serving | 1 |
| Bệnh thận | `nutrient_limit` | `sodium_mg` | `lte` | 500.00 | per_serving | 1 |
| Gút | `nutrient_limit` | `purine_mg` | `lte` | 100.00 | per_serving | 1 |
| Dị ứng hải sản | `exclude_tag` | `contains_seafood` | — | — | per_serving | 1 |
| Dị ứng đậu phộng | `exclude_tag` | `contains_peanut` | — | — | per_serving | 1 |
| Không dung nạp lactose | `exclude_tag` | `contains_dairy` | — | — | per_serving | 1 |
| Ăn chay | `require_tag` | `vegetarian` | — | — | per_serving | 1 |
| Ăn thuần chay | `require_tag` | `vegan` | — | — | per_serving | 1 |

> **Giá trị ngưỡng trong bảng trên là số minh họa.** Khi triển khai thật phải tra theo tài liệu *Nhu cầu dinh dưỡng khuyến nghị cho người Việt Nam (NIN 2016)* — chính là tài liệu ban đầu ghi trong file nhiệm vụ — và ghi rõ nguồn của từng ngưỡng trong cột `note`.

**Vì sao tách `is_hard`.** Không phải quy tắc dinh dưỡng nào cũng tuyệt đối. "Không được ăn tôm khi dị ứng hải sản" là cứng. "Nên hạn chế chất béo khi rối loạn mỡ máu" là mềm — nếu xử lý như ràng buộc cứng, tập ứng viên sẽ bị thu hẹp quá mức và Bước 4 không tìm nổi tổ hợp thỏa hạn mức năng lượng. Cột này cho phép diễn đạt đúng sự khác biệt đó.

---

## 5.2 `rda_reference` — Nhu cầu dinh dưỡng khuyến nghị

```sql
CREATE TABLE rda_reference (
    id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    gender    ENUM('male','female','all') NOT NULL,
    age_min   TINYINT UNSIGNED NOT NULL,
    age_max   TINYINT UNSIGNED NOT NULL,
    nutrient  VARCHAR(30)  NOT NULL,
    rda_value DECIMAL(8,2) NOT NULL,
    unit      VARCHAR(10)  NOT NULL,
    source    VARCHAR(150) NOT NULL DEFAULT 'NIN Vietnamese RDAs 2016',

    UNIQUE KEY uq_rda (gender, age_min, age_max, nutrient),
    INDEX idx_lookup (gender, age_min, age_max)
) ENGINE=InnoDB;
```

Bảng tra cứu tĩnh, nạp một lần từ tài liệu NIN 2016. Dùng để đối chiếu thực đơn sinh ra có đáp ứng nhu cầu vi chất hay không, và để hiển thị "bạn đã nạp đủ bao nhiêu phần trăm nhu cầu canxi hôm nay" ở màn hình thống kê.

---

# 6. Nhóm Tương tác và Phản hồi

## 6.1 `interactions` — Lịch sử vuốt

```sql
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

    INDEX idx_user_time   (user_id, interacted_at),
    INDEX idx_user_food   (user_id, food_id),
    INDEX idx_food        (food_id),
    INDEX idx_session     (session_id),
    INDEX idx_recommendation (recommendation_id)
) ENGINE=InnoDB;
```

| action | Cử chỉ | Ý nghĩa | Trọng số Rocchio | Nhãn ML |
|---|---|---|---|---|
| `like` | Vuốt phải | Thích | +1.0 | 0.90 |
| `dislike` | Vuốt trái | Không thích | −1.0 | 0.00 |
| `neutral` | Vuốt lên | Bình thường | 0.0 | 0.50 |
| `unknown` | Vuốt xuống | Chưa biết | Loại khỏi tổng | Loại khỏi tập huấn luyện |

**Ba cột mới so với thiết kế cũ, mỗi cột giải quyết một vấn đề cụ thể:**

| Cột | Vấn đề nó giải quyết |
|---|---|
| `session_type` | Phân biệt vuốt onboarding với vuốt trong quá trình dùng. Backend đếm số lượt `onboarding` để biết khi nào kết thúc phiên thăm dò và chuyển người dùng sang Giai đoạn 1 |
| `context_meal_type` | Sở thích phụ thuộc bữa ăn. Cùng một người thích phở buổi sáng nhưng không muốn ăn phở lúc 8 giờ tối. `NULL` với phiên onboarding vì lúc đó chưa gắn với bữa cụ thể |
| `recommendation_id` | **Bắt buộc để tính Precision@K và NDCG.** Không có liên kết ngược này thì không biết lượt vuốt nào ứng với gợi ý nào, và mọi độ đo xếp hạng đều không tính được |

> Bảng vẫn **không có** ràng buộc `UNIQUE (user_id, food_id)` — người dùng có thể vuốt lại cùng một món ở thời điểm khác, và lịch sử thay đổi khẩu vị theo thời gian chính là dữ liệu quý.

### Dư thừa có kiểm soát — chỗ duy nhất còn tồn tại trong lược đồ

Khi `recommendation_id` khác `NULL`, hai cột `user_id` và `food_id` lặp lại thông tin đã có ở `recommendations`. Đây là **đường đi vòng** (hai đường đi phân biệt từ `interactions` tới `users` và tới `foods`).

Ba chỗ trong lược đồ từng mắc lỗi này; hai chỗ kia đã được sửa bằng cách bỏ cột khóa ngoại cho phép `NULL` (xem `food_diary` Mục 6.2 và `feedbacks` Mục 6.3). Riêng chỗ này **cố ý giữ lại**, vì không bỏ được cột nào:

| Cột | Vì sao không bỏ được |
|---|---|
| `user_id`, `food_id` | `recommendation_id` cho phép `NULL` — lượt vuốt trong phiên onboarding không xuất phát từ gợi ý nào |
| `recommendation_id` | Bắt buộc để tính Precision@K và NDCG. Không khôi phục được bằng khóa tự nhiên, vì phải truy "gợi ý gần nhất trước thời điểm vuốt" — mơ hồ khi cùng một món được gợi ý nhiều lần |

**Phương án chuẩn hóa triệt để đã được cân nhắc và bác bỏ:** ghi mọi thẻ món hiển thị — kể cả 30 món onboarding — vào `recommendations` để `recommendation_id` thành `NOT NULL`, rồi bỏ `user_id`/`food_id`. Bác bỏ vì `recommendations` chứa các cột kết quả chấm điểm (`score`, `score_ml`, `alpha`, `model_id`), mà món thăm dò onboarding được chọn theo nguyên tắc **cực đại hóa độ đa dạng chứ không theo điểm ưa thích** — toàn bộ các cột đó sẽ là `NULL`. Gộp hai khái niệm khác nhau vào một bảng để tránh một cột dư thừa là đánh đổi tệ hơn.

**Bất biến mà Backend phải bảo đảm:**

```text
Nếu interactions.recommendation_id IS NOT NULL thì
    interactions.user_id = recommendations.user_id
    interactions.food_id = recommendations.food_id
```

Backend luôn ghi cả ba cột trong cùng một thao tác nên khó lệch. MySQL không hỗ trợ khóa ngoại có điều kiện, nên nếu muốn ràng buộc ở tầng CSDL thì phải dùng `TRIGGER BEFORE INSERT`.

---

## 6.2 `food_diary` — Nhật ký ăn uống

```sql
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

    INDEX idx_compliance (user_id, ate_on, meal_type, food_id),
    INDEX idx_user_food  (user_id, food_id, ate_on)
) ENGINE=InnoDB;
```

Bảng này phục vụ ba mục đích khác nhau:

| Vai trò | Chi tiết |
|---|---|
| **Sản phẩm bắt buộc** | Cả đề cương lẫn file nhiệm vụ đều liệt kê "ghi nhật ký ăn uống" |
| **Nhãn mạnh cho ML** | Đã ăn thật đáng tin hơn nhiều so với vuốt thích trên màn hình |
| **Đầu vào Bước 2** | Chỉ mục `idx_user_food` phục vụ điều kiện "loại món đã ăn trong N ngày gần đây" |

### Vì sao không có cột `meal_plan_item_id`

Bảng này **ghi lại mọi thứ người dùng ăn**, kể cả món không nằm trong thực đơn gợi ý — ổ bánh mì mua dọc đường, ly trà sữa buổi chiều. Với những dòng đó không tồn tại `meal_plan_item` nào tương ứng.

Một thiết kế trước đó có cột `meal_plan_item_id` cho phép `NULL` để liên kết dòng nhật ký với món đã gợi ý. Cột đó tạo ra **đường đi vòng**: `food_diary` có hai đường tới `foods` (trực tiếp qua `food_id`, và gián tiếp qua `meal_plan_items.food_id`), tương tự với `users`. Khi cột khác `NULL`, hai đường mô tả cùng một sự thật và có thể mâu thuẫn.

Hướng sửa **không phải** là bỏ `food_id` — làm vậy sẽ không ghi nổi món ăn ngoài kế hoạch, kéo theo nhật ký mất tác dụng, thống kê năng lượng sai, và mất nguồn nhãn `diary` cho ML. Hướng sửa đúng là **bỏ cột khóa ngoại cho phép `NULL`**, tức `meal_plan_item_id`.

### Tỷ lệ tuân thủ thực đơn tính bằng ghép theo khóa tự nhiên

Một món được coi là "ăn đúng gợi ý" khi trùng cả bốn yếu tố: cùng người dùng, cùng ngày, cùng bữa, cùng món. Chỉ mục `idx_compliance` được dựng đúng theo thứ tự bốn cột đó nên phép ghép chạy nhanh. Truy vấn đầy đủ xem Mục 8.4.

Bộ bốn `(user_id, ate_on, meal_type, food_id)` là duy nhất trong một thực đơn, vì Bước 4 đã có ràng buộc *"không hai món cùng nhóm thực phẩm trong một bữa"* và *"không lặp món đã xuất hiện trong ngày"*.

> Trường hợp biên: hệ thống gợi ý phở cho bữa sáng nhưng người dùng ăn phở vào bữa tối — phép ghép tính là "không tuân thủ". Đó chính là kết luận đúng, vì họ đã không ăn theo thực đơn được lập.

---

## 6.3 `feedbacks` — Đánh giá sau khi ăn

```sql
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
```

Đây là **nguồn nhãn có độ tin cậy cao nhất** trong toàn hệ thống. Bảng thống nhất nhãn ở Mục 7.4 gán trọng số mẫu 1.0 cho nguồn này.

### Vì sao không có cột `ate_at` và không có `food_diary_id`

Thiết kế ban đầu có cột `ate_at` lưu ngày ăn thực tế. Cột đó bị bỏ vì trùng với `food_diary.ate_on`.

Bản sửa sau đó thay `ate_at` bằng khóa ngoại `food_diary_id` cho phép `NULL`. Nhưng cột này mắc **đúng lỗi đường đi vòng** như `food_diary.meal_plan_item_id` — và còn nặng hơn: nó tạo ra tới **bốn đường đi** từ `feedbacks` tới `foods`, do thừa hưởng cả đường vòng của `food_diary`.

Cột `food_diary_id` phải cho phép `NULL` vì người dùng có thể đánh giá một món **mà không ghi nhật ký**. Khi đó `user_id` và `food_id` là nguồn duy nhất, không bỏ được. Nên cột bị bỏ là `food_diary_id`.

Về mặt nghiệp vụ điều này cũng đúng hơn: **đánh giá là ý kiến về một món ăn, không phải về một lần ăn cụ thể.** Nhãn mà ML cần là cặp `(người dùng, món ăn) → điểm`, không quan tâm lần ăn nào.

Khi cần lọc riêng những đánh giá của món người dùng đã thực sự ăn, ghép theo `(user_id, food_id)`:

```sql
SELECT fb.*
FROM feedbacks fb
WHERE EXISTS (
    SELECT 1 FROM food_diary fd
    WHERE fd.user_id = fb.user_id AND fd.food_id = fb.food_id
);
```

> Có thể cân nhắc thêm `UNIQUE (user_id, food_id)` để mỗi người chỉ có một đánh giá cho mỗi món. Hiện chưa đặt, để người dùng đánh giá lại khi khẩu vị thay đổi — bước dựng tập huấn luyện sẽ lấy đánh giá gần nhất.

---

## 6.4 `recommendations` — Nhật ký gợi ý

```sql
CREATE TABLE recommendations (
    id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    batch_id          CHAR(36) NOT NULL,
    user_id           BIGINT UNSIGNED NOT NULL,
    food_id           BIGINT UNSIGNED NOT NULL,
    context_meal_type ENUM('breakfast','lunch','dinner','snack') NULL,

    -- ══ Điểm số, tách theo từng thành phần ══
    score             DECIMAL(6,4) NOT NULL,
    score_content     DECIMAL(6,4) NULL,
    score_ml          DECIMAL(6,4) NULL,
    alpha             DECIMAL(4,3) NULL,

    rank_position     SMALLINT UNSIGNED NULL,
    source            ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id          INT UNSIGNED NULL,

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
```

| Cột | Mô tả |
|---|---|
| `batch_id` | Nhóm toàn bộ món trong **một lần gợi ý**. Bắt buộc để tính các độ đo `@K` |
| `score_content` / `score_ml` / `alpha` | Ba thành phần của công thức trộn, lưu tách riêng |
| `was_interacted` | Người dùng có vuốt món này không — **nguồn mẫu âm cho ML** |
| `was_selected` | Món có được đưa vào thực đơn cuối cùng không (sau Bước 4) |

**Vì sao tách `score_content`, `score_ml` và `alpha` thành ba cột riêng.**

Công thức chuyển tiếp là `score = α · score_ml + (1 − α) · score_content`. Nếu chỉ lưu `score` tổng thì không thể phân tích ngược. Lưu tách ba cột cho phép trả lời bằng truy vấn những câu hỏi mà hội đồng rất dễ hỏi:

- Thành phần học máy đóng góp thêm bao nhiêu so với thuần tương đồng nội dung?
- Mốc `n_min`, `n_max` chọn đã hợp lý chưa?
- Ở vùng chuyển tiếp, hai thành phần có mâu thuẫn nhau không?

Đây là dữ liệu thực nghiệm gần như miễn phí — chỉ tốn ba cột.

> **Giữ nguyên `was_interacted` từ thiết kế cũ.** Cột này ban đầu nhìn có vẻ chỉ để thống kê, nhưng thực ra nó là **mỏ mẫu âm** của mô hình. Người dùng chủ yếu để lại tín hiệu dương, và không có mẫu âm thì mô hình sẽ học ra "món nào cũng thích".

---

# 7. Nhóm Thực đơn và Machine Learning

## 7.1 `meal_plans` — Thực đơn theo ngày (bảng cha)

```sql
CREATE TABLE meal_plans (
    id                     BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id                BIGINT UNSIGNED NOT NULL,
    plan_date              DATE NOT NULL,

    -- ══ Hạn mức từ Bước 1, chụp lại tại thời điểm sinh thực đơn ══
    target_calories_kcal   SMALLINT UNSIGNED NOT NULL,
    target_protein_g       DECIMAL(6,2) NOT NULL,
    target_carbs_g         DECIMAL(6,2) NOT NULL,
    target_fat_g           DECIMAL(6,2) NOT NULL,

    -- ══ Kết quả thực tế của tổ hợp Bước 4 đã chọn ══
    -- NULL = chưa chạy xong Bước 4.
    -- TUYỆT ĐỐI KHÔNG dùng DEFAULT 0: số 0 là giá trị hợp lệ về mặt số học,
    -- sẽ khiến calorie_deviation_pct tính ra −100% ngay khi vừa tạo dòng.
    actual_calories_kcal   DECIMAL(7,2) NULL,
    actual_protein_g       DECIMAL(6,2) NULL,
    actual_carbs_g         DECIMAL(6,2) NULL,
    actual_fat_g           DECIMAL(6,2) NULL,

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
    INDEX idx_source (generation_source)
) ENGINE=InnoDB;
```

**Đây là thay đổi lớn nhất so với thiết kế cũ.** Bảng `meal_plans` cũ thực chất là danh sách món rời — mỗi dòng một món, không có bảng cha. Hậu quả là **không lưu được** tổng năng lượng của thực đơn, độ lệch so với hạn mức, mô hình nào đã sinh ra nó, hay người dùng có chấp nhận không.

| Cột | Vì sao cần |
|---|---|
| `target_*` | Chụp lại hạn mức **tại thời điểm sinh**. Người dùng giảm cân thì hạn mức đổi, nhưng thực đơn cũ phải giữ hạn mức cũ để đánh giá công bằng |
| `actual_*` | Tổng dinh dưỡng thực tế của tổ hợp Bước 4 đã chọn |
| `calorie_deviation_pct` | **Cột tính tự động.** Đề cương yêu cầu chứng minh sai lệch không quá 10 % — đây là chỗ lấy con số đó. `NULL` khi chưa chạy xong Bước 4 |
| `total_preference_score` | Tổng `Σ score` của thực đơn, dùng so sánh phương án học máy với phương án chỉ dùng quy tắc |
| `generation_source` | Ghi rõ thực đơn này sinh bằng phương pháp nào — nền tảng cho toàn bộ phần so sánh ở Chương 3 |

> `calorie_deviation_pct` là cột `GENERATED ... STORED` nên MySQL tự tính và tự cập nhật, đồng thời **đánh chỉ mục được** nếu cần lọc nhanh các thực đơn vi phạm ngưỡng. `chk_target_positive` chặn lỗi chia cho 0.

### Vì sao bốn cột `actual_*` phải cho phép `NULL`

Đây là một cái bẫy đáng chú ý. Nếu khai báo `NOT NULL DEFAULT 0`, thì ngay khi Backend chạy xong Bước 1 và tạo dòng `meal_plans` với `target_calories_kcal = 2000`, MySQL lập tức tính:

```text
calorie_deviation_pct = 100 × (0 − 2000) / 2000 = −100.00
```

Dòng đó mang **độ lệch −100 %** — một con số hoàn toàn bịa, và nó **không báo lỗi gì cả**. Các truy vấn thống kê ở Mục 8 sẽ gom cả những dòng này vào, kéo tụt kết quả trung bình. Bạn chỉ phát hiện khi thấy số liệu trong báo cáo vô lý, mà lúc đó thì đã muộn.

Nguyên nhân gốc: dùng số `0` để diễn đạt *"chưa có dữ liệu"*, trong khi `0` là một giá trị hợp lệ về mặt số học.

Cho phép `NULL` thì mọi phép tính có `NULL` đều cho `NULL`, nên `calorie_deviation_pct` cũng tự động `NULL` — đúng nghĩa "chưa xác định". Thêm nữa các hàm gộp `AVG()`, `MAX()`, `SUM()` **tự bỏ qua `NULL`**, nên truy vấn thống kê tự khắc đúng.

> Nhưng phải dùng `COUNT(calorie_deviation_pct)` chứ **không** dùng `COUNT(*)` làm mẫu số — `COUNT(*)` đếm cả dòng `NULL`, làm tỷ lệ đạt yêu cầu bị báo thấp hơn thực tế. Xem Mục 8.1.

---

## 7.2 `meal_plan_items` — Món trong thực đơn (bảng con)

```sql
CREATE TABLE meal_plan_items (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    meal_plan_id        BIGINT UNSIGNED NOT NULL,
    food_id             BIGINT UNSIGNED NOT NULL,
    meal_type           ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    serving_size_g      SMALLINT UNSIGNED NOT NULL DEFAULT 100,

    predicted_score     DECIMAL(6,4) NULL,
    status              ENUM('suggested','kept','replaced','eaten','skipped')
                            NOT NULL DEFAULT 'suggested',
    replaced_by_food_id BIGINT UNSIGNED NULL,
    replaced_at         DATETIME NULL,
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
```

| Cột | Vì sao cần |
|---|---|
| `status` | **Nguồn phản hồi ngầm định** mà đề cương gọi là "món được chọn, món bị thay thế" |
| `replaced_by_food_id` | Người dùng đổi sang món nào — tín hiệu kép: chê món cũ, thích món mới |
| `is_exploration` | Đánh dấu món do chiến lược thăm dò ε-greedy chèn vào, không phải do điểm cao |
| `predicted_score` | Điểm dự đoán lúc sinh, để về sau đối chiếu với phản hồi thực tế |

> **`is_exploration` phục vụ một thí nghiệm riêng.** Nó cho phép trả lời: món thăm dò có bị người dùng thay thế nhiều hơn món gợi ý bình thường không, và tỷ lệ ε bao nhiêu là hợp lý. Chỉ tốn một cột `TINYINT`, nhưng cho hẳn một mục thực nghiệm trong Chương 3.

---

## 7.3 `user_preference_profiles` — Hồ sơ sở thích (vector trọng số)

```sql
CREATE TABLE user_preference_profiles (
    user_id         BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    feature_version VARCHAR(20)   NOT NULL,
    weights         JSON          NOT NULL,
    sum_abs_weight  DECIMAL(10,4) NOT NULL DEFAULT 0,
    n_signals       INT UNSIGNED  NOT NULL DEFAULT 0,
    stage           ENUM('cold','content','hybrid','ml') NOT NULL DEFAULT 'cold',
    alpha           DECIMAL(4,3)  NOT NULL DEFAULT 0,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
```

Đây là hiện thực của **hồ sơ sở thích dạng vector trọng số** mà đề cương nêu đích danh, tính theo thuật toán Rocchio.

| Cột | Mô tả |
|---|---|
| `weights` | Vector `p_u`, lưu dạng JSON: `{"protein_g": 0.31, "cat_mon_nuoc": 0.12, "taste_spicy": -0.44, ...}` |
| `sum_abs_weight` | Tổng `Σ|w|` — **bắt buộc phải lưu**, xem giải thích bên dưới |
| `n_signals` | Số tín hiệu đã tích lũy, dùng tính hệ số trộn `α` |
| `stage` | Giai đoạn hiện tại của người dùng |
| `alpha` | Hệ số trộn đã hiệu lực, lưu sẵn để Backend không phải tính lại mỗi request |

### Vì sao bắt buộc lưu `sum_abs_weight`

Công thức Rocchio:

```text
        Σ w(a_i) · v_i          S
p_u = ──────────────────  =  ─────
        Σ |w(a_i)|             W
```

Cập nhật khi có tương tác mới, **không cần quét lại toàn bộ lịch sử**:

```text
S_mới = S_cũ + w_mới · v_mới          với  S_cũ = weights × sum_abs_weight
W_mới = W_cũ + |w_mới|

weights        ← S_mới / W_mới
sum_abs_weight ← W_mới
```

Chi phí `O(d)` cho mỗi lượt tương tác, `d` là số chiều đặc trưng.

**Nếu chỉ lưu `weights` mà không lưu `W`, phép cập nhật tăng dần này không khôi phục được `S`** — buộc phải đọc lại toàn bộ `interactions` và tính lại từ đầu mỗi lần người dùng vuốt. Một cột `DECIMAL` đổi lấy việc đó.

> **`stage` và `alpha` là dữ liệu dẫn xuất, cố ý lưu dư.** Về lý thuyết cả hai suy ra được từ `n_signals`. Nhưng lưu sẵn giúp gỡ lỗi dễ hơn nhiều — nhìn thẳng vào bảng là biết người dùng đang ở giai đoạn nào, không phải đọc ngược logic trong mã nguồn.

---

## 7.4 `ml_training_samples` — Tập dữ liệu huấn luyện đã đóng băng

```sql
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
    collected_at     DATETIME NOT NULL,
    profile_snapshot JSON NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_label CHECK (label BETWEEN 0 AND 1),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    INDEX idx_dataset_split (dataset_version, split),
    INDEX idx_dataset_user  (dataset_version, user_id),
    INDEX idx_collected     (collected_at)
) ENGINE=InnoDB;
```

### Bảng quy đổi nhãn từ các nguồn tín hiệu

| `source` | Bảng gốc | `label` | `sample_weight` |
|---|---|---|---|
| `feedback` (5 sao) | `feedbacks` | 1.000 | 1.0 |
| `feedback` (4 sao) | `feedbacks` | 0.750 | 1.0 |
| `feedback` (3 sao) | `feedbacks` | 0.500 | 1.0 |
| `feedback` (2 sao) | `feedbacks` | 0.250 | 1.0 |
| `feedback` (1 sao) | `feedbacks` | 0.000 | 1.0 |
| `diary` | `food_diary` | 0.800 | 0.9 |
| `swipe_onboarding` / `swipe_explore` (like) | `interactions` | 0.900 | 0.7 |
| `swipe_onboarding` / `swipe_explore` (neutral) | `interactions` | 0.500 | 0.7 |
| `swipe_onboarding` / `swipe_explore` (dislike) | `interactions` | 0.000 | 0.7 |
| `plan_kept` | `meal_plan_items` | 0.700 | 0.6 |
| `plan_replaced` | `meal_plan_items` | 0.150 | 0.6 |
| `impression_neg` | `recommendations` (`was_interacted = 0`) | 0.300 | 0.3 |
| `random_neg` | Lấy ngẫu nhiên từ món chưa hiển thị | 0.100 | 0.2 |
| — | `interactions` (`action = 'unknown'`) | **Loại khỏi tập** | — |

### Vì sao phải đóng băng tập dữ liệu vào bảng

Nếu mỗi lần huấn luyện lại tính nhãn trực tiếp từ các bảng gốc, thì **con số Precision@K trong báo cáo sẽ khác nhau ở mỗi lần chạy** — vì dữ liệu gốc liên tục có thêm tương tác mới. Khi hội đồng hỏi "vì sao chạy lại ra số khác", không có câu trả lời.

`dataset_version` gắn chặt một tập dữ liệu cố định với một mô hình cố định và một bộ kết quả cố định. Thực nghiệm tái lập được.

### Vì sao cần `profile_snapshot`

Đặc trưng người dùng gồm BMI, tuổi, mục tiêu sức khỏe. Nhưng người dùng **giảm 5 kg trong ba tháng thử nghiệm**. Nếu ghép BMI *hiện tại* với nhãn thu được *ba tháng trước*, mô hình học trên dữ liệu không bao giờ tồn tại — đây là một dạng rò rỉ dữ liệu.

`profile_snapshot` chụp lại hồ sơ tại đúng thời điểm phát sinh tín hiệu.

### Vì sao chia tập theo thời gian, không chia ngẫu nhiên

Hệ khuyến nghị có vòng lặp phản hồi: gợi ý hôm nay ảnh hưởng đến hành vi ngày mai. Chia ngẫu nhiên khiến mô hình được huấn luyện trên hành vi tương lai rồi đem kiểm thử trên quá khứ — kết quả đẹp giả tạo.

Cắt theo `collected_at`: `train` là tín hiệu trước mốc T, `test` là tín hiệu sau mốc T. Cột `fold` dành cho kiểm định chéo k-fold mà đề cương yêu cầu ở Chương 1.

---

## 7.5 `ml_models` — Đăng ký mô hình

```sql
CREATE TABLE ml_models (
    id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    version            VARCHAR(20) NOT NULL UNIQUE,
    algorithm          ENUM('logistic_regression','random_forest',
                            'gradient_boosting') NOT NULL,
    feature_version    VARCHAR(20) NOT NULL,
    dataset_version    VARCHAR(20) NOT NULL,

    hyperparams        JSON NULL,
    scaler_params      JSON NULL,
    feature_importance JSON NULL,

    n_train            INT UNSIGNED NOT NULL,
    n_test             INT UNSIGNED NOT NULL,
    artifact_path      VARCHAR(500) NOT NULL,
    is_active          TINYINT(1) NOT NULL DEFAULT 0,
    trained_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note               VARCHAR(255) NULL,

    INDEX idx_active (is_active)
) ENGINE=InnoDB;
```

| Cột | Mô tả |
|---|---|
| `scaler_params` | Tham số chuẩn hóa (min/max hoặc mean/std) **đóng băng tại lúc huấn luyện** |
| `feature_importance` | Độ quan trọng của từng đặc trưng — vẽ thẳng thành biểu đồ cho Chương 3 |
| `artifact_path` | Đường dẫn file `.joblib`. **Không lưu mô hình dạng BLOB trong CSDL** |

> **`scaler_params` là cột hay bị quên nhất và gây lỗi âm thầm nhất.** Lúc huấn luyện, đặc trưng được chuẩn hóa min-max theo min/max của tập huấn luyện. Lúc chấm điểm cho món mới, **phải dùng đúng bộ min/max đó**, không phải min/max của dữ liệu hiện tại. Nếu tính lại, cùng một món sẽ cho ra hai vector khác nhau ở hai thời điểm, và mô hình dự đoán sai mà không báo lỗi gì.

Cột `model_id` ở `recommendations` và `meal_plans` trỏ về bảng này. Thiết kế cũ có `model_version VARCHAR(20)` nhưng không có bảng nào để trỏ tới.

---

## 7.6 `ml_evaluations` — Kết quả đánh giá

```sql
CREATE TABLE ml_evaluations (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    model_id     INT UNSIGNED NOT NULL,
    variant      ENUM('ml','content_based','rule_based','popularity','hybrid') NOT NULL,
    metric       ENUM('precision','recall','ndcg','map','mae','rmse','f1','auc') NOT NULL,
    k_value      TINYINT UNSIGNED NULL,
    value        DECIMAL(8,5) NOT NULL,
    fold         TINYINT UNSIGNED NULL,
    evaluated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (model_id) REFERENCES ml_models(id) ON DELETE CASCADE,
    UNIQUE KEY uq_eval (model_id, variant, metric, k_value, fold)
) ENGINE=InnoDB;
```

**Cột `variant` là chìa khóa của toàn bộ phần thực nghiệm.** Đề cương yêu cầu *"so sánh với phương án khuyến nghị chỉ dựa trên quy tắc dinh dưỡng để làm rõ đóng góp của thành phần học máy"*.

Cách làm: chạy **cùng một tập kiểm thử** qua bốn nhánh khác nhau, ghi kết quả vào bốn dòng có `variant` khác nhau. Một câu `SELECT` là ra bảng so sánh hoàn chỉnh:

| variant | Ý nghĩa |
|---|---|
| `rule_based` | Chỉ dùng bộ quy tắc dinh dưỡng — **phương án đối chứng** |
| `popularity` | Chỉ xếp theo độ phổ biến chung — đối chứng đơn giản nhất |
| `content_based` | Chỉ dùng Rocchio + cosine — đo riêng đóng góp Giai đoạn 1 |
| `ml` | Mô hình học máy có giám sát |
| `hybrid` | Công thức trộn theo `α` |

`fold IS NULL` nghĩa là kết quả trên tập kiểm thử cuối; `fold` có giá trị là kết quả của một lần trong kiểm định chéo k-fold.

---

# 8. Truy vấn sinh số liệu cho báo cáo

Toàn bộ số liệu định lượng của Chương 3 lấy được bằng truy vấn, không phải tính tay.

### 8.1 Độ lệch năng lượng — chứng minh yêu cầu ≤ 10 %

```sql
SELECT
    generation_source,
    COUNT(*)                                     AS so_thuc_don,
    COUNT(calorie_deviation_pct)                 AS so_thuc_don_da_sinh_xong,
    ROUND(AVG(ABS(calorie_deviation_pct)), 2)    AS do_lech_tb_pct,
    ROUND(MAX(ABS(calorie_deviation_pct)), 2)    AS do_lech_lon_nhat_pct,
    ROUND(100.0 * SUM(ABS(calorie_deviation_pct) <= 10)
                / COUNT(calorie_deviation_pct), 2) AS ty_le_dat_yeu_cau_pct
FROM meal_plans
GROUP BY generation_source;
```

> **Mẫu số phải là `COUNT(calorie_deviation_pct)`, không phải `COUNT(*)`.** `SUM()` bỏ qua `NULL` nhưng `COUNT(*)` thì đếm tất cả — dùng `COUNT(*)` sẽ làm mẫu số phồng lên và tỷ lệ đạt yêu cầu bị **báo thấp hơn thực tế**. Cột `so_thuc_don_da_sinh_xong` còn cho biết luôn có bao nhiêu thực đơn bị treo giữa chừng.

### 8.2 Bảng so sánh học máy với phương án chỉ dùng quy tắc

```sql
SELECT
    e.metric,
    e.k_value,
    MAX(CASE WHEN e.variant = 'rule_based'    THEN e.value END) AS chi_quy_tac,
    MAX(CASE WHEN e.variant = 'content_based' THEN e.value END) AS rocchio,
    MAX(CASE WHEN e.variant = 'ml'            THEN e.value END) AS hoc_may,
    MAX(CASE WHEN e.variant = 'hybrid'        THEN e.value END) AS lai_ghep
FROM ml_evaluations e
JOIN ml_models m ON m.id = e.model_id
WHERE m.is_active = 1
  AND e.fold IS NULL
GROUP BY e.metric, e.k_value
ORDER BY e.metric, e.k_value;
```

### 8.3 Precision@5 đo trực tiếp trên hệ thống đang chạy

```sql
SELECT
    r.source,
    COUNT(*)                                              AS so_goi_y,
    ROUND(SUM(i.action = 'like') / COUNT(*), 4)           AS precision_at_5
FROM recommendations r
LEFT JOIN interactions i ON i.recommendation_id = r.id
WHERE r.rank_position <= 5
GROUP BY r.source;
```

> Truy vấn này chỉ chạy được nhờ khóa ngoại `interactions.recommendation_id` đã bổ sung ở Mục 6.1.

### 8.4 Tỷ lệ tuân thủ thực đơn — chỉ số thực tế thuyết phục nhất

```sql
SELECT
    mp.generation_source,
    COUNT(*)                                                  AS so_mon_goi_y,
    SUM(fd.id IS NOT NULL)                                    AS so_mon_an_that,
    ROUND(100.0 * SUM(fd.id IS NOT NULL) / COUNT(*), 2)       AS ty_le_tuan_thu_pct,
    ROUND(100.0 * SUM(mpi.status = 'replaced') / COUNT(*), 2) AS ty_le_thay_the_pct
FROM meal_plan_items mpi
JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
LEFT JOIN food_diary fd
       ON fd.user_id   = mp.user_id
      AND fd.ate_on    = mp.plan_date
      AND fd.meal_type = mpi.meal_type
      AND fd.food_id   = mpi.food_id
GROUP BY mp.generation_source;
```

> Ghép theo **khóa tự nhiên** `(user_id, ate_on, meal_type, food_id)` thay vì theo khóa ngoại, vì `food_diary` không còn cột `meal_plan_item_id` — xem lý do ở Mục 6.2. Chỉ mục `idx_compliance` được dựng đúng theo thứ tự bốn cột này.

### 8.5 Hiệu quả của chiến lược thăm dò ε-greedy

```sql
SELECT
    is_exploration,
    COUNT(*)                                                AS so_mon,
    ROUND(100.0 * SUM(status = 'replaced') / COUNT(*), 2)   AS ty_le_bi_thay_the_pct,
    ROUND(AVG(predicted_score), 4)                          AS diem_du_doan_tb
FROM meal_plan_items
GROUP BY is_exploration;
```

---

# 9. Tổng hợp chỉ mục

| Bảng | Chỉ mục | Phục vụ |
|---|---|---|
| `users` | `email` (UNIQUE) | Đăng nhập |
| `health_profiles` | `user_id` (UNIQUE) | Tra cứu 1-1 |
| `user_conditions` | `(user_id, condition_id)` (UNIQUE) | Chặn trùng, tra bệnh lý của user |
| `condition_rules` | `condition_id` | **Bộ lọc F1** nạp quy tắc |
| `foods` | `(is_active, category_id)` | Lấy tập ứng viên ban đầu |
| `foods` | `dish_role` | Bước 4 — ràng buộc cấu trúc bữa ăn |
| `food_tags` | `(food_id, tag_id)` (PK) | Lấy nhãn của một món |
| `food_tags` | `tag_id` | **Bộ lọc F1** truy ngược từ nhãn ra món |
| `interactions` | `(user_id, interacted_at)` | Lịch sử gần nhất của user |
| `interactions` | `(user_id, food_id)` | Tương tác gần nhất với một món |
| `interactions` | `recommendation_id` | **Tính Precision@K, NDCG** |
| `interactions` | `session_id` | Đếm lượt vuốt onboarding |
| `food_diary` | `(user_id, ate_on, meal_type, food_id)` | Nhật ký theo ngày; **ghép khóa tự nhiên** tính tỷ lệ tuân thủ |
| `food_diary` | `(user_id, food_id, ate_on)` | **Bước 2** — lọc món đã ăn trong N ngày |
| `feedbacks` | `(food_id, rating)` | Điểm trung bình theo món |
| `recommendations` | `batch_id` | Nhóm một lần gợi ý để tính `@K` |
| `recommendations` | `(user_id, recommended_at)` | Gợi ý gần nhất |
| `meal_plans` | `(user_id, plan_date)` (UNIQUE) | Thực đơn theo ngày, chặn trùng |
| `meal_plan_items` | `(meal_plan_id, meal_type)` | Lấy món theo bữa |
| `ml_training_samples` | `(dataset_version, split)` | Nạp tập train / test |
| `ml_evaluations` | `(model_id, variant, metric, k_value, fold)` (UNIQUE) | Chặn ghi trùng kết quả |

---

# 10. Ghi chú thiết kế

| Quyết định | Lý do |
|---|---|
| `bmi` dùng `GENERATED COLUMN` | Tự đồng bộ khi cân nặng hoặc chiều cao thay đổi |
| `calorie_deviation_pct` dùng `GENERATED COLUMN` | Số liệu bắt buộc của đề cương, không để tính tay |
| Tách `meal_plans` thành cha–con | Thực đơn là một thực thể có thuộc tính riêng, không phải danh sách món rời |
| Tách `food_nutrition` khỏi `foods` | Dữ liệu dinh dưỡng có thể khuyết lúc đầu; giữ `foods` gọn |
| Vi chất cho phép `NULL`, macro thì không | Trung thực với thực tế thu thập dữ liệu; macro là bắt buộc để Bước 4 chạy được |
| Từ điển `tags` và `conditions` thay chuỗi tự do | Bảo đảm từ vựng nhất quán cho bước mã hóa one-hot |
| Nhãn dị nguyên thay bảng nguyên liệu | Đủ chính xác cho dị ứng phổ biến, chi phí nhập liệu thấp hơn nhiều lần. Ghi vào hạn chế và hướng phát triển |
| Bộ quy tắc F1 lưu thành dữ liệu | Là sản phẩm phải nộp, đồng thời là phương án đối chứng ở Chương 3 |
| `condition_rules.is_hard` | Phân biệt ràng buộc tuyệt đối với khuyến cáo nên hạn chế |
| `interactions` không `UNIQUE (user, food)` | Lịch sử thay đổi khẩu vị theo thời gian là dữ liệu quý |
| `users` không có `role` | Không có ứng dụng quản trị — nhập liệu bằng script seed, xem kết quả bằng truy vấn SQL |
| `users` không có `is_active` | Không có nghiệp vụ khóa tài khoản. Nhưng `foods.is_active` thì giữ, vai trò khác hẳn |
| `meal_plans.actual_*` cho phép `NULL` | Số `0` là giá trị hợp lệ về mặt số học, dùng nó để nói "chưa có dữ liệu" sẽ khiến cột dẫn xuất tính ra −100 % |
| `food_diary` không có `meal_plan_item_id` | Đường đi vòng tới `foods` và `users`. Thay bằng ghép khóa tự nhiên |
| `feedbacks` không có `food_diary_id` | Cùng lỗi đường đi vòng. Đánh giá là ý kiến về **món ăn**, không phải về một **lần ăn** |
| `interactions` giữ cả `user_id`, `food_id` lẫn `recommendation_id` | Dư thừa **có kiểm soát** — chỗ duy nhất còn lại, vì không bỏ được cột nào. Xem Mục 6.1 |
| `meal_plan_items` có hai FK cùng trỏ `foods` | Không phải dư thừa — `food_id` và `replaced_by_food_id` là hai **vai trò** khác nhau |
| `interactions.recommendation_id` | Không có cột này thì không tính được Precision@K và NDCG |
| `interactions.context_meal_type` | Sở thích món ăn phụ thuộc bữa ăn |
| Tách `score_content`, `score_ml`, `alpha` | Cho phép phân tích ngược hiệu quả của cơ chế chuyển tiếp |
| `user_preference_profiles.sum_abs_weight` | Bắt buộc để cập nhật vector Rocchio tăng dần |
| `ml_training_samples` đóng băng tập dữ liệu | Bảo đảm số liệu báo cáo tái lập được |
| `profile_snapshot` | Chống rò rỉ dữ liệu khi hồ sơ người dùng thay đổi theo thời gian |
| Chia tập theo thời gian | Chia ngẫu nhiên gây rò rỉ trong hệ có vòng lặp phản hồi |
| `ml_models.scaler_params` | Tham số chuẩn hóa phải đóng băng, nếu tính lại mô hình sẽ sai âm thầm |
| Mô hình lưu ra file, không lưu BLOB | CSDL không phải nơi chứa file nhị phân lớn |
| `ml_evaluations.variant` | Sinh trực tiếp bảng so sánh học máy với phương án chỉ dùng quy tắc |

---

# 11. Những gì cố ý KHÔNG đưa vào

Ghi lại để tránh phình lược đồ và để trả lời được khi hội đồng hỏi.

| Không có | Lý do |
|---|---|
| Bảng lưu vector đặc trưng của từng món | 300–500 món, Python tính lại trong vài chục mili-giây. Cache là tối ưu hóa sớm |
| Ma trận người dùng – món ăn | Đề tài không dùng lọc cộng tác |
| Bảng `ingredients` / `food_ingredients` | Chi phí nhập liệu vượt phạm vi đồ án. Ghi vào hướng phát triển |
| Bảng lịch sử hồ sơ sức khỏe | Đã thay bằng `profile_snapshot` trong `ml_training_samples` — gọn hơn, đủ dùng |
| Nhật ký huấn luyện chi tiết theo epoch | Mô hình cây quyết định không cần; tổng kết trong `ml_models` là đủ |
| Bảng embedding / vector database | Vector đặc trưng chỉ khoảng 30 chiều |
