# ERD — bảng đối chiếu tên tiếng Anh và tên tiếng Việt

Ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa — Trần Lâm Nghĩa (22115053122231).

CSDL `nutrition_rec` · MySQL 8 · InnoDB · utf8mb4_unicode_ci · **22 bảng, 211 cột, 29 khóa ngoại, 30 cột ENUM**.

> Tài liệu này sinh tự động bằng `tools/baocao/build_erd_vi.py`. Kiểu dữ liệu và khóa đọc thẳng từ `information_schema`, tên tiếng Việt lấy từ `tools/baocao/erd_vi.py`. Sửa tay vào đây sẽ mất khi chạy lại.

## 1. Quy tắc đặt tên tiếng Việt

Tên tiếng Anh chuyển thẳng sang tiếng Việt rồi viết dính liền theo kiểu lạc đà: **chữ cái đầu không viết hoa, không khoảng trắng, giữ nguyên dấu**.

| Tên tiếng Anh | Tên tiếng Việt |
|---|---|
| `users` | `ngườiDùng` |
| `password_hash` | `mãBămMậtKhẩu` |
| `meal_plan_items` | `mónTrongThựcĐơn` |
| `vitamin_a_mcg` | `vitaminAMicrogam` |

Vài quy ước giữ giống nhau ở mọi bảng, để đọc tên là đoán được ý nghĩa:

- `id` → `mã`, còn `<bảng>_id` → `mã<Bảng>`.
- Cột `DATETIME` dùng tiền tố `thờiĐiểm`, cột `DATE` dùng `ngày`. Đọc tên cột là biết cột đó có giờ phút hay không.
- `note` → `ghiChú`, `description` → `môTả`, `created_at` → `thờiĐiểmTạo`.

**Sơ đồ ERD nộp kèm vẫn để tên tiếng Anh không dấu**, theo yêu cầu tên thực thể và tên thuộc tính không có dấu tiếng Việt. Bảng dưới đây là cầu nối giữa sơ đồ đó và phần thuyết minh tiếng Việt của báo cáo.

## 2. Danh sách thực thể

| STT | Tên tiếng Anh | Tên tiếng Việt | Số cột | Diễn giải |
|---:|---|---|---:|---|
| 1 | `users` | `ngườiDùng` | 10 | Tài khoản dùng chung cho ứng dụng Android và trang quản trị, phân biệt bằng vai trò. |
| 2 | `conditions` | `bệnhLý` | 4 | Từ điển bệnh lý, dị ứng, chứng không dung nạp và chế độ ăn. |
| 3 | `tags` | `nhãn` | 4 | Từ vựng có kiểm soát gắn cho món ăn: chất gây dị ứng, chế độ ăn, đặc điểm dinh dưỡng. |
| 4 | `food_categories` | `danhMụcMónĂn` | 4 | Nhóm món ăn, dùng làm đặc trưng one-hot cho học máy. |
| 5 | `ml_models` | `môHìnhHọcMáy` | 14 | Mỗi dòng là một lần huấn luyện đã hoàn tất, kèm tham số và đường dẫn tệp mô hình. |
| 6 | `rda_reference` | `nhuCầuKhuyếnNghị` | 9 | Bảng tra cứu nhu cầu dinh dưỡng khuyến nghị theo tuổi và giới. |
| 7 | `health_profiles` | `hồSơSứcKhỏe` | 17 | Số đo cơ thể và mục tiêu dinh dưỡng của người dùng, mỗi người một dòng. |
| 8 | `user_conditions` | `bệnhLýNgườiDùng` | 6 | Người dùng khai mắc bệnh lý nào, ở mức độ nào. |
| 9 | `user_preference_profiles` | `hồSơKhẩuVị` | 8 | Véc-tơ khẩu vị của người dùng, cập nhật sau mỗi tín hiệu tương tác. |
| 10 | `body_logs` | `nhậtKýCơThể` | 6 | Người dùng tự ghi cân nặng theo ngày để theo dõi tiến triển. |
| 11 | `foods` | `mónĂn` | 12 | Món ăn trong hệ thống, gồm cả món do người dùng tự thêm. |
| 12 | `condition_rules` | `quyTắcBệnhLý` | 12 | Ràng buộc mà mỗi bệnh lý đặt ra: cấm nhãn, buộc có nhãn, hoặc giới hạn một chất. |
| 13 | `food_nutrition` | `dinhDưỡngMónĂn` | 18 | Thành phần dinh dưỡng của một khẩu phần, mỗi món một dòng. |
| 14 | `food_tags` | `nhãnCủaMónĂn` | 2 | Bảng nối nhiều-nhiều giữa món ăn và nhãn. |
| 15 | `meal_plans` | `thựcĐơnNgày` | 18 | Thực đơn hệ thống sinh cho một người trong một ngày. |
| 16 | `recommendations` | `khuyếnNghịMónĂn` | 14 | Nhật ký từng món đã được gợi ý, giữ lại điểm số để đánh giá về sau. |
| 17 | `food_diary` | `nhậtKýĂnUống` | 7 | Người dùng tự ghi đã ăn món gì, vào buổi nào. |
| 18 | `feedbacks` | `phảnHồi` | 6 | Người dùng chấm điểm và nhận xét về món ăn. |
| 19 | `interactions` | `tươngTác` | 6 | Thao tác vuốt thích hoặc không thích trong phiên thăm dò khẩu vị. |
| 20 | `ml_training_samples` | `mẫuHuấnLuyện` | 13 | Tập mẫu đã đóng băng theo phiên bản dữ liệu để huấn luyện lại cho ra cùng kết quả. |
| 21 | `ml_evaluations` | `đánhGiáMôHình` | 8 | Kết quả đo chất lượng của từng mô hình theo từng độ đo. |
| 22 | `meal_plan_items` | `mónTrongThựcĐơn` | 13 | Từng món trong một thực đơn ngày, kèm việc người dùng giữ hay đổi món. |

## 3. Thuộc tính của từng thực thể

Cột **Khóa**: `PK` khóa chính · `FK` khóa ngoại · `UQ` duy nhất một cột · `UQ*` duy nhất theo tổ hợp nhiều cột.

### 3.1. `users` — `ngườiDùng`

Tài khoản dùng chung cho ứng dụng Android và trang quản trị, phân biệt bằng vai trò.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `email` | `thưĐiệnTử` | `VARCHAR(255)` | UQ | — |
| 3 | `role` | `vaiTrò` | `ENUM('user', 'admin')` |  | — |
| 4 | `is_active` | `đangHoạtĐộng` | `TINYINT(1)` |  | — |
| 5 | `password_hash` | `mãBămMậtKhẩu` | `VARCHAR(255)` |  | — |
| 6 | `display_name` | `tênHiểnThị` | `VARCHAR(100)` |  | — |
| 7 | `avatar_url` | `đườngDẫnẢnhĐạiDiện` | `VARCHAR(500)` |  | có |
| 8 | `onboarding_completed_at` | `thờiĐiểmHoànTấtKhởiTạo` | `DATETIME` |  | có |
| 9 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |
| 10 | `updated_at` | `thờiĐiểmCậpNhật` | `DATETIME` |  | — |

### 3.2. `conditions` — `bệnhLý`

Từ điển bệnh lý, dị ứng, chứng không dung nạp và chế độ ăn.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `INT UNSIGNED` | PK | — |
| 2 | `name_vi` | `tênTiếngViệt` | `VARCHAR(100)` | UQ | — |
| 3 | `condition_type` | `loạiBệnhLý` | `ENUM('disease', 'allergy', 'intolerance', 'diet')` |  | — |
| 4 | `description` | `môTả` | `VARCHAR(255)` |  | có |

### 3.3. `tags` — `nhãn`

Từ vựng có kiểm soát gắn cho món ăn: chất gây dị ứng, chế độ ăn, đặc điểm dinh dưỡng.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `INT UNSIGNED` | PK | — |
| 2 | `name_vi` | `tênTiếngViệt` | `VARCHAR(100)` | UQ | — |
| 3 | `tag_type` | `loạiNhãn` | `ENUM('allergen', 'diet', 'nutrition')` |  | — |
| 4 | `description` | `môTả` | `VARCHAR(255)` |  | có |

### 3.4. `food_categories` — `danhMụcMónĂn`

Nhóm món ăn, dùng làm đặc trưng one-hot cho học máy.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `name` | `tên` | `VARCHAR(100)` | UQ | — |
| 3 | `description` | `môTả` | `VARCHAR(255)` |  | có |
| 4 | `icon_url` | `đườngDẫnBiểuTượng` | `VARCHAR(500)` |  | có |

### 3.5. `ml_models` — `môHìnhHọcMáy`

Mỗi dòng là một lần huấn luyện đã hoàn tất, kèm tham số và đường dẫn tệp mô hình.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `INT UNSIGNED` | PK | — |
| 2 | `version` | `phiênBản` | `VARCHAR(20)` | UQ | — |
| 3 | `algorithm` | `thuậtToán` | `ENUM('logistic_regression', 'random_forest', 'gradient_boosting')` |  | — |
| 4 | `feature_version` | `phiênBảnĐặcTrưng` | `VARCHAR(20)` |  | — |
| 5 | `dataset_version` | `phiênBảnTậpDữLiệu` | `VARCHAR(20)` |  | — |
| 6 | `hyperparams` | `siêuThamSố` | `JSON` |  | có |
| 7 | `scaler_params` | `thamSốChuẩnHóa` | `JSON` |  | có |
| 8 | `feature_importance` | `độQuanTrọngĐặcTrưng` | `JSON` |  | có |
| 9 | `n_train` | `sốMẫuHuấnLuyện` | `INT UNSIGNED` |  | — |
| 10 | `n_test` | `sốMẫuKiểmTra` | `INT UNSIGNED` |  | — |
| 11 | `artifact_path` | `đườngDẫnTệpMôHình` | `VARCHAR(500)` |  | — |
| 12 | `is_active` | `đangHoạtĐộng` | `TINYINT(1)` |  | — |
| 13 | `trained_at` | `thờiĐiểmHuấnLuyện` | `DATETIME` |  | — |
| 14 | `note` | `ghiChú` | `VARCHAR(255)` |  | có |

### 3.6. `rda_reference` — `nhuCầuKhuyếnNghị`

Bảng tra cứu nhu cầu dinh dưỡng khuyến nghị theo tuổi và giới.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `gender` | `giớiTính` | `ENUM('male', 'female', 'all')` | UQ* | — |
| 3 | `age_min` | `tuổiTốiThiểu` | `TINYINT UNSIGNED` | UQ* | — |
| 4 | `age_max` | `tuổiTốiĐa` | `TINYINT UNSIGNED` | UQ* | — |
| 5 | `nutrient` | `chấtDinhDưỡng` | `ENUM('calories_kcal', 'protein_g', 'carbs_g', 'fat_g', 'fiber_g', 'sugar_g', 'sodium_mg', 'cholesterol_mg', 'purine_mg', 'calcium_mg', 'iron_mg', 'zinc_mg', 'vitamin_a_mcg', 'vitamin_c_mg')` | UQ* | — |
| 6 | `qualifier` | `nhómPhụNguyênVăn` | `VARCHAR(30)` | UQ* | có |
| 7 | `rda_value` | `giáTrịKhuyếnNghị` | `DECIMAL(8,2)` |  | — |
| 8 | `unit` | `đơnVị` | `VARCHAR(10)` |  | — |
| 9 | `source` | `nguồnTàiLiệu` | `VARCHAR(150)` |  | — |

Duy nhất theo tổ hợp: (`gender`, `age_min`, `age_max`, `nutrient`, `COALESCE(qualifier, '')`) — `giớiTính`, `tuổiTốiThiểu`, `tuổiTốiĐa`, `chấtDinhDưỡng`, `COALESCE(qualifier, '')`.

### 3.7. `health_profiles` — `hồSơSứcKhỏe`

Số đo cơ thể và mục tiêu dinh dưỡng của người dùng, mỗi người một dòng.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK UQ | — |
| 3 | `gender` | `giớiTính` | `ENUM('male', 'female', 'other')` |  | — |
| 4 | `date_of_birth` | `ngàySinh` | `DATE` |  | — |
| 5 | `height_cm` | `chiềuCaoCm` | `DECIMAL(5,2)` |  | — |
| 6 | `weight_kg` | `cânNặngKg` | `DECIMAL(5,2)` |  | — |
| 7 | `bmi` | `chỉSốKhốiCơThể` | `DECIMAL(5,2)` |  | có |
| 8 | `activity_level` | `mứcVậnĐộng` | `ENUM('sedentary', 'light', 'moderate', 'active', 'very_active')` |  | — |
| 9 | `goal` | `mụcTiêu` | `ENUM('lose_weight', 'maintain', 'gain_weight', 'healthy_eating')` |  | — |
| 10 | `bmr_kcal` | `nhuCầuChuyểnHóaCơBản` | `SMALLINT UNSIGNED` |  | có |
| 11 | `tdee_kcal` | `tổngNăngLượngTiêuHao` | `SMALLINT UNSIGNED` |  | có |
| 12 | `daily_calories_target` | `năngLượngMụcTiêuNgày` | `SMALLINT UNSIGNED` |  | có |
| 13 | `target_protein_pct` | `tỷLệĐạmMụcTiêu` | `TINYINT UNSIGNED` |  | — |
| 14 | `target_carbs_pct` | `tỷLệTinhBộtMụcTiêu` | `TINYINT UNSIGNED` |  | — |
| 15 | `target_fat_pct` | `tỷLệChấtBéoMụcTiêu` | `TINYINT UNSIGNED` |  | — |
| 16 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |
| 17 | `updated_at` | `thờiĐiểmCậpNhật` | `DATETIME` |  | — |

### 3.8. `user_conditions` — `bệnhLýNgườiDùng`

Người dùng khai mắc bệnh lý nào, ở mức độ nào.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK UQ* | — |
| 3 | `condition_id` → `conditions.id` | `mãBệnhLý` | `INT UNSIGNED` | FK UQ* | — |
| 4 | `severity` | `mứcĐộNặng` | `ENUM('mild', 'moderate', 'severe')` |  | — |
| 5 | `note` | `ghiChú` | `VARCHAR(255)` |  | có |
| 6 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |

Duy nhất theo tổ hợp: (`user_id`, `condition_id`) — `mãNgườiDùng`, `mãBệnhLý`.

### 3.9. `user_preference_profiles` — `hồSơKhẩuVị`

Véc-tơ khẩu vị của người dùng, cập nhật sau mỗi tín hiệu tương tác.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | PK FK | — |
| 2 | `feature_version` | `phiênBảnĐặcTrưng` | `VARCHAR(20)` |  | — |
| 3 | `weights` | `véctơTrọngSố` | `JSON` |  | — |
| 4 | `sum_abs_weight` | `tổngTrịTuyệtĐốiTrọngSố` | `DECIMAL(10,4)` |  | — |
| 5 | `n_signals` | `sốTínHiệuĐãHọc` | `INT UNSIGNED` |  | — |
| 6 | `stage` | `giaiĐoạnGợiÝ` | `ENUM('cold', 'content', 'hybrid', 'ml')` |  | — |
| 7 | `alpha` | `hệSốPhaTrộn` | `DECIMAL(4,3)` |  | — |
| 8 | `updated_at` | `thờiĐiểmCậpNhật` | `DATETIME` |  | — |

### 3.10. `body_logs` — `nhậtKýCơThể`

Người dùng tự ghi cân nặng theo ngày để theo dõi tiến triển.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK UQ* | — |
| 3 | `logged_on` | `ngàyGhi` | `DATE` | UQ* | — |
| 4 | `weight_kg` | `cânNặngKg` | `DECIMAL(5,2)` |  | — |
| 5 | `note` | `ghiChú` | `VARCHAR(255)` |  | có |
| 6 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |

Duy nhất theo tổ hợp: (`user_id`, `logged_on`) — `mãNgườiDùng`, `ngàyGhi`.

### 3.11. `foods` — `mónĂn`

Món ăn trong hệ thống, gồm cả món do người dùng tự thêm.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `category_id` → `food_categories.id` | `mãDanhMục` | `CHAR(36)` | FK | — |
| 3 | `name` | `tên` | `VARCHAR(200)` | UQ* | — |
| 4 | `description` | `môTả` | `TEXT` |  | có |
| 5 | `image_url` | `đườngDẫnẢnh` | `VARCHAR(500)` |  | có |
| 6 | `spice_level` | `mứcĐộCay` | `TINYINT UNSIGNED` |  | — |
| 7 | `dish_role` | `vaiTròMón` | `ENUM('main', 'side_protein', 'side_veg', 'soup', 'snack', 'dessert', 'drink')` |  | — |
| 8 | `popularity_score` | `điểmPhổBiến` | `DECIMAL(5,4)` |  | — |
| 9 | `is_active` | `đangHoạtĐộng` | `TINYINT(1)` |  | — |
| 10 | `owner_id` → `users.id` | `mãChủSởHữu` | `CHAR(36)` | FK UQ* | có |
| 11 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |
| 12 | `updated_at` | `thờiĐiểmCậpNhật` | `DATETIME` |  | — |

Duy nhất theo tổ hợp: (`COALESCE(owner_id, '')`, `name`) — `COALESCE(owner_id, '')`, `tên`.

### 3.12. `condition_rules` — `quyTắcBệnhLý`

Ràng buộc mà mỗi bệnh lý đặt ra: cấm nhãn, buộc có nhãn, hoặc giới hạn một chất.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `condition_id` → `conditions.id` | `mãBệnhLý` | `INT UNSIGNED` | FK | — |
| 3 | `rule_type` | `loạiQuyTắc` | `ENUM('exclude_tag', 'require_tag', 'nutrient_limit')` |  | — |
| 4 | `tag_id` → `tags.id` | `mãNhãn` | `INT UNSIGNED` | FK | có |
| 5 | `nutrient` | `chấtDinhDưỡng` | `ENUM('calories_kcal', 'protein_g', 'carbs_g', 'fat_g', 'fiber_g', 'sugar_g', 'sodium_mg', 'cholesterol_mg', 'purine_mg', 'calcium_mg', 'iron_mg', 'zinc_mg', 'vitamin_a_mcg', 'vitamin_c_mg')` |  | có |
| 6 | `comparator` | `phépSoSánh` | `ENUM('lte', 'gte')` |  | có |
| 7 | `threshold` | `ngưỡng` | `DECIMAL(8,2)` |  | có |
| 8 | `scope` | `phạmViÁpDụng` | `ENUM('per_serving', 'per_meal', 'per_day')` |  | — |
| 9 | `severity_min` | `mứcĐộNặngTốiThiểu` | `ENUM('mild', 'moderate', 'severe')` |  | — |
| 10 | `is_hard` | `làRàngBuộcCứng` | `TINYINT(1)` |  | — |
| 11 | `penalty` | `điểmPhạt` | `DECIMAL(4,3)` |  | có |
| 12 | `note` | `ghiChú` | `VARCHAR(255)` |  | có |

### 3.13. `food_nutrition` — `dinhDưỡngMónĂn`

Thành phần dinh dưỡng của một khẩu phần, mỗi món một dòng.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK UQ | — |
| 3 | `serving_size_g` | `khẩuPhầnGam` | `SMALLINT UNSIGNED` |  | — |
| 4 | `calories_kcal` | `năngLượngKcal` | `DECIMAL(7,2)` |  | — |
| 5 | `protein_g` | `đạmGam` | `DECIMAL(6,2)` |  | — |
| 6 | `carbs_g` | `tinhBộtGam` | `DECIMAL(6,2)` |  | — |
| 7 | `fat_g` | `chấtBéoGam` | `DECIMAL(6,2)` |  | — |
| 8 | `fiber_g` | `chấtXơGam` | `DECIMAL(6,2)` |  | có |
| 9 | `sugar_g` | `đườngGam` | `DECIMAL(6,2)` |  | có |
| 10 | `sodium_mg` | `natriMiligam` | `DECIMAL(7,2)` |  | có |
| 11 | `cholesterol_mg` | `cholesterolMiligam` | `DECIMAL(7,2)` |  | có |
| 12 | `purine_mg` | `purinMiligam` | `DECIMAL(7,2)` |  | có |
| 13 | `calcium_mg` | `canxiMiligam` | `DECIMAL(7,2)` |  | có |
| 14 | `iron_mg` | `sắtMiligam` | `DECIMAL(6,2)` |  | có |
| 15 | `zinc_mg` | `kẽmMiligam` | `DECIMAL(6,2)` |  | có |
| 16 | `vitamin_a_mcg` | `vitaminAMicrogam` | `DECIMAL(7,2)` |  | có |
| 17 | `vitamin_c_mg` | `vitaminCMiligam` | `DECIMAL(6,2)` |  | có |
| 18 | `updated_at` | `thờiĐiểmCậpNhật` | `DATETIME` |  | — |

### 3.14. `food_tags` — `nhãnCủaMónĂn`

Bảng nối nhiều-nhiều giữa món ăn và nhãn.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | PK FK | — |
| 2 | `tag_id` → `tags.id` | `mãNhãn` | `INT UNSIGNED` | PK FK | — |

### 3.15. `meal_plans` — `thựcĐơnNgày`

Thực đơn hệ thống sinh cho một người trong một ngày.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK UQ* | — |
| 3 | `plan_date` | `ngàyÁpDụng` | `DATE` | UQ* | — |
| 4 | `target_calories_kcal` | `năngLượngMụcTiêuKcal` | `SMALLINT UNSIGNED` |  | — |
| 5 | `target_protein_g` | `đạmMụcTiêuGam` | `DECIMAL(6,2)` |  | — |
| 6 | `target_carbs_g` | `tinhBộtMụcTiêuGam` | `DECIMAL(6,2)` |  | — |
| 7 | `target_fat_g` | `chấtBéoMụcTiêuGam` | `DECIMAL(6,2)` |  | — |
| 8 | `actual_calories_kcal` | `năngLượngThựcTếKcal` | `DECIMAL(7,2)` |  | có |
| 9 | `actual_protein_g` | `đạmThựcTếGam` | `DECIMAL(6,2)` |  | có |
| 10 | `actual_carbs_g` | `tinhBộtThựcTếGam` | `DECIMAL(6,2)` |  | có |
| 11 | `actual_fat_g` | `chấtBéoThựcTếGam` | `DECIMAL(6,2)` |  | có |
| 12 | `calorie_deviation_pct` | `tỷLệLệchNăngLượng` | `DECIMAL(6,2)` |  | có |
| 13 | `total_preference_score` | `tổngĐiểmƯaThích` | `DECIMAL(8,4)` |  | có |
| 14 | `exploration_ratio` | `tỷLệThămDò` | `DECIMAL(4,3)` |  | có |
| 15 | `generation_source` | `nguồnSinhThựcĐơn` | `ENUM('rule_based', 'content_based', 'ml', 'hybrid')` |  | — |
| 16 | `model_id` → `ml_models.id` | `mãMôHình` | `INT UNSIGNED` | FK | có |
| 17 | `status` | `trạngThái` | `ENUM('draft', 'active', 'completed')` |  | — |
| 18 | `generated_at` | `thờiĐiểmSinh` | `DATETIME` |  | — |

Duy nhất theo tổ hợp: (`user_id`, `plan_date`) — `mãNgườiDùng`, `ngàyÁpDụng`.

### 3.16. `recommendations` — `khuyếnNghịMónĂn`

Nhật ký từng món đã được gợi ý, giữ lại điểm số để đánh giá về sau.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `batch_id` | `mãLượtGợiÝ` | `CHAR(36)` |  | — |
| 3 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK | — |
| 4 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK | — |
| 5 | `context_meal_type` | `buổiĂnNgữCảnh` | `ENUM('breakfast', 'lunch', 'dinner', 'snack')` |  | có |
| 6 | `score` | `điểmTổngHợp` | `DECIMAL(6,4)` |  | — |
| 7 | `score_content` | `điểmTheoNộiDung` | `DECIMAL(6,4)` |  | có |
| 8 | `score_ml` | `điểmTheoHọcMáy` | `DECIMAL(6,4)` |  | có |
| 9 | `alpha` | `hệSốPhaTrộn` | `DECIMAL(4,3)` |  | có |
| 10 | `rank_position` | `thứHạng` | `SMALLINT UNSIGNED` |  | có |
| 11 | `source` | `nguồnGợiÝ` | `ENUM('rule_based', 'content_based', 'ml', 'hybrid')` |  | — |
| 12 | `model_id` → `ml_models.id` | `mãMôHình` | `INT UNSIGNED` | FK | có |
| 13 | `was_selected` | `đãĐượcChọn` | `TINYINT(1)` |  | — |
| 14 | `recommended_at` | `thờiĐiểmGợiÝ` | `DATETIME` |  | — |

### 3.17. `food_diary` — `nhậtKýĂnUống`

Người dùng tự ghi đã ăn món gì, vào buổi nào.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK | — |
| 3 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK | — |
| 4 | `ate_on` | `ngàyĂn` | `DATE` |  | — |
| 5 | `meal_type` | `buổiĂn` | `ENUM('breakfast', 'lunch', 'dinner', 'snack')` |  | — |
| 6 | `portion_multiplier` | `hệSốKhẩuPhần` | `DECIMAL(4,2)` |  | — |
| 7 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |

### 3.18. `feedbacks` — `phảnHồi`

Người dùng chấm điểm và nhận xét về món ăn.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK | — |
| 3 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK | — |
| 4 | `rating` | `điểmĐánhGiá` | `TINYINT UNSIGNED` |  | — |
| 5 | `comment` | `nhậnXét` | `TEXT` |  | có |
| 6 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |

### 3.19. `interactions` — `tươngTác`

Thao tác vuốt thích hoặc không thích trong phiên thăm dò khẩu vị.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK | — |
| 3 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK | — |
| 4 | `action` | `hànhĐộng` | `ENUM('like', 'dislike', 'neutral', 'unknown')` |  | — |
| 5 | `session_id` | `mãPhiênVuốt` | `CHAR(36)` |  | — |
| 6 | `interacted_at` | `thờiĐiểmTươngTác` | `DATETIME` |  | — |

### 3.20. `ml_training_samples` — `mẫuHuấnLuyện`

Tập mẫu đã đóng băng theo phiên bản dữ liệu để huấn luyện lại cho ra cùng kết quả.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `dataset_version` | `phiênBảnTậpDữLiệu` | `VARCHAR(20)` | UQ* | — |
| 3 | `user_id` → `users.id` | `mãNgườiDùng` | `CHAR(36)` | FK UQ* | — |
| 4 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK UQ* | — |
| 5 | `label` | `nhãnMụcTiêu` | `DECIMAL(4,3)` |  | — |
| 6 | `sample_weight` | `trọngSốMẫu` | `DECIMAL(4,3)` |  | — |
| 7 | `source` | `nguồnTínHiệu` | `ENUM('feedback', 'swipe', 'diary', 'plan_kept', 'plan_replaced', 'plan_skipped', 'random_neg')` | UQ* | — |
| 8 | `context_meal_type` | `buổiĂnNgữCảnh` | `ENUM('breakfast', 'lunch', 'dinner', 'snack')` |  | có |
| 9 | `split` | `phầnChiaDữLiệu` | `ENUM('train', 'val', 'test')` |  | — |
| 10 | `fold` | `lượtKiểmChứngChéo` | `TINYINT UNSIGNED` |  | có |
| 11 | `collected_at` | `thờiĐiểmThuThập` | `DATETIME` |  | — |
| 12 | `profile_snapshot` | `ảnhChụpHồSơ` | `JSON` |  | có |
| 13 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |

Duy nhất theo tổ hợp: (`dataset_version`, `user_id`, `food_id`, `source`) — `phiênBảnTậpDữLiệu`, `mãNgườiDùng`, `mãMónĂn`, `nguồnTínHiệu`.

### 3.21. `ml_evaluations` — `đánhGiáMôHình`

Kết quả đo chất lượng của từng mô hình theo từng độ đo.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `BIGINT UNSIGNED` | PK | — |
| 2 | `model_id` → `ml_models.id` | `mãMôHình` | `INT UNSIGNED` | FK UQ* | — |
| 3 | `variant` | `phươngÁnSoSánh` | `ENUM('ml', 'content_based', 'rule_based', 'popularity', 'hybrid')` | UQ* | — |
| 4 | `metric` | `độĐo` | `ENUM('precision', 'recall', 'ndcg', 'map', 'mae', 'rmse', 'f1', 'auc')` | UQ* | — |
| 5 | `k_value` | `giáTrịK` | `TINYINT UNSIGNED` | UQ* | — |
| 6 | `value` | `giáTrị` | `DECIMAL(8,5)` |  | — |
| 7 | `fold` | `lượtKiểmChứngChéo` | `TINYINT UNSIGNED` | UQ* | — |
| 8 | `evaluated_at` | `thờiĐiểmĐánhGiá` | `DATETIME` |  | — |

Duy nhất theo tổ hợp: (`model_id`, `variant`, `metric`, `k_value`, `fold`) — `mãMôHình`, `phươngÁnSoSánh`, `độĐo`, `giáTrịK`, `lượtKiểmChứngChéo`.

### 3.22. `meal_plan_items` — `mónTrongThựcĐơn`

Từng món trong một thực đơn ngày, kèm việc người dùng giữ hay đổi món.

| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | Khóa | Rỗng |
|---:|---|---|---|---|---|
| 1 | `id` | `mã` | `CHAR(36)` | PK | — |
| 2 | `meal_plan_id` → `meal_plans.id` | `mãThựcĐơn` | `CHAR(36)` | FK | — |
| 3 | `food_id` → `foods.id` | `mãMónĂn` | `CHAR(36)` | FK | — |
| 4 | `meal_type` | `buổiĂn` | `ENUM('breakfast', 'lunch', 'dinner', 'snack')` |  | — |
| 5 | `portion_multiplier` | `hệSốKhẩuPhần` | `DECIMAL(4,2)` |  | — |
| 6 | `predicted_score` | `điểmDựĐoán` | `DECIMAL(6,4)` |  | có |
| 7 | `status` | `trạngThái` | `ENUM('suggested', 'kept', 'replaced', 'eaten', 'skipped')` |  | — |
| 8 | `replaced_by_food_id` → `foods.id` | `mãMónThayThế` | `CHAR(36)` | FK | có |
| 9 | `replaced_at` | `thờiĐiểmThayThế` | `DATETIME` |  | có |
| 10 | `exploration_delta` | `mứcThămDò` | `DECIMAL(4,3)` |  | có |
| 11 | `position` | `thứTựTrongBuổi` | `TINYINT UNSIGNED` |  | có |
| 12 | `note` | `ghiChú` | `VARCHAR(255)` |  | có |
| 13 | `created_at` | `thờiĐiểmTạo` | `DATETIME` |  | — |

## 4. Quan hệ giữa các thực thể

29 khóa ngoại. Một cặp bảng có thể nối nhau nhiều lần qua nhiều cột khác nhau — `meal_plan_items` trỏ tới `foods` hai lần, một lần cho món được xếp và một lần cho món dùng thay thế.

| Thực thể cha | Thực thể con | Qua cột | Lượng số |
|---|---|---|---|
| `users` · `ngườiDùng` | `body_logs` · `nhậtKýCơThể` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `conditions` · `bệnhLý` | `condition_rules` · `quyTắcBệnhLý` | `condition_id` · `mãBệnhLý` | 1 — 0..* |
| `tags` · `nhãn` | `condition_rules` · `quyTắcBệnhLý` | `tag_id` · `mãNhãn` | 1 — 0..* |
| `users` · `ngườiDùng` | `feedbacks` · `phảnHồi` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `foods` · `mónĂn` | `feedbacks` · `phảnHồi` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `users` · `ngườiDùng` | `food_diary` · `nhậtKýĂnUống` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `foods` · `mónĂn` | `food_diary` · `nhậtKýĂnUống` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `foods` · `mónĂn` | `food_nutrition` · `dinhDưỡngMónĂn` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `foods` · `mónĂn` | `food_tags` · `nhãnCủaMónĂn` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `tags` · `nhãn` | `food_tags` · `nhãnCủaMónĂn` | `tag_id` · `mãNhãn` | 1 — 0..* |
| `food_categories` · `danhMụcMónĂn` | `foods` · `mónĂn` | `category_id` · `mãDanhMục` | 1 — 0..* |
| `users` · `ngườiDùng` | `foods` · `mónĂn` | `owner_id` · `mãChủSởHữu` | 1 — 0..* |
| `users` · `ngườiDùng` | `health_profiles` · `hồSơSứcKhỏe` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `users` · `ngườiDùng` | `interactions` · `tươngTác` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `foods` · `mónĂn` | `interactions` · `tươngTác` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `meal_plans` · `thựcĐơnNgày` | `meal_plan_items` · `mónTrongThựcĐơn` | `meal_plan_id` · `mãThựcĐơn` | 1 — 0..* |
| `foods` · `mónĂn` | `meal_plan_items` · `mónTrongThựcĐơn` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `foods` · `mónĂn` | `meal_plan_items` · `mónTrongThựcĐơn` | `replaced_by_food_id` · `mãMónThayThế` | 1 — 0..* |
| `users` · `ngườiDùng` | `meal_plans` · `thựcĐơnNgày` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `ml_models` · `môHìnhHọcMáy` | `meal_plans` · `thựcĐơnNgày` | `model_id` · `mãMôHình` | 1 — 0..* |
| `ml_models` · `môHìnhHọcMáy` | `ml_evaluations` · `đánhGiáMôHình` | `model_id` · `mãMôHình` | 1 — 0..* |
| `users` · `ngườiDùng` | `ml_training_samples` · `mẫuHuấnLuyện` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `foods` · `mónĂn` | `ml_training_samples` · `mẫuHuấnLuyện` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `users` · `ngườiDùng` | `recommendations` · `khuyếnNghịMónĂn` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `foods` · `mónĂn` | `recommendations` · `khuyếnNghịMónĂn` | `food_id` · `mãMónĂn` | 1 — 0..* |
| `ml_models` · `môHìnhHọcMáy` | `recommendations` · `khuyếnNghịMónĂn` | `model_id` · `mãMôHình` | 1 — 0..* |
| `users` · `ngườiDùng` | `user_conditions` · `bệnhLýNgườiDùng` | `user_id` · `mãNgườiDùng` | 1 — 0..* |
| `conditions` · `bệnhLý` | `user_conditions` · `bệnhLýNgườiDùng` | `condition_id` · `mãBệnhLý` | 1 — 0..* |
| `users` · `ngườiDùng` | `user_preference_profiles` · `hồSơKhẩuVị` | `user_id` · `mãNgườiDùng` | 1 — 0..* |

## 5. Miền giá trị của các cột ENUM

30 cột dùng kiểu liệt kê. Tập giá trị do CSDL quy định nên không thể nhập sai ở tầng ứng dụng.

| Thực thể | Cột | Tên tiếng Việt | Giá trị |
|---|---|---|---|
| `users` | `role` | `vaiTrò` | `user`, `admin` |
| `conditions` | `condition_type` | `loạiBệnhLý` | `disease`, `allergy`, `intolerance`, `diet` |
| `tags` | `tag_type` | `loạiNhãn` | `allergen`, `diet`, `nutrition` |
| `ml_models` | `algorithm` | `thuậtToán` | `logistic_regression`, `random_forest`, `gradient_boosting` |
| `rda_reference` | `gender` | `giớiTính` | `male`, `female`, `all` |
| `rda_reference` | `nutrient` | `chấtDinhDưỡng` | `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sugar_g`, `sodium_mg`, `cholesterol_mg`, `purine_mg`, `calcium_mg`, `iron_mg`, `zinc_mg`, `vitamin_a_mcg`, `vitamin_c_mg` |
| `health_profiles` | `gender` | `giớiTính` | `male`, `female`, `other` |
| `health_profiles` | `activity_level` | `mứcVậnĐộng` | `sedentary`, `light`, `moderate`, `active`, `very_active` |
| `health_profiles` | `goal` | `mụcTiêu` | `lose_weight`, `maintain`, `gain_weight`, `healthy_eating` |
| `user_conditions` | `severity` | `mứcĐộNặng` | `mild`, `moderate`, `severe` |
| `user_preference_profiles` | `stage` | `giaiĐoạnGợiÝ` | `cold`, `content`, `hybrid`, `ml` |
| `foods` | `dish_role` | `vaiTròMón` | `main`, `side_protein`, `side_veg`, `soup`, `snack`, `dessert`, `drink` |
| `condition_rules` | `rule_type` | `loạiQuyTắc` | `exclude_tag`, `require_tag`, `nutrient_limit` |
| `condition_rules` | `nutrient` | `chấtDinhDưỡng` | `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sugar_g`, `sodium_mg`, `cholesterol_mg`, `purine_mg`, `calcium_mg`, `iron_mg`, `zinc_mg`, `vitamin_a_mcg`, `vitamin_c_mg` |
| `condition_rules` | `comparator` | `phépSoSánh` | `lte`, `gte` |
| `condition_rules` | `scope` | `phạmViÁpDụng` | `per_serving`, `per_meal`, `per_day` |
| `condition_rules` | `severity_min` | `mứcĐộNặngTốiThiểu` | `mild`, `moderate`, `severe` |
| `meal_plans` | `generation_source` | `nguồnSinhThựcĐơn` | `rule_based`, `content_based`, `ml`, `hybrid` |
| `meal_plans` | `status` | `trạngThái` | `draft`, `active`, `completed` |
| `recommendations` | `context_meal_type` | `buổiĂnNgữCảnh` | `breakfast`, `lunch`, `dinner`, `snack` |
| `recommendations` | `source` | `nguồnGợiÝ` | `rule_based`, `content_based`, `ml`, `hybrid` |
| `food_diary` | `meal_type` | `buổiĂn` | `breakfast`, `lunch`, `dinner`, `snack` |
| `interactions` | `action` | `hànhĐộng` | `like`, `dislike`, `neutral`, `unknown` |
| `ml_training_samples` | `source` | `nguồnTínHiệu` | `feedback`, `swipe`, `diary`, `plan_kept`, `plan_replaced`, `plan_skipped`, `random_neg` |
| `ml_training_samples` | `context_meal_type` | `buổiĂnNgữCảnh` | `breakfast`, `lunch`, `dinner`, `snack` |
| `ml_training_samples` | `split` | `phầnChiaDữLiệu` | `train`, `val`, `test` |
| `ml_evaluations` | `variant` | `phươngÁnSoSánh` | `ml`, `content_based`, `rule_based`, `popularity`, `hybrid` |
| `ml_evaluations` | `metric` | `độĐo` | `precision`, `recall`, `ndcg`, `map`, `mae`, `rmse`, `f1`, `auc` |
| `meal_plan_items` | `meal_type` | `buổiĂn` | `breakfast`, `lunch`, `dinner`, `snack` |
| `meal_plan_items` | `status` | `trạngThái` | `suggested`, `kept`, `replaced`, `eaten`, `skipped` |
