# Context dự án tốt nghiệp — Hệ thống khuyến nghị thực đơn dinh dưỡng cá nhân hóa bằng Machine Learning

## 1. Tổng quan dự án

Đây là đồ án tốt nghiệp đại học với mục tiêu xây dựng một **ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa** dựa trên thông tin cá nhân, tình trạng sức khỏe, thông tin dinh dưỡng của món ăn và đặc biệt là lịch sử tương tác của người dùng.

Ý tưởng cốt lõi:

> Hệ thống không chỉ dựa vào các luật cố định để gợi ý món ăn, mà sẽ thu thập phản hồi của người dùng, sử dụng dữ liệu đó để huấn luyện mô hình Machine Learning và dần cá nhân hóa các món ăn được đề xuất.

Bài toán mà hệ thống phải giải:

> Với người dùng này, dựa trên thông tin sức khỏe và những món họ từng thích/không thích, **tổ hợp món ăn nào** vừa hợp khẩu vị của họ, vừa thỏa mãn hạn mức năng lượng và tỷ lệ dinh dưỡng theo mục tiêu sức khỏe?

Điểm cần nhấn mạnh: đây **không phải bài toán xếp hạng món ăn đơn lẻ**. Đầu ra cuối cùng là một **thực đơn** — tập hợp món cho các bữa trong ngày, phải cân đối dinh dưỡng như một tổng thể. Xếp hạng chỉ là bước trung gian.

---

## 2. Hai vai trò của cơ chế vuốt

Cơ chế tương tác vuốt thẻ món ăn:

| Cử chỉ | Hành động | Ý nghĩa | Giá trị nhãn |
|---|---|---|---|
| Vuốt phải | `like` | Thích | 0.9 |
| Vuốt trái | `dislike` | Không thích | 0.0 |
| Vuốt lên | `neutral` | Bình thường, không cảm xúc đặc biệt | 0.5 |
| Vuốt xuống | `unknown` | Chưa biết / chưa từng ăn | Loại khỏi tập huấn luyện |

Vuốt là **cơ chế thu thập dữ liệu**, không phải sản phẩm chính. Sản phẩm chính vẫn là thực đơn hằng ngày.

### Hạn chế đã biết: không có thao tác hoàn tác

Màn hình khảo sát được thiết kế **thuần cử chỉ** — không có nút bấm, kể cả nút hoàn tác. Đổi lại, một cú vuốt lỡ tay sẽ đi thẳng vào tập huấn luyện và **không rút lại được**.

Đây là đánh đổi có chủ ý, chấp nhận nhiễu nhãn để giữ giao diện gọn. Cần ghi vào phần hạn chế của báo cáo, kèm hai điểm:

- Ngưỡng vuốt đặt ở 26 % bề rộng thẻ theo phương ngang và 22 % chiều cao theo phương dọc, cùng ngưỡng vận tốc 820 px/s. Ngưỡng này đã lọc bớt phần lớn thao tác chạm nhẹ ngoài ý muốn, nhưng không lọc được cú vuốt dứt khoát nhầm hướng.
- Nhiễu nhãn từ nguồn này nằm trong nhóm tín hiệu **trọng số mẫu 0.7** (vuốt khảo sát), tức đã được đánh giá thấp hơn đánh giá sao (1.0) và nhật ký ăn uống (0.9). Ảnh hưởng của nó tới mô hình vì vậy bị hạn chế sẵn bởi cơ chế trọng số.

### Vuốt chỉ dùng ở đúng một chỗ bắt buộc

| Thời điểm | Vai trò | Phạm vi |
|---|---|---|
| **Phiên khảo sát lúc đăng ký** | Giải bài toán khởi đầu nguội. Người dùng vuốt một gói khoảng 30 món ngay sau khi khai báo hồ sơ, để hệ thống nhận diện nhanh gu ăn uống | **Bắt buộc** |
| **Sau đó** | Không còn màn hình vuốt nào. Hệ thống học từ hành vi thật: món giữ lại, món thay thế, món đã ăn, điểm đánh giá | — |

Sở dĩ không cần vuốt thêm: sau khảo sát, tín hiệu sở thích đã đến từ ba nguồn khác, và hai trong số đó **đáng tin hơn vuốt**.

| Nguồn tín hiệu | Trọng số nhãn |
|---|---|
| Đánh giá sao sau khi ăn | 1.0 |
| Món đã ăn thật (nhật ký) | 0.9 |
| *Vuốt khảo sát ban đầu* | *0.7* |
| Giữ hoặc thay thế món trong thực đơn | 0.6 |

Việc chống thực đơn một màu **không** giải quyết bằng cách cho vuốt thêm, mà bằng **cơ chế 70-30** ngay trong bước sinh thực đơn — xem `SYSTEM_ARCHITECTURE.md` mục 4.6.

---

## 3. Chiến lược khởi đầu nguội (Cold-start)

### Khởi đầu nguội là gì

**Khởi đầu nguội** (cold-start) là tình huống hệ thống khuyến nghị **chưa có dữ liệu lịch sử nào** về một người dùng, nên không có căn cứ để cá nhân hóa.

```
Người dùng đã dùng 3 tháng          Người dùng vừa đăng ký 5 phút trước
──────────────────────────          ───────────────────────────────────
· 200 lượt vuốt                     · 0 lượt vuốt
· 40 món đã ăn, có nhật ký          · 0 món đã ăn
· 25 lượt đánh giá sao              · 0 đánh giá
                                     
→ Mô hình biết rõ gu ăn uống        → Mô hình KHÔNG biết gì về khẩu vị
→ Gợi ý sát nhu cầu                 → Gợi ý dựa vào đâu?
                                            ↑
                                   đây chính là bài toán
                                   khởi đầu nguội
```

Gọi là "nguội" vì hệ thống khởi động từ con số không, chưa có dữ liệu nào để "hâm nóng". Đây là **hạn chế cố hữu** của mọi hệ khuyến nghị dựa trên học máy: mô hình cần lịch sử để học, mà người dùng mới thì chưa có lịch sử.

**Cách đề tài giải quyết:** thay vì chờ người dùng tích lũy dữ liệu một cách tự nhiên (mất hàng tuần), hệ thống **chủ động thu thập ngay** bằng một phiên khảo sát khẩu vị — cho người dùng vuốt khoảng 30 món ăn ngay sau khi đăng ký. Chỉ mất 2–3 phút nhưng đủ dựng được hồ sơ sở thích ban đầu.

> Trong giao diện ứng dụng nên gọi là **"khảo sát khẩu vị"** cho thân thiện với người dùng. Trong báo cáo giữ nguyên thuật ngữ **"khởi đầu nguội (cold-start)"** vì đây là thuật ngữ chuẩn, trích dẫn được.

### Ba giai đoạn

Hệ thống hoạt động theo **ba giai đoạn** tương ứng với độ trưởng thành dữ liệu của từng người dùng.

### Giai đoạn 0 — Vừa đăng ký, chưa có tín hiệu nào

Người dùng khai báo hồ sơ sức khỏe: giới tính, ngày sinh, chiều cao, cân nặng, mức vận động, mục tiêu, bệnh lý và dị ứng.

Từ đây hệ thống **đã tính được hạn mức dinh dưỡng** (BMI, BMR, TDEE) và **đã lọc được món an toàn** (ràng buộc cứng). Nhưng chưa biết gì về khẩu vị.

### Giai đoạn 1 — Sau phiên khảo sát khẩu vị (khoảng 30 tín hiệu)

Hệ thống đưa ra một **tập món thăm dò** được chọn có chủ đích: phủ đều các nhóm món, phương pháp chế biến và khẩu vị khác nhau, chứ không chọn ngẫu nhiên. Mục tiêu là mỗi lần vuốt thu được lượng thông tin lớn nhất.

Từ kết quả vuốt, hệ thống dựng **hồ sơ sở thích của người dùng dưới dạng vector trọng số** — trung bình có trọng số của các vector đặc trưng món ăn mà họ đã đánh giá. Món được chấm điểm bằng **độ tương đồng cosin** giữa vector sở thích và vector món.

Ở giai đoạn này hệ thống đã trả lời được câu hỏi *"người dùng này thuộc nhóm ăn uống nào"* — thích món nước hay món khô, ăn cay được hay không, thiên về đạm hay tinh bột, chuộng món chiên rán hay hấp luộc.

### Giai đoạn 2 — Sau một thời gian sử dụng (đủ tín hiệu tích lũy)

Khi người dùng đã ăn thật, ghi nhật ký và đánh giá món, hệ thống chuyển sang **mô hình học máy có giám sát**, huấn luyện trên toàn bộ tín hiệu tích lũy: vuốt khảo sát ban đầu, món giữ lại hoặc bị thay thế trong thực đơn, món đã ăn thật, và điểm đánh giá sau khi ăn.

Chuyển tiếp giữa hai giai đoạn là **chuyển dần**, không nhảy đột ngột:

```text
score = α · score_học_máy  +  (1 − α) · score_tương_đồng_nội_dung

α tăng dần từ 0 → 1 theo số tín hiệu người dùng tích lũy được
```

---

## 4. Vòng lặp phản hồi

```text
Khai báo hồ sơ sức khỏe
        ↓
Tính hạn mức năng lượng và dinh dưỡng  (BMI → BMR → TDEE)
        ↓
Vuốt thăm dò onboarding  ─────────────┐
        ↓                             │
Dựng hồ sơ sở thích ban đầu           │  Giai đoạn khởi đầu nguội
        ↓                             │
Lọc bỏ món vi phạm ràng buộc cứng  ───┘
        ↓
Chấm điểm mức độ phù hợp từng món
        ↓
Chọn tổ hợp món thỏa ràng buộc dinh dưỡng  →  THỰC ĐƠN
        ↓
Người dùng giữ / thay thế món trong thực đơn
        ↓
Người dùng ăn và ghi nhật ký
        ↓
Người dùng đánh giá món sau khi ăn
        ↓
Tích lũy dữ liệu phản hồi
        ↓
Huấn luyện lại mô hình học máy
        ↓
Thực đơn cá nhân hóa tốt hơn  ──► (quay lại bước chấm điểm)
```

---

## 5. Mục tiêu dự án

### 5.1 Khía cạnh phần mềm

- Ứng dụng di động (Flutter, nền tảng Android)
- Dịch vụ phía máy chủ (ASP.NET Core Web API)
- Cơ sở dữ liệu quan hệ (MySQL)
- Quản lý người dùng và hồ sơ sức khỏe
- Quản lý món ăn và dữ liệu dinh dưỡng
- Sinh thực đơn hằng ngày
- Khảo sát khẩu vị ban đầu bằng cơ chế vuốt
- Nhật ký ăn uống
- Thu thập đánh giá sau khi ăn
- Theo dõi tiến trình sức khỏe

### 5.2 Khía cạnh Machine Learning

| Hạng mục | Nội dung |
|---|---|
| **Thu thập dữ liệu** | Xây dựng tập dữ liệu 300–500 món ăn Việt Nam có đầy đủ thông tin dinh dưỡng |
| **Tiền xử lý** | Làm sạch, xử lý dữ liệu khuyết, chuẩn hóa min-max hoặc z-score, mã hóa one-hot |
| **Trích chọn đặc trưng** | Biểu diễn món ăn thành vector: thành phần dinh dưỡng, nhóm thực phẩm, phương pháp chế biến, khẩu vị |
| **Hồ sơ sở thích** | Vector trọng số tổng hợp từ lịch sử tương tác của người dùng |
| **Thống nhất nhãn** | Quy đổi 6 nguồn tín hiệu khác nhau về một thang điểm ưa thích chung |
| **Huấn luyện** | Học có giám sát: hồi quy Logistic, Rừng ngẫu nhiên, Gradient Boosting |
| **Đánh giá** | Precision@K, Recall@K, NDCG, MAE, RMSE; kiểm định chéo k-fold |
| **Tối ưu tổ hợp** | Chọn tập món thỏa ràng buộc dinh dưỡng (bài toán cái túi, giải bằng tham lam + tìm kiếm cục bộ) |
| **So sánh baseline** | Đối chiếu với phương án chỉ dùng quy tắc dinh dưỡng để chứng minh đóng góp của học máy |
| **Học liên tục** | Huấn luyện lại định kỳ từ dữ liệu phản hồi tích lũy |

---

## 6. Phạm vi — những gì KHÔNG làm

Ghi rõ để tránh mở rộng phạm vi ngoài tầm của một đồ án tốt nghiệp:

| Không làm | Lý do |
|---|---|
| **Lọc cộng tác (Collaborative Filtering)** | Số người dùng thử nghiệm quá ít, ma trận người dùng–món ăn quá thưa. Xếp vào hướng phát triển tương lai |
| **Học sâu / mạng nơ-ron** | Dữ liệu không đủ lớn; mô hình cây quyết định phù hợp hơn và giải thích được |
| **Học tăng cường** | Hướng phát triển tương lai |
| **Nhận diện món ăn từ ảnh** | Hướng phát triển tương lai |
| **Kết nối thiết bị đeo** | Hướng phát triển tương lai |
