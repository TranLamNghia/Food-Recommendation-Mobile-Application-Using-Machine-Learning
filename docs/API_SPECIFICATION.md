# Đặc tả API — Ứng dụng khuyến nghị thực đơn dinh dưỡng cá nhân hóa

## 1. Mục đích tài liệu

Đây là **hợp đồng giữa Frontend và Backend**. Hai bên code song song, không bên nào phải chờ bên nào:

- **Frontend (Flutter)** đọc phần `Response` để dựng model và giao diện, dùng luôn JSON mẫu trong tài liệu làm dữ liệu giả
- **Backend (ASP.NET Core)** đọc phần `Request` và `Status codes` để hiện thực controller
- Khi cả hai xong, ghép lại chỉ cần đổi base URL từ máy chủ giả sang máy chủ thật

Mọi thay đổi API **phải cập nhật tài liệu này trước**, rồi mới sửa code hai bên.

Tài liệu liên quan: `SYSTEM_ARCHITECTURE.md` (luồng xử lý), `DATABASE_DESIGN.md` (lược đồ dữ liệu).

---

## 2. Quy ước chung

### 2.1 Địa chỉ và phiên bản

| Môi trường | Base URL |
|---|---|
| Phát triển | `http://localhost:5000/api/v1` |
| Máy ảo Android | `http://10.0.2.2:5000/api/v1` |
| Thiết bị thật | `http://<IP-máy-tính>:5000/api/v1` |
| ML Service (nội bộ) | `http://localhost:8000` |

> Máy ảo Android không hiểu `localhost` — địa chỉ đó trỏ về chính máy ảo. Phải dùng `10.0.2.2`.

Phiên bản nằm trong đường dẫn (`/api/v1`). Thay đổi phá vỡ tương thích thì tăng lên `/api/v2`.

### 2.2 Quy ước đặt tên

| Nơi | Kiểu | Ví dụ |
|---|---|---|
| JSON (request và response) | `camelCase` | `heightCm`, `dailyCaloriesTarget` |
| Cơ sở dữ liệu | `snake_case` | `height_cm`, `daily_calories_target` |
| Đường dẫn URL | `kebab-case`, danh từ số nhiều | `/meal-plans`, `/food-diary` |
| Tham số truy vấn | `camelCase` | `?mealType=lunch&pageSize=20` |

ASP.NET Core mặc định tuần tự hóa `camelCase`, không cần cấu hình thêm.

### 2.3 Kiểu dữ liệu

| Kiểu | Định dạng | Ví dụ |
|---|---|---|
| Ngày | `YYYY-MM-DD` | `"2026-11-20"` |
| Ngày giờ | ISO 8601, múi giờ UTC | `"2026-11-20T07:15:30Z"` |
| Số thập phân | `number`, không phải chuỗi | `68.5` |
| Khóa chính | `number` (int64) | `42` |
| UUID | chuỗi 36 ký tự | `"3f2c8a1e-..."` |
| Trường rỗng | `null`, **không** dùng chuỗi rỗng | `"avatarUrl": null` |

### 2.4 Xác thực

Dùng **JWT Bearer**. Mọi endpoint đánh dấu `🔒 Protected` đều bắt buộc header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

| Loại token | Thời hạn | Dùng để |
|---|---|---|
| `accessToken` | 1 giờ | Gọi mọi API |
| `refreshToken` | 30 ngày | Lấy `accessToken` mới khi hết hạn |

Payload của `accessToken`:

```json
{
  "sub": "1",
  "email": "nghia@example.com",
  "onboarded": true,
  "exp": 1795000000,
  "iat": 1794996400
}
```

> `onboarded` cho phép Frontend biết ngay có cần đẩy người dùng vào màn hình vuốt thăm dò hay không, mà không cần gọi thêm API.

**Ba mức truy cập:**

| Ký hiệu | Nghĩa |
|---|---|
| 🌐 **Public** | Không cần token |
| 🔒 **Protected** | Cần `accessToken` hợp lệ |
| ⚙️ **Internal** | Chỉ Backend gọi ML Service, không lộ ra ngoài |

Hệ thống **không có vai trò quản trị** — mọi endpoint `Protected` chỉ thao tác trên dữ liệu của chính người dùng đang đăng nhập. Backend lấy `userId` từ token, **không bao giờ nhận `userId` từ tham số**.

### 2.5 Định dạng lỗi

Mọi lỗi trả về cùng một cấu trúc:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Dữ liệu gửi lên không hợp lệ",
    "details": [
      { "field": "heightCm", "message": "Chiều cao phải trong khoảng 50 đến 250" },
      { "field": "goal",     "message": "Giá trị không nằm trong danh sách cho phép" }
    ],
    "traceId": "0HN7GKLM9QRST:00000001"
  }
}
```

`details` chỉ xuất hiện với lỗi `VALIDATION_FAILED`, các lỗi khác bỏ trống.

### 2.6 Phân trang

Endpoint trả danh sách dài dùng chung cấu trúc:

```json
{
  "items": [ ],
  "page": 1,
  "pageSize": 20,
  "totalItems": 137,
  "totalPages": 7
}
```

Tham số: `?page=1&pageSize=20`. Mặc định `page=1`, `pageSize=20`, tối đa `pageSize=100`.

Danh sách ngắn và cố định (danh mục món, từ điển bệnh lý) trả mảng thuần, không phân trang.

---

## 3. Mã trạng thái HTTP

| Mã | Tên | Dùng khi |
|---|---|---|
| `200` | OK | Đọc dữ liệu, hoặc cập nhật thành công |
| `201` | Created | Tạo mới thành công, trả về tài nguyên vừa tạo |
| `204` | No Content | Xóa thành công, không có nội dung trả về |
| `400` | Bad Request | Dữ liệu sai định dạng hoặc vi phạm ràng buộc |
| `401` | Unauthorized | Thiếu token, token sai hoặc đã hết hạn |
| `403` | Forbidden | Token hợp lệ nhưng cố truy cập dữ liệu người khác |
| `404` | Not Found | Tài nguyên không tồn tại |
| `409` | Conflict | Xung đột trạng thái (trùng email, chưa khai báo hồ sơ...) |
| `422` | Unprocessable Entity | Dữ liệu đúng định dạng nhưng nghiệp vụ không xử lý được |
| `429` | Too Many Requests | Vượt giới hạn tần suất |
| `500` | Internal Server Error | Lỗi phía máy chủ |

---

## 4. Danh mục mã lỗi

| `code` | HTTP | Ý nghĩa | Frontend nên làm gì |
|---|---|---|---|
| `VALIDATION_FAILED` | 400 | Dữ liệu không hợp lệ | Hiển thị lỗi theo từng trường trong `details` |
| `INVALID_CREDENTIALS` | 401 | Sai email hoặc mật khẩu | Báo lỗi chung, không nói rõ sai cái nào |
| `TOKEN_EXPIRED` | 401 | `accessToken` hết hạn | Gọi `/auth/refresh` rồi thử lại |
| `TOKEN_INVALID` | 401 | Token hỏng hoặc đã thu hồi | Đăng xuất, về màn hình đăng nhập |
| `FORBIDDEN` | 403 | Truy cập dữ liệu người khác | Về màn hình chính |
| `NOT_FOUND` | 404 | Không tìm thấy tài nguyên | Thông báo và quay lại |
| `EMAIL_ALREADY_EXISTS` | 409 | Email đã đăng ký | Gợi ý đăng nhập |
| `PROFILE_REQUIRED` | 409 | Chưa khai báo hồ sơ sức khỏe | Chuyển tới màn hình khai báo hồ sơ |
| `ONBOARDING_REQUIRED` | 409 | Chưa hoàn tất phiên khảo sát khẩu vị | Chuyển tới màn hình vuốt |
| `ONBOARDING_ALREADY_COMPLETED` | 409 | Đã hoàn tất khảo sát trước đó | Bỏ qua, vào thẳng màn hình chính |
| `ONBOARDING_INSUFFICIENT` | 422 | Vuốt chưa đủ số lượng tối thiểu | Hiện số còn thiếu, cho vuốt tiếp |
| `FEEDBACK_NOT_ALLOWED` | 409 | Món chưa từng ở trong thực đơn, hoặc chưa ghi vào nhật ký | Ẩn nút đánh giá với món chưa đủ điều kiện |
| `MEAL_PLAN_EXISTS` | 409 | Ngày đó đã có thực đơn | Gọi `GET` thay vì `POST`, hoặc hỏi có tạo lại không |
| `NO_FEASIBLE_PLAN` | 422 | Ràng buộc quá chặt, không sinh nổi thực đơn | Xem mục 7.6.2 |
| `RATE_LIMITED` | 429 | Gọi quá nhanh | Chờ theo header `Retry-After` |
| `INTERNAL_ERROR` | 500 | Lỗi máy chủ | Báo lỗi chung, cho thử lại |

---

## 5. Từ điển giá trị enum

**Đây là mục quan trọng nhất để hai bên khớp nhau.** Mọi giá trị đều là chuỗi, phân biệt hoa thường, và **trùng khớp chính xác với ENUM trong cơ sở dữ liệu**.

### 5.1 Người dùng và hồ sơ

| Trường | Giá trị hợp lệ |
|---|---|
| `gender` | `male` · `female` · `other` |
| `activityLevel` | `sedentary` · `light` · `moderate` · `active` · `very_active` |
| `goal` | `lose_weight` · `maintain` · `gain_weight` · `healthy_eating` |
| `severity` | `mild` · `moderate` · `severe` |
| `conditionType` | `disease` · `allergy` · `intolerance` · `diet` |
| `bmiCategory` | `underweight` · `normal` · `overweight` · `obese` |

> Bảng tra cứu `rda_reference` trong CSDL cũng có cột `gender` nhưng nhận thêm giá trị `all`. Cột đó **không bao giờ xuất hiện trong API** — nó chỉ dùng nội bộ để tra nhu cầu dinh dưỡng áp dụng cho cả hai giới. Đừng nhầm hai chỗ này.

Hệ số nhân TDEE tương ứng `activityLevel`: `1.200` · `1.375` · `1.550` · `1.725` · `1.900`.

### 5.2 Món ăn

| Trường | Giá trị hợp lệ |
|---|---|
| `cookingMethod` | `luoc` · `hap` · `xao` · `chien` · `nuong` · `kho` · `nau_canh` · `tron` · `song` · `khac` |
| `dishRole` | `main` · `side` · `soup` · `dessert` · `drink` |
| `spiceLevel` | số nguyên `0` – `3` |
| `suitableMeals` | mảng các giá trị `mealType` |
| `tagType` | `allergen` · `diet` · `nutrition` · `taste` |

### 5.3 Bữa ăn và tương tác

| Trường | Giá trị hợp lệ |
|---|---|
| `mealType` | `breakfast` · `lunch` · `dinner` · `snack` |
| `action` | `like` · `dislike` · `neutral` · `unknown` |

Ánh xạ cử chỉ vuốt sang `action` — Frontend chịu trách nhiệm:

| Cử chỉ | `action` |
|---|---|
| Vuốt phải | `like` |
| Vuốt trái | `dislike` |
| Vuốt lên | `neutral` |
| Vuốt xuống | `unknown` |

### 5.4 Thực đơn

| Trường | Giá trị hợp lệ |
|---|---|
| `mealPlanStatus` | `draft` · `active` · `completed` |
| `itemStatus` | `suggested` · `kept` · `replaced` · `eaten` · `skipped` |
| `generationSource` | `rule_based` · `content_based` · `ml` · `hybrid` |

### 5.5 Machine Learning

| Trường | Giá trị hợp lệ |
|---|---|
| `stage` | `cold` · `content` · `hybrid` · `ml` |
| `algorithm` | `logistic_regression` · `random_forest` · `gradient_boosting` |

---

## 6. Bảng tổng hợp toàn bộ endpoint

**30 endpoint công khai + 4 endpoint nội bộ.**

### Xác thực — 4

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 1 | Đăng ký | `POST` | `/auth/register` | 🌐 |
| 2 | Đăng nhập | `POST` | `/auth/login` | 🌐 |
| 3 | Làm mới token | `POST` | `/auth/refresh` | 🌐 |
| 4 | Thông tin tài khoản | `GET` | `/auth/me` | 🔒 |

### Hồ sơ sức khỏe — 5

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 5 | Xem hồ sơ | `GET` | `/profile` | 🔒 |
| 6 | Tạo / cập nhật hồ sơ | `PUT` | `/profile` | 🔒 |
| 7 | Xem hạn mức dinh dưỡng | `GET` | `/profile/nutrition-targets` | 🔒 |
| 8 | Xem bệnh lý của tôi | `GET` | `/profile/conditions` | 🔒 |
| 9 | Cập nhật bệnh lý | `PUT` | `/profile/conditions` | 🔒 |

### Danh mục tra cứu — 3

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 10 | Từ điển bệnh lý | `GET` | `/conditions` | 🌐 |
| 11 | Danh mục món ăn | `GET` | `/food-categories` | 🌐 |
| 12 | Từ điển nhãn | `GET` | `/tags` | 🌐 |

### Khảo sát khẩu vị — 2

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 13 | Lấy gói món khảo sát | `GET` | `/onboarding/survey` | 🔒 |
| 14 | Gửi kết quả khảo sát | `POST` | `/onboarding/survey` | 🔒 |

### Món ăn — 2

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 15 | Tìm kiếm món ăn | `GET` | `/foods` | 🔒 |
| 16 | Chi tiết món ăn | `GET` | `/foods/{id}` | 🔒 |

### Thực đơn — 6

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 17 | Lấy thực đơn theo ngày | `GET` | `/meal-plans` | 🔒 |
| 18 | Sinh thực đơn | `POST` | `/meal-plans` | 🔒 |
| 19 | Chi tiết thực đơn | `GET` | `/meal-plans/{id}` | 🔒 |
| 20 | Gợi ý món thay thế | `GET` | `/meal-plan-items/{id}/alternatives` | 🔒 |
| 21 | Thay thế món | `PUT` | `/meal-plan-items/{id}/replace` | 🔒 |
| 22 | Cập nhật trạng thái món | `PATCH` | `/meal-plan-items/{id}/status` | 🔒 |

### Nhật ký ăn uống — 5

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 23 | Xem nhật ký | `GET` | `/food-diary` | 🔒 |
| 24 | Thêm món đã ăn | `POST` | `/food-diary` | 🔒 |
| 25 | Sửa món đã ăn | `PUT` | `/food-diary/{id}` | 🔒 |
| 26 | Xóa món đã ăn | `DELETE` | `/food-diary/{id}` | 🔒 |
| 27 | Tổng kết dinh dưỡng ngày | `GET` | `/food-diary/summary` | 🔒 |

### Đánh giá — 2

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 28 | Gửi đánh giá | `POST` | `/feedbacks` | 🔒 |
| 29 | Xem đánh giá của tôi | `GET` | `/feedbacks` | 🔒 |

### Thống kê — 1

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| 30 | Tiến trình sức khỏe | `GET` | `/stats/progress` | 🔒 |

### ML Service nội bộ — 4

| # | Tên | Method | Đường dẫn | Quyền |
|---|---|---|---|---|
| I1 | Chấm điểm món | `POST` | `/predict` | ⚙️ |
| I2 | Dựng lại hồ sơ sở thích | `POST` | `/profiles/{userId}/rebuild` | ⚙️ |
| I3 | Huấn luyện lại mô hình | `POST` | `/train` | ⚙️ |
| I4 | Kiểm tra sống | `GET` | `/health` | ⚙️ |

---

# 7. Chi tiết từng nhóm API

## 7.1 Xác thực

### 7.1.1 Đăng ký

| | |
|---|---|
| **Tên** | Đăng ký tài khoản |
| **Loại** | 🌐 Public |
| **Method** | `POST /auth/register` |

**Headers**

```http
Content-Type: application/json
```

**Body**

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `email` | string | ✔ | Đúng định dạng email, tối đa 255 ký tự |
| `password` | string | ✔ | Tối thiểu 8 ký tự, có chữ và số |
| `displayName` | string | ✔ | 2–100 ký tự |

```json
{
  "email": "nghia@example.com",
  "password": "MatKhau123",
  "displayName": "Trần Lâm Nghĩa"
}
```

**Response `201 Created`**

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "d4f8b1c2-9e7a-4c3d-8b5f-1a2e3d4c5b6a",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "user": {
    "id": 1,
    "email": "nghia@example.com",
    "displayName": "Trần Lâm Nghĩa",
    "avatarUrl": null,
    "onboardingCompletedAt": null,
    "createdAt": "2026-11-20T07:15:30Z"
  }
}
```

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `201` | — | Đăng ký thành công |
| `400` | `VALIDATION_FAILED` | Email sai định dạng, mật khẩu quá ngắn |
| `409` | `EMAIL_ALREADY_EXISTS` | Email đã tồn tại |

> Sau khi đăng ký, `onboardingCompletedAt` là `null` — Frontend phải đưa người dùng qua màn hình khai báo hồ sơ trước, rồi tới màn hình vuốt thăm dò.

---

### 7.1.2 Đăng nhập

| | |
|---|---|
| **Tên** | Đăng nhập |
| **Loại** | 🌐 Public |
| **Method** | `POST /auth/login` |

**Body**

```json
{
  "email": "nghia@example.com",
  "password": "MatKhau123"
}
```

**Response `200 OK`** — cấu trúc giống hệt đăng ký.

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Thành công |
| `400` | `VALIDATION_FAILED` | Thiếu trường |
| `401` | `INVALID_CREDENTIALS` | Sai email hoặc mật khẩu |

> Không phân biệt "email không tồn tại" và "sai mật khẩu" — cả hai đều trả `INVALID_CREDENTIALS`, tránh lộ thông tin email nào đã đăng ký.

---

### 7.1.3 Làm mới token

| | |
|---|---|
| **Tên** | Làm mới access token |
| **Loại** | 🌐 Public |
| **Method** | `POST /auth/refresh` |

**Body**

```json
{ "refreshToken": "d4f8b1c2-9e7a-4c3d-8b5f-1a2e3d4c5b6a" }
```

**Response `200 OK`**

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
  "tokenType": "Bearer",
  "expiresIn": 3600
}
```

**Status codes:** `200` · `401 TOKEN_INVALID`

> `refreshToken` được **xoay vòng**: mỗi lần làm mới trả về token mới và thu hồi token cũ. Frontend phải lưu lại token mới.

---

### 7.1.4 Thông tin tài khoản

| | |
|---|---|
| **Tên** | Lấy thông tin người dùng hiện tại |
| **Loại** | 🔒 Protected |
| **Method** | `GET /auth/me` |

**Headers**

```http
Authorization: Bearer <accessToken>
```

**Response `200 OK`**

```json
{
  "id": 1,
  "email": "nghia@example.com",
  "displayName": "Trần Lâm Nghĩa",
  "avatarUrl": null,
  "onboardingCompletedAt": "2026-11-20T08:02:11Z",
  "hasHealthProfile": true,
  "preferenceStage": "content",
  "createdAt": "2026-11-20T07:15:30Z"
}
```

| Trường | Ý nghĩa |
|---|---|
| `hasHealthProfile` | Đã khai báo hồ sơ sức khỏe chưa |
| `preferenceStage` | Giai đoạn cá nhân hóa hiện tại: `cold` · `content` · `hybrid` · `ml` |

**Status codes:** `200` · `401`

> Đây là endpoint Frontend gọi đầu tiên sau khi mở app, để quyết định điều hướng vào màn hình nào.

---

## 7.2 Hồ sơ sức khỏe

### 7.2.1 Xem hồ sơ

| | |
|---|---|
| **Tên** | Xem hồ sơ sức khỏe |
| **Loại** | 🔒 Protected |
| **Method** | `GET /profile` |

**Response `200 OK`**

```json
{
  "gender": "male",
  "dateOfBirth": "2004-11-14",
  "age": 22,
  "heightCm": 172.0,
  "weightKg": 68.5,
  "bmi": 23.15,
  "bmiCategory": "normal",
  "activityLevel": "moderate",
  "goal": "maintain",
  "conditions": [
    {
      "conditionId": 2,
      "code": "hypertension",
      "nameVi": "Tăng huyết áp",
      "conditionType": "disease",
      "severity": "mild",
      "note": null
    }
  ],
  "createdAt": "2026-11-20T07:20:00Z",
  "updatedAt": "2026-11-20T07:20:00Z"
}
```

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Có hồ sơ |
| `404` | `NOT_FOUND` | Chưa khai báo hồ sơ |
| `401` | | |

> `bmi` và `age` do Backend tính, Frontend chỉ hiển thị. `bmi` là cột `GENERATED` trong CSDL.

---

### 7.2.2 Tạo hoặc cập nhật hồ sơ

| | |
|---|---|
| **Tên** | Tạo / cập nhật hồ sơ sức khỏe |
| **Loại** | 🔒 Protected |
| **Method** | `PUT /profile` |

Dùng `PUT` chứ không phải `POST` vì quan hệ người dùng–hồ sơ là **1:1** — gọi lần đầu thì tạo mới, gọi lại thì ghi đè.

**Body**

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `gender` | string | ✔ | Xem mục 5.1 |
| `dateOfBirth` | date | ✔ | Tuổi từ 13 đến 100 |
| `heightCm` | number | ✔ | 50 – 250 |
| `weightKg` | number | ✔ | 20 – 300 |
| `activityLevel` | string | ✔ | Xem mục 5.1 |
| `goal` | string | ✔ | Xem mục 5.1 |

```json
{
  "gender": "male",
  "dateOfBirth": "2004-11-14",
  "heightCm": 172.0,
  "weightKg": 68.5,
  "activityLevel": "moderate",
  "goal": "maintain"
}
```

**Response `200 OK`** — trả về hồ sơ đầy đủ như 7.2.1, **kèm hạn mức dinh dưỡng vừa tính lại**:

```json
{
  "profile": { },
  "nutritionTargets": { }
}
```

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Cập nhật thành công |
| `201` | — | Tạo mới lần đầu |
| `400` | `VALIDATION_FAILED` | Chiều cao / cân nặng ngoài khoảng, enum sai |
| `401` | | |

> Mỗi lần gọi endpoint này, Backend **tính lại BMR, TDEE và hạn mức macro** rồi lưu vào `health_profiles`. Thực đơn đã sinh trước đó **không bị ảnh hưởng**, vì chúng đã chụp lại hạn mức tại thời điểm sinh.

---

### 7.2.3 Xem hạn mức dinh dưỡng

| | |
|---|---|
| **Tên** | Hạn mức năng lượng và dinh dưỡng |
| **Loại** | 🔒 Protected |
| **Method** | `GET /profile/nutrition-targets` |

Đây là **đầu ra Bước 1** của thuật toán khuyến nghị.

**Response `200 OK`**

```json
{
  "bmi": 23.15,
  "bmiCategory": "normal",
  "bmrKcal": 1660,
  "tdeeKcal": 2573,
  "activityFactor": 1.55,
  "dailyCaloriesTarget": 2573,
  "goalAdjustmentKcal": 0,
  "macroTargets": {
    "proteinPct": 15, "proteinG": 96.5,
    "carbsPct":   60, "carbsG":   385.9,
    "fatPct":     25, "fatG":     71.5
  },
  "mealDistribution": [
    { "mealType": "breakfast", "pct": 25, "caloriesKcal": 643 },
    { "mealType": "lunch",     "pct": 40, "caloriesKcal": 1029 },
    { "mealType": "dinner",    "pct": 27, "caloriesKcal": 695 },
    { "mealType": "snack",     "pct": 8,  "caloriesKcal": 206 }
  ],
  "formula": {
    "bmr": "Mifflin-St Jeor",
    "expression": "10 × 68.5 + 6.25 × 172 − 5 × 22 + 5 = 1660"
  },
  "computedAt": "2026-11-20T07:20:05Z"
}
```

**Status codes:** `200` · `401` · `409 PROFILE_REQUIRED`

> Trường `formula.expression` để màn hình hồ sơ giải thích cho người dùng con số đến từ đâu — tăng độ tin cậy, và cũng là một điểm cộng khi demo bảo vệ.

---

### 7.2.4 Xem bệnh lý của tôi

| | |
|---|---|
| **Tên** | Danh sách bệnh lý và dị ứng đã khai |
| **Loại** | 🔒 Protected |
| **Method** | `GET /profile/conditions` |

**Response `200 OK`** — mảng thuần, không phân trang:

```json
[
  {
    "conditionId": 2,
    "code": "hypertension",
    "nameVi": "Tăng huyết áp",
    "conditionType": "disease",
    "severity": "mild",
    "note": null
  },
  {
    "conditionId": 6,
    "code": "allergy_seafood",
    "nameVi": "Dị ứng hải sản",
    "conditionType": "allergy",
    "severity": "severe",
    "note": "Dị ứng nặng với tôm cua"
  }
]
```

**Status codes:** `200` · `401`

---

### 7.2.5 Cập nhật bệnh lý

| | |
|---|---|
| **Tên** | Cập nhật danh sách bệnh lý |
| **Loại** | 🔒 Protected |
| **Method** | `PUT /profile/conditions` |

**Thay thế toàn bộ danh sách**, không phải thêm từng cái. Frontend gửi lên trạng thái cuối cùng mà người dùng chọn.

**Body**

```json
{
  "conditions": [
    { "conditionId": 2, "severity": "mild",   "note": null },
    { "conditionId": 6, "severity": "severe", "note": "Dị ứng nặng với tôm cua" }
  ]
}
```

Gửi `{ "conditions": [] }` để xóa hết.

**Response `200 OK`** — trả về danh sách sau khi cập nhật, giống 7.2.4.

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Thành công |
| `400` | `VALIDATION_FAILED` | `conditionId` không tồn tại, `severity` sai |
| `401` | | |

> Thay đổi danh sách này **ảnh hưởng trực tiếp tới Bộ lọc F1**. Thực đơn sinh ra sau đó sẽ khác. Frontend nên gợi ý người dùng sinh lại thực đơn hôm nay.

---

## 7.3 Danh mục tra cứu

Ba endpoint này trả dữ liệu **tĩnh, hiếm thay đổi**. Frontend nên tải một lần khi khởi động rồi lưu vào bộ nhớ đệm cục bộ.

### 7.3.1 Từ điển bệnh lý

| | |
|---|---|
| **Tên** | Danh sách bệnh lý / dị ứng / chế độ ăn |
| **Loại** | 🌐 Public |
| **Method** | `GET /conditions` |

**Query params**

| Tham số | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `type` | string | ✗ | Lọc theo `conditionType` |

**Response `200 OK`**

```json
[
  { "id": 1, "code": "diabetes",     "nameVi": "Đái tháo đường", "conditionType": "disease", "description": "Cần hạn chế đường và tinh bột hấp thu nhanh" },
  { "id": 2, "code": "hypertension", "nameVi": "Tăng huyết áp",  "conditionType": "disease", "description": "Cần hạn chế natri" },
  { "id": 6, "code": "allergy_seafood", "nameVi": "Dị ứng hải sản", "conditionType": "allergy", "description": null },
  { "id": 11, "code": "vegetarian",  "nameVi": "Ăn chay",        "conditionType": "diet",    "description": "Không ăn thịt, có thể dùng trứng và sữa" }
]
```

**Status codes:** `200`

---

### 7.3.2 Danh mục món ăn

| | |
|---|---|
| **Tên** | Danh mục món ăn |
| **Loại** | 🌐 Public |
| **Method** | `GET /food-categories` |

**Response `200 OK`**

```json
[
  { "id": 1, "code": "mon_nuoc", "name": "Món nước", "description": "Phở, bún, miến, hủ tiếu", "iconUrl": null },
  { "id": 5, "code": "mon_canh", "name": "Món canh", "description": "Canh chua, canh rau",     "iconUrl": null }
]
```

---

### 7.3.3 Từ điển nhãn

| | |
|---|---|
| **Tên** | Danh sách nhãn món ăn |
| **Loại** | 🌐 Public |
| **Method** | `GET /tags` |

**Query params:** `?type=allergen` (lọc theo `tagType`)

**Response `200 OK`**

```json
[
  { "id": 1,  "code": "contains_seafood", "nameVi": "Có hải sản",  "tagType": "allergen" },
  { "id": 13, "code": "salty",            "nameVi": "Mặn",         "tagType": "taste" }
]
```

---

## 7.4 Khảo sát khẩu vị

> **Khởi đầu nguội (cold-start)** là tình huống hệ thống chưa có bất kỳ dữ liệu lịch sử nào về người dùng mới, nên không có căn cứ để cá nhân hóa gợi ý. Đề tài giải quyết bằng một **phiên khảo sát khẩu vị** ngay sau khi đăng ký: người dùng vuốt một gói món ăn, hệ thống dựng hồ sơ sở thích từ đó.

### Cơ chế này chỉ chạy đúng một lần

Vuốt **chỉ xuất hiện ở phiên khảo sát lúc tạo tài khoản**. Sau đó ứng dụng không còn màn hình vuốt nào nữa.

Từ lúc đó trở đi, tín hiệu sở thích đến từ chính thực đơn hằng ngày:

```
   Hệ thống gửi thực đơn  →  người dùng KHÔNG ăn hết 100 %
                             ↓
              món họ giữ lại / thay thế   →  tín hiệu ngầm định
              món họ ăn rồi đánh giá      →  tín hiệu mạnh nhất
```

Ba nguồn đó đủ nuôi mô hình, và hai trong số chúng đáng tin hơn vuốt:

| Nguồn tín hiệu | Endpoint | Trọng số nhãn |
|---|---|---|
| Đánh giá sao sau khi ăn | `POST /feedbacks` | 1.0 |
| Món đã ăn thật | `POST /food-diary` | 0.9 |
| Vuốt khảo sát ban đầu | `POST /onboarding/survey` | 0.7 |
| Giữ hoặc thay thế món | `PATCH /meal-plan-items/{id}/status` | 0.6 |

Chống hiện tượng thực đơn một màu **không** bằng cách cho vuốt thêm, mà bằng **cơ chế 70-30** ngay trong bước sinh thực đơn — xem `SYSTEM_ARCHITECTURE.md` mục 4.6.

### Luồng hoạt động

Gói món **cố định trong suốt phiên**, nên chỉ cần gọi máy chủ đúng hai lần:

```
   ┌────────────────────────────────────────────────────────────────┐
   │  ①  GET /onboarding/survey                        │
   │      Máy chủ trả về sessionId + đúng 30 món, chọn một lần       │
   └───────────────────────────┬────────────────────────────────────┘
                               ▼
   ┌────────────────────────────────────────────────────────────────┐
   │      Người dùng vuốt hết 30 món — HOÀN TOÀN NGOẠI TUYẾN         │
   │      Flutter giữ kết quả trong bộ nhớ, tự đếm tiến độ,          │
   │      tự hiển thị thanh "đã vuốt 18/30"                          │
   │      Không gọi máy chủ lần nào trong giai đoạn này              │
   └───────────────────────────┬────────────────────────────────────┘
                               ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  ②  POST /onboarding/survey                    │
   │      Gửi trọn gói kết quả. Máy chủ ghi interactions, dựng       │
   │      hồ sơ sở thích, đóng dấu onboarding_completed_at           │
   └────────────────────────────────────────────────────────────────┘
```

Bốn hệ quả của thiết kế này:

| Hệ quả | Vì sao |
|---|---|
| **Không có endpoint xem tiến độ** | Flutter đang giữ toàn bộ trạng thái trong bộ nhớ, tự đếm được. Hỏi máy chủ là thừa |
| **Không có endpoint ghi từng lượt** | Cả phiên là một sự kiện, gửi một lần |
| **Không thích ứng giữa chừng** | Gói món chọn theo nguyên tắc cực đại hóa độ đa dạng ngay từ đầu. Vuốt món thứ 5 **không** làm đổi món thứ 6 |
| **Vuốt được khi mất mạng** | Chỉ cần mạng ở hai thời điểm: lúc tải gói món và lúc gửi kết quả |

---

### 7.4.1 Lấy gói món khảo sát

| | |
|---|---|
| **Tên** | Tạo phiên khảo sát và lấy gói món |
| **Loại** | 🔒 Protected |
| **Method** | `GET /onboarding/survey` |

**Headers**

```http
Authorization: Bearer <accessToken>
```

**Query params**

| Tham số | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `size` | int | `30` | Số món trong gói, cho phép 20–50 |

**Cách máy chủ chọn gói món:** theo nguyên tắc **cực đại hóa độ đa dạng** — phủ đều nhóm thực phẩm, phương pháp chế biến và khẩu vị, sao cho mỗi lượt vuốt mang lại nhiều thông tin nhất. Gói đã đi qua Bộ lọc F1 nên không chứa món người dùng dị ứng.

**Response `200 OK`**

```json
{
  "sessionId": "3f2c8a1e-7d4b-4a91-b2c6-8e5f1a0d3c7b",
  "totalItems": 30,
  "minRequired": 20,
  "items": [
    {
      "id": 1,
      "name": "Phở bò",
      "imageUrl": "https://cdn.example.com/foods/pho-bo.jpg",
      "origin": "Hà Nội",
      "categoryName": "Món nước",
      "cookingMethod": "nau_canh",
      "spiceLevel": 0,
      "dishRole": "main",
      "caloriesKcal": 430.0,
      "servingSizeG": 400,
      "tags": ["salty"]
    },
    {
      "id": 8,
      "name": "Rau muống luộc",
      "imageUrl": "https://cdn.example.com/foods/rau-muong-luoc.jpg",
      "origin": null,
      "categoryName": "Món luộc hấp",
      "cookingMethod": "luoc",
      "spiceLevel": 0,
      "dishRole": "side",
      "caloriesKcal": 35.0,
      "servingSizeG": 150,
      "tags": ["light", "high_fiber", "vegan"]
    }
  ]
}
```

| Trường | Ý nghĩa |
|---|---|
| `sessionId` | Mã phiên, gửi lại nguyên vẹn ở bước ② |
| `totalItems` | Số món trong gói — Flutter dùng làm mẫu số thanh tiến độ |
| `minRequired` | Số lượt vuốt **có ý kiến** tối thiểu. Vuốt xuống (`unknown`) không tính |

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Thành công |
| `400` | `VALIDATION_FAILED` | `size` ngoài khoảng 20–50 |
| `401` | | Thiếu hoặc sai token |
| `409` | `PROFILE_REQUIRED` | Chưa khai báo hồ sơ sức khỏe |
| `409` | `ONBOARDING_ALREADY_COMPLETED` | Đã hoàn tất khảo sát trước đó — cơ chế chỉ chạy một lần |

> Gọi lại endpoint này sẽ trả về **gói mới với `sessionId` mới**. Flutter nên tải một lần rồi lưu cục bộ, để người dùng thoát ứng dụng giữa chừng vẫn vuốt tiếp được đúng gói cũ.

---

### 7.4.2 Gửi kết quả khảo sát

| | |
|---|---|
| **Tên** | Gửi trọn gói kết quả khảo sát |
| **Loại** | 🔒 Protected |
| **Method** | `POST /onboarding/survey` |

Gọi **đúng một lần trong đời tài khoản**, sau khi người dùng đã vuốt xong toàn bộ gói món. Máy chủ thực hiện trong **một giao dịch**:

| Bước | Nội dung |
|---|---|
| ① | Ghi toàn bộ lượt vuốt vào `interactions` với `session_type = 'onboarding'` |
| ② | Dựng **hồ sơ sở thích** bằng thuật toán Rocchio, lưu vào `user_preference_profiles` |
| ③ | Đóng dấu `onboarding_completed_at` cho người dùng |

Nếu bất kỳ bước nào lỗi, cả giao dịch bị hủy — không để lại trạng thái dở dang.

**Headers**

```http
Authorization: Bearer <accessToken>
Content-Type: application/json
```

**Body**

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `sessionId` | uuid | ✔ | Lấy từ bước ① |
| `swipes` | array | ✔ | 1–50 phần tử, không trùng `foodId` |
| `swipes[].foodId` | int | ✔ | Món trong gói đã nhận ở bước ① |
| `swipes[].action` | string | ✔ | `like` · `dislike` · `neutral` · `unknown` |

```json
{
  "sessionId": "3f2c8a1e-7d4b-4a91-b2c6-8e5f1a0d3c7b",
  "swipes": [
    { "foodId": 1,  "action": "like" },
    { "foodId": 8,  "action": "dislike" },
    { "foodId": 12, "action": "neutral" },
    { "foodId": 15, "action": "unknown" },
    { "foodId": 21, "action": "like" }
  ]
}
```

> Không cần gửi thời điểm vuốt từng món. Máy chủ đóng dấu chung một thời điểm cho cả phiên — về mặt dữ liệu, đây **là một sự kiện duy nhất**.

**Response `200 OK`**

```json
{
  "sessionId": "3f2c8a1e-7d4b-4a91-b2c6-8e5f1a0d3c7b",
  "onboardingCompletedAt": "2026-11-20T08:02:11Z",
  "recorded": {
    "total": 30,
    "opinionated": 26,
    "skipped": 4
  },
  "preferenceProfile": {
    "stage": "content",
    "nSignals": 26,
    "alpha": 0.0,
    "featureVersion": "fv1"
  },
  "tasteSummary": {
    "topLikedCategories": ["Món nước", "Món chiên rán"],
    "topLikedTastes": ["salty", "fatty"],
    "avoidedTastes": ["sour"],
    "spiceTolerance": 2
  }
}
```

| Trường | Ý nghĩa |
|---|---|
| `onboardingCompletedAt` | Thời điểm hoàn tất khảo sát |
| `recorded.total` | Tổng số lượt vuốt đã ghi |
| `recorded.opinionated` | Số lượt có ý kiến — `like`, `dislike`, `neutral` |
| `recorded.skipped` | Số lượt `unknown`, bị loại khỏi công thức dựng vector |
| `preferenceProfile.stage` | Giai đoạn cá nhân hóa sau khi cập nhật |
| `tasteSummary` | Bản tóm tắt **dễ đọc** của vector sở thích, để màn hình kết thúc hiện câu kiểu *"Có vẻ bạn thích món nước và đồ chiên, ăn cay được ở mức vừa"* |

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Thành công |
| `400` | `VALIDATION_FAILED` | Mảng rỗng, quá 50 phần tử, trùng `foodId`, `action` sai |
| `401` | | Thiếu hoặc sai token |
| `404` | `NOT_FOUND` | Có `foodId` không tồn tại |
| `409` | `ONBOARDING_ALREADY_COMPLETED` | Đã hoàn tất khảo sát trước đó |
| `422` | `ONBOARDING_INSUFFICIENT` | Số lượt có ý kiến chưa đạt `minRequired` |

Ví dụ lỗi `422`:

```json
{
  "error": {
    "code": "ONBOARDING_INSUFFICIENT",
    "message": "Cần vuốt thêm 3 món nữa để hoàn tất khảo sát",
    "details": [
      { "field": "swipes", "message": "Có 17 lượt có ý kiến, cần tối thiểu 20" }
    ],
    "traceId": "0HN7GKLM9QRST:00000042"
  }
}
```

> Flutter nên **kiểm tra `minRequired` ngay tại máy** trước khi gọi, để người dùng không phải chờ một vòng mạng mới biết là thiếu. Máy chủ vẫn kiểm tra lại vì không được tin dữ liệu từ client.

**Vector sở thích không trả về cho Frontend.** Nó là dữ liệu nội bộ của ML Service, gồm khoảng 30 chiều số thực, không có ý nghĩa hiển thị. Frontend chỉ nhận `tasteSummary` đã diễn giải sang ngôn ngữ người dùng hiểu được.

---

---

## 7.5 Món ăn

### 7.5.1 Tìm kiếm món ăn

| | |
|---|---|
| **Tên** | Tìm kiếm và duyệt món ăn |
| **Loại** | 🔒 Protected |
| **Method** | `GET /foods` |

**Query params**

| Tham số | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `q` | string | — | Tìm theo tên món |
| `categoryId` | int | — | Lọc theo danh mục |
| `mealType` | string | — | Chỉ món hợp bữa này |
| `dishRole` | string | — | Lọc theo vai trò món |
| `maxCalories` | number | — | Trần năng lượng mỗi khẩu phần |
| `excludeUnsafe` | bool | `true` | Áp Bộ lọc F1 theo bệnh lý của người dùng |
| `page` | int | `1` | |
| `pageSize` | int | `20` | Tối đa 100 |

**Response `200 OK`**

```json
{
  "items": [
    {
      "id": 5,
      "name": "Canh chua cá lóc",
      "imageUrl": "https://cdn.example.com/foods/canh-chua-ca-loc.jpg",
      "origin": "Miền Tây",
      "categoryName": "Món canh",
      "dishRole": "soup",
      "cookingMethod": "nau_canh",
      "spiceLevel": 1,
      "caloriesKcal": 120.0,
      "servingSizeG": 250,
      "isSafeForUser": true
    }
  ],
  "page": 1,
  "pageSize": 20,
  "totalItems": 137,
  "totalPages": 7
}
```

**Status codes:** `200` · `400 VALIDATION_FAILED` · `401`

> `excludeUnsafe=true` (mặc định) loại hẳn món vi phạm ràng buộc cứng. Đặt `false` khi muốn hiện toàn bộ để người dùng tự tra cứu — khi đó `isSafeForUser` cho biết món nào không phù hợp, Frontend nên hiện cảnh báo thay vì ẩn đi.

---

### 7.5.2 Chi tiết món ăn

| | |
|---|---|
| **Tên** | Chi tiết món ăn |
| **Loại** | 🔒 Protected |
| **Method** | `GET /foods/{id}` |

**Path params**

| Tham số | Kiểu | Mô tả |
|---|---|---|
| `id` | int | Mã món ăn |

**Response `200 OK`**

```json
{
  "id": 5,
  "name": "Canh chua cá lóc",
  "description": "Canh chua nấu với cá lóc, dứa, cà chua, giá đỗ và rau thơm",
  "imageUrl": "https://cdn.example.com/foods/canh-chua-ca-loc.jpg",
  "origin": "Miền Tây",
  "category": { "id": 5, "code": "mon_canh", "name": "Món canh" },
  "cookingMethod": "nau_canh",
  "spiceLevel": 1,
  "dishRole": "soup",
  "suitableMeals": ["lunch", "dinner"],
  "nutrition": {
    "servingSizeG": 250,
    "caloriesKcal": 120.0,
    "proteinG": 14.0,
    "carbsG": 10.0,
    "fatG": 3.0,
    "fiberG": 1.8,
    "sugarG": 6.0,
    "sodiumMg": 650.0,
    "cholesterolMg": 40.0,
    "purineMg": 90.0,
    "calciumMg": null,
    "ironMg": null,
    "zincMg": null,
    "vitaminAMcg": null,
    "vitaminCMg": null,
    "dataSource": "Bảng thành phần thực phẩm Việt Nam"
  },
  "tags": [
    { "code": "sour",  "nameVi": "Chua",       "tagType": "taste" },
    { "code": "light", "nameVi": "Thanh đạm",  "tagType": "taste" }
  ],
  "isSafeForUser": true,
  "warnings": [],
  "myFeedback": { "rating": 4, "comment": "Ngon, hơi mặn", "createdAt": "2026-11-18T12:30:00Z" }
}
```

Khi món vi phạm ràng buộc của người dùng:

```json
{
  "isSafeForUser": false,
  "warnings": [
    {
      "conditionCode": "hypertension",
      "conditionName": "Tăng huyết áp",
      "ruleType": "nutrient_limit",
      "message": "Natri 650 mg vượt ngưỡng 600 mg mỗi khẩu phần",
      "isHard": true
    }
  ]
}
```

**Status codes:** `200` · `401` · `404 NOT_FOUND`

> Các trường vi chất trả `null` khi chưa có số liệu — Frontend hiển thị "chưa có dữ liệu" chứ không hiện `0`. `myFeedback` là `null` nếu người dùng chưa đánh giá món này.

---

## 7.6 Thực đơn

### 7.6.1 Lấy thực đơn theo ngày

| | |
|---|---|
| **Tên** | Lấy thực đơn của một ngày |
| **Loại** | 🔒 Protected |
| **Method** | `GET /meal-plans` |

**Query params**

| Tham số | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `date` | date | ✔ | Ngày cần lấy, `YYYY-MM-DD` |
| `autoGenerate` | bool | ✗ | Mặc định `true` — tự sinh nếu chưa có |

**Response `200 OK`**

```json
{
  "id": 42,
  "planDate": "2026-11-20",
  "status": "active",
  "generationSource": "hybrid",
  "modelVersion": "v1.0.3",
  "targets": {
    "caloriesKcal": 2573,
    "proteinG": 96.5,
    "carbsG": 385.9,
    "fatG": 71.5
  },
  "actuals": {
    "caloriesKcal": 2495.0,
    "proteinG": 101.2,
    "carbsG": 370.4,
    "fatG": 68.9
  },
  "calorieDeviationPct": -3.03,
  "withinTolerance": true,
  "totalPreferenceScore": 3.4821,
  "explorationRatio": 0.300,
  "meals": [
    {
      "mealType": "breakfast",
      "targetCaloriesKcal": 643,
      "actualCaloriesKcal": 430.0,
      "items": [
        {
          "id": 301,
          "food": {
            "id": 1,
            "name": "Phở bò",
            "imageUrl": "https://cdn.example.com/foods/pho-bo.jpg",
            "categoryName": "Món nước",
            "dishRole": "main",
            "caloriesKcal": 430.0
          },
          "servingSizeG": 400,
          "predictedScore": 0.8412,
          "status": "suggested",
          "replacedByFood": null,
          "explorationDelta": null,
          "position": 1
        }
      ]
    },
    {
      "mealType": "lunch",
      "targetCaloriesKcal": 1029,
      "actualCaloriesKcal": 1080.0,
      "items": [
        {
          "id": 302,
          "food": { "id": 3, "name": "Cơm tấm sườn nướng", "imageUrl": "...", "categoryName": "Cơm", "dishRole": "main", "caloriesKcal": 620.0 },
          "servingSizeG": 400,
          "predictedScore": 0.9105,
          "status": "kept",
          "replacedByFood": null,
          "explorationDelta": null,
          "position": 1
        },
        {
          "id": 303,
          "food": { "id": 5, "name": "Canh chua cá lóc", "imageUrl": "...", "categoryName": "Món canh", "dishRole": "soup", "caloriesKcal": 120.0 },
          "servingSizeG": 250,
          "predictedScore": 0.6733,
          "status": "suggested",
          "replacedByFood": null,
          "explorationDelta": 0.180,
          "position": 2
        }
      ]
    }
  ],
  "generatedAt": "2026-11-20T06:00:00Z"
}
```

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Có thực đơn, hoặc vừa sinh xong |
| `401` | | |
| `404` | `NOT_FOUND` | Chưa có và `autoGenerate=false` |
| `409` | `PROFILE_REQUIRED` | Chưa khai báo hồ sơ |
| `422` | `NO_FEASIBLE_PLAN` | Xem 7.7.2 |

| Trường | Ý nghĩa |
|---|---|
| `withinTolerance` | `|calorieDeviationPct| <= 10` — Frontend hiện dấu hiệu xanh hoặc vàng |
| `explorationRatio` | Tỷ lệ thăm dò **mục tiêu** của cơ chế 70-30 khi sinh thực đơn này |
| `explorationDelta` | Khác `null` nghĩa là món thuộc **nhóm thăm dò**, giá trị là biên độ nhiễu δ đã dùng. Frontend có thể hiện nhãn nhỏ kiểu *"Thử món mới"* |

> Cơ chế 70-30: 70 % số suất chọn theo vector sở thích `p_u` (khai thác), 30 % chọn theo vector đã nhiễu nhẹ `p_u'` (thăm dò). Chi tiết xem `SYSTEM_ARCHITECTURE.md` mục 4.6.

---

### 7.6.2 Sinh thực đơn

| | |
|---|---|
| **Tên** | Sinh thực đơn cho một ngày |
| **Loại** | 🔒 Protected |
| **Method** | `POST /meal-plans` |

**Body**

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `planDate` | date | ✔ | Ngày cần sinh |
| `regenerate` | bool | ✗ | Mặc định `false`. `true` để xóa và sinh lại |
| `mealTypes` | array | ✗ | Chỉ sinh một số bữa. Mặc định cả bốn |
| `explorationRatio` | number | ✗ | Tỷ lệ thăm dò, `0` – `0.5`. Mặc định `0.3`. Dùng cho thực nghiệm Chương 3 |

```json
{ "planDate": "2026-11-21", "regenerate": false }
```

**Response `201 Created`** — cấu trúc giống 7.7.1.

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `201` | — | Sinh thành công |
| `400` | `VALIDATION_FAILED` | Ngày sai định dạng |
| `401` | | |
| `409` | `MEAL_PLAN_EXISTS` | Đã có thực đơn và `regenerate=false` |
| `409` | `PROFILE_REQUIRED` | Chưa khai báo hồ sơ |
| `422` | `NO_FEASIBLE_PLAN` | Không tìm được tổ hợp thỏa ràng buộc |

**Lỗi `NO_FEASIBLE_PLAN`** xảy ra thật khi ràng buộc cứng quá chặt — ví dụ người vừa ăn chay, vừa dị ứng đậu nành, vừa bị bệnh thận, khiến tập ứng viên còn quá ít món để ghép đủ hạn mức năng lượng:

```json
{
  "error": {
    "code": "NO_FEASIBLE_PLAN",
    "message": "Không tìm được thực đơn thỏa mãn đồng thời mọi ràng buộc",
    "details": [
      { "field": "lunch", "message": "Chỉ còn 3 món hợp lệ, không đủ để ghép đạt 1029 kcal" }
    ],
    "traceId": "0HN7GKLM9QRST:00000091"
  }
}
```

Frontend nên gợi ý người dùng xem lại danh sách bệnh lý, hoặc chấp nhận thực đơn có độ lệch năng lượng lớn hơn.

> **Suy giảm mềm:** nếu ML Service không phản hồi, Backend **vẫn sinh được thực đơn** bằng quy tắc dinh dưỡng và trả `200` bình thường, chỉ khác `generationSource = "rule_based"` và `modelVersion = null`. Frontend không cần xử lý gì đặc biệt, nhưng có thể hiện ghi chú "gợi ý cơ bản".

---

### 7.6.3 Chi tiết thực đơn

| | |
|---|---|
| **Tên** | Chi tiết một thực đơn |
| **Loại** | 🔒 Protected |
| **Method** | `GET /meal-plans/{id}` |

**Response `200 OK`** — giống 7.7.1.

**Status codes:** `200` · `401` · `403 FORBIDDEN` · `404 NOT_FOUND`

> Trả `403` khi thực đơn thuộc người dùng khác, không phải `404` — nhưng chỉ khi thực sự tồn tại. Nếu không tồn tại thì `404`.

---

### 7.6.4 Gợi ý món thay thế

| | |
|---|---|
| **Tên** | Danh sách món có thể thay thế |
| **Loại** | 🔒 Protected |
| **Method** | `GET /meal-plan-items/{id}/alternatives` |

Backend tìm các món **cùng vai trò, năng lượng tương đương**, đã qua Bộ lọc F1, xếp theo điểm ưa thích.

**Query params:** `?limit=10` (mặc định 10, tối đa 30)

**Response `200 OK`**

```json
{
  "originalItem": {
    "id": 303,
    "foodName": "Canh chua cá lóc",
    "caloriesKcal": 120.0,
    "dishRole": "soup"
  },
  "alternatives": [
    {
      "food": { "id": 6, "name": "Canh bí đao", "imageUrl": "...", "categoryName": "Món canh", "dishRole": "soup", "caloriesKcal": 45.0 },
      "servingSizeG": 250,
      "predictedScore": 0.7218,
      "calorieDeltaKcal": -75.0,
      "keepsWithinTolerance": true
    },
    {
      "food": { "id": 21, "name": "Canh rau ngót thịt băm", "imageUrl": "...", "categoryName": "Món canh", "dishRole": "soup", "caloriesKcal": 95.0 },
      "servingSizeG": 250,
      "predictedScore": 0.6904,
      "calorieDeltaKcal": -25.0,
      "keepsWithinTolerance": true
    }
  ]
}
```

**Status codes:** `200` · `401` · `403` · `404`

> `keepsWithinTolerance` cho biết nếu đổi sang món này thì cả thực đơn còn giữ được độ lệch ≤ 10 % hay không. Frontend nên làm mờ hoặc cảnh báo với những món `false`.

---

### 7.6.5 Thay thế món

| | |
|---|---|
| **Tên** | Thay thế một món trong thực đơn |
| **Loại** | 🔒 Protected |
| **Method** | `PUT /meal-plan-items/{id}/replace` |

**Body**

```json
{ "newFoodId": 6, "servingSizeG": 250 }
```

**Response `200 OK`** — trả về **toàn bộ thực đơn đã cập nhật** (giống 7.7.1), vì thay một món làm đổi tổng dinh dưỡng và độ lệch của cả ngày.

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `200` | — | Thay thế thành công |
| `400` | `VALIDATION_FAILED` | `newFoodId` không hợp lệ |
| `401` | | |
| `403` | `FORBIDDEN` | Món thuộc thực đơn của người khác |
| `404` | `NOT_FOUND` | Không tìm thấy món trong thực đơn |
| `422` | `VALIDATION_FAILED` | Món mới vi phạm ràng buộc cứng của người dùng |

> Đây là **tín hiệu học quan trọng**. Backend ghi `status = 'replaced'` và `replaced_by_food_id` cho món cũ, sinh dòng mới cho món thay thế. Bảng thống nhất nhãn gán 0.15 cho món bị thay và điểm cao cho món được chọn.

---

### 7.6.6 Cập nhật trạng thái món

| | |
|---|---|
| **Tên** | Đánh dấu trạng thái món trong thực đơn |
| **Loại** | 🔒 Protected |
| **Method** | `PATCH /meal-plan-items/{id}/status` |

**Body**

```json
{ "status": "eaten" }
```

Giá trị cho phép từ Frontend: `kept` · `eaten` · `skipped`. Hai giá trị `suggested` và `replaced` do Backend tự đặt.

**Response `200 OK`**

```json
{
  "id": 302,
  "status": "eaten",
  "diaryEntryCreated": true,
  "diaryEntryId": 88
}
```

**Status codes:** `200` · `400` · `401` · `403` · `404`

> Khi đặt `status = "eaten"`, Backend **tự tạo luôn một dòng trong nhật ký ăn uống** — người dùng không phải nhập lại. `diaryEntryId` cho Frontend biết dòng vừa tạo để điều hướng sang màn hình đánh giá.

---

## 7.7 Nhật ký ăn uống

### 7.7.1 Xem nhật ký

| | |
|---|---|
| **Tên** | Xem nhật ký ăn uống |
| **Loại** | 🔒 Protected |
| **Method** | `GET /food-diary` |

**Query params**

| Tham số | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `from` | date | ✔ | Ngày bắt đầu |
| `to` | date | ✔ | Ngày kết thúc, tối đa 90 ngày sau `from` |
| `mealType` | string | ✗ | Lọc theo bữa |

**Response `200 OK`**

```json
{
  "from": "2026-11-20",
  "to": "2026-11-20",
  "days": [
    {
      "date": "2026-11-20",
      "totalCaloriesKcal": 1830.0,
      "entries": [
        {
          "id": 88,
          "food": { "id": 3, "name": "Cơm tấm sườn nướng", "imageUrl": "...", "categoryName": "Cơm", "caloriesKcal": 620.0 },
          "mealType": "lunch",
          "servingSizeG": 400,
          "actualCaloriesKcal": 620.0,
          "fromMealPlan": true,
          "hasFeedback": false,
          "createdAt": "2026-11-20T12:35:00Z"
        },
        {
          "id": 89,
          "food": { "id": 47, "name": "Trà sữa trân châu", "imageUrl": "...", "categoryName": "Đồ uống", "caloriesKcal": 340.0 },
          "mealType": "snack",
          "servingSizeG": 500,
          "actualCaloriesKcal": 340.0,
          "fromMealPlan": false,
          "hasFeedback": false,
          "createdAt": "2026-11-20T15:10:00Z"
        }
      ]
    }
  ]
}
```

**Status codes:** `200` · `400 VALIDATION_FAILED` · `401`

> `fromMealPlan` do Backend tính bằng cách **ghép khóa tự nhiên** `(userId, ateOn, mealType, foodId)` với bảng `meal_plan_items` — trong CSDL không có khóa ngoại giữa hai bảng này (xem `DATABASE_DESIGN.md` mục 6.2). Món có `fromMealPlan = false` là món ăn ngoài thực đơn, ví dụ ly trà sữa ở trên.

---

### 7.7.2 Thêm món đã ăn

| | |
|---|---|
| **Tên** | Ghi một món vào nhật ký |
| **Loại** | 🔒 Protected |
| **Method** | `POST /food-diary` |

**Body**

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `foodId` | int | ✔ | |
| `ateOn` | date | ✔ | Không được là ngày tương lai |
| `mealType` | string | ✔ | |
| `servingSizeG` | int | ✗ | Mặc định lấy khẩu phần chuẩn của món |

```json
{ "foodId": 47, "ateOn": "2026-11-20", "mealType": "snack", "servingSizeG": 500 }
```

**Response `201 Created`**

```json
{
  "id": 89,
  "food": { "id": 47, "name": "Trà sữa trân châu", "imageUrl": "...", "categoryName": "Đồ uống", "caloriesKcal": 340.0 },
  "ateOn": "2026-11-20",
  "mealType": "snack",
  "servingSizeG": 500,
  "actualCaloriesKcal": 340.0,
  "fromMealPlan": false,
  "createdAt": "2026-11-20T15:10:00Z"
}
```

**Status codes:** `201` · `400 VALIDATION_FAILED` · `401` · `404 NOT_FOUND`

> Endpoint này **không áp Bộ lọc F1**. Người dùng ghi lại thứ họ đã ăn thật, kể cả món không phù hợp sức khỏe — chặn lại sẽ làm nhật ký sai lệch và mất luôn tín hiệu học.

---

### 7.7.3 Sửa món đã ăn

| | |
|---|---|
| **Tên** | Cập nhật một dòng nhật ký |
| **Loại** | 🔒 Protected |
| **Method** | `PUT /food-diary/{id}` |

**Body:** giống 7.8.2.
**Response `200 OK`:** giống 7.8.2.
**Status codes:** `200` · `400` · `401` · `403` · `404`

---

### 7.7.4 Xóa món đã ăn

| | |
|---|---|
| **Tên** | Xóa một dòng nhật ký |
| **Loại** | 🔒 Protected |
| **Method** | `DELETE /food-diary/{id}` |

**Response `204 No Content`** — không có body.

**Status codes:** `204` · `401` · `403` · `404`

---

### 7.7.5 Tổng kết dinh dưỡng ngày

| | |
|---|---|
| **Tên** | Tổng kết dinh dưỡng trong ngày |
| **Loại** | 🔒 Protected |
| **Method** | `GET /food-diary/summary` |

**Query params:** `?date=2026-11-20` (bắt buộc)

**Response `200 OK`**

```json
{
  "date": "2026-11-20",
  "targets": { "caloriesKcal": 2573, "proteinG": 96.5, "carbsG": 385.9, "fatG": 71.5 },
  "consumed": { "caloriesKcal": 1830.0, "proteinG": 78.2, "carbsG": 240.5, "fatG": 58.1 },
  "remaining": { "caloriesKcal": 743.0, "proteinG": 18.3, "carbsG": 145.4, "fatG": 13.4 },
  "progressPct": { "calories": 71.1, "protein": 81.0, "carbs": 62.3, "fat": 81.3 },
  "byMeal": [
    { "mealType": "breakfast", "caloriesKcal": 430.0,  "targetCaloriesKcal": 643 },
    { "mealType": "lunch",     "caloriesKcal": 1060.0, "targetCaloriesKcal": 1029 },
    { "mealType": "dinner",    "caloriesKcal": 0.0,    "targetCaloriesKcal": 695 },
    { "mealType": "snack",     "caloriesKcal": 340.0,  "targetCaloriesKcal": 206 }
  ],
  "micronutrients": [
    { "nutrient": "calcium_mg",   "nameVi": "Canxi",     "consumed": 620.0, "rda": 800.0, "pct": 77.5, "unit": "mg" },
    { "nutrient": "iron_mg",      "nameVi": "Sắt",       "consumed": 9.2,   "rda": 11.9,  "pct": 77.3, "unit": "mg" },
    { "nutrient": "vitamin_c_mg", "nameVi": "Vitamin C", "consumed": 45.0,  "rda": 85.0,  "pct": 52.9, "unit": "mg" }
  ],
  "planCompliance": { "suggestedItems": 6, "eatenItems": 4, "compliancePct": 66.7 }
}
```

**Status codes:** `200` · `401` · `409 PROFILE_REQUIRED`

> `micronutrients` đối chiếu với bảng `rda_reference` theo giới tính và nhóm tuổi của người dùng. Chỉ liệt kê các vi chất có đủ số liệu — món thiếu dữ liệu vi chất bị bỏ qua khi cộng dồn, nên con số này là **ước lượng dưới**.

---

## 7.8 Đánh giá

### 7.8.1 Gửi đánh giá

| | |
|---|---|
| **Tên** | Đánh giá món ăn sau khi ăn |
| **Loại** | 🔒 Protected |
| **Method** | `POST /feedbacks` |

**Điều kiện bắt buộc — món phải thỏa đồng thời hai vế:**

| Vế | Kiểm tra | Chặn tình huống |
|---|---|---|
| ① Đã từng ở trong thực đơn của người dùng | `meal_plan_items` + `meal_plans` | Duyệt catalogue rồi chấm sao hàng loạt món chưa bao giờ được gợi ý |
| ② Đã ghi vào nhật ký ăn uống | `food_diary` | Chấm sao món **chưa từng ăn** — món bị thay thế hoặc bỏ bữa |

Vi phạm một trong hai vế thì trả `409 FEEDBACK_NOT_ALLOWED`. Frontend nên **ẩn sẵn nút đánh giá** với món chưa đủ điều kiện, thay vì để người dùng bấm rồi mới báo lỗi.

**Body**

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `foodId` | int | ✔ | Phải thỏa hai vế điều kiện ở trên |
| `rating` | int | ✔ | 1 – 5 |
| `comment` | string | ✗ | Tối đa 1000 ký tự |

```json
{ "foodId": 3, "rating": 4, "comment": "Ngon, hơi mặn" }
```

**Response `201 Created`**

```json
{
  "id": 55,
  "foodId": 3,
  "foodName": "Cơm tấm sườn nướng",
  "rating": 4,
  "comment": "Ngon, hơi mặn",
  "createdAt": "2026-11-20T13:05:00Z",
  "profileUpdated": true
}
```

**Status codes**

| Mã | `code` | Khi nào |
|---|---|---|
| `201` | — | Ghi nhận thành công |
| `400` | `VALIDATION_FAILED` | `rating` ngoài khoảng 1–5 |
| `401` | | |
| `404` | `NOT_FOUND` | `foodId` không tồn tại |
| `409` | `FEEDBACK_NOT_ALLOWED` | Món chưa từng ở trong thực đơn, hoặc chưa ghi vào nhật ký |

Ví dụ lỗi `409`:

```json
{
  "error": {
    "code": "FEEDBACK_NOT_ALLOWED",
    "message": "Chỉ được đánh giá món đã có trong thực đơn và đã ghi vào nhật ký ăn uống",
    "traceId": "0HN7GKLM9QRST:00000073"
  }
}
```

> Đây là **nguồn nhãn tin cậy nhất** của hệ thống, trọng số mẫu 1.0 — và hai điều kiện ở trên chính là cơ sở cho trọng số đó.

### Đánh giá lại theo thời gian

Người dùng **được phép đánh giá lại** cùng một món ở lần khác. Khẩu vị thay đổi: hôm nay thấy ngon chấm 5 sao, ba tháng sau ăn lại thấy dở chấm 2 sao. Mỗi lần chấm tạo một bản ghi mới với `createdAt` riêng, bản ghi cũ **không bị ghi đè**.

Bước dựng tập huấn luyện lấy đánh giá **gần nhất tính đến mốc cắt tập**, nên dữ liệu mới tự động thay thế dữ liệu cũ mà vẫn giữ được lịch sử để phân tích.

---

### 7.8.2 Xem đánh giá của tôi

| | |
|---|---|
| **Tên** | Danh sách đánh giá đã gửi |
| **Loại** | 🔒 Protected |
| **Method** | `GET /feedbacks` |

**Query params:** `?foodId=3` (lọc theo món) · `?page=1&pageSize=20`

**Response `200 OK`**

```json
{
  "items": [
    {
      "id": 55,
      "food": { "id": 3, "name": "Cơm tấm sườn nướng", "imageUrl": "...", "categoryName": "Cơm" },
      "rating": 4,
      "comment": "Ngon, hơi mặn",
      "createdAt": "2026-11-20T13:05:00Z"
    }
  ],
  "page": 1,
  "pageSize": 20,
  "totalItems": 12,
  "totalPages": 1
}
```

**Status codes:** `200` · `401`

---

## 7.9 Thống kê

### 7.9.1 Tiến trình sức khỏe

| | |
|---|---|
| **Tên** | Thống kê tiến trình theo khoảng thời gian |
| **Loại** | 🔒 Protected |
| **Method** | `GET /stats/progress` |

**Query params**

| Tham số | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `from` | date | ✔ | |
| `to` | date | ✔ | Tối đa 365 ngày sau `from` |
| `groupBy` | string | ✗ | `day` (mặc định) · `week` |

**Response `200 OK`**

```json
{
  "from": "2026-11-14",
  "to": "2026-11-20",
  "groupBy": "day",
  "series": [
    { "date": "2026-11-14", "caloriesConsumed": 2410.0, "caloriesTarget": 2573, "compliancePct": 83.3, "loggedMeals": 4 },
    { "date": "2026-11-15", "caloriesConsumed": 2688.0, "caloriesTarget": 2573, "compliancePct": 66.7, "loggedMeals": 3 },
    { "date": "2026-11-20", "caloriesConsumed": 1830.0, "caloriesTarget": 2573, "compliancePct": 66.7, "loggedMeals": 3 }
  ],
  "summary": {
    "daysLogged": 6,
    "daysInRange": 7,
    "avgCaloriesConsumed": 2312.5,
    "avgCaloriesTarget": 2573,
    "avgCompliancePct": 71.4,
    "avgCalorieDeviationPct": -10.1,
    "totalFeedbacks": 9
  },
  "weightTrend": [
    { "date": "2026-11-14", "weightKg": 69.0 },
    { "date": "2026-11-20", "weightKg": 68.5 }
  ]
}
```

**Status codes:** `200` · `400 VALIDATION_FAILED` · `401`

> `compliancePct` là tỷ lệ món trong thực đơn được ăn thật, tính bằng ghép khóa tự nhiên với `food_diary`. `weightTrend` lấy từ lịch sử cập nhật `health_profiles`, chỉ có điểm dữ liệu vào những ngày người dùng sửa cân nặng.

---

# 8. API nội bộ — ML Service

Chỉ **Backend** gọi các endpoint này. Không lộ ra Internet, không đi qua Gateway. Xác thực bằng khóa dùng chung trong header:

```http
X-Internal-Key: <giá trị cấu hình trong biến môi trường>
Content-Type: application/json
```

Trả `401` nếu thiếu hoặc sai khóa.

### 8.1 Chấm điểm món — Bước 3

| | |
|---|---|
| **Tên** | Chấm điểm mức độ ưa thích |
| **Loại** | ⚙️ Internal |
| **Method** | `POST /predict` |

**Body**

```json
{
  "userId": 1,
  "contextMealType": "lunch",
  "candidateFoodIds": [3, 5, 6, 12, 21, 47],
  "userFeatures": {
    "age": 22,
    "gender": "male",
    "bmi": 23.15,
    "activityLevel": "moderate",
    "goal": "maintain",
    "remainingCaloriesKcal": 1143.0
  }
}
```

**Response `200 OK`**

```json
{
  "modelVersion": "v1.0.3",
  "featureVersion": "fv1",
  "stage": "hybrid",
  "alpha": 0.42,
  "scores": [
    { "foodId": 3,  "score": 0.9105, "scoreContent": 0.8802, "scoreMl": 0.9523 },
    { "foodId": 5,  "score": 0.6733, "scoreContent": 0.7011, "scoreMl": 0.6349 },
    { "foodId": 47, "score": 0.2140, "scoreContent": 0.1902, "scoreMl": 0.2469 }
  ],
  "elapsedMs": 34
}
```

**Status codes**

| Mã | Khi nào |
|---|---|
| `200` | Thành công |
| `400` | Thiếu `userId` hoặc `candidateFoodIds` rỗng |
| `401` | Sai `X-Internal-Key` |
| `503` | Chưa có mô hình đang hoạt động |

> Backend đặt **timeout 2 giây**. Quá hạn hoặc gặp `503` thì bỏ qua Bước 3, dùng điểm theo quy tắc, và đặt `generationSource = "rule_based"`. Đây là cơ chế suy giảm mềm đã nêu ở mục 7.6.2.

---

### 8.2 Dựng lại hồ sơ sở thích

| | |
|---|---|
| **Tên** | Dựng lại vector sở thích |
| **Loại** | ⚙️ Internal |
| **Method** | `POST /profiles/{userId}/rebuild` |

Gọi sau khi hoàn tất onboarding, hoặc khi `featureVersion` thay đổi.

**Response `200 OK`**

```json
{
  "userId": 1,
  "featureVersion": "fv1",
  "nSignals": 26,
  "sumAbsWeight": 21.0,
  "stage": "content",
  "alpha": 0.0,
  "updatedAt": "2026-11-20T08:02:11Z"
}
```

**Status codes:** `200` · `401` · `404` · `422` (không đủ tín hiệu)

---

### 8.3 Huấn luyện lại mô hình

| | |
|---|---|
| **Tên** | Huấn luyện lại mô hình |
| **Loại** | ⚙️ Internal |
| **Method** | `POST /train` |

Chạy bất đồng bộ, thường do lịch định kỳ kích hoạt.

**Body**

```json
{ "datasetVersion": "ds-2026-11-20", "algorithm": "random_forest", "activate": false }
```

**Response `202 Accepted`**

```json
{ "jobId": "train-20261120-0900", "status": "queued", "startedAt": "2026-11-20T09:00:00Z" }
```

**Status codes:** `202` · `401` · `409` (đang có phiên huấn luyện chạy)

---

### 8.4 Kiểm tra sống

| | |
|---|---|
| **Tên** | Health check |
| **Loại** | ⚙️ Internal |
| **Method** | `GET /health` |

**Response `200 OK`**

```json
{
  "status": "healthy",
  "activeModel": { "version": "v1.0.3", "algorithm": "random_forest", "trainedAt": "2026-11-18T02:00:00Z" },
  "featureVersion": "fv1"
}
```

Khi chưa có mô hình nào hoạt động:

```json
{ "status": "degraded", "activeModel": null, "featureVersion": "fv1" }
```

**Status codes:** `200` · `503`

---

# 9. Luồng gọi API theo màn hình

Bảng này giúp Frontend biết thứ tự gọi, và giúp Backend biết endpoint nào cần làm trước.

| Màn hình | Thứ tự gọi |
|---|---|
| **Khởi động app** | `GET /auth/me` → điều hướng theo `hasHealthProfile` và `onboardingCompletedAt` |
| **Đăng ký** | `POST /auth/register` → màn hình khai báo hồ sơ |
| **Đăng nhập** | `POST /auth/login` → `GET /auth/me` |
| **Khai báo hồ sơ** | `GET /conditions` (tải danh mục) → `PUT /profile` → `PUT /profile/conditions` → màn hình vuốt |
| **Khảo sát khẩu vị** | `GET /onboarding/survey` → *(vuốt hết, Flutter giữ trong bộ nhớ)* → `POST /onboarding/survey`. **Chỉ chạy một lần trong đời tài khoản** |
| **Thực đơn hôm nay** | `GET /meal-plans?date=today` |
| **Chi tiết món** | `GET /foods/{id}` |
| **Đổi món** | `GET /meal-plan-items/{id}/alternatives` → `PUT /meal-plan-items/{id}/replace` |
| **Đánh dấu đã ăn** | `PATCH /meal-plan-items/{id}/status` với `eaten` → tự tạo dòng nhật ký |
| **Nhật ký** | `GET /food-diary?from=&to=` · `POST /food-diary` · `GET /food-diary/summary?date=` |
| **Đánh giá món** | `POST /feedbacks` |
| **Thống kê** | `GET /stats/progress?from=&to=` |
| **Sửa hồ sơ** | `PUT /profile` → gợi ý `POST /meal-plans` với `regenerate=true` |

---

# 10. Ghi chú cho phát triển song song

### 10.1 Frontend làm việc trước khi có Backend

Mọi JSON mẫu trong tài liệu này đều **hợp lệ và đầy đủ**, dùng trực tiếp làm dữ liệu giả được. Ba cách:

| Cách | Ghi chú |
|---|---|
| Tệp JSON cục bộ trong `assets/mock/` | Đơn giản nhất, không cần mạng |
| Máy chủ giả bằng `json-server` hoặc Mockoon | Gọi qua HTTP thật, dễ chuyển sang API thật |
| Lớp `ApiClient` có cờ `useMock` | Đổi một biến là chuyển qua lại |

Khuyến nghị cách thứ ba: viết interface `ApiClient`, hiện thực hai lớp `MockApiClient` và `HttpApiClient`. Khi Backend xong chỉ đổi lớp được tiêm vào.

### 10.2 Backend làm việc trước khi có Frontend

Bật Swagger để tự kiểm thử:

```
http://localhost:5000/swagger
```

Thứ tự hiện thực đề xuất, theo mức độ phụ thuộc:

| Đợt | Nhóm API | Vì sao trước |
|---|---|---|
| 1 | Xác thực + Danh mục tra cứu | Mọi thứ khác đều cần token |
| 2 | Hồ sơ sức khỏe + Hạn mức | Bước 1 của thuật toán, không phụ thuộc ML |
| 3 | Món ăn | Cần dữ liệu 300–500 món đã nạp |
| 4 | Khảo sát khẩu vị (2 endpoint) | Cần ML Service dựng vector sở thích |
| 5 | Thực đơn | Cần đủ Bước 1 → Bước 4 |
| 6 | Nhật ký + Đánh giá + Thống kê | Phụ thuộc thực đơn |

### 10.3 Quy tắc bất di bất dịch

| Quy tắc | Lý do |
|---|---|
| **Không bao giờ nhận `userId` từ client** | Lấy từ token. Nhận từ tham số là lỗ hổng truy cập dữ liệu người khác |
| **Enum gửi lên đúng chuỗi trong mục 5** | Không dịch sang tiếng Việt, không viết hoa |
| **Ngày giờ luôn UTC, có hậu tố `Z`** | Tránh lệch múi giờ khi so sánh |
| **Trường thiếu dữ liệu trả `null`** | Không trả `0` hay chuỗi rỗng — Frontend phân biệt được "chưa có" và "bằng không" |
| **Lỗi luôn theo cấu trúc mục 2.5** | Frontend chỉ cần một hàm xử lý lỗi duy nhất |
| **Thay đổi API phải sửa tài liệu này trước** | Nếu không, hai bên sẽ lệch nhau lúc ghép |
