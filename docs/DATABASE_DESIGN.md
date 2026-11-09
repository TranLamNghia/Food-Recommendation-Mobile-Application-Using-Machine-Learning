# Thiết kế cơ sở dữ liệu — Hệ thống khuyến nghị thực đơn dinh dưỡng cá nhân hóa

## 1. Tổng quan

**Hệ quản trị CSDL:** MySQL 8.x
**Storage engine:** InnoDB
**Charset:** `utf8mb4` — **Collation:** `utf8mb4_unicode_ci`

Cơ sở dữ liệu gồm **22 bảng**, chia thành 6 nhóm chức năng:

| Nhóm | Số bảng | Bảng |
|---|---|---|
| 👤 Người dùng | 5 | `users`, `health_profiles`, `body_logs`, `conditions`, `user_conditions` |
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

Tài liệu này trình bày các bảng theo **nhóm chức năng** để dễ đọc, nhưng đó **không phải** thứ tự tạo bảng.

Sau khi bỏ `interactions.recommendation_id`, **không còn khóa ngoại nào trỏ ngược sang nhóm khác**. Đồ thị phụ thuộc rất nông, chỉ 4 tầng:

```text
Tầng 0 — không phụ thuộc bảng nào
    users, conditions, food_categories, tags, rda_reference, ml_models

Tầng 1
    health_profiles, body_logs, password_resets, user_conditions, foods,
    condition_rules, user_preference_profiles

Tầng 2
    food_nutrition, food_tags, meal_plans, recommendations,
    food_diary, feedbacks, interactions, ml_training_samples, ml_evaluations

Tầng 3
    meal_plan_items
```

> Khi viết `schema.sql`, đặt các câu `CREATE TABLE` theo đúng thứ tự này. Nếu dùng Entity Framework Core Migrations thì công cụ tự sắp xếp, không cần quan tâm.

---

# 3. Nhóm Người dùng

## 3.1 `users` — Tài khoản

```sql
CREATE TABLE users (
    id                      CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    role                    ENUM('user','admin') NOT NULL DEFAULT 'user',
    is_active               TINYINT(1)   NOT NULL DEFAULT 1,
    password_hash           VARCHAR(255) NOT NULL,
    display_name            VARCHAR(100) NOT NULL,
    avatar_url              VARCHAR(500) NULL,
    onboarding_completed_at DATETIME     NULL,
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_role (role, is_active)
) ENGINE=InnoDB;
```

| Cột | Mô tả |
|---|---|
| `role` | `user` — người dùng ứng dụng Android · `admin` — tài khoản trang quản trị web |
| `is_active` | Khóa tài khoản mà không xóa dữ liệu |
| `onboarding_completed_at` | Mốc hoàn tất phiên vuốt thăm dò. `NULL` nghĩa là người dùng còn ở **Giai đoạn 0**. Tài khoản `admin` luôn để `NULL` vì không đi qua luồng này |

> `onboarding_completed_at` là cột đánh dấu ranh giới Giai đoạn 0 → Giai đoạn 1. Backend dựa vào cột này để quyết định có cần đẩy người dùng vào màn hình vuốt thăm dò hay không.

**Cột `role`.** Hệ thống có **hai giao diện**: ứng dụng Android cho người dùng cuối, và trang quản trị trên web dành cho việc quản lý danh mục món ăn, bộ quy tắc dinh dưỡng và theo dõi kết quả huấn luyện mô hình. Cả hai dùng chung bảng `users`, phân biệt bằng `role` nhận một trong hai giá trị `user` hoặc `admin`.

**Vì sao không tách bảng `admins` riêng.** Hệ thống chỉ có đúng hai vai trò và không có phân quyền chi tiết theo chức năng. Tách thành bảng riêng sẽ sinh ra hai luồng xác thực, hai cơ chế đổi mật khẩu và một thực thể nữa trong ERD, mà không đổi lại được gì về mặt nghiệp vụ. Tài khoản quản trị đơn giản là không có dòng trong `health_profiles`, không có `meal_plans`, không có `interactions` — mọi khóa ngoại đều cho phép điều đó mà không cần sửa gì thêm.

**Cột `is_active`.** Khóa tài khoản mà không xóa dữ liệu. Cột này chỉ có nghĩa khi đã có trang quản trị để thao tác; không có giao diện quản trị thì nó là cột chết.

Chỉ mục `idx_role (role, is_active)` phục vụ truy vấn liệt kê tài khoản trong trang quản trị.

> **Lưu ý phân biệt:** `foods.is_active` mang vai trò khác — ẩn một món khỏi danh sách gợi ý **mà không xóa dữ liệu**. Xóa cứng một món sẽ `CASCADE` xóa luôn lịch sử tương tác, nhật ký ăn uống và mẫu huấn luyện liên quan, làm hỏng tập dữ liệu ML.

---

## 3.2 `health_profiles` — Hồ sơ sức khỏe và hạn mức dinh dưỡng

```sql
CREATE TABLE health_profiles (
    id                    CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id               CHAR(36) NOT NULL UNIQUE,
    gender                ENUM('male','female','other') NOT NULL,
    date_of_birth         DATE         NOT NULL,
    height_cm             DECIMAL(5,2) NOT NULL,
    weight_kg             DECIMAL(5,2) NOT NULL,
    bmi                   DECIMAL(5,2) GENERATED ALWAYS AS
                              (weight_kg / ((height_cm / 100) * (height_cm / 100))) VIRTUAL,
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

**Vì sao lưu BMR/TDEE thay vì tính mỗi lần cần?**

Ba lý do. Thứ nhất, người dùng thay đổi cân nặng theo thời gian, và ta cần biết **hạn mức tại thời điểm sinh thực đơn** chứ không phải hạn mức hôm nay. Thứ hai, `chk_macro_sum` bảo đảm tỷ lệ macro luôn hợp lệ ở tầng CSDL. Thứ ba, đây là đầu ra của Bước 1 — lưu lại thì Bước 4 và ML Service đọc trực tiếp, không phải tính lặp.

> `CHECK` ràng buộc `height_cm ≥ 50` cũng chặn luôn lỗi chia cho 0 ở cột `bmi`.

---

## 3.3 `body_logs` — Lịch sử cân nặng

```sql
CREATE TABLE body_logs (
    id         CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id    CHAR(36) NOT NULL,
    logged_on  DATE NOT NULL,
    weight_kg  DECIMAL(5,2) NOT NULL,
    note       VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_log_weight CHECK (weight_kg BETWEEN 20 AND 300),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY uq_user_day (user_id, logged_on),
    INDEX idx_user_time (user_id, logged_on)
) ENGINE=InnoDB;
```

**Vì sao cần bảng riêng thay vì dùng `health_profiles`.**

`health_profiles.user_id` là `UNIQUE`, tức mỗi người dùng có **đúng một dòng**. Cột `weight_kg` ở đó bị ghi đè mỗi lần người dùng cập nhật cân nặng, nên không còn dấu vết của những lần trước.

Hệ quả: đề cương liệt kê "theo dõi tiến trình sức khỏe" là một chức năng của ứng dụng di động, nhưng nếu không có bảng này thì màn hình tiến trình chỉ hiện được con số hôm nay — không vẽ được biểu đồ cân nặng theo thời gian, vốn là thứ người dùng mong đợi nhất ở một ứng dụng dinh dưỡng.

**Phân vai giữa hai bảng:**

| | Vai trò |
|---|---|
| `health_profiles.weight_kg` | Cân nặng **hiện hành** — đầu vào để tính BMI, BMR, TDEE và hạn mức năng lượng |
| `body_logs.weight_kg` | **Lịch sử** — chỉ dùng để hiển thị biểu đồ và tính mức thay đổi |

Khi người dùng ghi cân nặng mới, Backend ghi vào **cả hai**: cập nhật `health_profiles` để hạn mức tính lại cho đúng, và chèn thêm một dòng `body_logs` để giữ lịch sử.

**Vì sao `UNIQUE (user_id, logged_on)`.** Mỗi ngày tối đa một bản ghi. Người dùng cân hai lần trong ngày — sáng và tối, chênh nhau cả kilogram vì ăn uống — sẽ tạo ra hai điểm trên biểu đồ và làm đường cong răng cưa vô nghĩa. Ghi lại trong cùng ngày thì cập nhật dòng cũ bằng `ON DUPLICATE KEY UPDATE`.

---

## 3.4 `conditions` — Từ điển bệnh lý, dị ứng, chế độ ăn

```sql
CREATE TABLE conditions (
    id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name_vi        VARCHAR(100) NOT NULL UNIQUE,
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

## 3.5 `user_conditions` — Bệnh lý của từng người dùng

```sql
CREATE TABLE user_conditions (
    id           CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id      CHAR(36) NOT NULL,
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

## 3.6 `password_resets` — Mã đặt lại mật khẩu

```sql
CREATE TABLE password_resets (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id     CHAR(36) NOT NULL,
    token_hash  CHAR(64) NOT NULL,
    expires_at  DATETIME NOT NULL,
    used_at     DATETIME NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_reset_window CHECK (expires_at > created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY uq_reset_token (token_hash),
    INDEX idx_reset_user_time (user_id, created_at)
) ENGINE=InnoDB;
```

**Bài toán mà bảng này giải.** Luồng "Quên mật khẩu" có một nghịch lý: để đổi mật khẩu thì phải chứng minh mình là chủ tài khoản, mà bằng chứng duy nhất hệ thống có — chính mật khẩu — thì người dùng không nhớ. Nên hệ thống tạm thay nó bằng một bằng chứng khác: **quyền đọc hộp thư đã đăng ký**. Mã đặt lại là bằng chứng đó.

| | |
|---|---|
| `POST /auth/forgot-password` | Sinh mã, băm, chèn một dòng, gửi liên kết chứa mã gốc vào email |
| `POST /auth/reset-password` | Nhận mã gốc, băm lại, tra `token_hash`, kiểm `expires_at` và `used_at`, đổi mật khẩu, ghi `used_at` |

**Vì sao một bảng riêng thay vì bốn cột trong `users`.** Một mã gồm bốn thứ: mã đã băm, thuộc về ai, hết hạn lúc nào, đã dùng chưa. Nhồi cả bốn vào `users` thì:

- **Mỗi người chỉ có một mã sống được.** Email đến chậm nên người ta bấm "Gửi lại" là chuyện thường — và lúc đó mã trong email thứ nhất chết, trong khi đó mới là email họ đang mở.
- **Bốn cột ấy rỗng với gần như mọi dòng.** Tại một thời điểm chỉ vài người đang đặt lại mật khẩu trong số hàng trăm tài khoản.
- **Không có lịch sử.** Một tài khoản bị xin mã 50 lần trong một phút là dấu hiệu bị dò, mà cột bị ghi đè thì không nhìn thấy điều đó.

**Vì sao lưu mã đã băm.** Lý do giống hệt chỗ `users.password_hash`: ai đọc được bảng này mà mã nằm nguyên trong đó thì đổi được mật khẩu của **mọi** tài khoản đang có mã sống. Băm thì bảng đó vô dụng với họ. Không truy vấn nào cần mã gốc, vì người dùng luôn nộp lại nó từ liên kết trong email.

Dùng SHA-256 chứ không BCrypt, có chủ ý. BCrypt cố ý chậm để chống dò **mật khẩu do người đặt** — thứ có entropy thấp và nằm trong từ điển. Mã ở đây là 32 byte ngẫu nhiên, không dò được bằng từ điển, nên cái chậm đó chỉ còn là chi phí trên mỗi lượt gọi.

**Mã phải sinh bằng bộ sinh số ngẫu nhiên mật mã.** Cột `id` dùng `UUID()` của MySQL, và điều đó **chỉ** đúng cho một khóa chính. `UUID()` sinh UUID phiên bản 1 — ghép từ thời điểm và địa chỉ MAC của máy chủ, nên đoán được. Dùng nó làm mã đặt lại thì ai biết thời điểm gửi email là thu hẹp được không gian tìm kiếm xuống còn vài nghìn khả năng. Backend phải dùng `SecureRandom`, 32 byte.

**Vì sao `used_at` chứ không phải xóa dòng.** Mã dùng được đúng một lần. Nhưng đánh dấu đã dùng và xóa dòng đi không tương đương: một mã bị nộp **hai lần** là dấu hiệu liên kết đã rò ra ngoài, và nếu dòng đã bị xóa thì lần thứ hai không phân biệt được với một mã bịa.

**`CHECK (expires_at > created_at)`.** Một mã hết hạn trước khi được tạo là chết ngay khi sinh ra, và lỗi đó không báo gì — người dùng chỉ thấy "mã không hợp lệ" với mọi mã, và không ai nối được hiện tượng ấy với một phép tính thời gian sai ở Backend.

**Giới hạn số lần xin mã, và chỗ nó không che được.** `INDEX (user_id, created_at)` tồn tại để đếm số lần xin mã gần đây của một tài khoản, phục vụ mức `429 RATE_LIMITED`. Nhưng phép giới hạn này **chỉ che được email đã đăng ký**: email không có trong hệ thống không sinh dòng nào — cố ý, vì lưu lại mọi địa chỉ người lạ nhập vào là tự dựng một danh sách email mà hệ thống không cần. Nhóm đó phải giới hạn ở tầng trước CSDL, theo địa chỉ IP.

**Dọn dòng cũ.** Mã sống 15 phút, nên gần như mọi dòng trong bảng này là rác sau một giờ. Xóa những dòng đã hết hạn **trên bảy ngày** bằng một việc định kỳ; giữ lại bảy ngày để còn tra được khi có nghi vấn về truy cập.

---

# 4. Nhóm Món ăn

## 4.1 `food_categories` — Danh mục

```sql
CREATE TABLE food_categories (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
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
    id               CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    category_id      CHAR(36) NOT NULL,
    name             VARCHAR(200) NOT NULL,
    description      TEXT         NULL,
    image_url        VARCHAR(500) NULL,

    -- ══ Đặc trưng phục vụ vector ML (theo đề cương) ══
    spice_level      TINYINT UNSIGNED NOT NULL DEFAULT 0,
    dish_role        ENUM('main','side_protein','side_veg','soup',
                          'snack','dessert','drink')
                         NOT NULL DEFAULT 'main',

    popularity_score DECIMAL(5,4) NOT NULL DEFAULT 0,
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,
    owner_id         CHAR(36) NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_spice CHECK (spice_level BETWEEN 0 AND 3),
    FOREIGN KEY (category_id) REFERENCES food_categories(id),
    FOREIGN KEY (owner_id)    REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY uq_food_name ((COALESCE(owner_id, '')), name),
    INDEX idx_active_category (owner_id, is_active, category_id),
    INDEX idx_dish_role (dish_role)
) ENGINE=InnoDB;
```

| Cột | Mô tả | Dùng ở đâu |
|---|---|---|
| `spice_level` | Độ cay 0–3 | Vector đặc trưng ML |
| `dish_role` | Vai trò trong bữa: `main` món chính · `side_protein` món mặn · `side_veg` món rau · `soup` canh · `snack` món phụ · `dessert` tráng miệng · `drink` đồ uống | **Bước 4** — ràng buộc cấu trúc bữa ăn |
| `owner_id` | `NULL` — món thuộc **danh mục chung**; có giá trị — món **riêng** của người dùng đó | **Bước 2** — giới hạn tập ứng viên |
| `popularity_score` | Độ phổ biến chung, tính từ tỷ lệ thích toàn hệ thống | **Giai đoạn 0** — chấm điểm khi chưa biết gì về người dùng |

**Vì sao khóa `uq_food_name` đi theo biểu thức chứ không theo `owner_id` trần.**
MySQL coi **mọi `NULL` là khác nhau** trong chỉ mục `UNIQUE`. Mọi món của danh
mục chung đều có `owner_id` là `NULL` — đo trên CSDL thật là **318/318 dòng** —
nên khóa `(owner_id, name)` không chặn trùng ở một dòng nào trong toàn bộ danh
mục công khai.

Đây không phải lỗi lý thuyết. Bản lược đồ trước ghi chú rằng phần chặn trùng
của danh mục chung "do trình nạp và trang quản trị kiểm", và chính trình nạp là
thứ vỡ: `tools/load_foods.py --apply` chết ngay ở món đầu tiên với

```
(1242, 'Subquery returns more than 1 row')
```

vì `ON DUPLICATE KEY UPDATE` không thấy khóa nào trùng nên **chèn thêm** một
món `Cơm trắng` thứ hai, rồi câu lệnh tiếp theo tra
`SELECT id FROM foods WHERE name = 'Cơm trắng'` thì nhận về hai dòng.

Cách vá: đặt khóa lên **biểu thức** `COALESCE(owner_id, '')` — MySQL 8.0.13
trở lên cho phép. Phép quy đổi biến `NULL` thành chuỗi rỗng, là một giá trị
thật, nên khóa chặn được trùng tên ở cả món danh mục chung lẫn món riêng, mà
hai người dùng khác nhau vẫn đặt trùng tên món của mình được.

Không điền thẳng chuỗi rỗng vào `owner_id` được: cột đó có khóa ngoại sang
`users(id)`, nên giá trị rỗng đòi phải có một dòng `users` mang `id` rỗng —
thử thì MySQL báo `(1452, 'a foreign key constraint fails')`. Tạo một tài
khoản giả để làm chỗ dựa thì tốn hơn nhiều: một dòng không phải người thật nằm
trong `users`, lọt vào mọi phép đếm người dùng, và vì khóa ngoại là
`ON DELETE CASCADE` nên xóa nhầm nó là mất sạch danh mục món.

Trước đây phép quy đổi nằm ở một cột sinh tên `owner_key`. Cột đó **đã bỏ**:
nó không mang thông tin nào mà `owner_id` chưa có, nên trên sơ đồ ERD nó là
một dòng thừa phải giải thích. Bên trong, MySQL vẫn dựng một cột ảo ẩn cho
khóa biểu thức — cơ chế y hệt, chỉ khác là không hiện ra trong danh sách
cột.

Bài học mang tính thiết kế: một ràng buộc toàn vẹn giao cho tầng ứng dụng chỉ
còn đúng tới khi xuất hiện tầng ứng dụng thứ hai. Ở đây tầng thứ hai là trang
quản trị, nơi admin nhập món bằng tay.

**Vì sao cần `dish_role`.** Bước 4 phải bảo đảm mỗi bữa có cấu trúc hợp lý — một món chính, một món canh, có thể thêm món phụ. Không có cột này thì thuật toán tham lam có thể chọn ra ba món tráng miệng vì cả ba đều điểm cao.

**Vì sao cần `owner_id` — món ngoài danh mục.**

Người dùng ăn ở hàng quán, ăn cơm nhà nấu, ăn đồ đóng gói — luôn có những món không nằm trong danh mục đã dựng. Nếu không ghi được, tổng năng lượng trong ngày sẽ thiếu hụt, tỷ lệ tuân thủ sai theo, và màn hình tiến trình nói dối người dùng.

`owner_id` giải quyết bằng cách cho phép món tồn tại ở **hai phạm vi**:

| Giá trị | Ý nghĩa |
|---|---|
| `NULL` | Món thuộc **danh mục chung**, do quản trị viên duyệt, mọi người dùng đều thấy. Chỉ những món này mới tính vào mốc 300–500 món của đề cương |
| có giá trị | Món **riêng** của người dùng đó, tự thêm khi ăn thứ ngoài danh mục. Chỉ người đó thấy |

Bộ lọc F1 ở Bước 2 vì vậy thêm đúng một mệnh đề:

```sql
WHERE f.is_active = 1
  AND (f.owner_id IS NULL OR f.owner_id = :current_user_id)
```

**Vì sao cách này tốt hơn việc cho `food_diary.food_id` nhận `NULL`.** Giữ được `NOT NULL` và khóa ngoại nguyên vẹn, không sinh ra cột `NULL` tạo đường đi vòng — đúng nguyên tắc đã áp dụng khi từ chối `meal_plan_item_id`. Quan trọng hơn: món riêng **vẫn có đầy đủ vector đặc trưng** (nhóm món, cách chế biến, mức cay, macro) nên vẫn sinh được tín hiệu học, khác hẳn một dòng nhật ký nhập tự do không trỏ tới món nào.

**Ba chi tiết trong ràng buộc:**

`UNIQUE (owner_id, name)` chứ không chỉ `name` — hai người dùng hoàn toàn có thể cùng tự thêm một món tên *"Cơm gà bà Năm"*; ràng buộc chỉ trên `name` sẽ chặn oan người thứ hai. Lưu ý MySQL coi mọi `NULL` là khác nhau, nên ràng buộc này **không** chặn trùng tên trong danh mục chung; phần đó do trình nạp và trang quản trị kiểm.

`ON DELETE CASCADE` chứ không `SET NULL` — xóa tài khoản mà để `owner_id` thành `NULL` là **đẩy món chưa kiểm duyệt vào danh mục chung** của mọi người dùng khác.

`owner_id` đứng **đầu** chỉ mục `idx_active_category` vì mệnh đề lọc phạm vi luôn có mặt trong mọi truy vấn lấy tập ứng viên.

**Nguyên tắc với dữ liệu huấn luyện.** Món riêng cập nhật **vector sở thích cá nhân** (Rocchio) nhưng **không vào tập huấn luyện của mô hình toàn cục**. Mô hình toàn cục dùng chung cho mọi người dùng; nhiễm số liệu dinh dưỡng phỏng đoán của một cá nhân là làm hại tất cả, trong khi vector cá nhân chỉ ảnh hưởng đúng người đó.

**Vì sao cần `side_protein` tách khỏi `side_veg`.** Bản thiết kế đầu gộp cả hai vào một giá trị `side`. Nhưng mâm cơm Việt thiếu món mặn thì không còn là bữa ăn, mà khi gộp chung thì bộ sinh thực đơn hoàn toàn có thể chọn ra hai món rau và không có nguồn đạm nào. Giá trị `snack` cũng được thêm vì món phụ như gỏi cuốn hay bánh mì không phải `side` cũng không phải `dessert`.

**Vì sao không có cột "phương pháp chế biến".** Bản thiết kế trước đây có cột `cooking_method` kiểu `ENUM` 10 giá trị, đã bỏ.

Đề cương nêu vector đặc trưng gồm "thành phần dinh dưỡng, nhóm thực phẩm, phương pháp chế biến và khẩu vị". **Cả bốn thành phần đó vẫn còn**: phương pháp chế biến nay do `category_id` đại diện, vì 8 trong 12 mã nhóm *chính là* phương pháp chế biến — `mon_chien` là chiên, `mon_nuong` là nướng, `mon_xao` là xào, `mon_kho` là kho, `mon_luoc_hap` là luộc và hấp, `mon_canh` là nấu canh, `mon_goi` là trộn và sống, `mon_nuoc` là nấu nước. Bốn mã còn lại — `com`, `trang_mieng`, `do_uong`, `mon_cuon` — phân theo vai trò hoặc dạng món chứ không theo cách tác động nhiệt.

Nói cách khác, bỏ `cooking_method` **không làm mất tín hiệu cách chế biến**, nó chỉ bỏ một trục *trùng lặp* với trục đã có. Ba lý do:

Thứ nhất, **`food_categories` đã mang thông tin đó**. Nhóm `mon_chien` thì cách chế biến là chiên, `mon_nuong` thì là nướng — 12 nhóm món của hệ thống phần lớn *chính là* phương pháp chế biến. Hai one-hot gần như trùng nhau, và trong mã nguồn điều này đã lộ ra từ trước: hàm tổng hợp đặc trưng ở màn hình kết quả khảo sát phải có cơ chế khử trùng, vì hai nhãn `Chiên` và `Món chiên` cùng lọt vào danh sách và nói đi nói lại một ý.

Thứ hai, **hai trục độc lập cho phép những trạng thái vô nghĩa**. Mì tôm nấu nước và mì tôm xào khô là *hai món khác nhau* với thành phần dinh dưỡng khác nhau, không phải một món với hai cách chế biến. Để `cooking_method` tách khỏi `category_id` thì không gì ngăn một dòng thuộc nhóm `mon_nuoc` lại mang `cooking_method = 'xao'` — dữ liệu tự mâu thuẫn mà không ràng buộc nào bắt được. Gộp về một trục thì mỗi cách chế biến là một món riêng, một dòng riêng, một bộ số dinh dưỡng riêng.

Thứ ba, **nó gần như không mang thông tin**. Trong 83 món của tập dữ liệu, 63 món mang giá trị `khac`.

Thống kê sở thích theo cách chế biến vẫn làm được: tra `popularity_score` hoặc `food_diary` rồi nhóm theo `category_id`.

**Vì sao không có cột "bữa ăn phù hợp".** Bản thiết kế trước đây có cột `suitable_meals` kiểu `SET`, đã bỏ vì hai lý do.

Thứ nhất, **không có nguồn nào để điền nó**. Bảng thành phần thực phẩm không nói món nào ăn bữa nào, và không có chuẩn nào về chuyện này. Giá trị điền vào chỉ là phán đoán của người nhập, mà `validate_foods.py` chỉ kiểm được *từ vựng* hợp lệ chứ không kiểm được *gán đúng hay sai*. Lọc cứng dựa trên dữ liệu phỏng đoán là khuếch đại sai số của chính mình.

Thứ hai, **`dish_role` đã mang thông tin đó**. `main` là món của bữa chính, `snack` là món ăn lúc nào cũng được, `dessert` và `drink` đi kèm chứ không đứng một mình. Hai cột cùng diễn đạt một điều thì cột yếu hơn phải đi.

Nếu sau này cần biết món nào thường ăn vào bữa nào, câu trả lời **đo được** từ `food_diary`:

```sql
SELECT meal_type, COUNT(*) AS so_lan
FROM food_diary WHERE food_id = :food_id
GROUP BY meal_type ORDER BY so_lan DESC;
```

Con số này là sự thật quan sát được, khác hẳn một cột phỏng đoán điền sẵn.

---

## 4.3 `food_nutrition` — Thành phần dinh dưỡng

```sql
CREATE TABLE food_nutrition (
    id              CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    food_id         CHAR(36) NOT NULL UNIQUE,
    serving_size_g  SMALLINT UNSIGNED NOT NULL DEFAULT 100,

    -- ══ Năng lượng và ba chất sinh năng lượng ══
    calories_kcal   DECIMAL(7,2) NOT NULL,
    protein_g       DECIMAL(6,2) NOT NULL DEFAULT 0,
    carbs_g         DECIMAL(6,2) NOT NULL DEFAULT 0,
    fat_g           DECIMAL(6,2) NOT NULL DEFAULT 0,

    -- ══ Thành phần liên quan ràng buộc bệnh lý ══
    fiber_g         DECIMAL(6,2) NULL,
    sugar_g         DECIMAL(6,2) NULL,
    sodium_mg       DECIMAL(7,2) NULL,
    cholesterol_mg  DECIMAL(7,2) NULL,
    purine_mg       DECIMAL(7,2) NULL,

    -- ══ Vi chất ══
    calcium_mg      DECIMAL(7,2) NULL,
    iron_mg         DECIMAL(6,2) NULL,
    zinc_mg         DECIMAL(6,2) NULL,
    vitamin_a_mcg   DECIMAL(7,2) NULL,
    vitamin_c_mg    DECIMAL(6,2) NULL,

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

> **Vì sao vi chất cho phép NULL còn macro thì không.** Mục tiêu đề tài nêu "calo, protein, vi chất", nhưng thực tế thu thập dữ liệu 300–500 món Việt Nam thì số liệu vi chất khuyết khá nhiều. Cho `NULL` là trung thực; bước tiền xử lý của ML sẽ xử lý dữ liệu khuyết theo phương pháp đã trình bày ở Chương 1. Ngược lại 4 trường macro là bắt buộc vì thiếu chúng thì Bước 4 không chạy được.

> **Vì sao không có cột truy xuất nguồn.** Bản thiết kế trước có `data_source`
> và `source_url`. Đã bỏ cả hai: đây là đồ án công nghệ thông tin, trọng tâm là
> thuật toán khuyến nghị, không phải chứng minh độ chính xác của số liệu thực
> phẩm. Quy tắc **không vay số liệu ba chất sinh năng lượng từ nguồn khác** vẫn
> được thực thi trong `tools/fill_gaps_usda.py` (danh sách `BORROWABLE` loại
> macro); chỉ là không còn lưu lại vết trong CSDL. Nguồn chung của tập dữ liệu
> ghi ở `data/reference/SOURCING_POLICY.md`.

---

## 4.4 `tags` — Từ điển nhãn món ăn

```sql
CREATE TABLE tags (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name_vi     VARCHAR(100) NOT NULL UNIQUE,
    tag_type    ENUM('allergen','diet','nutrition') NOT NULL,
    description VARCHAR(255) NULL,
    INDEX idx_tag_type (tag_type)
) ENGINE=InnoDB;
```

**Dữ liệu mẫu theo từng loại:**

Không còn cột `code`: `name_vi` đã là `UNIQUE` và làm luôn khóa tự nhiên.
**13 nhãn**, đúng bằng số dòng trong `db/seed.sql`:

| tag_type | name_vi | Số món đang gắn | Dùng làm gì |
|---|---|---|---|
| `allergen` | Có hải sản | 90 | Ràng buộc cứng — dị ứng |
| `allergen` | Có đậu nành | 20 | Ràng buộc cứng |
| `allergen` | Có trứng | 15 | Ràng buộc cứng |
| `allergen` | Có gluten | 8 | Ràng buộc cứng |
| `allergen` | Có đậu phộng | 2 | Ràng buộc cứng |
| `allergen` | Có sữa / chế phẩm sữa | 0 | Ràng buộc cứng |
| `diet` | Món chay | 117 | Ràng buộc cứng |
| `diet` | Món thuần chay | 116 | Ràng buộc cứng |
| `nutrition` | Giàu purin | 91 | Quy tắc bệnh gút |
| `nutrition` | Giàu chất xơ | 1 | *chưa quy tắc nào dùng* |
| `nutrition` | Ít natri | 0 | *chưa quy tắc nào dùng* |
| `nutrition` | Ít đường | 0 | *chưa quy tắc nào dùng* |
| `nutrition` | Giàu đạm | 0 | *chưa quy tắc nào dùng* |

**Nhãn `Có đậu nành` từng là nhãn dị nguyên duy nhất không bệnh nào dùng tới**
— 6 nhãn dị nguyên mà chỉ 5 bệnh trong `conditions`, nên người dị ứng đậu nành
không khai được và Bộ lọc F1 không loại gì cho họ. Phát hiện khi chạy
`tools/check_f1.py`. Đã thêm bệnh `Dị ứng đậu nành` kèm quy tắc `exclude_tag`;
giờ cả 6 nhãn đều có bệnh tương ứng.

**Nhóm `taste` đã bị bỏ hoàn toàn** (`Mặn`, `Ngọt`, `Chua`, `Béo`, `Thanh
đạm`). Khi đối chiếu nhãn gắn tay với số đo thì chúng mâu thuẫn với dữ liệu:
món gắn `Mặn` trung bình 1041 mg natri (thấp nhất 805), món **không** gắn
trung bình 959 mg nhưng cao nhất tới 1378. Và 0/20 quy tắc nào dùng tới một
nhãn vị. Vị mặn và vị ngọt nay là **chiều số** trong vector, lấy thẳng từ
`sodium_mg` và `sugar_g`.

**Bốn nhãn `nutrition` cuối bảng đang là ứng viên bị bỏ nốt** — cùng lý do:
cả bốn đều suy được từ cột số (`sodium_mg`, `sugar_g`, `protein_g`,
`fiber_g` phủ 95–100 %), không quy tắc nào dùng, và ngưỡng "ít" hay "giàu" là
bao nhiêu thì nhãn không nói. `Giàu purin` thì **giữ**, vì `purine_mg` chỉ
phủ 70/318 món nên nhãn mang thông tin mà cột số không có. Đó cũng là phép
thử chung: giữ nhãn khi con số thiếu hoặc không suy ra được.

**Vì sao dùng nhãn dị ứng thay vì bảng nguyên liệu chi tiết.**

Phương án chính xác nhất là dựng bảng `ingredients` + `food_ingredients`, rồi truy dị ứng đến từng nguyên liệu. Nhưng với 300–500 món, đó là khối lượng nhập liệu rất lớn và nằm ngoài phạm vi khả thi của đồ án.

Phương án đã chọn: khoảng 6–8 nhãn dị nguyên phổ biến gắn trực tiếp lên món. Đủ chính xác cho các nhóm dị ứng thường gặp, chi phí nhập liệu chỉ bằng một phần nhỏ.

Cái mất là độ chi tiết với các dị ứng hiếm. **Ghi nhận thẳng vào phần hạn chế của báo cáo**, và đề xuất bảng nguyên liệu như hướng phát triển — như vậy vừa trung thực vừa cho thấy đã cân nhắc phương án.

---

## 4.5 `food_tags` — Gán nhãn cho món

```sql
CREATE TABLE food_tags (
    food_id CHAR(36) NOT NULL,
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
    id           CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    condition_id INT UNSIGNED NOT NULL,
    rule_type    ENUM('exclude_tag','require_tag','nutrient_limit') NOT NULL,

    -- Dùng khi rule_type = 'exclude_tag' hoặc 'require_tag'
    tag_id       INT UNSIGNED NULL,

    -- Dùng khi rule_type = 'nutrient_limit'
    nutrient     ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g',
                      'sugar_g','sodium_mg','cholesterol_mg','purine_mg',
                      'calcium_mg','iron_mg','zinc_mg','vitamin_a_mcg',
                      'vitamin_c_mg') NULL,
    comparator   ENUM('lte','gte') NULL,
    threshold    DECIMAL(8,2) NULL,
    scope        ENUM('per_serving','per_meal','per_day') NOT NULL DEFAULT 'per_serving',

    severity_min ENUM('mild','moderate','severe') NOT NULL DEFAULT 'mild',
    is_hard      TINYINT(1)   NOT NULL DEFAULT 1,
    penalty      DECIMAL(4,3) NULL,
    evidence_level ENUM('definitional','published','derived','unsupported')
                 NOT NULL DEFAULT 'derived',
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
| `penalty` | **Hệ số nhân** điểm khi `is_hard = 0` — nhỏ hơn là phạt nặng hơn |
| `evidence_level` | Mức tin cậy của **ngưỡng**: `definitional` (quy tắc nhãn, không có ngưỡng để dẫn nguồn) · `published` (lấy nguyên từ nguồn đang hiệu lực) · `derived` (suy ra kèm giả thiết) · `unsupported` (không có nguồn đang hiệu lực) |

**Dữ liệu mẫu — đây chính là bảng sẽ in vào báo cáo:**

| Bệnh lý | rule_type | Nhãn / Chất | So sánh | Ngưỡng | scope | is_hard | penalty | severity_min |
|---|---|---|---|---|---|---|---|---|
| Ăn chay | `require_tag` | `Món chay` | — | — | per_serving | 1 | — | mild |
| Ăn thuần chay | `require_tag` | `Món thuần chay` | — | — | per_serving | 1 | — | mild |
| Bệnh thận | `nutrient_limit` | `protein_g` | `lte` | 48.00 | per_day | 1 | — | mild |
| Bệnh thận | `nutrient_limit` | `sodium_mg` | `lte` | 2000.00 | per_day | 1 | — | mild |
| Dị ứng đậu nành | `exclude_tag` | `Có đậu nành` | — | — | per_serving | 1 | — | mild |
| Dị ứng đậu phộng | `exclude_tag` | `Có đậu phộng` | — | — | per_serving | 1 | — | mild |
| Dị ứng hải sản | `exclude_tag` | `Có hải sản` | — | — | per_serving | 1 | — | mild |
| Dị ứng trứng | `exclude_tag` | `Có trứng` | — | — | per_serving | 1 | — | mild |
| Đái tháo đường | `nutrient_limit` | `carbs_g` | `lte` | 60.00 | per_meal | 0 | 0.700 | mild |
| Đái tháo đường | `nutrient_limit` | `sugar_g` | `lte` | 25.00 | per_day | 0 | 0.600 | mild |
| Gút | `exclude_tag` | `Giàu purin` | — | — | per_serving | 1 | — | **moderate** |
| Gút | `nutrient_limit` | `purine_mg` | `lte` | 400.00 | per_day | 1 | — | mild |
| Gút | `nutrient_limit` | `purine_mg` | `lte` | 150.00 | per_serving | 0 | 0.500 | mild |
| Không dung nạp gluten | `exclude_tag` | `Có gluten` | — | — | per_serving | 1 | — | mild |
| Không dung nạp lactose | `exclude_tag` | `Có sữa / chế phẩm sữa` | — | — | per_serving | 1 | — | mild |
| Rối loạn mỡ máu | `nutrient_limit` | `cholesterol_mg` | `lte` | 300.00 | per_day | 0 | 0.700 | mild |
| Rối loạn mỡ máu | `nutrient_limit` | `fat_g` | `lte` | 25.00 | per_serving | 0 | 0.750 | mild |
| Tăng huyết áp | `nutrient_limit` | `sodium_mg` | `lte` | 2000.00 | per_day | 1 | — | mild |
| Tăng huyết áp | `nutrient_limit` | `sodium_mg` | `lte` | 700.00 | per_serving | 0 | 0.600 | mild |
| Tăng huyết áp | `nutrient_limit` | `sodium_mg` | `lte` | 500.00 | per_serving | 0 | 0.400 | **severe** |

Hai mươi dòng trên là **dữ liệu thật trong `nutrition_rec`**, không phải số minh họa. Mỗi ngưỡng ghi nguồn trong cột `note`, và nguồn chia làm ba mức tin cậy khác nhau — tài liệu không được trình bày chúng như nhau:

| Mức | Ví dụ `note` |
|---|---|
| **Có nguồn công bố** | `WHO: người lớn dưới 2000 mg natri/ngày`; `KDIGO 2024: 0,8 g đạm/kg/ngày`; hướng dẫn gút Nhật Bản dưới 400 mg/ngày |
| **Suy diễn** | `400 mg/ngày chia cho 3 bữa chính; là suy diễn, không phải ngưỡng công bố` |
| **Chưa xác minh** | `Ngưỡng theo ngày cho mức nặng CẦN TRA AHA/ESC — chưa xác minh` |

Hai dòng in đậm ở cột `severity_min` là hai quy tắc duy nhất **không** áp từ mức nhẹ. Luật `Giàu purin` cần mức vừa, nên người bị gút mức nhẹ không bị loại món nào (318 món đi qua F1), còn mức vừa thì bị loại 91 món.

Ba ghi chú đáng nhớ về nhóm `is_hard = 0`:

- Ngưỡng cholesterol 300 mg/ngày **đã bị rút** khỏi *Dietary Guidelines for Americans 2015* và AHA/ACC 2019, nên nó được giữ ở mức khuyến cáo chứ không phải chống chỉ định.
- Mục tiêu thật của AHA là **béo bão hòa** dưới 10% năng lượng, nhưng bảng thành phần thực phẩm Việt Nam không tách béo bão hòa, nên `fat_g` tổng được dùng thay.
- ADA *Standards of Care* nêu rõ **không có** tỷ lệ bột đường lý tưởng; mốc 45–60 g mỗi bữa là cách làm cũ, giữ làm khuyến cáo.

**Hai ràng buộc ép tính nhất quán.**

`condition_rules` là một **bảng đa hình**: mỗi `rule_type` dùng một bộ cột khác nhau, các cột còn lại để `NULL`. Không có ràng buộc thì một dòng `nutrient_limit` bỏ trống `threshold` vẫn chèn được bình thường, và quy tắc đó **lặng lẽ không bao giờ kích hoạt** — người bệnh vẫn nhận món lẽ ra phải bị lọc, mà hệ thống tưởng đã lọc.

```sql
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
CONSTRAINT chk_rule_penalty CHECK (is_hard = 1 OR penalty IS NOT NULL)
```

Ràng buộc thứ hai ép quy tắc mềm phải khai mức phạt — quy tắc mềm không có `penalty` thì bước chấm điểm không biết nhân bao nhiêu.

**Vì sao tách `is_hard`.** Không phải quy tắc dinh dưỡng nào cũng tuyệt đối. "Không được ăn tôm khi dị ứng hải sản" là cứng. "Nên hạn chế chất béo khi rối loạn mỡ máu" là mềm — nếu xử lý như ràng buộc cứng, tập ứng viên sẽ bị thu hẹp quá mức và Bước 4 không tìm nổi tổ hợp thỏa hạn mức năng lượng. Cột này cho phép diễn đạt đúng sự khác biệt đó.

---

## 5.2 `rda_reference` — Nhu cầu dinh dưỡng khuyến nghị

```sql
CREATE TABLE rda_reference (
    id        CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    gender    ENUM('male','female','all') NOT NULL,
    age_min   TINYINT UNSIGNED NOT NULL,
    age_max   TINYINT UNSIGNED NOT NULL,
    nutrient  ENUM('calories_kcal','protein_g','carbs_g','fat_g','fiber_g',
                   'sugar_g','sodium_mg','cholesterol_mg','purine_mg',
                   'calcium_mg','iron_mg','zinc_mg','vitamin_a_mcg',
                   'vitamin_c_mg') NOT NULL,
    qualifier VARCHAR(30)  NULL,
    rda_value DECIMAL(8,2) NOT NULL,
    unit      VARCHAR(10)  NOT NULL,
    source    VARCHAR(150) NOT NULL DEFAULT 'NIN Vietnamese RDAs 2016',

    UNIQUE KEY uq_rda (gender, age_min, age_max, nutrient,
                       (COALESCE(qualifier, ''))),
    INDEX idx_lookup (gender, age_min, age_max)
) ENGINE=InnoDB;
```

**Vì sao khóa `uq_rda` phải đi qua `COALESCE`.** `qualifier` để trống ở mọi
chất không phân mức hấp thu — hiện là 12/12 dòng. MySQL coi **mọi `NULL` là
khác nhau**, nên một khóa `UNIQUE` đi thẳng qua `qualifier` sẽ không chặn
trùng ở đúng những dòng đó. Đổi `NULL` thành chuỗi rỗng thì khóa mới cắn:
chèn lại y nguyên một dòng đã có nay báo
`1062 Duplicate entry 'male-19-30-protein_g-' for key 'rda_reference.uq_rda'`,
trong khi ba mức giá trị sinh học của chất sắt — cùng `(giới, tuổi,
'iron_mg')` nhưng khác `qualifier` — vẫn chèn được cả ba.

Phép quy đổi nằm **ngay trong khóa**, dạng khóa hàm (MySQL 8.0.13 trở lên).
Trước đây nó nằm ở một cột sinh tên `qualifier_key`. Cột đó **đã bỏ**, cùng
lý do và cùng cách làm như `foods.owner_key`: nó không mang ý nghĩa nghiệp vụ
nào, chỉ tồn tại để phục vụ khóa, nên nó làm ERD dài thêm một dòng mà không
nói thêm gì về bài toán. Hai chỗ trong cùng một lược đồ cần cùng một phép quy
đổi thì nên giải giống nhau — xem `foods.uq_food_name`.

Bảng tra cứu tĩnh, nạp một lần từ tài liệu NIN 2016. Dùng để đối chiếu thực đơn sinh ra có đáp ứng nhu cầu vi chất hay không, và để hiển thị "bạn đã nạp đủ bao nhiêu phần trăm nhu cầu canxi hôm nay" ở màn hình thống kê.

---

# 6. Nhóm Tương tác và Phản hồi

## 6.1 `interactions` — Lịch sử vuốt

```sql
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

    INDEX idx_user_time (user_id, interacted_at),
    INDEX idx_user_food (user_id, food_id),
    INDEX idx_food      (food_id),
    INDEX idx_session   (session_id)
) ENGINE=InnoDB;
```

| action | Cử chỉ | Ý nghĩa | Trọng số Rocchio | Nhãn ML |
|---|---|---|---|---|
| `like` | Vuốt phải | Thích | +1.0 | 0.90 |
| `dislike` | Vuốt trái | Không thích | −1.0 | 0.00 |
| `neutral` | Vuốt lên | Bình thường | 0.0 | 0.50 |
| `unknown` | Vuốt xuống | Chưa biết | Loại khỏi tổng | Loại khỏi tập huấn luyện |

### Bảng này chỉ chứa kết quả phiên khảo sát khẩu vị

Cơ chế vuốt chạy **đúng một lần trong đời tài khoản**, ở phiên khảo sát ngay sau khi khai báo hồ sơ. Sau đó ứng dụng không còn màn hình vuốt nào.

Vì vậy bảng cố ý **không có** ba cột từng xuất hiện trong bản thiết kế trước:

| Cột đã bỏ | Giá trị thực tế nếu giữ | Lý do bỏ |
|---|---|---|
| `session_type` | Luôn là `'onboarding'` | Không còn loại phiên nào khác |
| `context_meal_type` | Luôn `NULL` | Vuốt khảo sát không gắn với bữa ăn cụ thể nào |
| `recommendation_id` | Luôn `NULL` | Gói món khảo sát chọn theo độ đa dạng, không phải bản ghi gợi ý |

Cả ba đều sẽ là **cột hằng số** — dạng dư thừa dữ liệu rõ ràng nhất.

> **Hệ quả quan trọng: lược đồ giờ không còn đường đi vòng nào.** `interactions.recommendation_id` là chỗ cuối cùng còn dư thừa có kiểm soát; bỏ nó đi thì mọi bảng chỉ còn đúng một đường tới mỗi bảng đích. Xem thêm Mục 10.

### Chỉ số xếp hạng chuyển sang tính trên thực đơn

Cột `recommendation_id` từng được biện minh là *"bắt buộc để tính Precision@K và NDCG"*. Lập luận đó dựa trên giả định người dùng vuốt các món được gợi ý — giả định không còn đúng.

Chỗ đúng để đo chất lượng khuyến nghị là **thực đơn**, vì đó mới là thứ hệ thống thật sự đưa cho người dùng:

| Loại độ đo | Nguồn dữ liệu | Ghi ở đâu |
|---|---|---|
| Ngoại tuyến — Precision@K, Recall@K, NDCG | `ml_training_samples` tập `test` | Mục 8.2 |
| Trực tuyến — tỷ lệ tuân thủ, tỷ lệ thay thế | `meal_plan_items.status` + `food_diary` | Mục 8.3, 8.4 |

Cách này còn đúng hơn về mặt nghiệp vụ: một món "được gợi ý" nghĩa là nó **vào được thực đơn**, không phải nó được chấm điểm cao trong danh sách ứng viên.

---

## 6.2 `food_diary` — Nhật ký ăn uống

```sql
CREATE TABLE food_diary (
    id             CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id        CHAR(36) NOT NULL,
    food_id        CHAR(36) NOT NULL,
    ate_on         DATE NOT NULL,
    meal_type      ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    portion_multiplier DECIMAL(4,2) NOT NULL DEFAULT 1.00,
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
```

Đây là **nguồn nhãn có độ tin cậy cao nhất** trong toàn hệ thống. Bảng thống nhất nhãn ở Mục 7.4 gán trọng số mẫu 1.0 cho nguồn này.

### Điều kiện được đánh giá — ràng buộc nghiệp vụ bắt buộc

Người dùng **không được đánh giá món tùy ý trong catalogue**. Một món chỉ được chấm sao khi thỏa **đồng thời hai điều kiện**:

```text
① Món đã từng nằm trong thực đơn của người dùng
   EXISTS (SELECT 1 FROM meal_plan_items mpi
           JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
           WHERE mp.user_id = ? AND mpi.food_id = ?)

② Người dùng đã ghi nhận là đã ăn món đó
   EXISTS (SELECT 1 FROM food_diary
           WHERE user_id = ? AND food_id = ?)
```

| Điều kiện | Chặn tình huống nào |
|---|---|
| ① Có trong thực đơn | Người dùng duyệt catalogue rồi chấm sao hàng loạt món chưa bao giờ được gợi ý |
| ② Có trong nhật ký | Chấm sao món **chưa từng ăn** — ví dụ món bị thay thế hoặc bỏ bữa |

Điều kiện ② là cơ sở để bảng thống nhất nhãn gán trọng số **1.0** cho nguồn `feedback`: *đã ăn thật rồi mới đánh giá thì mới đáng tin nhất*. Bỏ điều kiện này thì lý do cho trọng số 1.0 không còn.

**MySQL không kiểm tra được ràng buộc này bằng `CHECK`** vì cần truy vấn con. Backend phải kiểm tra trước khi ghi, trả lỗi `409 FEEDBACK_NOT_ALLOWED` nếu vi phạm. Hai chỉ mục phục vụ phép kiểm tra: `food_diary.idx_user_food` và `meal_plan_items.idx_food`.

### Đánh giá lại theo thời gian

Bảng **cố ý không đặt** `UNIQUE (user_id, food_id)`. Khẩu vị thay đổi: hôm nay thấy ngon chấm 5 sao, ba tháng sau ăn lại thấy dở chấm 2 sao. Cả hai dòng đều được giữ.

| Cột | Vai trò với việc đánh giá lại |
|---|---|
| `created_at` | **Ngày đánh giá.** Phân biệt lần chấm cũ với lần chấm mới |
| `idx_user_food_time` | Chỉ mục `(user_id, food_id, created_at)` để lấy nhanh đánh giá gần nhất |

Bước dựng tập huấn luyện lấy **đánh giá gần nhất tính đến mốc thời gian cắt tập**:

```sql
SELECT f.*
FROM feedbacks f
JOIN (
    SELECT user_id, food_id, MAX(created_at) AS latest
    FROM feedbacks
    WHERE created_at < ?          -- mốc cắt train / test
    GROUP BY user_id, food_id
) m ON m.user_id = f.user_id AND m.food_id = f.food_id
   AND m.latest  = f.created_at;
```

> Không đưa **cả hai** đánh giá cũ và mới vào cùng một tập huấn luyện. Cùng một cặp `(người dùng, món ăn)` mang hai nhãn mâu thuẫn sẽ làm nhiễu mô hình. Lấy bản gần nhất trong mỗi khung thời gian là đúng: dữ liệu cũ đã bị dữ liệu mới thay thế.

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
    id                CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    batch_id          CHAR(36) NOT NULL,
    user_id           CHAR(36) NOT NULL,
    food_id           CHAR(36) NOT NULL,
    context_meal_type ENUM('breakfast','lunch','dinner','snack') NULL,

    -- ══ Điểm số, tách theo từng thành phần ══
    score             DECIMAL(6,4) NOT NULL,
    score_content     DECIMAL(6,4) NULL,
    score_ml          DECIMAL(6,4) NULL,
    alpha             DECIMAL(4,3) NULL,

    rank_position     SMALLINT UNSIGNED NULL,
    source            ENUM('rule_based','content_based','ml','hybrid') NOT NULL,
    model_id          INT UNSIGNED NULL,

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
| `was_selected` | Món có được Bước 4 đưa vào thực đơn cuối cùng không — cho biết ràng buộc dinh dưỡng đã bác bỏ bao nhiêu món điểm cao |

**Vì sao tách `score_content`, `score_ml` và `alpha` thành ba cột riêng.**

Công thức chuyển tiếp là `score = α · score_ml + (1 − α) · score_content`. Nếu chỉ lưu `score` tổng thì không thể phân tích ngược. Lưu tách ba cột cho phép trả lời bằng truy vấn những câu hỏi mà hội đồng rất dễ hỏi:

- Thành phần học máy đóng góp thêm bao nhiêu so với thuần tương đồng nội dung?
- Mốc `n_min`, `n_max` chọn đã hợp lý chưa?
- Ở vùng chuyển tiếp, hai thành phần có mâu thuẫn nhau không?

Đây là dữ liệu thực nghiệm gần như miễn phí — chỉ tốn ba cột.

> **Bảng này là nhật ký chấm điểm, không phải nhật ký hiển thị.** Nó ghi lại toàn bộ món đã được chấm điểm cho một lần sinh thực đơn, kèm thứ hạng. Đối chiếu `rank_position` với `was_selected` cho biết ràng buộc dinh dưỡng ở Bước 4 đã loại bỏ bao nhiêu món điểm cao — một phân tích đắt giá cho Chương 3.

> Cột `was_interacted` của thiết kế trước **đã bị bỏ**. Nó đếm số lượt vuốt trên món được gợi ý, nhưng người dùng không còn vuốt sau khi qua phiên khảo sát. Nguồn mẫu âm thay thế: món trong thực đơn bị `replaced` hoặc `skipped`.

---

# 7. Nhóm Thực đơn và Machine Learning

## 7.1 `meal_plans` — Thực đơn theo ngày (bảng cha)

```sql
CREATE TABLE meal_plans (
    id                     CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id                CHAR(36) NOT NULL,
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
             / target_calories_kcal) VIRTUAL,

    total_preference_score DECIMAL(8,4) NULL,
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
| `exploration_ratio` | Tỷ lệ thăm dò **mục tiêu** của cơ chế 70-30. Trần `0.5` |
| `generation_source` | Ghi rõ thực đơn này sinh bằng phương pháp nào — nền tảng cho toàn bộ phần so sánh ở Chương 3 |

> `calorie_deviation_pct` là cột `GENERATED ... VIRTUAL` nên MySQL tự tính lúc đọc và **không lưu trữ byte nào**. Chọn `VIRTUAL` thay vì `STORED` để không có dư thừa lưu trữ — đây là một **thuộc tính dẫn xuất**, phụ thuộc hoàn toàn vào `actual_calories_kcal` và `target_calories_kcal`, nên lưu lại là vi phạm chuẩn 3. MySQL 8 vẫn đánh được chỉ mục trên cột `VIRTUAL` nếu sau này cần lọc nhanh. `chk_target_positive` chặn lỗi chia cho 0.

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
    id                  CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    meal_plan_id        CHAR(36) NOT NULL,
    food_id             CHAR(36) NOT NULL,
    meal_type           ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    portion_multiplier  DECIMAL(4,2) NOT NULL DEFAULT 1.00,

    predicted_score     DECIMAL(6,4) NULL,
    status              ENUM('suggested','kept','replaced','eaten','skipped')
                            NOT NULL DEFAULT 'suggested',
    replaced_by_food_id CHAR(36) NULL,
    replaced_at         DATETIME NULL,
    exploration_delta   DECIMAL(4,3) NULL,
    position            TINYINT UNSIGNED NULL,
    note                VARCHAR(255) NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (meal_plan_id)        REFERENCES meal_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id)             REFERENCES foods(id),
    FOREIGN KEY (replaced_by_food_id) REFERENCES foods(id),

    CONSTRAINT chk_expl_delta CHECK (exploration_delta IS NULL
                                     OR exploration_delta BETWEEN 0 AND 1),

    INDEX idx_plan_meal (meal_plan_id, meal_type),
    INDEX idx_status    (status),
    -- Kiểm tra "món này từng nằm trong thực đơn của user chưa"
    -- -> điều kiện bắt buộc để được đánh giá
    INDEX idx_food      (food_id)
) ENGINE=InnoDB;
```

| Cột | Vì sao cần |
|---|---|
| `status` | **Nguồn phản hồi ngầm định** mà đề cương gọi là "món được chọn, món bị thay thế" |
| `replaced_by_food_id` | Người dùng đổi sang món nào — tín hiệu kép: chê món cũ, thích món mới |
| `exploration_delta` | Biên độ nhiễu δ nếu món này thuộc nhóm thăm dò. `NULL` = nhóm khai thác |
| `predicted_score` | Điểm dự đoán lúc sinh, để về sau đối chiếu với phản hồi thực tế |

### Cơ chế 70-30 và hai cột phục vụ nó

Để tránh thực đơn chỉ toàn một kiểu món, hệ thống chia số suất trong mỗi thực đơn thành hai nhóm:

```text
p_u   = vector sở thích hiện tại
p_u'  = chuẩn_hóa( p_u + δ · n )      n = vector nhiễu ngẫu nhiên đơn vị
                                       δ = biên độ nhiễu

70 %  số suất  →  chọn theo điểm với p_u    (KHAI THÁC — món chắc chắn hợp gu)
30 %  số suất  →  chọn theo điểm với p_u'   (THĂM DÒ  — món lân cận khẩu vị)
```

Điểm khác biệt so với thăm dò ngẫu nhiên thuần túy: món thăm dò vẫn nằm trong **vùng lân cận** khẩu vị người dùng, không phải món bất kỳ. Nhờ vậy xác suất được chấp nhận cao hơn, và khi được chấp nhận thì vector `p_u` dịch dần về hướng đó — khẩu vị mở rộng theo thời gian.

Hai cột ghi lại tham số của cơ chế này:

| Cột | Bảng | Ghi lại |
|---|---|---|
| `meal_plans.exploration_ratio` | Cha | Tỷ lệ thăm dò **mục tiêu** khi sinh thực đơn: `0.300`, `0.400`, `0.500` |
| `meal_plan_items.exploration_delta` | Con | Biên độ nhiễu δ của **từng món** thăm dò. `NULL` = món khai thác |

**Vì sao không có cột `is_exploration`.** Cột cờ đó suy ra được hoàn toàn từ `exploration_delta IS NOT NULL` — giữ cả hai là dư thừa dữ liệu, đúng loại lỗi đã sửa ở `food_diary` và `feedbacks`. Một cột `DECIMAL` vừa trả lời được câu hỏi "có phải món thăm dò không", vừa cho biết luôn δ bằng bao nhiêu.

**Vì sao `exploration_ratio` nằm ở bảng cha dù suy ra được từ các dòng con.** Đây là **tỷ lệ mục tiêu**, không phải tỷ lệ đạt được — giống cặp `target_calories_kcal` với `actual_calories_kcal`. Bước 4 có thể không tìm đủ món thăm dò khả thi, khiến tỷ lệ thực tế thấp hơn mục tiêu. Muốn phân tích được điều đó thì phải lưu con số mục tiêu.

**Ràng buộc trần 0.5.** Quá nửa thực đơn là món thử nghiệm thì nó không còn là gợi ý cá nhân hóa nữa. `chk_expl_ratio` chặn ở tầng CSDL.

> Hai cột này cho hẳn một mục thực nghiệm Chương 3: chạy hệ thống ở các mức `0.300`, `0.400`, `0.500`, đo tỷ lệ món thăm dò bị thay thế và tỷ lệ được ăn thật, từ đó chọn tỷ lệ tối ưu. Truy vấn sẵn ở Mục 8.5.

---

## 7.3 `user_preference_profiles` — Hồ sơ sở thích (vector trọng số)

```sql
CREATE TABLE user_preference_profiles (
    user_id         CHAR(36) NOT NULL PRIMARY KEY,
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

> **`weights` KHÔNG phải cân nặng.** Đây là **hệ số** của vector khẩu vị — nghĩa
> toán học của chữ "trọng số", không liên quan gì tới `weight_kg`. Trong lược đồ
> có 5 cột chứa chữ `weight` với hai nghĩa khác nhau; xem bảng phân biệt ở cuối
> mục này.

Nội dung thật của cột, đúng 20 khóa khớp với 20 chiều của vector đặc trưng:

```json
{
  "protein_share":  0.31,
  "carb_share":    -0.08,
  "fat_share":      0.12,
  "kcal_norm":      0.22,
  "sugar_share":    0.09,
  "sodium_norm":   -0.52,
  "fiber_norm":     0.41,
  "spice":         -0.44,

  "cat_com":            0.05,
  "cat_do_uong":       -0.11,
  "cat_mon_canh":       0.18,
  "cat_mon_chien":     -0.37,
  "cat_mon_cuon":       0.02,
  "cat_mon_goi":        0.24,
  "cat_mon_kho":        0.09,
  "cat_mon_luoc_hap":   0.15,
  "cat_mon_nuoc":       0.35,
  "cat_mon_nuong":     -0.06,
  "cat_mon_xao":       -0.21,
  "cat_trang_mieng":    0.03
}
```

Đọc vector này ra tiếng người: *người dùng thiên về món nước (0,35) và món gỏi
(0,24), tránh món chiên (−0,37) và món xào (−0,21), không thích đồ cay (−0,44),
ưa món giàu đạm (0,31) hơn giàu bột đường (−0,08).*

Chính khả năng diễn giải này là lý do dùng Rocchio ở Giai đoạn 1 — nó cho phép
nói với người dùng *vì sao* một món được gợi ý.

| Cột | Mô tả |
|---|---|
| `user_id` | Vừa là khóa chính vừa là khóa ngoại — quan hệ 1:1 với `users`, mỗi người đúng một hồ sơ sở thích |
| `feature_version` | Phiên bản định nghĩa đặc trưng mà `weights` được dựng theo. **Bắt buộc**: đổi tập nhóm món là đổi số chiều, nên mọi vector cũ phải dựng lại — cột này cho biết vector nào đã lạc hậu |
| `weights` | Vector `p_u` — **19 hệ số** của thuật toán Rocchio, lưu dạng JSON. Xem ví dụ đầy đủ bên dưới |
| `sum_abs_weight` | Tổng `Σ|w|` — **bắt buộc phải lưu**, xem giải thích bên dưới |
| `n_signals` | Số tín hiệu đã tích lũy, dùng tính hệ số trộn `α` |
| `stage` | Giai đoạn hiện tại của người dùng |
| `alpha` | Hệ số trộn đã hiệu lực, lưu sẵn để Backend không phải tính lại mỗi request |
| `updated_at` | Lần cuối vector được cập nhật. Dùng để phát hiện hồ sơ "chết" — người dùng không tương tác nhiều tháng |

> **Bảng này KHÔNG chứa dữ liệu cơ thể.** Chiều cao, cân nặng, tuổi, giới tính nằm ở `health_profiles`; chúng là dữ liệu **cơ thể**, không phải dữ liệu **khẩu vị**. Nhưng dữ liệu cơ thể vẫn tham gia mô hình ở Giai đoạn 2 — khối "đặc trưng người dùng" trong vector đầu vào được JOIN từ `health_profiles` lúc trích xuất đặc trưng, không phải lưu trùng ở đây.

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

### Năm cột chứa chữ `weight` — hai nghĩa khác nhau

Đây là chỗ dễ nhầm nhất của toàn bộ lược đồ, vì trong một ứng dụng dinh dưỡng
thì "weight" gần như luôn có nghĩa là cân nặng.

| Cột | Nghĩa | Kiểu |
|---|---|---|
| `health_profiles.weight_kg` | **Cân nặng** cơ thể, hiện tại | `DECIMAL(5,2)` |
| `body_logs.weight_kg` | **Cân nặng** cơ thể theo thời gian | `DECIMAL(5,2)` |
| `user_preference_profiles.weights` | **Hệ số** vector khẩu vị (17 số) | `JSON` |
| `user_preference_profiles.sum_abs_weight` | **Mẫu số** `Σ\|w\|` của công thức Rocchio | `DECIMAL(10,4)` |
| `ml_training_samples.sample_weight` | **Độ tin cậy** của một mẫu huấn luyện | `DECIMAL(4,3)` |

Hai cột đầu là cân nặng. Ba cột sau là trọng số theo nghĩa toán học — hệ số
trong một tổ hợp tuyến tính — và không liên quan gì tới cơ thể người dùng.

Phân biệt bằng một câu: **`weight_kg` có đơn vị, `weights` thì không.**

> **`stage` và `alpha` là dữ liệu dẫn xuất, cố ý lưu dư.** Về lý thuyết cả hai suy ra được từ `n_signals`. Nhưng lưu sẵn giúp gỡ lỗi dễ hơn nhiều — nhìn thẳng vào bảng là biết người dùng đang ở giai đoạn nào, không phải đọc ngược logic trong mã nguồn.

---

## 7.4 `ml_training_samples` — Tập dữ liệu huấn luyện đã đóng băng

```sql
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
    collected_at     DATETIME NOT NULL,
    profile_snapshot JSON NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_label CHECK (label BETWEEN 0 AND 1),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,

    UNIQUE KEY uq_sample (dataset_version, user_id, food_id, source),
    INDEX idx_dataset_split (dataset_version, split),
    INDEX idx_dataset_user  (dataset_version, user_id),
    INDEX idx_collected     (collected_at)
) ENGINE=InnoDB;
```

| Cột | Ý nghĩa |
|---|---|
| `dataset_version` | Nhãn phiên bản tập dữ liệu, ví dụ `ds_2026_10_v1`. Mọi kết quả đánh giá truy về được đúng tập đã sinh ra nó |
| `user_id` / `food_id` | Cặp (người, món) mà mẫu này nói về |
| `label` | Mức độ ưa thích `∈ [0,1]` — **biến mục tiêu** của mô hình |
| `sample_weight` | **Độ tin cậy** của nhãn `∈ [0,1]` — khác hẳn `label`, xem bên dưới |
| `source` | Tín hiệu đến từ bảng nào, 7 giá trị |
| `context_meal_type` | Bữa ăn lúc thu tín hiệu. Cùng một món có thể được thích ở bữa sáng mà không ở bữa tối |
| `split` | `train` / `val` / `test` — **đóng băng**, không chia lại mỗi lần chạy |
| `fold` | Số thứ tự lần gập khi kiểm định chéo |
| `collected_at` | Thời điểm thu tín hiệu **gốc**, không phải thời điểm tạo dòng này |
| `profile_snapshot` | Vector sở thích **tại thời điểm thu tín hiệu** — chống rò rỉ dữ liệu |

**`label` và `sample_weight` trả lời hai câu khác nhau.** `label` là *người dùng thích món này đến mức nào*; `sample_weight` là *ta tin con số đó đến mức nào*. Một đánh giá 5 sao (trọng số 1,0) đáng tin hơn hẳn một suất bị bỏ không ăn (0,3), vì bỏ bữa là tín hiệu nhập nhằng — có thể không thích, có thể hôm đó không có thời gian.

**`profile_snapshot` tồn tại để chống rò rỉ dữ liệu.** Đặc trưng chéo `cos(p_u, vᵢ)` là đầu vào của mô hình. Nếu dựng tập huấn luyện bằng `p_u` *hiện tại* — vector đã được cập nhật bởi chính tín hiệu đang xét — thì đặc trưng đã chứa thông tin về nhãn. Mô hình sẽ cho kết quả đánh giá rất đẹp mà vô dụng khi chạy thật.

**`split` phải đóng băng.** Chia lại mỗi lần chạy thì một mẫu hôm nay ở `test`, mai ở `train`; khi đó hai mô hình không so sánh được với nhau vì chúng được đánh giá trên hai tập khác nhau.

**`collected_at` khác `created_at`.** Một tín hiệu từ tháng 8 có thể được đưa vào tập dữ liệu dựng tháng 10. Chia tập theo thời gian — huấn luyện trên quá khứ, kiểm tra trên tương lai — cần `collected_at`.

### Bảng quy đổi nhãn từ các nguồn tín hiệu

| `source` | Bảng gốc | `label` | `sample_weight` |
|---|---|---|---|
| `feedback` (5 sao) | `feedbacks` | 1.000 | 1.0 |
| `feedback` (4 sao) | `feedbacks` | 0.750 | 1.0 |
| `feedback` (3 sao) | `feedbacks` | 0.500 | 1.0 |
| `feedback` (2 sao) | `feedbacks` | 0.250 | 1.0 |
| `feedback` (1 sao) | `feedbacks` | 0.000 | 1.0 |
| `diary` | `food_diary` | 0.800 | 0.9 |
| `swipe` (like) | `interactions` | 0.900 | 0.7 |
| `swipe` (neutral) | `interactions` | 0.500 | 0.7 |
| `swipe` (dislike) | `interactions` | 0.000 | 0.7 |
| `plan_kept` | `meal_plan_items` | 0.700 | 0.6 |
| `plan_replaced` | `meal_plan_items` | 0.150 | 0.6 |
| `plan_skipped` | `meal_plan_items` (`status = 'skipped'`) | 0.300 | 0.3 |
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
| `version` | Nhãn phiên bản mô hình, `UNIQUE`. Ví dụ `v1.2.0`. Là thứ `meal_plans.model_id` truy về để biết thực đơn do mô hình nào sinh |
| `algorithm` | Thuật toán đã dùng. Ba giá trị tương ứng ba mô hình sẽ thử và so sánh |
| `feature_version` | Phiên bản định nghĩa đặc trưng. Phải khớp với `user_preference_profiles.feature_version` của người dùng, nếu không thì vector đầu vào có số chiều khác với lúc huấn luyện |
| `dataset_version` | Phiên bản tập dữ liệu đã huấn luyện trên. Trỏ về `ml_training_samples.dataset_version` — nhờ vậy mọi kết quả đều truy lại được chính xác tập dữ liệu nào tạo ra nó |
| `hyperparams` | Siêu tham số, ví dụ `{"n_estimators": 200, "max_depth": 8}`. Cần để tái lập lại đúng mô hình |
| `scaler_params` | Tham số chuẩn hóa (min/max hoặc mean/std) **đóng băng tại lúc huấn luyện** |
| `feature_importance` | Độ quan trọng của từng đặc trưng — vẽ thẳng thành biểu đồ cho Chương 3 |
| `n_train` / `n_test` | Cỡ tập huấn luyện và tập kiểm tra. `NOT NULL` — buộc phải là số thật, không được để trống. Đây là con số hội đồng sẽ hỏi đầu tiên |
| `artifact_path` | Đường dẫn file `.joblib`. **Không lưu mô hình dạng BLOB trong CSDL** |
| `is_active` | Đúng **một** mô hình mang giá trị 1 — mô hình đang phục vụ. Các mô hình cũ giữ lại để so sánh và để quay về nếu bản mới kém hơn |
| `trained_at` | Thời điểm huấn luyện |
| `note` | Ghi chú tự do, ví dụ *"thêm đặc trưng chéo cosin"* — để sau ba tháng còn biết bản này khác bản trước ở đâu |

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

| Cột | Ý nghĩa |
|---|---|
| `model_id` | Mô hình được đánh giá |
| `variant` | **Phương án nào** được đo — xem bảng dưới |
| `metric` | Chỉ số: `precision` / `recall` / `ndcg` / `map` / `mae` / `rmse` / `f1` / `auc` |
| `k_value` | Giá trị `k` của chỉ số top-k. `NULL` với chỉ số không cần `k` |
| `value` | Con số đo được |
| `fold` | Lần gập thứ mấy. `NULL` nếu không kiểm định chéo |
| `evaluated_at` | Thời điểm đo |

**Vì sao cần `k_value`.** Người dùng chỉ thấy 4–6 suất mỗi ngày, nên `precision@5` nói đúng điều ta quan tâm; `precision` trên toàn bộ 500 món thì không nói gì.

**Vì sao `ndcg@k` quan trọng hơn `precision@k` với hệ này.** `precision` chỉ đếm bao nhiêu món trong top-k là đúng, bỏ qua thứ tự. `ndcg` có tính thứ tự — gợi ý đúng món nhưng xếp cuối danh sách thì người dùng không bao giờ thấy.

**Vì sao `fold` là cột riêng chứ không lưu sẵn giá trị trung bình.** Lưu từng lần gập cho phép báo cáo **trung bình ± độ lệch chuẩn**. Một mô hình đạt 0,72 ± 0,02 khác hẳn một mô hình đạt 0,72 ± 0,15 — cái thứ hai không ổn định và không đáng tin.

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

### 8.3 Ràng buộc dinh dưỡng đã bác bỏ bao nhiêu món điểm cao

Đối chiếu thứ hạng chấm điểm với việc có vào được thực đơn hay không:

```sql
SELECT
    r.source,
    r.rank_position,
    COUNT(*)                                          AS so_lan_duoc_cham_diem,
    SUM(r.was_selected)                               AS so_lan_vao_thuc_don,
    ROUND(100.0 * SUM(r.was_selected) / COUNT(*), 2)  AS ty_le_duoc_chon_pct,
    ROUND(AVG(r.score), 4)                            AS diem_tb
FROM recommendations r
WHERE r.rank_position <= 10
GROUP BY r.source, r.rank_position
ORDER BY r.source, r.rank_position;
```

> Món xếp hạng 1 mà tỷ lệ vào thực đơn thấp nghĩa là **ràng buộc năng lượng ở Bước 4 thường xuyên bác bỏ món hợp khẩu vị nhất**. Đây chính là sự đánh đổi giữa "hợp khẩu vị" và "cân đối dinh dưỡng" mà đề cương gọi là *hai yêu cầu vốn mâu thuẫn nhau* — có số liệu định lượng để trình bày.

Các độ đo xếp hạng chuẩn (Precision@K, Recall@K, NDCG) tính **ngoại tuyến** trên tập `test` của `ml_training_samples`, kết quả ghi vào `ml_evaluations` — xem Mục 8.2.

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

### 8.5 Hiệu quả của cơ chế thăm dò 70-30

Truy vấn này trả lời câu hỏi trung tâm: **tỷ lệ thăm dò bao nhiêu là hợp lý?** Chạy hệ thống lần lượt ở các mức `0.300`, `0.400`, `0.500` rồi đối chiếu.

```sql
SELECT
    mp.exploration_ratio                                            AS ty_le_tham_do,
    CASE WHEN mpi.exploration_delta IS NULL
         THEN 'khai thac' ELSE 'tham do' END                        AS nhom,
    COUNT(*)                                                        AS so_mon,
    ROUND(AVG(mpi.exploration_delta), 3)                            AS bien_do_nhieu_tb,
    ROUND(AVG(mpi.predicted_score), 4)                              AS diem_du_doan_tb,
    ROUND(100.0 * SUM(mpi.status = 'replaced') / COUNT(*), 2)       AS ty_le_bi_thay_the_pct,
    ROUND(100.0 * SUM(mpi.status = 'eaten')    / COUNT(*), 2)       AS ty_le_duoc_an_pct
FROM meal_plan_items mpi
JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
GROUP BY mp.exploration_ratio, nhom
ORDER BY mp.exploration_ratio, nhom;
```

**Cách đọc kết quả:**

| Dấu hiệu | Kết luận |
|---|---|
| Nhóm thăm dò bị thay thế nhiều hơn hẳn nhóm khai thác | Biên độ nhiễu δ quá lớn — món gợi ý ra xa khẩu vị |
| Nhóm thăm dò được ăn gần bằng nhóm khai thác | δ hợp lý, có thể nâng tỷ lệ thăm dò lên |
| Hai nhóm có điểm dự đoán gần như nhau | δ quá nhỏ — món "mới" thực chất trùng món cũ, không khám phá được gì |

Truy vấn kèm theo để xem tỷ lệ thăm dò **thực tế** có đạt mục tiêu không:

```sql
SELECT
    mp.id,
    mp.exploration_ratio                                              AS muc_tieu,
    ROUND(SUM(mpi.exploration_delta IS NOT NULL) / COUNT(*), 3)       AS thuc_te,
    COUNT(*)                                                          AS so_mon
FROM meal_plans mp
JOIN meal_plan_items mpi ON mpi.meal_plan_id = mp.id
WHERE mp.exploration_ratio IS NOT NULL
GROUP BY mp.id, mp.exploration_ratio
HAVING thuc_te < muc_tieu * 0.8;
```

> Thực đơn xuất hiện trong kết quả là những lần Bước 4 **không tìm đủ món thăm dò khả thi** — thường do ràng buộc cứng thu hẹp tập ứng viên quá mức.

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
| `interactions` | `session_id` | Nhóm các lượt vuốt của một phiên khảo sát |
| `food_diary` | `(user_id, ate_on, meal_type, food_id)` | Nhật ký theo ngày; **ghép khóa tự nhiên** tính tỷ lệ tuân thủ |
| `food_diary` | `(user_id, food_id, ate_on)` | **Bước 2** — lọc món đã ăn trong N ngày |
| `feedbacks` | `(food_id, rating)` | Điểm trung bình theo món |
| `feedbacks` | `(user_id, food_id, created_at)` | Lấy **đánh giá gần nhất** khi khẩu vị thay đổi theo thời gian |
| `meal_plan_items` | `food_id` | Kiểm tra điều kiện được đánh giá: món từng ở trong thực đơn |
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
| `users.role` chỉ hai giá trị, không tách bảng `admins` | Chỉ có hai vai trò và không phân quyền chi tiết; tách bảng sinh hai luồng xác thực mà không đổi lại được gì |
| `users.is_active` | Khóa tài khoản từ trang quản trị. Khác vai trò với `foods.is_active` — cột kia là ẩn món khỏi gợi ý |
| `foods.owner_id` dùng `ON DELETE CASCADE` | Để `NULL` là đẩy món chưa kiểm duyệt vào danh mục chung của mọi người |
| `UNIQUE (owner_id, name)` thay vì chỉ `name` | Hai người dùng có thể cùng tự thêm món trùng tên; ràng buộc chỉ trên `name` chặn oan người thứ hai |
| Bỏ `foods.origin` | Món phổ biến ở mọi miền nên vùng xuất xứ không chứng minh được gì; không mã nào đọc tới cột này |
| `body_logs` tách khỏi `health_profiles` | `health_profiles` chỉ có một dòng mỗi người nên `weight_kg` bị ghi đè; không tách thì không vẽ được biểu đồ tiến trình |
| `meal_plans.actual_*` cho phép `NULL` | Số `0` là giá trị hợp lệ về mặt số học, dùng nó để nói "chưa có dữ liệu" sẽ khiến cột dẫn xuất tính ra −100 % |
| `food_diary` không có `meal_plan_item_id` | Đường đi vòng tới `foods` và `users`. Thay bằng ghép khóa tự nhiên |
| `feedbacks` không có `food_diary_id` | Cùng lỗi đường đi vòng. Đánh giá là ý kiến về **món ăn**, không phải về một **lần ăn** |
| `meal_plan_items` có hai FK cùng trỏ `foods` | Không phải dư thừa — `food_id` và `replaced_by_food_id` là hai **vai trò** khác nhau |
| `feedbacks` không có `UNIQUE (user_id, food_id)` | Cố ý, để đánh giá lại được khi khẩu vị đổi theo thời gian. `created_at` phân biệt các lần chấm |
| Điều kiện được đánh giá kiểm tra ở tầng ứng dụng | MySQL không hỗ trợ truy vấn con trong `CHECK`. Backend kiểm tra, trả `409 FEEDBACK_NOT_ALLOWED` |
| `exploration_delta` thay cho cột cờ `is_exploration` | Cột cờ suy ra được từ `exploration_delta IS NOT NULL` — giữ cả hai là dư thừa |
| `meal_plans.exploration_ratio` vẫn giữ dù suy ra được | Đây là tỷ lệ **mục tiêu**, khác tỷ lệ **đạt được** — cùng logic với cặp `target` / `actual` |
| `interactions` bỏ `session_type`, `context_meal_type`, `recommendation_id` | Cả ba là cột hằng số vì vuốt chỉ chạy một lần. Bỏ đi thì lược đồ **hết sạch đường đi vòng** |
| `recommendations` bỏ `was_interacted` | Không còn ai vuốt món được gợi ý. Mẫu âm lấy từ `status` = `replaced` hoặc `skipped` |
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
| Bảng embedding / vector database | Vector đặc trưng chỉ 20 chiều |
