# Kiến trúc hệ thống — Ứng dụng khuyến nghị thực đơn dinh dưỡng cá nhân hóa bằng Machine Learning

## 1. Tổng quan kiến trúc

Hệ thống được xây dựng theo mô hình **3 tầng** (Three-tier Architecture) kết hợp với một **ML Service** độc lập, tạo thành vòng lặp học liên tục từ phản hồi của người dùng.

```
┌──────────────────────────────────────────────────────────────────┐
│                        Ứng dụng Mobile                           │
│                            Flutter                               │
│                                                                  │
│   [Đăng nhập]  [Khai báo hồ sơ sức khỏe]  [Vuốt onboarding]      │
│   [Thực đơn hằng ngày]  [Chi tiết món]  [Thay thế món]           │
│   [Nhật ký ăn uống]  [Đánh giá món]  [Thống kê tiến trình]       │
└─────────────────────────────┬────────────────────────────────────┘
                              │ HTTPS / REST API
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      ASP.NET Core API                            │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐   │
│  │  Người     │  │  Hồ sơ     │  │  Món ăn    │  │  Hạn mức  │   │
│  │  dùng      │  │  sức khỏe  │  │  & Dinh    │  │  dinh     │   │
│  │            │  │            │  │  dưỡng     │  │  dưỡng    │   │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘   │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐   │
│  │  Bộ lọc F1 │  │  Tương     │  │  Nhật ký   │  │  Sinh     │   │
│  │  ràng buộc │  │  tác &     │  │  ăn uống   │  │  thực đơn │   │
│  │  cứng      │  │  Phản hồi  │  │            │  │  (tổ hợp) │   │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘   │
└──────────────────┬───────────────────────────┬───────────────────┘
                   │                           │
                   ▼                           ▼
    ┌──────────────────────┐     ┌──────────────────────────┐
    │        MySQL         │     │       ML Service         │
    │                      │     │       (Python)           │
    │  - Người dùng        │     │                          │
    │  - Hồ sơ sức khỏe    │     │  - Trích chọn đặc trưng  │
    │  - Món ăn & dinh     │◄────│  - Dựng hồ sơ sở thích   │
    │    dưỡng             │     │  - Huấn luyện mô hình    │
    │  - Bộ quy tắc F1     │────►│  - Chấm điểm mức độ      │
    │  - Lịch sử tương tác │     │    ưa thích              │
    │  - Nhật ký & Phản hồi│     │  - Đánh giá mô hình      │
    │  - Mô hình & Đánh giá│     │  - Huấn luyện lại        │
    └──────────────────────┘     └──────────────────────────┘
```

---

## 2. Các thành phần chính

### 2.1 Ứng dụng Mobile (Client)

| Thành phần | Mô tả |
|---|---|
| **Framework** | Flutter (nền tảng Android) |
| **Khai báo hồ sơ** | Giới tính, ngày sinh, chiều cao, cân nặng, mức vận động, mục tiêu, bệnh lý, dị ứng |
| **Khảo sát khẩu vị** | Vuốt một gói món cố định ngay sau khi khai báo hồ sơ, giải bài toán khởi đầu nguội. **Chỉ chạy một lần** |
| **Cơ chế vuốt** | Phải (Thích), Trái (Không thích), Lên (Bình thường), Xuống (Chưa biết) |
| **Thực đơn hằng ngày** | Hiển thị thực đơn sáng / trưa / tối / phụ kèm tổng năng lượng và tỷ lệ dinh dưỡng |
| **Thay thế món** | Cho phép đổi một món trong thực đơn — hành động này là tín hiệu học quan trọng |
| **Nhật ký ăn uống** | Ghi lại món đã ăn thực tế, kể cả món ngoài thực đơn gợi ý |
| **Đánh giá món** | Chấm điểm 1–5 sao sau khi ăn |
| **Thống kê tiến trình** | Biểu đồ năng lượng nạp vào, cân nặng, mức độ tuân thủ thực đơn |
| **Giao tiếp** | REST API qua HTTPS, xác thực JWT |

---

### 2.2 Backend — ASP.NET Core API

Tầng xử lý nghiệp vụ chính, đóng vai trò điều phối giữa Mobile Client, Database và ML Service.

| Module | Chức năng |
|---|---|
| **Người dùng** | Đăng ký, đăng nhập, xác thực JWT |
| **Hồ sơ sức khỏe** | Lưu trữ và cập nhật chiều cao, cân nặng, mức vận động, mục tiêu, bệnh lý |
| **Hạn mức dinh dưỡng** | Tính BMI, BMR (Mifflin-St Jeor), TDEE, hạn mức năng lượng và tỷ lệ macro theo mục tiêu |
| **Món ăn & Dinh dưỡng** | CRUD món ăn, thông tin năng lượng, ba chất sinh năng lượng, vi chất |
| **Bộ lọc F1 (Rule-based)** | Loại bỏ món vi phạm ràng buộc cứng trước khi đưa vào chấm điểm |
| **Khảo sát khẩu vị** | Phát gói món khảo sát và nhận trọn gói kết quả vuốt, chỉ chạy một lần lúc tạo tài khoản |
| **Nhật ký ăn uống** | Ghi nhận món đã ăn thực tế theo ngày và theo bữa |
| **Phản hồi & Rating** | Thu thập đánh giá chi tiết sau khi dùng món |
| **Sinh thực đơn** | Gọi ML Service chấm điểm, sau đó chạy thuật toán chọn tổ hợp món thỏa ràng buộc dinh dưỡng |

> **Ghi chú phân chia trách nhiệm:** Backend giữ **Bước 1 (hạn mức)**, **Bước 2 (lọc cứng)** và **Bước 4 (chọn tổ hợp)** vì đây là logic nghiệp vụ tất định. ML Service chỉ giữ **Bước 3 (chấm điểm)**. Nhờ vậy hệ thống vẫn sinh được thực đơn ngay cả khi ML Service tạm ngừng — khi đó Bước 3 dùng điểm mặc định từ quy tắc.

---

### 2.3 Cơ sở dữ liệu — MySQL

Chi tiết đầy đủ xem `DATABASE_DESIGN.md`. Tóm tắt các nhóm dữ liệu:

| Nhóm | Dữ liệu lưu trữ |
|---|---|
| **Người dùng** | Tài khoản, hồ sơ sức khỏe, bệnh lý và dị ứng |
| **Món ăn** | Danh mục, món ăn, thành phần dinh dưỡng, nhãn đặc trưng |
| **Quy tắc** | Bộ quy tắc ràng buộc cứng, bảng nhu cầu khuyến nghị RDA |
| **Tương tác** | Lịch sử vuốt, nhật ký ăn uống, đánh giá sau khi ăn |
| **Thực đơn** | Thực đơn theo ngày và các món trong thực đơn kèm trạng thái |
| **Machine Learning** | Hồ sơ sở thích, tập dữ liệu huấn luyện, mô hình và kết quả đánh giá |

---

### 2.4 ML Service (Python)

Dịch vụ học máy độc lập, chạy song song với Backend. Đọc dữ liệu từ MySQL, huấn luyện mô hình và cung cấp API chấm điểm cho Backend.

**Phương pháp:** khuyến nghị theo nội dung (content-based filtering) kết hợp học máy có giám sát (supervised learning).

| Giai đoạn | Nội dung |
|---|---|
| **Thu thập dữ liệu** | Đọc kết quả khảo sát khẩu vị, nhật ký ăn uống, đánh giá và trạng thái món trong thực đơn |
| **Thống nhất nhãn** | Quy đổi các nguồn tín hiệu khác nhau về một thang điểm ưa thích chung trong đoạn [0, 1] |
| **Tiền xử lý** | Làm sạch, xử lý dữ liệu khuyết, chuẩn hóa min-max hoặc z-score, mã hóa one-hot |
| **Trích chọn đặc trưng** | Dựng vector đặc trưng món ăn và vector đặc trưng người dùng |
| **Dựng hồ sơ sở thích** | Vector trọng số tổng hợp từ lịch sử tương tác của từng người dùng |
| **Huấn luyện mô hình** | Hồi quy Logistic, Rừng ngẫu nhiên, Gradient Boosting |
| **Đánh giá** | Precision@K, Recall@K, NDCG, MAE, RMSE; kiểm định chéo k-fold |
| **Chấm điểm** | Trả về điểm mức độ ưa thích cho từng cặp (người dùng, món ăn) |
| **Huấn luyện lại** | Định kỳ khi tích lũy đủ phản hồi mới |

#### Cách biểu diễn đặc trưng

**Vector đặc trưng món ăn** gồm bốn nhóm, đúng theo đề cương:

| Nhóm | Thành phần | Xử lý |
|---|---|---|
| Thành phần dinh dưỡng | Năng lượng, đạm, tinh bột, chất béo, chất xơ, đường, natri | Chuẩn hóa min-max về [0, 1] |
| Nhóm thực phẩm | Danh mục món ăn | Mã hóa one-hot |
| Phương pháp chế biến | Luộc, hấp, xào, chiên, nướng, kho, nấu canh, trộn | Mã hóa one-hot |
| Khẩu vị | Mặn, ngọt, chua, cay, béo, thanh đạm | Vector nhiều nhãn (multi-hot) |

**Vector đặc trưng người dùng:** tuổi, giới tính, BMI, mức vận động, mục tiêu sức khỏe, tình trạng bệnh lý.

**Đặc trưng chéo (cross features)** — quan trọng, đây là chỗ mô hình học được mối liên hệ giữa người và món:

- Độ tương đồng cosin giữa vector sở thích của người dùng và vector món ăn
- Tỷ lệ năng lượng món ăn so với hạn mức còn lại trong ngày
- Độ lệch tỷ lệ macro của món so với tỷ lệ mục tiêu của người dùng
- Ngữ cảnh bữa ăn (sáng / trưa / tối / phụ)
- Số ngày kể từ lần cuối người dùng ăn món này

> **Ghi chú về ngữ cảnh bữa ăn:** sở thích món ăn phụ thuộc vào bữa. Cùng một người có thể rất thích phở cho bữa sáng nhưng không muốn ăn phở lúc 8 giờ tối. Vì vậy nhãn và đặc trưng đều phải gắn với `meal_type`, không thể chỉ là cặp (người dùng, món ăn).

#### Thống nhất nhãn từ nhiều nguồn tín hiệu

Mô hình cần một nhãn duy nhất trong đoạn [0, 1], nhưng tín hiệu đến từ nhiều nguồn với độ tin cậy khác nhau:

| Nguồn tín hiệu | Bảng | Nhãn | Trọng số mẫu |
|---|---|---|---|
| Đánh giá 5 sao | `feedbacks` | 1.00 | 1.0 |
| Đánh giá 4 sao | `feedbacks` | 0.75 | 1.0 |
| Đánh giá 3 sao | `feedbacks` | 0.50 | 1.0 |
| Đánh giá 2 sao | `feedbacks` | 0.25 | 1.0 |
| Đánh giá 1 sao | `feedbacks` | 0.00 | 1.0 |
| Đã ăn thật | `food_diary` | 0.80 | 0.9 |
| Vuốt thích | `interactions` | 0.90 | 0.7 |
| Vuốt bình thường | `interactions` | 0.50 | 0.7 |
| Vuốt không thích | `interactions` | 0.00 | 0.7 |
| Giữ món trong thực đơn | `meal_plan_items` | 0.70 | 0.6 |
| Thay thế món trong thực đơn | `meal_plan_items` | 0.15 | 0.6 |
| Được gợi ý nhưng không tương tác | `recommendations` | 0.30 | 0.3 |
| Vuốt chưa biết | `interactions` | — | Loại khỏi tập huấn luyện |

**Hai lưu ý bắt buộc khi xây tập dữ liệu:**

1. **Lấy mẫu âm.** Người dùng chủ yếu để lại tín hiệu dương, mô hình sẽ học ra "món nào cũng thích". Nguồn mẫu âm gồm: món đã gợi ý nhưng không được tương tác, và món lấy ngẫu nhiên trong số chưa từng hiển thị.
2. **Chia tập theo thời gian, không chia ngẫu nhiên.** Với hệ khuyến nghị có vòng lặp phản hồi, chia ngẫu nhiên gây rò rỉ dữ liệu vì mô hình được huấn luyện trên hành vi tương lai rồi kiểm thử trên quá khứ. Phải cắt theo mốc thời gian: huấn luyện trên tín hiệu trước ngày T, kiểm thử trên tín hiệu sau ngày T.

---

## 3. Thuật toán khuyến nghị thực đơn — bốn bước

Đây là phần lõi của đề tài. Đầu vào là hồ sơ người dùng, đầu ra là thực đơn hoàn chỉnh cho một ngày.

```
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 1 — Tính hạn mức năng lượng và dinh dưỡng              │
│ Hồ sơ sức khỏe  →  BMI, BMR, TDEE  →  hạn mức từng bữa      │
│ Thực hiện tại: Backend        Độ phức tạp: O(1)             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 2 — Lọc bỏ món vi phạm ràng buộc cứng (Bộ lọc F1)      │
│ Toàn bộ món  →  tập ứng viên an toàn                        │
│ Thực hiện tại: Backend        Độ phức tạp: O(n)             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 3 — Chấm điểm mức độ ưa thích bằng học máy             │
│ Tập ứng viên  →  điểm số trong [0, 1] cho từng món          │
│ Thực hiện tại: ML Service     Độ phức tạp: O(n)             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 4 — Chọn tổ hợp món thỏa ràng buộc dinh dưỡng          │
│ Điểm số  →  THỰC ĐƠN cho từng bữa trong ngày                │
│ Thực hiện tại: Backend    Độ phức tạp: O(K · |S| · n)       │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.1 Bước 1 — Tính hạn mức năng lượng và dinh dưỡng

**Đầu vào:** giới tính, ngày sinh, chiều cao, cân nặng, mức vận động, mục tiêu sức khỏe.

**Chỉ số khối cơ thể:**

```text
BMI = cân_nặng(kg) / chiều_cao(m)²
```

**Chuyển hóa cơ bản** theo công thức Mifflin-St Jeor:

```text
Nam:  BMR = 10 × W + 6.25 × H − 5 × A + 5
Nữ:   BMR = 10 × W + 6.25 × H − 5 × A − 161

W = cân nặng (kg), H = chiều cao (cm), A = tuổi (năm)
```

**Tổng năng lượng tiêu hao trong ngày:**

```text
TDEE = BMR × hệ_số_vận_động
```

| Mức vận động | Hệ số |
|---|---|
| `sedentary` — ít vận động | 1.200 |
| `light` — vận động nhẹ | 1.375 |
| `moderate` — vận động vừa | 1.550 |
| `active` — vận động nhiều | 1.725 |
| `very_active` — vận động rất nhiều | 1.900 |

**Hạn mức năng lượng theo mục tiêu:**

| Mục tiêu | Hạn mức | Ràng buộc an toàn |
|---|---|---|
| `lose_weight` | TDEE − 500 kcal | Không thấp hơn BMR |
| `maintain` | TDEE | — |
| `healthy_eating` | TDEE | — |
| `gain_weight` | TDEE + 500 kcal | — |

**Phân bổ ba chất sinh năng lượng** theo khuyến nghị của Viện Dinh dưỡng Quốc gia:

| Chất | Tỷ lệ năng lượng | Quy đổi |
|---|---|---|
| Carbohydrate | 55 – 65 % | 4 kcal/g |
| Protein | 13 – 20 % | 4 kcal/g |
| Lipid | 20 – 25 % | 9 kcal/g |

**Phân bổ theo bữa ăn:**

| Bữa | Tỷ lệ năng lượng ngày |
|---|---|
| Sáng | 25 – 30 % |
| Trưa | 35 – 40 % |
| Tối | 25 – 30 % |
| Phụ | 5 – 10 % |

**Đầu ra:** hạn mức năng lượng `E_target` và bộ ba `(P_target, C_target, F_target)` tính theo gram, cho cả ngày và cho từng bữa.

---

### 3.2 Bước 2 — Lọc bỏ món vi phạm ràng buộc cứng (Bộ lọc F1)

Ràng buộc cứng là ràng buộc **không được phép vi phạm trong bất kỳ trường hợp nào**, kể cả khi món đó được người dùng rất thích. Đây là tầng bảo vệ an toàn sức khỏe, phải đặt **trước** bước chấm điểm học máy.

**Đầu vào:** toàn bộ món ăn đang hoạt động, danh sách bệnh lý và dị ứng của người dùng, bộ quy tắc ràng buộc.

**Các loại ràng buộc:**

| Loại | Ví dụ | Cách kiểm tra |
|---|---|---|
| Dị ứng thực phẩm | Dị ứng hải sản, đậu phộng, gluten | Loại món chứa nguyên liệu tương ứng |
| Bệnh lý | Đái tháo đường, tăng huyết áp, bệnh thận | Áp ngưỡng dinh dưỡng và loại nhãn bị cấm |
| Chế độ ăn bắt buộc | Ăn chay, ăn kiêng theo tôn giáo | Chỉ giữ món có nhãn phù hợp |
| Phù hợp bữa ăn | Món tráng miệng không dùng làm món chính bữa trưa | Đối chiếu nhãn bữa ăn phù hợp của món |
| Tránh lặp lại | Món đã ăn trong N ngày gần đây | Đối chiếu nhật ký ăn uống |

**Nguyên tắc thiết kế quan trọng:** bộ quy tắc này phải được lưu **dưới dạng dữ liệu trong cơ sở dữ liệu**, không hard-code trong mã nguồn. Hai lý do:

1. Đề cương liệt kê "bộ quy tắc ràng buộc dinh dưỡng" là một sản phẩm phải nộp — nó cần trình bày được thành bảng trong báo cáo.
2. Cùng bộ quy tắc này sẽ được dùng làm **phương án đối chứng (baseline) chỉ dùng quy tắc** khi so sánh với mô hình học máy ở Chương 3.

**Đầu ra:** tập ứng viên `C_valid` gồm các món an toàn cho người dùng này, trong ngữ cảnh bữa ăn này.

---

### 3.3 Bước 3 — Chấm điểm mức độ ưa thích

**Đầu vào:** tập ứng viên `C_valid`, hồ sơ người dùng, hồ sơ sở thích, ngữ cảnh bữa ăn.

**Đầu ra:** `score(u, i) ∈ [0, 1]` cho từng món `i` trong `C_valid`.

Bước này có hai chế độ tùy theo độ trưởng thành dữ liệu của người dùng — chi tiết xem Mục 4.

**Ràng buộc mềm** được xử lý tại bước này, dưới dạng điểm số chứ không phải loại bỏ: khẩu vị, sự đa dạng món ăn, độ mới lạ. Món không hợp khẩu vị sẽ bị điểm thấp nhưng vẫn nằm trong tập ứng viên, để thuật toán tổ hợp ở Bước 4 vẫn có đủ lựa chọn khi ràng buộc dinh dưỡng bị siết chặt.

---

### 3.4 Bước 4 — Chọn tổ hợp món thỏa ràng buộc dinh dưỡng

Đây là bước tạo nên khác biệt của đề tài. Xếp hạng ở Bước 3 chỉ cho biết **món nào người dùng thích**, nhưng lấy top-K món điểm cao nhất **không tạo thành một thực đơn hợp lệ** — tổng năng lượng có thể vượt xa hạn mức, tỷ lệ dinh dưỡng có thể mất cân đối, và cả ba món có thể cùng là món mặn.

#### Phát biểu bài toán

Với mỗi bữa ăn `m`, tìm tập món `S_m ⊆ C_valid` sao cho:

```text
Cực đại:    Σ  score(u, i)
          i ∈ S

Thỏa mãn:   | calo(S) − E_m |  ≤  0.10 × E_m               (ràng buộc năng lượng)
            | macro_k(S) − T_k | ≤ δ_k   ∀k ∈ {P, C, F}    (ràng buộc dinh dưỡng)
            S chứa đúng cấu trúc bữa ăn quy định
            không có hai món cùng nhóm thực phẩm trong S
            không lặp món đã xuất hiện trong ngày
```

Đây là **bài toán cái túi đa chiều** (multi-dimensional knapsack) — thuộc lớp NP-khó. Với 300–500 món ứng viên, tìm lời giải tối ưu tuyệt đối bằng vét cạn là không khả thi trong thời gian đáp ứng của một API. Vì vậy hệ thống dùng **lời giải gần đúng**.

#### Hàm mục tiêu có phạt

Thay vì xử lý ràng buộc một cách cứng nhắc, ràng buộc dinh dưỡng được đưa vào hàm mục tiêu dưới dạng thành phần phạt. Cách này cho phép thuật toán đi qua các lời giải tạm thời vi phạm nhẹ, tránh bị kẹt sớm ở một lời giải kém:

```text
                        | calo(S) − E_m |              | macro_k(S) − T_k |
F(S) =  Σ score(u,i)  − λ ─────────────────  −  μ  Σ  ─────────────────────
       i∈S                      E_m            k∈{P,C,F}       T_k

λ, μ : hệ số phạt, hiệu chỉnh bằng thực nghiệm
```

#### Thuật toán giải

**Pha 1 — Tham lam (greedy).** Xây dựng nhanh một lời giải khả thi ban đầu.

```text
INPUT:  C_valid, score(·), E_m, (P_m, C_m, F_m)
OUTPUT: S_m

S ← ∅
Sắp xếp C_valid giảm dần theo mật độ điểm:  d(i) = score(u, i) / calo(i)

for i in C_valid theo thứ tự đã sắp xếp:
    if calo(S ∪ {i}) ≤ 1.10 × E_m
       and nhóm_thực_phẩm(i) chưa xuất hiện trong S
       and i chưa xuất hiện trong thực đơn ngày:
           S ← S ∪ {i}
    if calo(S) ≥ 0.90 × E_m and S đã đủ cấu trúc bữa ăn:
        break

return S
```

> Sắp xếp theo **mật độ điểm** `score / calo` chứ không theo `score` thuần là điểm mấu chốt. Đây là chiến lược tham lam kinh điển của bài toán cái túi: ưu tiên món mang lại nhiều điểm ưa thích nhất trên mỗi đơn vị năng lượng tiêu tốn.

**Pha 2 — Tìm kiếm cục bộ (local search).** Cải thiện lời giải bằng phép hoán đổi từng món.

```text
INPUT:  S từ Pha 1, C_valid, số vòng lặp tối đa K
OUTPUT: S đã cải thiện

lặp tối đa K vòng:
    cải_thiện ← false
    for each i in S:
        for each j in C_valid \ S:
            S' ← (S \ {i}) ∪ {j}
            if S' hợp lệ và F(S') > F(S):
                S ← S'
                cải_thiện ← true
    if not cải_thiện:
        break

return S
```

**Độ phức tạp:**

| Pha | Độ phức tạp | Ghi chú |
|---|---|---|
| Sắp xếp | O(n log n) | n = số món ứng viên |
| Tham lam | O(n) | Duyệt một lượt |
| Tìm kiếm cục bộ | O(K × \|S\| × n) | K vòng lặp, \|S\| khoảng 3–5 món |

Với `n ≈ 400`, `|S| ≈ 4`, `K ≈ 20`, tổng số phép đánh giá khoảng 32.000 — chạy trong vài chục mili-giây, hoàn toàn đáp ứng được yêu cầu thời gian đáp ứng của API.

#### Đầu ra và các chỉ số cần lưu

Thực đơn sinh ra phải lưu kèm các chỉ số để phục vụ đánh giá ở Chương 3:

| Chỉ số | Mục đích |
|---|---|
| Tổng năng lượng thực tế của thực đơn | So với hạn mức |
| **Độ lệch năng lượng so với hạn mức** | Đề cương yêu cầu chứng minh không quá 10 % |
| Tỷ lệ ba chất sinh năng lượng thực tế | Kiểm tra cân đối dinh dưỡng |
| Phiên bản mô hình đã sinh ra thực đơn | Phân tích và so sánh giữa các phiên bản |
| Tổng điểm ưa thích của thực đơn | So sánh phương án học máy với phương án chỉ dùng quy tắc |

---

## 4. Chiến lược khởi đầu nguội (Cold-start)

Đề tài giải bài toán khởi đầu nguội bằng **phiên vuốt thăm dò lúc onboarding**, kết hợp cơ chế chuyển tiếp dần giữa hai phương pháp chấm điểm.

### 4.1 Ba giai đoạn theo độ trưởng thành dữ liệu

> **Cơ chế vuốt chỉ chạy đúng một lần**, ở phiên khảo sát lúc tạo tài khoản. Từ Giai đoạn 1 trở đi, tín hiệu sở thích đến từ chính thực đơn hằng ngày: món người dùng giữ lại, món họ thay thế, món họ ăn thật và điểm họ đánh giá. Việc chống thực đơn một màu do **cơ chế 70-30** ở mục 4.6 đảm nhiệm, không phải bằng cách cho vuốt thêm.

```
     Số tín hiệu tích lũy của người dùng
     0                    ~30                    ~50+
     │                     │                      │
     ▼                     ▼                      ▼
┌─────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ GIAI ĐOẠN 0 │   │   GIAI ĐOẠN 1    │   │   GIAI ĐOẠN 2    │
│             │   │                  │   │                  │
│ Chỉ có hồ   │   │ Đã vuốt thăm dò  │   │ Đã ăn thật, có   │
│ sơ sức khỏe │   │ onboarding       │   │ nhật ký và đánh  │
│             │   │                  │   │ giá              │
│             │   │                  │   │                  │
│ Chấm điểm   │   │ Tương đồng cosin │   │ Mô hình học máy  │
│ theo quy    │   │ với hồ sơ sở     │   │ có giám sát      │
│ tắc và độ   │   │ thích            │   │                  │
│ phổ biến    │   │                  │   │                  │
└─────────────┘   └──────────────────┘   └──────────────────┘
```

### 4.2 Giai đoạn 0 — Chưa có tín hiệu nào

Ngay sau khi khai báo hồ sơ, hệ thống **đã đủ dữ liệu để chạy Bước 1, Bước 2 và Bước 4**. Chỉ riêng Bước 3 chưa có căn cứ cá nhân hóa.

Điểm số tạm thời được tính từ mức độ phù hợp dinh dưỡng và độ phổ biến chung của món trong toàn hệ thống. Người dùng vẫn nhận được thực đơn hợp lệ về mặt dinh dưỡng ngay từ ngày đầu — chỉ là chưa hợp khẩu vị.

### 4.3 Giai đoạn 1 — Phiên vuốt thăm dò onboarding

**Chọn tập món thăm dò.** Đây là bước dễ bị làm sai. Nếu chọn ngẫu nhiên 30 món, rất có thể cả 30 món đều rơi vào vài nhóm phổ biến, và hệ thống không học được gì về những vùng khẩu vị còn lại.

Tập món thăm dò phải được chọn theo nguyên tắc **cực đại hóa độ đa dạng**: phủ đều các nhóm thực phẩm, các phương pháp chế biến và các kiểu khẩu vị, sao cho mỗi lần vuốt mang lại lượng thông tin lớn nhất. Tập này vẫn phải đi qua Bộ lọc F1 trước — không hiển thị món mà người dùng dị ứng.

**Tập món được chọn một lần và cố định trong suốt phiên.** Hệ thống **không** điều chỉnh món tiếp theo dựa trên lượt vuốt vừa rồi. Ba lý do:

| Lý do | Giải thích |
|---|---|
| Độ đa dạng đã tối ưu từ đầu | Chọn thích ứng từng bước dễ rơi vào tối ưu cục bộ, phủ kém hơn so với chọn cả tập một lần |
| Ứng dụng vuốt được khi mất mạng | Tải một lần rồi vuốt ngoại tuyến, chỉ cần mạng lúc gửi kết quả |
| Đơn giản hóa giao tiếp | Cả phiên chỉ cần 2 lần gọi API thay vì hàng chục lần |

Vì vậy toàn bộ kết quả vuốt được ứng dụng giữ trong bộ nhớ và **gửi lên một lần duy nhất** khi người dùng vuốt xong. Việc đếm tiến độ do ứng dụng tự làm, không hỏi máy chủ. Chi tiết giao diện lập trình xem `API_SPECIFICATION.md` mục 7.4.

**Dựng hồ sơ sở thích.** Hồ sơ sở thích của người dùng là vector trọng số tổng hợp từ các món đã vuốt:

```text
           Σ  w(a_i) · v_i
          i∈I
   p_u = ──────────────────
           Σ  | w(a_i) |
          i∈I

   v_i    : vector đặc trưng đã chuẩn hóa của món i
   a_i    : hành động vuốt trên món i
   w(a_i) : trọng số theo hành động
            like = +1.0 ,  neutral = 0.0 ,  dislike = −1.0
            unknown → loại khỏi tổng
   I      : tập món người dùng đã vuốt
```

**Chấm điểm.** Dùng độ tương đồng cosin giữa hồ sơ sở thích và vector món ăn, đưa từ đoạn [−1, 1] về [0, 1]:

```text
                        p_u · v_i
   cos(p_u, v_i) = ───────────────────
                    ‖p_u‖ · ‖v_i‖

                    1 + cos(p_u, v_i)
   score(u, i) =  ─────────────────────
                            2
```

**Vì sao giai đoạn này không huấn luyện một mô hình học máy riêng cho từng người dùng.** Với khoảng 30 mẫu và hàng chục chiều đặc trưng, một mô hình như Rừng ngẫu nhiên sẽ quá khớp nghiêm trọng — nó học thuộc 30 món đó thay vì học ra quy luật khẩu vị.

Công thức vector trọng số ở trên **bản chất vẫn là một mô hình tuyến tính** học từ chính 30 mẫu ấy, chỉ khác ở chỗ nghiệm được tính bằng công thức đóng thay vì tối ưu lặp. Nhờ vậy nó ổn định khi dữ liệu ít, cho kết quả tức thì ngay khi người dùng vuốt xong, và giải thích được với người dùng — có thể chỉ rõ *"gợi ý món này vì bạn đã thích các món cùng nhóm, cùng cách chế biến"*.

Đồng thời, toàn bộ tín hiệu vuốt onboarding vẫn được ghi vào cơ sở dữ liệu và **tham gia vào tập huấn luyện của mô hình toàn cục** ở Giai đoạn 2. Không có dữ liệu nào bị bỏ phí.

### 4.4 Giai đoạn 2 — Mô hình học máy có giám sát

Khi người dùng đã tích lũy đủ tín hiệu, đặc biệt là tín hiệu mạnh từ nhật ký ăn uống và đánh giá sau khi ăn, hệ thống chuyển sang mô hình học máy.

**Mô hình toàn cục, không phải mô hình riêng từng người.** Hệ thống huấn luyện **một mô hình duy nhất** trên dữ liệu của **toàn bộ người dùng**, với đầu vào là vector ghép:

```text
   x = [ đặc trưng người dùng  ⊕  đặc trưng món ăn  ⊕  đặc trưng chéo ]
   y = nhãn mức độ ưa thích ∈ [0, 1]
```

Cách này có ba ưu điểm so với việc huấn luyện riêng cho từng người:

| Ưu điểm | Giải thích |
|---|---|
| Tận dụng dữ liệu chéo | Người dùng có hồ sơ tương tự đóng góp dữ liệu cho nhau, giảm mạnh nhu cầu dữ liệu trên mỗi người |
| Chống quá khớp | Tập huấn luyện lớn hơn nhiều lần so với dữ liệu của một cá nhân |
| Vận hành đơn giản | Một mô hình để huấn luyện, đánh giá và triển khai, thay vì hàng trăm mô hình rời rạc |

Tính cá nhân hóa được bảo đảm nhờ **đặc trưng người dùng và đặc trưng chéo** nằm ngay trong vector đầu vào — trong đó đặc trưng chéo quan trọng nhất chính là độ tương đồng cosin với hồ sơ sở thích cá nhân đã dựng ở Giai đoạn 1.

**Chuyển tiếp mượt.** Không chuyển đột ngột giữa hai phương pháp, vì như vậy người dùng sẽ thấy thực đơn thay đổi bất thường ngay khi vừa vượt ngưỡng:

```text
   score(u, i) = α · score_học_máy(u, i)  +  (1 − α) · score_tương_đồng(u, i)

              ⎧ 0                              nếu  n < n_min
          α = ⎨ (n − n_min) / (n_max − n_min)   nếu  n_min ≤ n ≤ n_max
              ⎩ 1                              nếu  n > n_max

   n : số tín hiệu người dùng đã tích lũy
   n_min ≈ 30 ,  n_max ≈ 100   (hiệu chỉnh bằng thực nghiệm)
```

### 4.5 Hướng mở rộng — phân cụm nhóm khẩu vị

Khi số lượng người dùng đủ lớn, có thể phân cụm các hồ sơ sở thích `p_u` bằng k-means để tìm ra các **nhóm khẩu vị** đặc trưng. Người dùng mới sẽ được gán vào nhóm gần nhất ngay sau phiên vuốt onboarding, và nhận gợi ý dựa trên món phổ biến trong nhóm đó.

Đây là cách khai thác dữ liệu cộng đồng mà **không cần dựng ma trận người dùng–món ăn** như lọc cộng tác truyền thống, nên vẫn hoạt động được khi dữ liệu thưa. Ghi nhận như hướng phát triển, không nằm trong phạm vi bắt buộc của đồ án.

---

### 4.6 Chống thực đơn một màu — cơ chế 70-30

> **Bong bóng lọc (filter bubble)** là hiện tượng hệ thống chỉ hiển thị những thứ nó đã biết người dùng thích, khiến phạm vi lựa chọn của họ hẹp dần theo thời gian. Thuật ngữ do Eli Pariser đặt năm 2011; trong lĩnh vực hệ khuyến nghị nó còn được gọi là **thiên lệch vòng lặp phản hồi** (feedback loop bias).

Điểm nguy hiểm không nằm ở chỗ gợi ý nhàm chán, mà ở chỗ **vòng lặp tự nuôi chính nó**:

```text
   Hệ thống cho rằng người dùng thích món chiên
                    ↓
   Chỉ gợi ý món chiên
                    ↓
   Người dùng chỉ có cơ hội ăn và đánh giá món chiên
                    ↓
   Dữ liệu mới thu được toàn là món chiên
                    ↓
   Mô hình càng chắc chắn người dùng thích món chiên
                    ↓
             (quay lại đầu, chặt hơn)
```

Mô hình không hề **sai** — nó chỉ không bao giờ **biết thêm**. Người dùng có thể rất thích canh chua, nhưng nếu hệ thống chưa từng gợi ý canh chua thì nó sẽ chẳng bao giờ biết điều đó.

**Hệ thống này dễ dính bong bóng lọc hơn bình thường.** Với 300–500 món trong kho nhưng chỉ 4–6 suất mỗi ngày, vùng điểm cao có thể chỉ gồm 30–50 món — tức khoảng **10% kho món**. Ba trăm món còn lại không bao giờ được hiển thị, nên không bao giờ có tín hiệu, nên không bao giờ vào tập huấn luyện.

Quan trọng hơn: vì cơ chế vuốt chỉ chạy một lần lúc tạo tài khoản, **nguồn dữ liệu mới duy nhất là thực đơn**. Không có kênh nào khác để hệ thống hỏi thêm. Thực đơn hẹp thì dữ liệu hẹp, vĩnh viễn. Ở ứng dụng cho vuốt liên tục, người dùng còn tự khám phá được; ở đây thì hệ thống **phải tự thăm dò**.

Nếu luôn chọn món có điểm cao nhất theo vector sở thích, vector `p_u` càng bị củng cố về hướng cũ, và vòng lặp phản hồi tự bóp nghẹt chính nó.

Vì cơ chế vuốt chỉ chạy một lần lúc tạo tài khoản, hệ thống **không thể hỏi thêm** để mở rộng hiểu biết. Nó phải tự thăm dò ngay trong thực đơn hằng ngày.

#### Cách làm

Chia số suất trong mỗi thực đơn thành hai nhóm, chấm điểm bằng hai vector khác nhau:

```text
p_u   = vector sở thích hiện tại

p_u'  = chuẩn_hóa( p_u + δ · n )       n = vector nhiễu ngẫu nhiên đơn vị
                                        δ = biên độ nhiễu

┌──────────────────────────────────────────────────────────────────┐
│  70 % số suất  →  xếp hạng theo cos(p_u,  v_i)                   │
│                   KHAI THÁC — món chắc chắn hợp gu               │
├──────────────────────────────────────────────────────────────────┤
│  30 % số suất  →  xếp hạng theo cos(p_u', v_i)                   │
│                   THĂM DÒ — món lân cận khẩu vị, loại các món    │
│                   đã được chọn ở nhóm khai thác                  │
└──────────────────────────────────────────────────────────────────┘
```

Cả hai nhóm đều lấy từ tập ứng viên đã qua Bộ lọc F1, và đều đi tiếp vào Bước 4 để ghép thành tổ hợp thỏa ràng buộc năng lượng.

#### Vì sao xoay vector thay vì chọn ngẫu nhiên

Cách thăm dò kinh điển là ε-greedy: với xác suất ε, chèn một món **ngẫu nhiên**. Cách đó có nhược điểm rõ: món ngẫu nhiên có thể nằm rất xa khẩu vị, người dùng thấy vô lý và thay thế ngay, vừa mất một suất trong thực đơn vừa không thu được thông tin hữu ích.

Xoay nhẹ chính vector sở thích cho kết quả khác hẳn:

| | ε-greedy ngẫu nhiên | Xoay vector (70-30) |
|---|---|---|
| Món thăm dò nằm ở đâu | Bất kỳ đâu trong không gian đặc trưng | **Vùng lân cận** khẩu vị hiện tại |
| Xác suất được chấp nhận | Thấp | Cao hơn đáng kể |
| Thông tin thu được khi bị từ chối | Ít — đã biết trước là món lạ | Nhiều — biết ranh giới khẩu vị nằm ở đâu |
| Điều khiển được mức độ mạo hiểm | Không, chỉ có tần suất ε | Có, qua biên độ δ |

Khi món thăm dò được chấp nhận, tín hiệu đó đi vào tập huấn luyện, vector `p_u` dịch dần về hướng mới, và lần sau vùng khai thác đã rộng hơn. Đó chính là cơ chế mở rộng khẩu vị theo thời gian.

#### Hai tham số cần hiệu chỉnh bằng thực nghiệm

**Biên độ nhiễu δ** quyết định món thăm dò lệch bao xa:

| δ | Hậu quả |
|---|---|
| Quá nhỏ | Món "mới" gần như trùng món cũ — không khám phá được gì |
| Quá lớn | Suy biến thành ngẫu nhiên, mất hết ưu điểm so với ε-greedy |

**Tỷ lệ thăm dò** khởi đầu ở 30 %. Nếu thực nghiệm cho thấy người dùng hiếm khi chọn món ngoài vùng khai thác, có thể nâng dần lên 40 % rồi 50 %. **Trần cứng là 50 %** — quá nửa thực đơn là món thử nghiệm thì nó không còn là gợi ý cá nhân hóa nữa. Ràng buộc `chk_expl_ratio` trong cơ sở dữ liệu chặn ngưỡng này.

#### Dữ liệu ghi lại để đánh giá

| Cột | Bảng | Ghi lại |
|---|---|---|
| `exploration_ratio` | `meal_plans` | Tỷ lệ thăm dò **mục tiêu** của thực đơn |
| `exploration_delta` | `meal_plan_items` | Biên độ δ của **từng món** thăm dò. `NULL` = món khai thác |

Từ hai cột này tính được các chỉ số quyết định:

| Chỉ số | Ý nghĩa |
|---|---|
| Tỷ lệ món thăm dò bị thay thế | Cao hơn hẳn nhóm khai thác → δ quá lớn |
| Tỷ lệ món thăm dò được ăn thật | Gần bằng nhóm khai thác → δ hợp lý, có thể nâng tỷ lệ |
| Chênh lệch điểm dự đoán giữa hai nhóm | Gần bằng 0 → δ quá nhỏ, không thực sự khám phá |
| Tỷ lệ thăm dò thực tế so với mục tiêu | Thấp hơn nhiều → Bước 4 không tìm đủ món thăm dò khả thi |
| **Số món khác nhau đã xuất hiện sau N ngày** | **Đo trực tiếp bong bóng lọc.** Chạy song song hai cấu hình tỷ lệ thăm dò `0` và `0.3`, chênh lệch chính là bằng chứng định lượng |
| Độ dịch chuyển của vector `p_u` theo thời gian | Vector đứng yên nghĩa là bong bóng đã đóng, hệ thống ngừng học |

Một tính chất đáng chú ý: **kể cả khi người dùng từ chối món thăm dò, hệ thống vẫn học được** — nó biết thêm một điểm về ranh giới khẩu vị, điều mà nhóm khai thác không bao giờ cho biết vì món nào cũng được chấp nhận.

> **Thăm dò chỉ nới lỏng về khẩu vị, không nới lỏng về an toàn.** Món thăm dò vẫn phải qua Bộ lọc F1 (dị ứng, bệnh lý, chế độ ăn) và vẫn phải nằm trong tổ hợp thỏa hạn mức năng lượng ở Bước 4. Không bao giờ có chuyện vì thăm dò mà gợi ý món tôm cho người dị ứng hải sản.

Truy vấn sẵn ở `DATABASE_DESIGN.md` mục 8.5. Đây là một mục thực nghiệm hoàn chỉnh cho Chương 3.

---

## 5. Luồng dữ liệu — Vòng lặp phản hồi

```
Khai báo hồ sơ sức khỏe
          │
          ▼
  Bước 1: Tính hạn mức
  BMI → BMR → TDEE → E_target
          │
          ▼
  Vuốt thăm dò onboarding  ──────► Dựng hồ sơ sở thích ban đầu
  (chỉ chạy một lần)                        │
          │                                 │
          ▼                                 │
  Bước 2: Lọc ràng buộc cứng                │
  Loại món dị ứng, món vi phạm bệnh lý      │
          │                                 │
          ▼                                 ▼
  Bước 3: Chấm điểm mức độ ưa thích ◄───────┘
  (tương đồng cosin hoặc học máy, tùy giai đoạn)
          │
          ▼
  Bước 4: Chọn tổ hợp món
  Tham lam + tìm kiếm cục bộ
          │
          ▼
  THỰC ĐƠN hiển thị trên app
          │
          ├──► Người dùng giữ món         ──┐
          ├──► Người dùng thay thế món    ──┤
          ├──► Người dùng vuốt thêm       ──┤  Tín hiệu
          ├──► Người dùng ăn và ghi nhật ký─┤  phản hồi
          └──► Người dùng đánh giá 1–5 sao ─┘
                                            │
                                            ▼
                             Ghi nhận vào cơ sở dữ liệu
                                            │
                                            ▼
                             Thống nhất nhãn từ các nguồn
                                            │
                                            ▼
                             Huấn luyện lại mô hình học máy
                                            │
                                            ▼
                             Thực đơn cá nhân hóa tốt hơn
                                            │
                                            └──► (quay lại Bước 3)
```

---

## 6. Luồng xử lý sinh thực đơn

```
Mobile App              Backend API                ML Service           MySQL
    │                        │                          │                 │
    │── GET /meal-plans ────►│                          │                 │
    │      ?date=...         │                          │                 │
    │                        │── Lấy hồ sơ sức khỏe ──────────────────────►│
    │                        │◄─ Hồ sơ + bệnh lý + dị ứng ─────────────────│
    │                        │                          │                 │
    │                        │ Bước 1: BMI → BMR → TDEE │                 │
    │                        │         → E_target       │                 │
    │                        │                          │                 │
    │                        │── Lấy món + bộ quy tắc ────────────────────►│
    │                        │◄─ Danh sách món ────────────────────────────│
    │                        │                          │                 │
    │                        │ Bước 2: Lọc ràng buộc    │                 │
    │                        │         cứng → C_valid   │                 │
    │                        │                          │                 │
    │                        │── POST /predict ────────►│                 │
    │                        │   {user, C_valid, meal}  │                 │
    │                        │                          │── Lấy hồ sơ ───►│
    │                        │                          │   sở thích      │
    │                        │                          │◄────────────────│
    │                        │                          │ Bước 3: Chấm    │
    │                        │                          │ điểm từng món   │
    │                        │◄─ score(u, i) ───────────│                 │
    │                        │                          │                 │
    │                        │ Bước 4: Tham lam +       │                 │
    │                        │ tìm kiếm cục bộ → S_m    │                 │
    │                        │                          │                 │
    │                        │── Lưu thực đơn + độ lệch ──────────────────►│
    │◄─ Thực đơn hoàn chỉnh ─│                          │                 │
    │                        │                          │                 │
    │── PUT /meal-plan-items/{id}/replace ──────────────────────────────► │
    │── POST /food-diary ───────────────────────────────────────────────► │
    │── POST /feedbacks ────────────────────────────────────────────────► │
    │                        │                          │                 │
```

---

## 7. Nguyên tắc thiết kế

| Nguyên tắc | Áp dụng |
|---|---|
| **Tách biệt trách nhiệm** | ML Service chỉ chấm điểm; logic nghiệp vụ tất định nằm ở Backend |
| **Suy giảm mềm** | ML Service ngừng hoạt động thì hệ thống vẫn sinh được thực đơn hợp lệ bằng quy tắc |
| **An toàn trước, sở thích sau** | Ràng buộc cứng lọc trước học máy — không bao giờ gợi ý món gây hại sức khỏe dù người dùng thích |
| **Ràng buộc cứng và mềm tách bạch** | Cứng thì loại bỏ ở Bước 2; mềm thì trừ điểm ở Bước 3 và phạt ở Bước 4 |
| **Quy tắc là dữ liệu, không phải mã** | Bộ quy tắc lưu trong cơ sở dữ liệu để trình bày trong báo cáo và làm phương án đối chứng |
| **Thực đơn là một tổng thể** | Tối ưu cả tổ hợp món, không phải xếp hạng từng món rồi lấy top-K |
| **Phản hồi liên tục** | Mọi tương tác đều được ghi nhận và quy về nhãn huấn luyện |
| **Khởi đầu nguội có lời giải** | Vuốt thăm dò onboarding cho cá nhân hóa ngay từ ngày đầu sử dụng |
| **Chuyển tiếp mượt** | Trộn dần hai phương pháp chấm điểm theo lượng dữ liệu tích lũy |
| **Thăm dò có hướng** | Cơ chế 70-30 xoay nhẹ vector sở thích thay vì chèn món ngẫu nhiên |
| **Vuốt chỉ một lần** | Sau khảo sát ban đầu, hệ thống học từ hành vi thật chứ không hỏi thêm |
| **Thực nghiệm tái lập được** | Tập dữ liệu, phân chia train/test và tham số chuẩn hóa đều đóng băng và lưu lại |
| **Khả năng mở rộng** | Các module có thể tách thành microservice khi cần |
