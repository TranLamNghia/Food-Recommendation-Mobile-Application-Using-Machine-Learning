# Context dự án tốt nghiệp — Hệ thống gợi ý món ăn cá nhân hóa bằng Machine Learning

## 1. Tổng quan dự án

Đây là đồ án tốt nghiệp đại học với mục tiêu xây dựng một **ứng dụng di động hỗ trợ gợi ý món ăn cá nhân hóa** dựa trên thông tin cá nhân, tình trạng sức khỏe, thông tin dinh dưỡng của món ăn và đặc biệt là lịch sử tương tác của người dùng.

Ý tưởng cốt lõi:

> Hệ thống không chỉ dựa vào các luật cố định để gợi ý món ăn, mà sẽ thu thập phản hồi của người dùng, sử dụng dữ liệu đó để huấn luyện mô hình Machine Learning và dần cá nhân hóa các món ăn được đề xuất.

Cơ chế tương tác ban đầu:
- Vuốt phải → Thích
- Vuốt trái → Không thích
- Vuốt xuống → Không biết / Chưa có ý kiến
- Vuốt lên → Bình thường / Không có cảm xúc đặc biệt

Cơ chế Feedback loop:
- Gợi ý món ăn
- Người dùng đánh giá
- Hệ thống ghi nhận vào database
- Huấn luyện lại mô hình bằng dataset
- Gợi ý món ăn cá nhân hóa tốt hơn


Mục tiêu cuối cùng là tạo ra một vòng lặp:

```text
Thông tin người dùng
        ↓
Lọc các món có khả năng phù hợp
        ↓
Người dùng tương tác với món ăn
        ↓
Thu thập dữ liệu sở thích
        ↓
Machine Learning
        ↓
Gợi ý món ăn cá nhân hóa
        ↓
Người dùng sử dụng và đánh giá
        ↓
Thu thập phản hồi mới
        ↓
Cập nhật dữ liệu cho Machine Learning
        ↓
Gợi ý tốt hơn
```

## 2. Mục tiêu dự án

Hệ thống hướng tới:

> Với người dùng này, dựa trên thông tin sức khỏe và những món họ từng thích/không thích, món ăn nào có khả năng phù hợp hoặc được họ yêu thích?

---
### 2.1 Khía cạnh phần mềm
- Ứng dụng di động
- Backend
- Cơ sở dữ liệu
- API
- Quản lý người dùng
- Quản lý món ăn
- Gợi ý món ăn
- Thu thập tương tác
- Thu thập đánh giá
- Lập thực đơn

### 2.2 Khía cạnh Machine Learning
- Thu thập dữ liệu
- Tiền xử lý dữ liệu
- Xây dựng tập dữ liệu
- Huấn luyện mô hình
- Đánh giá mô hình
- Dự đoán
- Xếp hạng món ăn
- Tích hợp mô hình vào hệ thống
- Sử dụng dữ liệu phản hồi để cải thiện mô hình