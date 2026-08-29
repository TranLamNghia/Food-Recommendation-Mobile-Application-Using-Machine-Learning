# Thiết kế cơ sở dữ liệu — Hệ thống gợi ý món ăn cá nhân hóa

## 1. Tổng quan

**Hệ quản trị CSDL:** MySQL 8.x  
**Charset:** `utf8mb4` (hỗ trợ tiếng Việt và emoji)  
**Collation:** `utf8mb4_unicode_ci`

Cơ sở dữ liệu gồm **11 bảng** chia thành 4 nhóm chức năng:

| Nhóm | Bảng |
|---|---|
| 👤 Người dùng | `users`, `health_profiles`, `health_conditions` |
| 🍜 Món ăn | `food_categories`, `foods`, `food_nutrition`, `food_tags` |
| 🤝 Tương tác & Phản hồi | `interactions`, `feedbacks` |
| 🤖 ML & Kết quả | `recommendations`, `meal_plans` |

---

## 2. Sơ đồ quan hệ (ERD)

```
users ──────────────────────────────────────────────────────┐
  │                                                          │
  ├──< health_profiles                                       │
  ├──< health_conditions                                     │
  ├──< interactions >──── foods ──< food_nutrition           │
  ├──< feedbacks >──────── │                                 │
  ├──< recommendations >── │    ──< food_tags               │
  └──< meal_plans >──────── │   ──< food_categories          │
                            └───────────────────────────────┘
```

---

## 3. Chi tiết các bảng

---

### 3.1 `users` — Tài khoản người dùng

```sql
CREATE TABLE users (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email         VARCHAR(255)    NOT NULL UNIQUE,
    password_hash VARCHAR(255)    NOT NULL,
    display_name  VARCHAR(100)    NOT NULL,
    avatar_url    VARCHAR(500)    NULL,
    is_active     TINYINT(1)      NOT NULL DEFAULT 1,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | BIGINT UNSIGNED | Khóa chính, tự tăng |
| `email` | VARCHAR(255) | Email đăng nhập, unique |
| `password_hash` | VARCHAR(255) | Mật khẩu đã hash (bcrypt) |
| `display_name` | VARCHAR(100) | Tên hiển thị |
| `avatar_url` | VARCHAR(500) | Đường dẫn ảnh đại diện |
| `is_active` | TINYINT(1) | Trạng thái tài khoản |

---

### 3.2 `health_profiles` — Hồ sơ sức khỏe

```sql
CREATE TABLE health_profiles (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT UNSIGNED NOT NULL UNIQUE,
    gender          ENUM('male', 'female', 'other') NOT NULL,
    date_of_birth   DATE            NOT NULL,
    height_cm       DECIMAL(5,2)    NOT NULL,      -- e.g. 170.50
    weight_kg       DECIMAL(5,2)    NOT NULL,      -- e.g. 65.00
    bmi             DECIMAL(5,2)    GENERATED ALWAYS AS (weight_kg / ((height_cm / 100) * (height_cm / 100))) STORED,
    activity_level  ENUM('sedentary', 'light', 'moderate', 'active', 'very_active') NOT NULL DEFAULT 'moderate',
    goal            ENUM('lose_weight', 'maintain', 'gain_weight', 'healthy_eating') NOT NULL DEFAULT 'maintain',
    daily_calories_target SMALLINT UNSIGNED NULL,  -- kcal/ngày (tính hoặc nhập tay)
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

| Cột | Kiểu | Mô tả |
|---|---|---|
| `user_id` | BIGINT UNSIGNED | FK → users, 1-1 |
| `gender` | ENUM | Giới tính |
| `date_of_birth` | DATE | Ngày sinh (tính tuổi động) |
| `height_cm` | DECIMAL(5,2) | Chiều cao (cm) |
| `weight_kg` | DECIMAL(5,2) | Cân nặng (kg) |
| `bmi` | DECIMAL(5,2) | **Cột tính tự động** từ height và weight |
| `activity_level` | ENUM | Mức độ vận động |
| `goal` | ENUM | Mục tiêu sức khỏe |
| `daily_calories_target` | SMALLINT | Mục tiêu calo mỗi ngày |

> **Ghi chú:** `bmi` dùng `GENERATED ALWAYS AS ... STORED` — MySQL tự tính, không cần tính ở code.

---

### 3.3 `health_conditions` — Bệnh lý / Dị ứng

```sql
CREATE TABLE health_conditions (
    id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT UNSIGNED NOT NULL,
    condition_type ENUM('disease', 'allergy', 'intolerance') NOT NULL DEFAULT 'disease',
    condition_name VARCHAR(100)    NOT NULL,  -- e.g. 'diabetes', 'hypertension', 'gluten'
    note           VARCHAR(255)    NULL,
    created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_condition (user_id, condition_name)
);
```

| Cột | Kiểu | Mô tả |
|---|---|---|
| `condition_type` | ENUM | Loại: bệnh lý / dị ứng / không dung nạp |
| `condition_name` | VARCHAR(100) | Tên bệnh / chất dị ứng |

> **Ghi chú:** Bảng này cung cấp dữ liệu đầu vào cho **Bộ lọc F1** — loại bỏ các món không phù hợp trước khi đưa vào ML.

---

### 3.4 `food_categories` — Danh mục món ăn

```sql
CREATE TABLE food_categories (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    icon_url    VARCHAR(500) NULL
);
```

> Ví dụ: Món Bắc, Món Nam, Món chay, Đồ uống, Tráng miệng, Ăn sáng...

---

### 3.5 `foods` — Món ăn

```sql
CREATE TABLE foods (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    category_id  INT UNSIGNED    NOT NULL,
    name         VARCHAR(200)    NOT NULL,
    description  TEXT            NULL,
    image_url    VARCHAR(500)    NULL,
    origin       VARCHAR(100)    NULL,    -- Vùng miền: Hà Nội, Huế, Sài Gòn...
    is_active    TINYINT(1)      NOT NULL DEFAULT 1,
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES food_categories(id)
);
```

| Cột | Kiểu | Mô tả |
|---|---|---|
| `category_id` | INT UNSIGNED | FK → food_categories |
| `name` | VARCHAR(200) | Tên món ăn |
| `origin` | VARCHAR(100) | Vùng miền (phục vụ bộ lọc và gợi ý) |
| `is_active` | TINYINT(1) | Ẩn/hiện món ăn |

---

### 3.6 `food_nutrition` — Thông tin dinh dưỡng

```sql
CREATE TABLE food_nutrition (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id         BIGINT UNSIGNED NOT NULL UNIQUE,
    serving_size_g  SMALLINT UNSIGNED NOT NULL DEFAULT 100,  -- Khẩu phần tính dinh dưỡng (gram)
    calories_kcal   DECIMAL(7,2)    NOT NULL,
    protein_g       DECIMAL(6,2)    NOT NULL DEFAULT 0,
    carbs_g         DECIMAL(6,2)    NOT NULL DEFAULT 0,
    fat_g           DECIMAL(6,2)    NOT NULL DEFAULT 0,
    fiber_g         DECIMAL(6,2)    NOT NULL DEFAULT 0,
    sugar_g         DECIMAL(6,2)    NOT NULL DEFAULT 0,
    sodium_mg       DECIMAL(7,2)    NOT NULL DEFAULT 0,
    cholesterol_mg  DECIMAL(7,2)    NOT NULL DEFAULT 0,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
);
```

| Cột | Đơn vị | Mô tả |
|---|---|---|
| `serving_size_g` | gram | Khẩu phần chuẩn (thường 100g) |
| `calories_kcal` | kcal | Năng lượng |
| `protein_g` | g | Đạm |
| `carbs_g` | g | Carbohydrate |
| `fat_g` | g | Chất béo |
| `fiber_g` | g | Chất xơ |
| `sugar_g` | g | Đường |
| `sodium_mg` | mg | Natri (quan trọng cho người huyết áp cao) |
| `cholesterol_mg` | mg | Cholesterol (quan trọng cho tim mạch) |

---

### 3.7 `food_tags` — Nhãn món ăn (phục vụ Bộ lọc F1)

```sql
CREATE TABLE food_tags (
    id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id BIGINT UNSIGNED NOT NULL,
    tag     VARCHAR(50)     NOT NULL,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    UNIQUE KEY uq_food_tag (food_id, tag),
    INDEX idx_tag (tag)
);
```

> **Ví dụ giá trị `tag`:** `vegetarian`, `vegan`, `low_sugar`, `low_sodium`, `low_fat`, `high_protein`, `gluten_free`, `dairy_free`, `spicy`, `diabetic_friendly`, `heart_healthy`

> **Ghi chú:** Bộ lọc F1 sẽ query bảng này để loại bỏ các món không phù hợp với `health_conditions` của người dùng trước khi đưa vào ML ranking.

---

### 3.8 `interactions` — Lịch sử tương tác (vuốt)

```sql
CREATE TABLE interactions (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT UNSIGNED NOT NULL,
    food_id       BIGINT UNSIGNED NOT NULL,
    action        ENUM('like', 'dislike', 'neutral', 'unknown') NOT NULL,
    -- like    = vuốt phải  (Thích)
    -- dislike = vuốt trái  (Không thích)
    -- neutral = vuốt lên   (Bình thường)
    -- unknown = vuốt xuống (Chưa biết)
    session_id    VARCHAR(36)     NULL,   -- UUID phiên gợi ý (nhóm các lần vuốt liên tiếp)
    interacted_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    INDEX idx_user_interactions (user_id, interacted_at),
    INDEX idx_food_interactions (food_id)
);
```

| action | Cử chỉ | Ý nghĩa | Giá trị ML |
|---|---|---|---|
| `like` | Vuốt phải | Thích | +1 |
| `dislike` | Vuốt trái | Không thích | -1 |
| `neutral` | Vuốt lên | Bình thường | 0 |
| `unknown` | Vuốt xuống | Chưa biết / Bỏ qua | NULL / bỏ qua |

> **Ghi chú:** Đây là bảng **quan trọng nhất** cho ML — tạo nên ma trận User-Item cho Collaborative Filtering.

---

### 3.9 `feedbacks` — Đánh giá sau khi dùng món

```sql
CREATE TABLE feedbacks (
    id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT UNSIGNED NOT NULL,
    food_id    BIGINT UNSIGNED NOT NULL,
    rating     TINYINT UNSIGNED NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment    TEXT            NULL,
    ate_at     DATE            NULL,   -- Ngày thực tế ăn món
    created_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    INDEX idx_user_feedbacks (user_id),
    INDEX idx_food_rating (food_id, rating)
);
```

| Cột | Mô tả |
|---|---|
| `rating` | Sao đánh giá (1–5) |
| `comment` | Nhận xét tự do |
| `ate_at` | Ngày ăn thực tế (khác với created_at là ngày gửi đánh giá) |

> **Ghi chú:** `feedbacks` bổ sung tín hiệu mạnh hơn `interactions` — người dùng đã ăn và đánh giá có độ tin cậy cao hơn. ML sẽ ưu tiên dữ liệu này khi có.

---

### 3.10 `recommendations` — Lịch sử gợi ý

```sql
CREATE TABLE recommendations (
    id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id          BIGINT UNSIGNED NOT NULL,
    food_id          BIGINT UNSIGNED NOT NULL,
    score            DECIMAL(6,4)    NOT NULL,   -- Điểm dự đoán từ ML (0.0000 – 1.0000)
    rank_position    TINYINT UNSIGNED NULL,       -- Vị trí trong batch gợi ý
    source           ENUM('ml', 'rule_based', 'hybrid') NOT NULL DEFAULT 'hybrid',
    model_version    VARCHAR(20)     NULL,        -- Phiên bản model dùng để sinh gợi ý
    was_interacted   TINYINT(1)      NOT NULL DEFAULT 0,   -- Người dùng có vuốt không?
    recommended_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
    INDEX idx_user_recommendations (user_id, recommended_at)
);
```

| Cột | Mô tả |
|---|---|
| `score` | Điểm ML dự đoán (dùng để xếp hạng) |
| `rank_position` | Thứ hạng trong lần gợi ý (1 = top) |
| `source` | Nguồn gợi ý: thuần ML, rule-based, hoặc kết hợp |
| `model_version` | Theo dõi gợi ý từ phiên bản model nào |
| `was_interacted` | Sau khi gợi ý, người dùng có tương tác không (phục vụ đánh giá hệ thống) |

---

### 3.11 `meal_plans` — Thực đơn theo ngày

```sql
CREATE TABLE meal_plans (
    id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT UNSIGNED NOT NULL,
    plan_date      DATE            NOT NULL,
    meal_type      ENUM('breakfast', 'lunch', 'dinner', 'snack') NOT NULL,
    food_id        BIGINT UNSIGNED NOT NULL,
    serving_size_g SMALLINT UNSIGNED NOT NULL DEFAULT 100,
    note           VARCHAR(255)    NULL,
    created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id),
    INDEX idx_user_plan_date (user_id, plan_date)
);
```

| Cột | Mô tả |
|---|---|
| `plan_date` | Ngày áp dụng thực đơn |
| `meal_type` | Bữa ăn: sáng / trưa / tối / phụ |
| `serving_size_g` | Khẩu phần ăn thực tế (gram) |

---

## 4. Tổng hợp Index

| Bảng | Index | Lý do |
|---|---|---|
| `users` | `email` (UNIQUE) | Đăng nhập nhanh theo email |
| `health_profiles` | `user_id` (UNIQUE) | Lookup 1-1 theo user |
| `health_conditions` | `(user_id, condition_name)` (UNIQUE) | Tránh trùng bệnh lý |
| `food_tags` | `tag` | Bộ lọc F1 query theo tag |
| `interactions` | `(user_id, interacted_at)` | Lấy lịch sử tương tác gần nhất của user |
| `interactions` | `food_id` | Thống kê tương tác theo món |
| `feedbacks` | `(food_id, rating)` | Tính rating trung bình theo món |
| `recommendations` | `(user_id, recommended_at)` | Lấy gợi ý gần nhất theo user |
| `meal_plans` | `(user_id, plan_date)` | Lấy thực đơn theo ngày |

---

## 5. Luồng dữ liệu cho ML

```
[health_profiles] + [health_conditions]
         │
         ▼
  Bộ lọc F1 (rule-based)
  → loại foods có tag không phù hợp health_conditions
         │
         ▼
  Danh sách foods đủ điều kiện
         │
         ▼
  [interactions] + [feedbacks]   ← Dữ liệu huấn luyện
         │
         ▼
  ML Model (Collaborative Filtering / Hybrid)
         │
         ▼
  score cho từng (user_id, food_id)
         │
         ▼
  Ghi vào [recommendations]
         │
         ▼
  Trả kết quả về API → Mobile App
```

---

## 6. Ghi chú thiết kế

| Quyết định | Lý do |
|---|---|
| `bmi` dùng `GENERATED COLUMN` | Tự động đồng bộ khi weight/height thay đổi, không cần xử lý ở code |
| Tách `food_nutrition` khỏi `foods` | Thông tin dinh dưỡng có thể NULL ban đầu; tách bảng giữ `foods` gọn |
| `interactions` không có UNIQUE trên `(user_id, food_id)` | Người dùng có thể tương tác nhiều lần với cùng 1 món — lịch sử là dữ liệu quý |
| `feedbacks` có thể tồn tại độc lập với `interactions` | Người dùng có thể đánh giá mà không cần qua màn hình vuốt |
| `recommendations.model_version` | Cho phép phân tích A/B test giữa các phiên bản model |
| `interactions.session_id` | Nhóm các lần vuốt trong 1 phiên → phân tích hành vi theo phiên |
