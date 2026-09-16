# Tập dữ liệu món ăn Việt Nam

Nguồn dữ liệu gốc của hệ thống, nhập bằng tay vào CSV rồi nạp vào bảng
`foods` và `food_nutrition`. Mục tiêu theo đề cương: **300 – 500 món**, mỗi
món đủ năng lượng và ba chất sinh năng lượng.

Mỗi tệp là một danh mục, trùng mã với bảng `food_categories`:

| Tệp | Danh mục |
|---|---|
| `mon_nuoc.csv` | Phở, bún, miến, hủ tiếu |
| `com.csv` | Cơm trắng, cơm tấm, cơm chiên, xôi |
| `mon_kho.csv` | Thịt kho, cá kho |
| `mon_xao.csv` | Rau xào, thịt xào |
| `mon_canh.csv` | Canh chua, canh rau |
| `mon_chien.csv` | Nem rán, gà rán, cá chiên |
| `mon_nuong.csv` | Thịt nướng, cá nướng |
| `mon_luoc_hap.csv` | Rau luộc, thịt luộc, cá hấp |
| `mon_cuon.csv` | Gỏi cuốn, bánh cuốn |
| `mon_goi.csv` | Gỏi, nộm, salad |
| `trang_mieng.csv` | Chè, bánh ngọt, trái cây |
| `do_uong.csv` | Nước ép, sữa, trà |

Chia theo danh mục để nhiều người nhập song song mà không giẫm chân nhau khi
gộp nhánh Git, và để nhìn ra ngay nhóm nào đang thiếu món.

---

## Trước khi commit

```bash
python tools/validate_foods.py
```

Không được commit khi còn **LỖI**. Bộ kiểm tra cũng in độ phủ từng cột và số
món còn thiếu so với mốc 300.

---

## Quy ước từng cột

### Bắt buộc

| Cột | Quy ước |
|---|---|
| `name` | Tên tiếng Việt có dấu, viết hoa chữ đầu. Ghi tên món cụ thể: "Bún bò Huế" chứ không phải "Bún". |
| `category` | Phải trùng tên tệp. |
| `dish_role` | Xem bảng vai trò bên dưới. |
| `cooking_method` | `luoc` `hap` `xao` `chien` `nuong` `kho` `nau_canh` `tron` `song` `khac` |
| `spice_level` | 0 không cay · 1 cay nhẹ · 2 cay vừa · 3 cay nhiều |
| `suitable_meals` | Ngăn bằng `\|`, ví dụ `breakfast\|lunch\|dinner`. Giá trị: `breakfast` `lunch` `dinner` `snack` |
| `serving_size_g` | Khối lượng **một suất ăn thực tế**, không phải 100 g. Xem mục dưới. |
| `calories_kcal` `protein_g` `carbs_g` `fat_g` | Tính cho **trọn một suất** như đã khai ở `serving_size_g`. |
| `data_source` | Tên nguồn, ví dụ `Bảng thành phần thực phẩm Việt Nam 2007` hoặc `USDA FoodData Central`. |

### Nên có — bộ quy tắc F1 cần

Để trống thì quy tắc tương ứng **lặng lẽ không bao giờ kích hoạt**: người
tăng huyết áp vẫn nhận món mặn mà hệ thống tưởng đã lọc. Ưu tiên điền cho
món có khả năng vi phạm.

| Cột | Phục vụ ràng buộc |
|---|---|
| `sodium_mg` | Tăng huyết áp, bệnh thận |
| `sugar_g` | Đái tháo đường |
| `cholesterol_mg` | Mỡ máu |
| `fiber_g` | Khuyến nghị chất xơ |

### Tùy chọn

`purine_mg` (gút) · `calcium_mg` · `iron_mg` · `zinc_mg` · `vitamin_a_mcg` ·
`vitamin_c_mg`. Chỉ điền khi nguồn có sẵn, đừng ước đoán.

### Nhãn và ghi chú

| Cột | Quy ước |
|---|---|
| `tags` | Ngăn bằng `\|`. Xem danh sách nhãn bên dưới. |
| `source_url` | Đường dẫn tới đúng trang chứa số liệu, không phải trang chủ. |
| `note` | Ghi chú tự do: điều còn ngờ, cách quy đổi đã dùng. |

---

## Vai trò món trong bữa

| Mã | Nghĩa | Ví dụ |
|---|---|---|
| `main` | Món chính, phần tinh bột chính của bữa | Cơm trắng, phở, bún chả |
| `side_protein` | Món mặn — nguồn đạm | Thịt kho, cá chiên, trứng rán |
| `side_veg` | Món rau | Rau muống luộc, nộm |
| `soup` | Món canh | Canh chua, canh bí đao |
| `snack` | Món phụ, ăn vặt | Gỏi cuốn, bánh mì |
| `dessert` | Tráng miệng | Chè, trái cây |
| `drink` | Đồ uống | Nước cam, sữa đậu nành |

> **Lưu ý về schema.** Cột `foods.dish_role` hiện chỉ có 5 giá trị
> (`main` `side` `soup` `dessert` `drink`), gộp *món mặn* và *món rau* chung
> vào `side`. Bộ sinh thực đơn cần tách hai thứ này, nếu không bữa tối có
> thể ra hai món rau và không có đạm nào. CSV dùng vốn từ đã tách; cần chạy
> `ALTER TABLE` trước khi nạp:
>
> ```sql
> ALTER TABLE foods MODIFY dish_role
>   ENUM('main','side_protein','side_veg','soup','snack','dessert','drink')
>   NOT NULL DEFAULT 'main';
> ```

---

## Nhãn hợp lệ

**Dị nguyên** — bắt buộc điền đúng, đây là ràng buộc an toàn:
`contains_seafood` `contains_peanut` `contains_egg` `contains_dairy`
`contains_gluten` `contains_soy`

**Chế độ ăn:** `vegetarian` `vegan`

**Dinh dưỡng:** `low_sodium` `low_sugar` `high_protein` `high_fiber`

**Khẩu vị** — thành phần vector đặc trưng của mô hình:
`salty` `sweet` `sour` `fatty` `light`

---

## Khẩu phần: ghi theo suất, không theo 100 g

Đây là chỗ dễ sai nhất.

Bảng thành phần thực phẩm công bố theo **100 g nguyên liệu**. Nhưng hệ thống
cần dinh dưỡng của **một suất ăn thật** — người dùng ăn "một tô phở", không
ăn "100 g phở". Thuật toán cộng dồn năng lượng theo suất để so với hạn mức,
nên nhập nhầm sang 100 g sẽ làm toàn bộ thực đơn sai lệch mà không có dấu
hiệu gì.

Quy đổi: `giá trị mỗi suất = giá trị mỗi 100 g × serving_size_g / 100`

Khẩu phần tham khảo: tô phở 500 g · đĩa cơm tấm 400 g · bát cơm trắng 200 g ·
bát canh 250 g · đĩa rau xào 150 g · cái gỏi cuốn 60 g.

Ghi vào `note` cách bạn đã quy đổi nếu nó không hiển nhiên.

---

## Phép đối chiếu Atwater

Bộ kiểm tra tự động so:

```
calories_kcal  ≈  4 × protein_g  +  4 × carbs_g  +  9 × fat_g
```

Sai lệch quá 12 % là báo lỗi. Phép này bắt gần như mọi lỗi chép số — nhầm
cột, lệch một chữ số thập phân, lẫn đơn vị — mà không cần biết món đó thật
sự bao nhiêu calo.

Lệch dưới ngưỡng là bình thường: chất xơ sinh ít năng lượng hơn bột đường,
rượu sinh 7 kcal/g, và số liệu công bố thường đã làm tròn.

---

## Thứ tự ưu tiên nguồn

1. **Bảng thành phần thực phẩm Việt Nam 2007** — Viện Dinh dưỡng Quốc gia.
   Ưu tiên cao nhất vì đúng nguyên liệu và cách chế biến Việt Nam.
   <https://www.fao.org/fileadmin/templates/food_composition/documents/pdf/VTN_FCT_2007.pdf>
2. **USDA FoodData Central** — dùng cho món không có trong bảng Việt Nam, và
   để bổ khuyết natri, đường, cholesterol. <https://fdc.nal.usda.gov/>
3. **Nguồn khác** — chỉ khi hai nguồn trên không có. Bắt buộc ghi
   `source_url` và nêu trong `note` vì sao phải dùng nguồn này.

Không lấy số từ ứng dụng đếm calo hay trang tin sức khỏe: phần lớn là dữ
liệu người dùng tự nhập, không truy nguồn được, và hội đồng sẽ hỏi.

---

## Trạng thái hiện tại

30 món đầu tiên được chuyển từ bộ dữ liệu giả của giao diện, **số liệu chưa
đối chiếu nguồn** — cột `data_source` và `serving_size_g` còn trống nên bộ
kiểm tra đang báo lỗi. Đây là trạng thái đúng: chúng là chỗ giữ tên món và
phân loại, không phải dữ liệu đã nghiệm thu. Cần tra nguồn và điền đủ trước
khi dùng cho thực nghiệm.
