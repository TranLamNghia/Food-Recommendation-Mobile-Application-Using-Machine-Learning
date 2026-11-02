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

## Nạp vào cơ sở dữ liệu

```bash
# Lần đầu: chỉnh lược đồ cho khớp tập dữ liệu
mysql -u <user> -p <db> < db/migrations/001_dataset_readiness.sql
mysql -u <user> -p <db> < db/migrations/002_food_name_unique.sql

# Sinh SQL rồi đọc lại trước khi chạy
python tools/load_foods.py
mysql -u <user> -p <db> < db/seed_foods.sql

# Hoặc nạp thẳng, cần MYSQL_* trong .env
python tools/load_foods.py --apply
```

`db/seed_foods.sql` **không nằm trong repo** — nó sinh ra từ chính các tệp
CSV ở đây, nên commit cả bản sinh ra chỉ tạo diff hàng trăm KB mỗi lần sửa
một món, và hai bản có thể lệch nhau lúc nào không biết. Cần thì chạy lại
`python tools/load_foods.py`.

Trình nạp **bỏ qua** dòng còn thiếu cột `NOT NULL` và báo rõ đã bỏ những gì.
Nạp lại nhiều lần cho cùng một kết quả nhờ `UNIQUE (name)` ở migration 002.

---

## Quy ước từng cột

### Bắt buộc

| Cột | Quy ước |
|---|---|
| `name` | Tên tiếng Việt có dấu, viết hoa chữ đầu. Ghi tên món cụ thể: "Bún bò Huế" chứ không phải "Bún". |
| `category` | Phải trùng tên tệp. |
| `dish_role` | Xem bảng vai trò bên dưới. |
| `spice_level` | 0 không cay · 1 cay nhẹ · 2 cay vừa · 3 cay nhiều |
| `serving_size_g` | Khối lượng **một suất ăn thực tế**, không phải 100 g. Xem mục dưới. |
| `calories_kcal` `protein_g` `carbs_g` `fat_g` | Tính cho **trọn một suất** như đã khai ở `serving_size_g`. |

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

> **Lưu ý về schema.** Lược đồ gốc chỉ có 5 vai trò, gộp *món mặn* và *món
> rau* chung vào `side` — bữa tối vì thế có thể ra hai món rau và không có
> đạm nào. Bảy giá trị ở trên chỉ dùng được sau khi chạy
> `db/migrations/001_dataset_readiness.sql`.

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
   nêu trong `note` vì sao phải dùng nguồn này.

Không lấy số từ ứng dụng đếm calo hay trang tin sức khỏe: phần lớn là dữ
liệu người dùng tự nhập, không truy nguồn được, và hội đồng sẽ hỏi.

---

## Trạng thái hiện tại

**318 món, cả 318 đều cộng dồn từ công thức.** Không còn món nào chuyển từ
dữ liệu giả của giao diện. Đã vượt mốc 300 món của đề cương.

| Nhóm | Số món | Công thức |
|---|---|---|
| `mon_nuoc` | 73 | 73 |
| `mon_luoc_hap` | 59 | 59 |
| `mon_canh` | 37 | 37 |
| `mon_xao` | 28 | 28 |
| `trang_mieng` | 25 | 25 |
| `mon_kho` | 25 | 25 |
| `do_uong` | 21 | 21 |
| `com` | 16 | 16 |
| `mon_chien` | 16 | 16 |
| `mon_nuong` | 12 | 12 |
| `mon_cuon` | 3 | 3 |
| `mon_goi` | 3 | 3 |

**13 món gần nhất là món chay**, thêm vì `tools/check_f1.py` đo được rằng sau
Bộ lọc F1, người ăn chay chỉ còn **1 món `side_protein` và 0 món `soup`** —
cả 31 món canh khi đó đều có thịt, cá hoặc nước mắm, nên Bước 4 không dựng nổi
một ngày. Một nửa số món mới nêm **muối** và lấy đạm từ **nấm**, không dùng
đậu nành ở đâu cả: đậu phụ và nước tương đều LÀ đậu nành, nên nếu món chay nào
cũng dựa vào chúng thì người vừa ăn chay vừa dị ứng đậu nành lại về 0 món.

Mỗi món có một mục trong `recipes/<nhóm>.json` ghi mã nguyên liệu của Bảng
thành phần 2007 kèm số gam — đó là phần truy xuất nguồn, và là thứ dựng lại
được toàn bộ CSV bằng `tools/compose_dishes.py`.

Vai trò món: `main` 89 · `side_protein` 78 · `side_veg` 52 · `soup` 37 ·
`dessert` 25 · `drink` 21 · `snack` 16.

### Độ phủ từng cột

| Cột | Phủ | |
|---|---|---|
| `serving_size_g` `calories_kcal` `protein_g` `carbs_g` `fat_g` | 318/318 | 100 % |
| `fiber_g` `cholesterol_mg` `calcium_mg` `iron_mg` `vitamin_a_mcg` | 318/318 | 100 % |
| `vitamin_c_mg` | 314/318 | 98,7 % |
| `sodium_mg` | 303/318 | 95,3 % |
| `zinc_mg` | 298/318 | 93,7 % |
| `sugar_g` | 230/318 | 72,3 % |
| `purine_mg` | 70/318 | 22,0 % |

`vitamin_a_mcg` phủ kín được là nhờ **quy đổi RAE**, không phải lấy thẳng cột
retinol của bảng gốc. Retinol bằng 0 ở mọi thực phẩm thực vật, nên lấy thẳng
thì cà rốt và bí đỏ đều ra 0. Xem `tools/extract_fct.py`, mục `RAE_FACTORS`.

### Hai hạn chế đã biết

**Purin phủ 22 %.** Bảng Việt Nam chỉ có purin ở 82/526 mục (15,6 %) và USDA
không công bố chất này, nên quy tắc định lượng cho người bệnh gút chỉ áp được
lên 70/318 món. Nhãn `Giàu purin` là tuyến bảo vệ chính — hiện gắn cho 91 món
(nội tạng và tiết, hải sản vỏ cứng, cá) và được một quy tắc `exclude_tag`
dùng. Đây là hạn chế cấu trúc cần nêu trong báo cáo, không phải thiếu sót
điền dữ liệu.

**Phép đối chiếu Atwater không bắt được lỗi công thức.** Với món cộng dồn từ
nguyên liệu, số liệu vốn đã tự nhất quán nên phép này luôn xanh. Ghi nhầm
thịt bò 60 g thành 160 g thì mọi phép kiểm vẫn qua. Chỉ người biết nấu ăn rà
lại `note` mới phát hiện được.
