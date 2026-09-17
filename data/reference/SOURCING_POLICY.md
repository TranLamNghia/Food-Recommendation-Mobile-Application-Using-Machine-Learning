# Quy tắc chọn nguồn số liệu dinh dưỡng

Tài liệu này trả lời câu hỏi mà hội đồng chắc chắn sẽ hỏi: **số liệu này lấy
ở đâu ra, và vì sao tin được?**

---

## 1. Nguồn chính — Bảng thành phần thực phẩm Việt Nam 2007

Viện Dinh dưỡng Quốc gia, Bộ Y tế. 526 thực phẩm, 14 nhóm, 86 chất dinh
dưỡng, mỗi mục một trang.

Đây là nguồn ưu tiên tuyệt đối vì ba lý do:

- Là số liệu của **cơ quan có thẩm quyền quốc gia** về dinh dưỡng.
- Phân tích trên **đúng giống loài, đúng cách chế biến của Việt Nam** — thịt
  lợn nuôi ở Việt Nam khác thịt lợn Hoa Kỳ, rau muống không có trong bảng
  nào khác.
- Trích dẫn được, và hội đồng nhận ra ngay.

Đã trích toàn bộ ra `fct2007.json` bằng `tools/extract_fct.py`.

### Độ phủ thực tế

| Chất | Độ phủ | |
|---|---|---|
| Năng lượng, glucid | 100 % | |
| Protein | 99,8 % | |
| Celluloza | 96,2 % | |
| Calci | 91,1 % | |
| Lipid | 85,7 % | |
| Cholesterol, sắt, vitamin C | ~81 % | |
| **Natri** | **47,3 %** | quy tắc tăng huyết áp |
| **Kẽm** | **44,3 %** | |
| **Đường** | **40,1 %** | quy tắc đái tháo đường |
| **Purin** | **15,6 %** | quy tắc gút |

Nói cách khác: **mọi thứ mô hình học máy cần thì bảng gốc phủ gần như trọn
vẹn**; chỗ thủng nằm ở các chất phục vụ **bộ quy tắc an toàn F1**.

Đây là phân biệt quan trọng. Vector đặc trưng của mô hình gồm năng lượng, ba
chất sinh năng lượng, nhóm món, cách chế biến, mức cay và nhãn khẩu vị — tất
cả đều có đủ. Mô hình khuyến nghị **không bị chặn** bởi các lỗ hổng trên.
Cái bị chặn là việc lọc an toàn cho người có bệnh lý, và đó là vấn đề khác,
hẹp hơn nhưng nghiêm trọng hơn.

---

## 2. Nguồn bổ khuyết — USDA FoodData Central

Chỉ dùng để lấp chỗ trống, theo quy tắc chặt bên dưới.

### Quy tắc vay số liệu

> **Không bao giờ vay chất sinh năng lượng.**
> Năng lượng, protein, lipid, glucid phải cùng đến từ một nguồn cho một
> nguyên liệu.

Lý do: hai bảng không đo cùng một mẫu vật. Đối chiếu ba nguyên liệu cho thấy
chênh lệch không nhỏ:

| Nguyên liệu | FCT 2007 | USDA SR Legacy |
|---|---|---|
| Bánh phở chín | 143 kcal · Na 31 mg | 108 kcal · Na 19 mg |
| Tôm | 58 kcal · đạm 11,7 g | 85 kcal · đạm 20,1 g |
| Cua | 87 kcal · đạm 12,3 g · Na 453 mg | 87 kcal · đạm 18,1 g · Na 293 mg |

Lấy đạm từ bảng này và năng lượng từ bảng kia sẽ tạo ra một nguyên liệu
**không tồn tại trên đời**, và phép đối chiếu Atwater sẽ sai — mà đó lại là
phép kiểm duy nhất bắt được lỗi số liệu.

Được phép vay các chất ngoại vi: **natri, đường, cholesterol, kẽm, sắt,
calci, vitamin C**. Đây là thông lệ "borrowed values" mà FAO/INFOODS chấp
nhận, với điều kiện bắt buộc là **ghi nguồn cho từng trường**, không phải
ghi nguồn cho cả mục.

### Lọc loại dữ liệu

Chỉ nhận `dataType` là `SR Legacy` hoặc `Foundation` — số liệu phân tích của
chính USDA. **Không dùng `Branded`**: đó là dữ liệu doanh nghiệp tự khai cho
sản phẩm đóng gói, không truy nguồn phân tích được.

### Bẫy đơn vị năng lượng

USDA trả về năng lượng ở **cả hai đơn vị** KCAL và KJ dưới cùng một tên chất
`Energy`. Lấy nhầm KJ thì con số lớn gấp 4,18 lần mà vẫn trông hợp lý —
"bánh phở 454" đọc qua không thấy sai. Bắt buộc lọc theo `unitName == "KCAL"`.

### Khóa API

`DEMO_KEY` chỉ cho khoảng 30 lượt mỗi giờ, không đủ để chạy hàng trăm nguyên
liệu. Đăng ký khóa miễn phí tại <https://api.data.gov/signup/> (tức thì,
1.000 lượt/giờ), rồi đặt vào biến môi trường `USDA_API_KEY`. Không commit
khóa vào repo — `.gitignore` đã chặn `.env`.

---

## 3. Purin: không lấy được từ đâu cả

Quy tắc ràng buộc cho người bệnh gút dựa trên cột `purine_mg`. Nhưng:

- Bảng thành phần Việt Nam 2007 chỉ có purin ở **15,6 %** số mục.
- **USDA FoodData Central không công bố purin**, đã kiểm chứng trực tiếp
  trên danh sách 70 chất của một mục.

Nghĩa là không có cách nào điền đủ cột này từ hai nguồn uy tín đang dùng.
Để nguyên thì quy tắc gút **lặng lẽ không bao giờ kích hoạt** — người bệnh
gút vẫn nhận món nội tạng và hải sản, mà hệ thống tưởng đã lọc. Đây là loại
hỏng nguy hiểm nhất: hỏng mà không báo.

### Hướng xử lý đề xuất

Đổi quy tắc gút từ `nutrient_limit` sang `exclude_tag`, dùng đúng cơ chế
nhãn mà lược đồ đã có sẵn:

```sql
-- Thay vì: purine_mg > 150 thì loại
-- Dùng:    món mang nhãn high_purine thì loại
INSERT INTO tags (code, name_vi, tag_type, description) VALUES
  ('high_purine', 'Giàu purin', 'nutrition',
   'Nội tạng, hải sản vỏ cứng, thịt đỏ đậm, nước dùng ninh xương');
```

Gán nhãn theo **nhóm thực phẩm** thay vì theo ngưỡng số:

| Gắn `high_purine` | Ví dụ |
|---|---|
| Nội tạng động vật | gan, lòng, tim, cật |
| Hải sản vỏ cứng và cá nhỏ nguyên con | tôm, cua, ghẹ, cá cơm, cá mòi |
| Nước dùng ninh xương lâu | nước phở, nước lẩu |
| Thịt đỏ phần đậm | thịt bò bắp, thịt dê |

Cách này kém chính xác hơn ngưỡng số, nhưng **chạy được** và **phủ đúng
nhóm thực phẩm mà y văn cảnh báo**. Ghi vào phần hạn chế của báo cáo: ràng
buộc gút ở mức phân loại nhóm chứ chưa ở mức định lượng.

---

## 4. Ghi nguồn ở cấp trường, không ở cấp mục

Mỗi giá trị đi kèm nguồn của riêng nó. Khi một nguyên liệu lấy năng lượng và
ba chất chính từ bảng Việt Nam nhưng vay natri từ USDA, `note` phải nói rõ
điều đó. Ghi chung một dòng "nguồn: bảng Việt Nam" cho cả mục là ghi sai.

---

## 5. Nguồn không được dùng

Ứng dụng đếm calo, trang tin sức khỏe, blog nấu ăn, và các bảng dinh dưỡng
không nêu phương pháp phân tích. Phần lớn là dữ liệu người dùng tự nhập,
chép vòng quanh lẫn nhau, không truy về được một phép đo nào. Hội đồng hỏi
"con số này ai đo" thì không có câu trả lời.
