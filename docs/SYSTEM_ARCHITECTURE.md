# Kiến trúc hệ thống — Ứng dụng gợi ý món ăn cá nhân hóa bằng Machine Learning

## 1. Tổng quan kiến trúc

Hệ thống được xây dựng theo mô hình **3 tầng** (Three-tier Architecture) kết hợp với một **ML Service** độc lập, tạo thành vòng lặp học liên tục từ phản hồi của người dùng.

```
┌──────────────────────────────────────────────────────────────────┐
│                        Ứng dụng Mobile                           │
│                    Flutter / React Native                        │
│                                                                  │
│   [Màn hình đăng nhập]  [Màn hình nhập hồ sơ lần đầu]            │
│   [Màn hình gợi ý]  [Vuốt tương tác]  [Lập thực đơn]  [Hồ sơ]    │
│   [Màn hình phản hồi sau khi dùng món ăn]                        │
└─────────────────────────────┬────────────────────────────────────┘
                              │ HTTPS / REST API
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      ASP.NET Core API                            │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐   │
│  │  Người     │  │  Hồ sơ     │  │  Món ăn    │  │  Bộ lọc   │   │
│  │  dùng      │  │  sức khỏe  │  │  & Dinh    │  │  F1 (rule-│   │
│  │            │  │            │  │  dưỡng     │  │  based)   │   │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘   │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐   │
│  │  Tương     │  │  Phản hồi  │  │  Gợi ý     │  │  Lập      │   │
│  │  tác       │  │  & Rating  │  │  (Recom.)  │  │  thực đơn │   │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘   │
└──────────────────┬───────────────────────────┬───────────────────┘
                   │                           │
                   ▼                           ▼
    ┌──────────────────────┐     ┌──────────────────────────┐
    │        MySQL         │     │       ML Service         │
    │                      │     │       (Python)           │
    │  - Người dùng        │     │                          │
    │  - Hồ sơ sức khỏe    │     │  - Tiền xử lý dữ liệu    │
    │  - Món ăn            │◄────│  - Huấn luyện mô hình    │
    │  - Thông tin dinh    │     │  - Dự đoán & Xếp hạng    │
    │    dưỡng             │────►│  - Đánh giá mô hình      │
    │  - Lịch sử tương tác │     │  - Cập nhật mô hình      │
    │  - Phản hồi          │     │    từ phản hồi mới       │
    └──────────────────────┘     └──────────────────────────┘
```

---

## 2. Các thành phần chính

### 2.1 Ứng dụng Mobile (Client)

| Thành phần | Mô tả |
|---|---|
| **Framework** | Flutter hoặc React Native |
| **Màn hình gợi ý** | Hiển thị các món ăn được gợi ý dạng card |
| **Cơ chế vuốt** | Vuốt phải (Thích), Trái (Không thích), Xuống (Chưa biết), Lên (Bình thường) |
| **Lập thực đơn** | Tạo thực đơn theo ngày / tuần dựa trên gợi ý |
| **Hồ sơ cá nhân** | Quản lý thông tin sức khỏe, mục tiêu dinh dưỡng |
| **Giao tiếp** | REST API qua HTTPS |

---

### 2.2 Backend — ASP.NET Core API

Tầng xử lý nghiệp vụ chính, đóng vai trò điều phối giữa Mobile Client, Database và ML Service.

| Module | Chức năng |
|---|---|
| **Người dùng** | Đăng ký, đăng nhập, xác thực JWT |
| **Hồ sơ sức khỏe** | Lưu trữ và cập nhật BMI, tuổi, giới tính, bệnh lý, mục tiêu |
| **Món ăn & Dinh dưỡng** | CRUD món ăn, thông tin calo, macro, vi chất |
| **Bộ lọc F1 (Rule-based)** | Lọc sơ bộ các món phù hợp sức khỏe trước khi đưa vào ML |
| **Tương tác** | Ghi nhận hành động vuốt của người dùng theo thời gian thực |
| **Phản hồi & Rating** | Thu thập đánh giá chi tiết sau khi dùng món |
| **Gợi ý (Recommendation)** | Gọi ML Service, xử lý và trả kết quả gợi ý về Mobile |
| **Lập thực đơn** | Tổng hợp gợi ý thành thực đơn cân đối dinh dưỡng |

---

### 2.3 Cơ sở dữ liệu — MySQL

| Bảng / Nhóm | Dữ liệu lưu trữ |
|---|---|
| `users` | Thông tin tài khoản người dùng |
| `health_profiles` | Hồ sơ sức khỏe, chỉ số BMI, bệnh lý, mục tiêu |
| `foods` | Danh sách món ăn và thông tin dinh dưỡng |
| `interactions` | Lịch sử vuốt (thích / không thích / bình thường / chưa biết) |
| `feedbacks` | Đánh giá chi tiết sau khi dùng món |
| `recommendations` | Lịch sử các lần gợi ý đã sinh ra |
| `meal_plans` | Thực đơn đã được lập theo ngày / tuần |

---

### 2.4 ML Service (Python)

Dịch vụ học máy độc lập, chạy song song với Backend. Nhận dữ liệu từ MySQL, huấn luyện mô hình và cung cấp API dự đoán cho Backend.

| Giai đoạn | Nội dung |
|---|---|
| **Thu thập dữ liệu** | Lấy lịch sử tương tác + phản hồi từ MySQL |
| **Tiền xử lý** | Làm sạch, encode đặc trưng, xây dựng ma trận user-item |
| **Huấn luyện mô hình** | Collaborative Filtering / Content-based / Hybrid |
| **Đánh giá** | Precision, Recall, RMSE, NDCG |
| **Dự đoán** | Tính điểm phù hợp (score) cho từng món với từng người dùng |
| **Xếp hạng** | Sắp xếp danh sách gợi ý theo điểm dự đoán |
| **Cập nhật** | Định kỳ re-train khi có đủ phản hồi mới |

---

## 3. Luồng dữ liệu — Feedback Loop

Đây là vòng lặp cốt lõi của hệ thống, đảm bảo gợi ý ngày càng cá nhân hóa hơn:

```
Thông tin sức khỏe người dùng
          │
          ▼
  Bộ lọc F1 (Rule-based)
  Loại bỏ món không phù hợp
  theo điều kiện sức khỏe
          │
          ▼
   ML Service dự đoán
   & Xếp hạng món ăn
          │
          ▼
  Hiển thị gợi ý trên app
  (dạng card vuốt)
          │
          ▼
  Người dùng tương tác
  (Thích / Không thích /
   Bình thường / Chưa biết)
          │
          ▼
  Ghi nhận vào Database
  (interactions, feedbacks)
          │
          ▼
  ML Service cập nhật
  & Huấn luyện lại mô hình
          │
          ▼
  Gợi ý cá nhân hóa tốt hơn  ──► (quay lại đầu vòng lặp)
```

---

## 4. Luồng xử lý gợi ý

```
Mobile App                Backend API              ML Service          MySQL
    │                         │                        │                 │
    │── GET /recommendations ─►│                        │                 │
    │                         │── Lấy hồ sơ sức khỏe ─────────────────►│
    │                         │◄─ Trả về health profile ────────────────│
    │                         │── Lọc F1 (rule-based) ──│               │
    │                         │── POST /predict ────────►│               │
    │                         │                         │── Lấy lịch sử ►│
    │                         │                         │◄─ interaction  │
    │                         │                         │── Dự đoán      │
    │                         │◄─ Danh sách gợi ý ──────│               │
    │◄─ Trả kết quả gợi ý ────│                        │                 │
    │                         │                        │                 │
    │── POST /interactions ───►│                        │                 │
    │  (vuốt / đánh giá)      │── Lưu interaction ─────────────────────►│
    │                         │                        │                 │
```

---

## 5. Nguyên tắc thiết kế

| Nguyên tắc | Áp dụng |
|---|---|
| **Tách biệt concerns** | ML Service hoạt động độc lập, không phụ thuộc vào vòng đời API |
| **Lọc hai tầng** | F1 lọc theo rule trước, ML xếp hạng sau — tránh gợi ý gây hại sức khỏe |
| **Phản hồi liên tục** | Mọi tương tác đều được ghi nhận để cải thiện mô hình |
| **Cá nhân hóa** | Mô hình được xây dựng per-user dựa trên lịch sử cá nhân |
| **Khả năng mở rộng** | Các module (Auth, Food, ML...) có thể tách thành microservice sau này |