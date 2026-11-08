# Phần học máy — nhiệm vụ, mô hình và quy trình đánh giá

Tài liệu này mô tả chi tiết phần học máy của hệ thống: những gì phải xây, mô
hình nào, dữ liệu huấn luyện lấy từ đâu, và đánh giá bằng cách nào.

`SYSTEM_ARCHITECTURE.md` mô tả thuật toán khuyến nghị bốn bước trong bối cảnh
toàn hệ thống; tài liệu này đi sâu vào riêng phần học máy và phần triển khai.
`DATABASE_DESIGN.md` mô tả bốn bảng `ml_*` ở mức từng cột.

---

## 1. Điều cần hiểu trước: đây không phải một mô hình

Sai lầm phổ biến khi đọc đề cương là hình dung một mô hình duy nhất nhận hồ sơ
người dùng rồi trả về thực đơn. Hệ thống không hoạt động như vậy. Có **bốn
giai đoạn** theo độ trưởng thành dữ liệu, và một người dùng mới sẽ đi lần lượt
qua cả bốn.

```
   cold  ─────────►  content  ─────────►  hybrid  ─────────►  ml
    │                  │                    │                 │
 chưa có           ~30 lượt vuốt         pha trộn          đủ tín hiệu
 tín hiệu          onboarding            theo α            (n > n_max)
    │                  │                    │                 │
 luật               Rocchio            α·ML + (1−α)·cos    mô hình toàn cục
```

Giai đoạn hiện tại của mỗi người được ghi ở `user_preference_profiles.stage`.

| Giai đoạn | `stage` | Cách chấm điểm | `meal_plans.generation_source` |
|---|---|---|---|
| 0 | `cold` | Luật: lọc bệnh lý, xếp theo `popularity_score` và độ khớp dinh dưỡng | `rule_based` |
| 1 | `content` | Tương đồng cosin với hồ sơ Rocchio | `content_based` |
| Chuyển tiếp | `hybrid` | `α · điểm_ML + (1−α) · điểm_cosin` | `hybrid` |
| 2 | `ml` | Mô hình học có giám sát toàn cục | `ml` |

Cột `generation_source` không phải để trang trí: nó cho phép trả lời câu
*"thực đơn này do phương pháp nào sinh ra"* khi phân tích kết quả, và là cơ sở
để tách số liệu theo từng giai đoạn trong Chương 3.

---

## 2. Vector đặc trưng món ăn

Mọi giai đoạn đều dựa trên một biểu diễn chung: mỗi món ăn là một vector
**20 chiều**.

| Khối | Số chiều | Nội dung | Nguồn |
|---|---|---|---|
| Dinh dưỡng | 3 | Tỷ lệ đạm / bột đường / béo trên tổng năng lượng | đo được |
| Năng lượng | 1 | `kcal` chuẩn hóa min–max về `[0,1]` | đo được |
| Vị ngọt | 1 | `sugar_g / serving_size_g` chuẩn hóa min–max | **đo được** |
| Vị mặn | 1 | `sodium_mg` chuẩn hóa min–max | **đo được** |
| Chất xơ | 1 | `fiber_g` chuẩn hóa min–max | **đo được** |
| Mức cay | 1 | `spice_level / 3` | **người nhập đánh giá** |
| Nhóm món | 12 | Mã hóa one-hot theo `food_categories` | đo được |

#### Chiều vị ngọt: mẫu số phải là khối lượng suất, không phải lượng bột đường

Bản `v1` dùng `sugar_g / carbs_g`. Nó **vỡ ở món ít bột đường**, vì tỷ lệ nổ
khi mẫu số nhỏ. Đo trên 318 món thật, **46 món bị kẹp về đúng 1,000** — 14 %
danh mục đọc ra "ngọt tối đa":

```
  1.000  Trứng luộc           (0,6 g bột đường)   ← không ngọt
  1.000  Canh hẹ đậu phụ      (2,2 g)             ← canh mặn
  1.000  Canh măng nấu thịt bò
  1.000  Chuối sứ                                 ← ngọt thật
  1.000  Nước ép lựu                              ← ngọt thật
```

Khi trứng luộc và nước ép lựu không phân biệt được trên chiều này thì Rocchio
**không thể học được sở thích ngọt** — nó là một chiều đầy nhiễu, không phải
một chiều đặc trưng. Đây là lỗi **công thức**, không phải lỗi dữ liệu.

`v2` đổi mẫu số sang `serving_size_g`. Vẫn là **nồng độ** nên vẫn giữ nguyên
ý định ban đầu — khẩu vị là về *cấu trúc* món ăn, không về khối lượng, một
suất 400 g chứa 20 g đường không ngọt bằng một suất 100 g chứa 15 g — nhưng
mẫu số là khối lượng cả suất nên không bao giờ nhỏ bất thường:

```
          v1 (sugar/carb)      v2 (sugar/serving, chuẩn hóa)
  kẹp ở 1,000     46/318                1/318
  Nước ép lựu      1.000                1.000
  Chuối sứ         1.000                0.564
  Dưa hấu          1.000                0.374
  Cơm trắng        0.059                0.108
  Canh hẹ đậu phụ  1.000                0.099
  Trứng luộc       1.000                0.048
  Phở gà           0.002                0.002
```

Phép **suy giá trị khuyết** cũng phải đổi mẫu số theo, nếu không nó tạo tác
ngay trên chiều vừa sửa: khi còn chia cho `carbs_g`, cơm trắng (60 g bột
đường) bị suy ra một lượng đường lớn và đọc thành 0,201 trên thang ngọt dù
cơm không ngọt.

Đổi chiều đặc trưng thì **phải tăng `FEATURE_VERSION`** (v1 → v2), nếu không
một mô hình cũ sẽ được nạp lại với một vector khác và không ai biết. Lúc đổi
chưa thu tín hiệu nào nên không mất gì; sau khi thu dữ liệu thì phải tính lại
toàn bộ `user_preference_profiles`.

**Vì sao ngọt và mặn dùng số đo, còn cay dùng mức.** `sugar_g` và `sodium_mg`
có trong bảng thành phần thực phẩm, nên lấy thẳng số. Không nguồn nào công bố
capsaicin hay độ đắng, nên một cột `capsaicin_mg` sẽ là cột **không thể điền** —
và nếu điền tay thì đó là **độ chính xác giả**, tệ hơn một mức 0–3 trung thực.

**Thêm chiều đo được không tốn thêm bước nào của người dùng.** Hệ thống học
khẩu vị từ **lượt vuốt**, không hỏi *"bạn thích cay mức nào"*. Hai chiều mới
chỉ làm lượt vuốt giàu thông tin hơn: vector tự học ra *"người này tránh món
nhiều natri"* mà không cần thêm một câu hỏi nào.

**Vị chua và vị đắng không được biểu diễn.** Trước đây có nhóm nhãn
`tag_type = 'taste'` (`Chua`, `Mặn`, `Ngọt`, `Béo`, `Thanh đạm`) định gánh
phần này. Đã **bỏ toàn bộ nhóm đó**: khi đối chiếu với số đo thì nhãn gắn tay
mâu thuẫn với dữ liệu — món gắn `Mặn` trung bình 1041 mg natri (thấp nhất
805), món không gắn trung bình 959 mg nhưng **cao nhất tới 1378**. Và 0/20
quy tắc nào dùng tới một nhãn vị. Một nhãn vừa sai vừa không ai dùng thì bỏ
tốt hơn giữ.

### 2.1 Vì sao có chiều chất xơ

Ba chiều ngọt – mặn – xơ không phải để mô tả *vị*, mà để vector biểu diễn
được những **nhu cầu dinh dưỡng mà người dùng thật sự có**. Chất xơ là ví dụ
rõ nhất: "tôi muốn ăn nhiều chất xơ" là một nhu cầu phổ biến, và nếu chất xơ
không nằm trong vector thì sở thích đó **không biểu diễn được** — bộ gợi ý
chỉ bắt được nó gián tiếp qua nhóm món.

Đo trên 318 món thật, mô phỏng người dùng thích 10 món giàu xơ nhất rồi chấm
điểm cosin cho phần còn lại:

| Vector | Chất xơ trung bình của top-20 | Thu hẹp được |
|---|---|---|
| Cả danh mục (mốc dưới) | 1,75 g | — |
| **Không có** chiều xơ | 2,97 g | 41,8 % |
| **Có** chiều xơ | 3,50 g | 59,7 % |
| 20 món giàu xơ nhất (mốc trên) | 4,67 g | 100 % |

Lưu ý phạm vi: chiều này phục vụ sở thích **suy ra từ hành vi vuốt**. Một mục
tiêu do người dùng **tự khai** — "tôi cần 25 g xơ mỗi ngày" — là đại lượng
theo **ngày**, không phải thuộc tính của một món, nên nó không thuộc về phép
đo góc ở đây. Xem mục 2.2.

**Nhãn vị là phán đoán của người nhập, không phải suy diễn tự động.** Tôi đã
thử suy nhãn `Chua` từ nguyên liệu và kết luận là không làm được một cách
trung thực:

- Trong 46 nguyên liệu mà 60 công thức dùng, **chỉ có một** mang vị chua là cà
  chua. Các chất gây chua thật — mẻ, dấm bỗng, me — **không có trong bảng
  thành phần thực phẩm**.
- Lượng cà chua tách hai nhóm rất đẹp (có nhãn 50–60 g, không nhãn đúng 40 g),
  nhưng công thức và nhãn được viết trong **cùng một phiên làm việc**, nên
  ngưỡng đó chỉ phát hiện lại quy ước của chính người nhập — một vòng lặp tự
  quy chiếu khoác vẻ ngoài luật suy diễn.

Vì vậy nhãn vị được gán tay và **phải ghi rõ trong báo cáo là phán đoán**,
cùng cách đã ghi cho `spice_level` và cho mức hấp thu ở `rda_reference`.

Cài đặt hiện tại: `mobile/lib/data/recommender/food_vector.dart`.

### 2.1 Vì sao dùng **tỷ lệ** macro chứ không phải số gam

Một món 600 kcal và một món 300 kcal có cùng cấu trúc dinh dưỡng (ví dụ cùng
20% đạm) thì phải nằm gần nhau trong không gian đặc trưng, vì **khẩu vị của
người dùng là về cấu trúc, không về khối lượng**. Khối lượng do Bước 4 lo khi
ghép tổ hợp thỏa hạn mức. Dùng số gam thì hai món giống nhau về bản chất lại
cách xa nhau chỉ vì khẩu phần khác nhau.

### 2.2 Vì sao không có khối riêng cho phương pháp chế biến

Đề cương nêu vector gồm *"thành phần dinh dưỡng, nhóm thực phẩm, phương pháp
chế biến và khẩu vị"*. **Cả bốn thành phần vẫn còn** — phương pháp chế biến do
khối one-hot nhóm món gánh, vì 8 trong 12 mã nhóm *chính là* phương pháp chế
biến:

| | | | |
|---|---|---|---|
| `mon_chien` → chiên | `mon_nuong` → nướng | `mon_xao` → xào | `mon_kho` → kho |
| `mon_luoc_hap` → luộc, hấp | `mon_canh` → nấu canh | `mon_goi` → trộn, sống | `mon_nuoc` → nấu nước |

Bốn mã còn lại — `com`, `trang_mieng`, `do_uong`, `mon_cuon` — phân theo vai
trò hoặc dạng món chứ không theo cách tác động nhiệt.

Lý do gộp về một trục là **tính toàn vẹn dữ liệu**. Mì tôm nấu nước và mì tôm
xào khô là *hai món khác nhau với dinh dưỡng khác nhau*, không phải một món
với hai cách chế biến. Để hai trục độc lập thì không gì ngăn một dòng thuộc
nhóm `mon_nuoc` lại mang cách chế biến `xao` — dữ liệu tự mâu thuẫn mà không
ràng buộc nào bắt được.

### 2.2 Một nhu cầu dinh dưỡng đi qua ba tầng, không phải một

Dễ nhầm rằng mọi nhu cầu đều giải quyết ở cùng một chỗ. Thật ra hệ thống có
ba tầng và mỗi tầng trả lời một loại câu hỏi khác nhau:

| Tầng | Trả lời | Đơn vị | Chất xơ nằm ở đâu |
|---|---|---|---|
| **Bước 2** — lọc F1 theo `condition_rules` | "món này có bị cấm không" | mỗi món / mỗi ngày | **Không loại món nào.** Thích ăn nhiều xơ không phải bệnh lý — xem mục dưới về vì sao lọc cứng ở đây là sai |
| **Bước 3** — vector + Rocchio | "người này có hợp kiểu món này không" | mỗi món | **Có** — chiều `fiber_g`, và mục tiêu tự khai nhúng thẳng vào `p_u` |
| **Bước 4** — cái túi đa chiều | "cả ngày đã đủ chưa" | **mỗi ngày** | **Chưa làm** — Bước 4 hiện chỉ bám `kcal` và ba macro |

**Mục tiêu tự khai phải tác động ở CẢ BA tầng, không chỉ tầng cuối.** Bản
trước của mục này viết rằng "phép đo góc cosin không bao giờ trả lời được nó
— đó là việc của Bước 4". Câu đó **sai**, và đo được là sai. Nó trộn hai mệnh
đề khác nhau:

- cosin không **bảo đảm** được một tổng theo ngày — đúng;
- cosin không **giúp gì** cho một mục tiêu tự khai — sai.

Vector ưa thích `p_u` chỉ là một vector. Mục tiêu tự khai **nhúng thẳng vào
nó được** bằng cách cộng thêm vào đúng chiều tương ứng — đây vốn là cách
Rocchio hoạt động trong tìm tin: vector truy vấn khởi tạo được từ ý định rõ
ràng, không nhất thiết phải học hết từ phản hồi.

Đo trên **318 món** thật, dựng thực đơn 2000 kcal cho 12 hồ sơ khẩu vị **cố ý
không liên quan tới xơ** (thích món nước và món kho), mục tiêu 25 g/ngày:

| Đưa mục tiêu vào đâu | Xơ/ngày | Đạt mục tiêu | Số lần Bước 4 phải sửa | Điểm hợp khẩu vị |
|---|---|---|---|---|
| Không đâu cả | 22,0 g · 88 % | 4/12 | 0 | 0,7410 |
| **Chỉ nhúng vào `p_u`** | 26,6 g · 106 % | 12/12 | 0 | 0,7357 |
| **Chỉ sửa ở Bước 4** | 28,5 g · 114 % | 12/12 | **1,7** | **0,7174** |
| **Cả hai** | 26,6 g · 106 % | 12/12 | **0** | 0,7357 |

Đọc bảng này ra kết luận:

1. Nhúng vào `p_u` lấp hết khoảng cách, gần như **không tốn gì** về khẩu vị
   (0,7410 → 0,7357). Nói cosin vô dụng với mục tiêu tự khai là sai.
2. **Nhưng đạt được không có nghĩa là bảo đảm được.** Đúng cấu hình này, trên
   danh mục 305 món trước đó, cho **0/12** — cùng một cơ chế, chỉ đổi danh
   mục, kết quả nhảy từ 0/12 lên 12/12. Vector chỉ **xếp hạng**; không có gì
   trong phép đo góc buộc tổng cả ngày phải đạt ngưỡng. Hai số đo trái ngược
   nhau của cùng một cơ chế chính là bằng chứng rằng nó không phải bảo đảm.
3. **Để tất cả cho Bước 4 thì tốn thật.** Bước 4 phải đổi 1,7 món mỗi ngày và
   điểm hợp khẩu vị rơi xuống 0,7174. Làm sớm ở `p_u` thì pha 5 **không phải
   đổi món nào** và khẩu vị giữ ở 0,7357. Đây chính là nghĩa của "không tối
   ưu": việc nào làm được sớm mà để tới pha sửa cuối thì phải sửa thô hơn, và
   cái bị hy sinh là khẩu vị.
4. Dòng cuối cho thấy hai tầng **không chồng chéo vô ích**: khi `p_u` đã lo
   xong, pha 5 tự nhận ra không còn vi phạm nào và không làm gì cả.

### Nhưng mục tiêu KHÔNG dùng được cơ chế lọc cứng của bệnh lý

Tác động sớm không có nghĩa là lọc sớm. Thử lọc cứng theo ngưỡng xơ đúng như
cách lọc dị nguyên:

| Ngưỡng lọc cứng | Còn lại | `main` | `side_protein` | `side_veg` | `soup` |
|---|---|---|---|---|---|
| không lọc | 318 | 89 | 78 | 52 | 37 |
| `fiber ≥ 1 g` | 191 | 51 | **6** | 51 | 34 |
| `fiber ≥ 2 g` | 115 | 27 | **1** | 39 | 17 |
| `fiber ≥ 3 g` | 64 | 13 | **1** | 25 | 9 |
| `fiber ≥ 5 g` | 17 | 3 | **0** | 5 | 2 |

Vai trò `side_protein` **sụp từ 78 xuống 1 món** ở ngưỡng 2 g và **về 0** ở
ngưỡng 5 g — một món thì không điền nổi hai suất bắt buộc. Lý do mang tính bản
chất chứ không phải thiếu dữ liệu: thịt và cá vốn **không có chất xơ**, và sáu
món còn sót ở ngưỡng 1 g đều là món nấm hoặc đậu phụ.

Để so sánh, lọc cứng cho dị ứng hải sản loại 90/318 món mà **không vai trò nào
về 0** — dị nguyên rải đều các vai trò, còn một vi chất thì tập trung theo nhóm
thực phẩm.

Nên quy tắc là: **bệnh lý thì LOẠI, mục tiêu thì NGHIÊNG.** Cùng tác động
sớm, khác cách tác động. Lọc cứng một mục tiêu sẽ tái hiện đúng thất bại của
ngưỡng natri 600 mg mỗi suất — Bước 4 không dựng nổi bữa ăn.

Con số mục tiêu lấy từ `rda_reference`, bảng đã có sẵn:

```
gender='all'  age 19–120  fiber_g  25.00 g   nguồn: WHO 2023 (khuyến nghị mạnh)
gender='all'  age 10–18   fiber_g  25.00 g   (có điều kiện)
gender='all'  age  6–9    fiber_g  21.00 g   (có điều kiện)
gender='all'  age  2–5    fiber_g  15.00 g   (có điều kiện)
```

`gender = 'all'` vì WHO **không phân biệt giới** cho chất xơ, khác hẳn sắt
(nam 11,90 / nữ 26,10 mg).

**Mục tiêu này có khả thi với danh mục hiện tại không** — câu hỏi bắt buộc
phải hỏi, vì chính nó đã hạ gục ngưỡng natri 600 mg mỗi suất trước đây (loại
58/60 món, Bước 4 không dựng nổi thực đơn). Đo trên 318 món:

| | Chất xơ cả ngày |
|---|---|
| Thực đơn 14 món tối đa xơ | **86,7 g** (347 % mục tiêu) |
| Thực đơn 14 món trung bình | 24,5 g (98 %) |
| Mục tiêu WHO | 25 g |

Khả thi, và khoảng cách trung bình phải lấp chỉ 0,5 g. Danh mục có 64 món ≥3 g
và 17 món ≥5 g để Bước 4 lấy khi cần kéo lên.

**Trạng thái, theo đúng thứ tự ưu tiên mà bảng đo chỉ ra:**

1. **Nhúng mục tiêu vào `p_u`** — **xong**: `PreferenceProfile.withNutrientGoals`.
   Rẻ nhất, lấp 79 % khoảng cách, gần như không tốn khẩu vị.
2. **Ràng buộc vi chất cấp ngày trong Bước 4** — **xong**: pha 5, xem mục 7.0.
   Đây là chỗ duy nhất **bảo đảm** được, nên không bỏ được dù đã làm việc 1.
   Trên 318 món thật, ngưỡng natri của WHO và sàn xơ 25 g thỏa **đồng thời
   12/12**.
3. Chỗ lưu mục tiêu người dùng khai — **chưa làm, cần quyết**:
   `health_profiles.goal` hiện chỉ có
   `lose_weight/maintain/gain_weight/healthy_eating`. Cách rẻ nhất là thêm giá
   trị `'goal'` vào `conditions.condition_type` rồi dùng lại `user_conditions`
   — **không thêm bảng nào**, nhưng là đổi ENUM trong ERD.

Pha 5 cũng làm lộ ra rằng **ngưỡng đạm 48 g/ngày của KDIGO đạt được rất thất
thường** — khả thi về nguyên tắc nhưng phép sửa chỉ tới được 4/12 lần. Chi
tiết ở mục 7.0.1.

### 2.3 Thứ tự chiều phải ổn định

Danh sách nhóm món được **sắp xếp** trước khi dựng one-hot. Nếu thứ tự chiều
phụ thuộc vào thứ tự duyệt, vector sở thích lưu ở lần trước sẽ không còn so
được với vector dựng ở lần sau — một lỗi âm thầm và rất khó truy.

Vì vậy `user_preference_profiles.feature_version` và `ml_models.feature_version`
ghi phiên bản định nghĩa đặc trưng. Đổi tập nhóm món là đổi số chiều, nên
**mọi hồ sơ sở thích cũ phải dựng lại**.

---

## 3. Giai đoạn 0 — chưa có tín hiệu nào

Người dùng vừa tạo tài khoản, chưa vuốt, chưa ăn. Không có gì để học.

Thực đơn sinh bằng luật thuần:

1. Tính hạn mức năng lượng và macro (Bước 1 — Mifflin-St Jeor + TDEE)
2. Lọc F1 theo bệnh lý và dị ứng (Mục 4)
3. Xếp hạng theo `popularity_score` kết hợp độ khớp với hạn mức của suất
4. Ghép tổ hợp bằng bộ tối ưu cái túi (Mục 7)

Đây đồng thời là **phương án đối chứng `rule_based`** trong bảng đánh giá. Một
lợi ích thiết kế: không phải viết riêng một baseline, vì Giai đoạn 0 chính là
nó.

---

## 4. Bộ lọc F1 — tầng an toàn, đặt trước mọi mô hình

Trước khi chấm điểm, loại bỏ mọi món vi phạm **ràng buộc cứng** — ràng buộc
không được phép vi phạm trong bất kỳ trường hợp nào, kể cả khi người dùng rất
thích món đó.

Bộ quy tắc lưu **dưới dạng dữ liệu** trong `condition_rules`, không hard-code.
Ba dạng quy tắc:

| `rule_type` | Trường dùng | Ý nghĩa |
|---|---|---|
| `exclude_tag` | `tag_id` | Loại mọi món mang nhãn đó (dị ứng hải sản, đậu phộng, gluten) |
| `require_tag` | `tag_id` | Chỉ giữ món mang nhãn đó (ăn chay, ăn kiêng tôn giáo) |
| `nutrient_limit` | `nutrient`, `comparator`, `threshold`, `scope` | Áp ngưỡng dinh dưỡng (natri ≤ 600 mg với tăng huyết áp) |

Ràng buộc `chk_rule_shape` đảm bảo tính nhất quán đa hình: quy tắc theo nhãn
thì ba trường dinh dưỡng phải `NULL`, và ngược lại. Không có ràng buộc này thì
một dòng vừa có `tag_id` vừa có `threshold` sẽ lọt vào mà không ai biết nó
được hiểu theo nghĩa nào.

### 4.1 Ràng buộc cứng và mềm trong cùng một bảng

```sql
is_hard  TINYINT(1)   NOT NULL DEFAULT 1
penalty  DECIMAL(4,3) NULL
CONSTRAINT chk_rule_penalty CHECK (is_hard = 1 OR penalty IS NOT NULL)
```

`is_hard = 1` → loại ở Bước 2. `is_hard = 0` → **trừ điểm** ở Bước 3 bằng
`penalty`, món vẫn nằm trong tập ứng viên.

Phân biệt này quan trọng với Bước 4: nếu mọi ràng buộc đều cứng, tập ứng viên
teo lại và bộ tối ưu không tìm nổi tổ hợp thỏa hạn mức năng lượng. Ràng buộc
mềm giữ đường xoay xở.

### 4.2 Giới hạn phạm vi món riêng tư

Mọi truy vấn lấy tập ứng viên phải kèm mệnh đề phạm vi:

```sql
WHERE f.is_active = 1
  AND (f.owner_id IS NULL OR f.owner_id = :current_user_id)
```

`owner_id IS NULL` là món danh mục chung; có giá trị là món riêng của người
dùng đó. Chỉ mục `idx_active_category (owner_id, is_active, category_id)` đặt
`owner_id` đứng đầu vì mệnh đề này **luôn** có mặt.

**Món riêng không vào tập huấn luyện của mô hình toàn cục.** Số liệu dinh
dưỡng của chúng do người dùng tự khai; nhiễm vào mô hình dùng chung là làm hại
mọi người dùng khác. Chúng chỉ cập nhật vector sở thích cá nhân, nơi thiệt hại
giới hạn đúng trong phạm vi người tạo ra nó.

---

## 5. Giai đoạn 1 — Rocchio, **không** phải học máy

Sau phiên vuốt onboarding (~30 món), dựng vector sở thích:

```
            Σ w(aᵢ) · vᵢ
    p_u  =  ───────────────      w: thích = +1, trung tính = 0, không thích = −1
             Σ |w(aᵢ)|
```

Điểm của một món là cosin giữa `p_u` và vector món, đưa về thang `[0,1]`:

```
    score(u, i) = (1 + cos(p_u, vᵢ)) / 2
```

Lưu ở `user_preference_profiles`: `weights` (JSON), `sum_abs_weight`,
`n_signals`, `stage = 'content'`.

### 5.1 Lượt vuốt "chưa biết" bị loại khỏi phép tính

Trọng số `w` chỉ nhận ba giá trị `+1 / 0 / −1`; lượt `unknown` **không tham
gia cả tử số lẫn mẫu số**. Người dùng nói *"tôi chưa biết món này"* khác hoàn
toàn với *"tôi thấy nó bình thường"*. Gộp `unknown` vào như một giá trị 0 sẽ
làm phình mẫu số và kéo vector về gốc, tức làm loãng mọi sở thích thật.

### 5.2 Vì sao không huấn luyện mô hình riêng cho từng người

Với ~30 mẫu và 20 chiều đặc trưng, một mô hình như Rừng ngẫu nhiên sẽ **quá
khớp nghiêm trọng** — nó học thuộc đúng 30 món đó thay vì học ra quy luật
khẩu vị.

Rocchio bản chất vẫn là một mô hình tuyến tính học từ chính 30 mẫu ấy, chỉ
khác ở chỗ nghiệm được tính bằng **công thức đóng** thay vì tối ưu lặp. Nhờ
vậy nó có ba tính chất mà một mô hình học máy không có khi dữ liệu ít:

- **Ổn định** khi số mẫu nhỏ — không có phương sai do khởi tạo ngẫu nhiên
- **Tức thì** — tính xong ngay khi người dùng vuốt hết, không cần chờ huấn luyện
- **Giải thích được** — chỉ rõ *"gợi ý món này vì bạn đã thích các món cùng nhóm"*

Đây là một lựa chọn kỹ thuật có lý lẽ, cần trình bày trong báo cáo như vậy chứ
đừng coi là giải pháp tạm thời.

### 5.3 Dữ liệu vuốt không bị bỏ phí

Toàn bộ tín hiệu vuốt vẫn ghi vào `interactions` và **tham gia tập huấn luyện
của mô hình toàn cục** ở Giai đoạn 2, với `source = 'swipe'`.

---

## 6. Giai đoạn 2 — một mô hình toàn cục

```
    x = [ đặc trưng người dùng  ⊕  đặc trưng món ăn  ⊕  đặc trưng chéo ]
    y = mức độ ưa thích ∈ [0, 1]
```

### 6.1 Một mô hình cho tất cả, không phải mỗi người một mô hình

| Ưu điểm | Giải thích |
|---|---|
| Tận dụng dữ liệu chéo | Người có hồ sơ tương tự đóng góp dữ liệu cho nhau, giảm mạnh nhu cầu dữ liệu trên mỗi người |
| Chống quá khớp | Tập huấn luyện lớn hơn nhiều lần dữ liệu của một cá nhân |
| Vận hành đơn giản | Một mô hình để huấn luyện, đánh giá, triển khai — thay vì hàng trăm mô hình rời rạc |

Tính cá nhân hóa **không** đến từ việc mỗi người một mô hình, mà từ **đặc
trưng chéo** nằm ngay trong vector đầu vào. Đặc trưng chéo quan trọng nhất
chính là `cos(p_u, vᵢ)` — độ tương đồng với hồ sơ Rocchio đã dựng ở Giai đoạn 1.

Nghĩa là Giai đoạn 1 **không bị bỏ đi** khi lên Giai đoạn 2; nó trở thành một
đầu vào của Giai đoạn 2.

### 6.2 Ba thuật toán sẽ thử

```sql
algorithm ENUM('logistic_regression','random_forest','gradient_boosting')
```

| Thuật toán | Vai trò trong đồ án |
|---|---|
| `logistic_regression` | Mốc tuyến tính. Giải thích được qua hệ số, nhanh, khó quá khớp |
| `random_forest` | Bắt được tương tác phi tuyến giữa đặc trưng. Cho `feature_importance` |
| `gradient_boosting` | Thường cho kết quả tốt nhất trên dữ liệu bảng, nhưng cần hiệu chỉnh siêu tham số kỹ hơn |

`ml_models` lưu `hyperparams`, `scaler_params`, `feature_importance` dạng JSON
cùng `artifact_path` trỏ tới tệp mô hình đã huấn luyện. `is_active = 1` đánh
dấu mô hình đang phục vụ.

Lưu `scaler_params` là bắt buộc, không phải tùy chọn: mô hình huấn luyện trên
dữ liệu đã chuẩn hóa thì khi suy luận phải chuẩn hóa **bằng đúng tham số đó**.
Tính lại min–max trên dữ liệu mới là một lỗi âm thầm làm điểm số lệch dần theo
thời gian.

### 6.3 Chuyển tiếp mượt giữa hai giai đoạn

Không chuyển đột ngột, vì người dùng sẽ thấy thực đơn đổi bất thường ngay khi
vừa vượt ngưỡng:

```
    score(u,i) = α · score_ML(u,i)  +  (1 − α) · score_cosin(u,i)

           ⎧ 0                              nếu  n < n_min
       α = ⎨ (n − n_min) / (n_max − n_min)   nếu  n_min ≤ n ≤ n_max
           ⎩ 1                              nếu  n > n_max

       n_min ≈ 30 ,  n_max ≈ 100      (hiệu chỉnh bằng thực nghiệm)
```

`α` lưu ở `user_preference_profiles.alpha`, `n` là `n_signals`.

---

## 7. Bước 4 — bộ tối ưu, **không phải học máy**

Điểm này rất dễ bị hỏi lẫn khi bảo vệ, nên cần phân biệt rõ:

> **Mô hình sinh ra điểm số. Bộ tối ưu sinh ra thực đơn.**

Bài toán là **cái túi đa chiều**: chọn tập món `S` tối đa tổng điểm ưa thích,
đồng thời thỏa hạn mức năng lượng và ba hạn mức macro, với cấu trúc bữa cho
trước. Hàm mục tiêu có phạt:

```
    F(S) = Σ score(i)  −  λ·|kcal(S) − E| / E  −  μ·Σ|macro(S) − T| / T
```

Cài đặt hiện tại chạy **năm** pha:

| Pha | Việc | Lý do tồn tại |
|---|---|---|
| 1 | Tham lam theo **mật độ điểm** trên các suất bắt buộc | Chiến lược kinh điển của cái túi |
| 2 | Bù suất tùy chọn ở **cấp ngày** | Một món không thể cân một bữa sáng 699 kcal |
| 3 | Tìm kiếm cục bộ — hoán đổi từng món, tối ưu **từng bữa** | Lời giải tham lam chỉ nhìn một suất tại một thời điểm |
| 4 | Bù lại ở **cấp ngày** | Sửa hậu quả của pha 3 |
| 5 | **Thi hành ràng buộc vi chất ở cấp ngày** | Ngưỡng cứng `per_day` trước đây không được thi hành ở đâu cả |

### 7.0 Pha 5 — chỗ trước đây hổng hoàn toàn

`condition_rules` lưu các ngưỡng cứng của bệnh lý với `scope = 'per_day'`, và
tài liệu nói Bước 4 kiểm chúng. **Bước 4 không kiểm.** Nó chỉ bám `kcal` và ba
chất sinh năng lượng, nên bốn ngưỡng theo ngày — natri ≤ 2000 mg của WHO,
purin ≤ 400 mg, đạm ≤ 48 g của KDIGO — không được thi hành ở bất cứ tầng nào
của hệ thống.

Pha 5 sửa bằng **hoán đổi một món cùng vai trò**, không thêm và không bớt món:
thêm thì phá hạn mức năng lượng, bớt thì phá cấu trúc bữa. Mỗi vòng xử lý vi
phạm **nặng nhất** trước, đo theo **tỷ lệ trên ngưỡng** — phải là tỷ lệ, vì
thiếu 5 g chất xơ trên ngưỡng 25 g nặng hơn nhiều so với vượt 5 mg natri trên
ngưỡng 2000 mg, mà đo bằng lượng tuyệt đối thì hai cái bằng nhau.

Một phép đổi chỉ được nhận khi thỏa cả ba:

1. làm vi phạm đang xét **nhỏ lại**;
2. **không tạo vi phạm mới** ở ràng buộc nào khác đang thỏa;
3. độ lệch năng lượng sau đổi vẫn trong 10 %, hoặc không tệ hơn mức đang có.

Điều kiện 2 là chỗ dễ sai nhất: không có nó thì pha 5 sẽ lấp chất xơ bằng cách
nhồi món nhiều natri, và người tăng huyết áp nhận một thực đơn đạt xơ nhưng vi
phạm đúng ngưỡng quan trọng với họ. Điều kiện 3 giữ cho pha này không chữa một
vi phạm bằng cách tạo ra một vi phạm khác.

Khi nhiều phép đổi cùng mức cải thiện thì chọn phép **giữ khẩu vị tốt nhất** —
đo được ở mục 2.2 rằng bỏ mặc tiêu chí này làm điểm hợp khẩu vị rơi 7,1 % thay
vì 2,1 %.

**Kết quả trên 318 món thật**, hạn mức 2000 kcal, 12 hồ sơ khẩu vị:

| Ràng buộc | Natri | Xơ | Đạm | Thỏa | Số lần đổi |
|---|---|---|---|---|---|
| không có | 5875 mg | 22,0 g | 76 g | — | 0 |
| natri ≤ 2000 (tăng huyết áp) | **1792 mg** | 23,7 g | 81 g | **12/12** | 4,4 |
| xơ ≥ 25 (mục tiêu tự khai) | 5827 mg | **26,0 g** | 77 g | **12/12** | 0,7 |
| **cả hai cùng lúc** | **1804 mg** | **26,7 g** | 84 g | **12/12** | 5,0 |
| đạm ≤ 48 + natri ≤ 2000 (bệnh thận) | 1856 mg | 24,1 g | 48 g | **4/12** | 9,8 |

Hai ràng buộc ngược hướng nhau **thỏa được đồng thời** — đó là phép thử thật
của điều kiện 2.

### 7.0.1 Ngưỡng đạm của KDIGO: khả thi nhưng phép sửa chỉ tới 4/12

Mục này đã **phải viết lại một lần**, và quá trình đó đáng ghi lại vì nó cho
thấy hai loại hạn chế rất dễ bị nhầm với nhau.

**Lần đo thứ nhất, trên 305 món: bất khả thi thật.** Lấy món nhẹ đạm nhất cho
từng suất bắt buộc thì sàn cứng là **59,6 g**, trong đó riêng hai suất
`side_protein` chiếm 30,1 g vì món nhẹ đạm nhất ở vai trò đó là **trứng luộc
14,8 g**. Ngưỡng KDIGO 48 g (người 60 kg) nằm dưới sàn, nên không tổ hợp nào
thỏa được.

**Rồi danh mục thêm 13 món chay** — vá cho một lỗ hoàn toàn khác, là việc người
ăn chay không có món canh nào. Trong đó có mấy món mặn làm từ **nấm**, và nấm
nhẹ đạm hơn trứng rất nhiều. Sàn cứng đo lại:

| Vai trò | Số suất | Đạm tối thiểu | Món nhẹ nhất |
|---|---|---|---|
| `main` | 3 | 14,3 g | Khoai lang luộc 2,0 g |
| `side_protein` | 2 | **11,1 g** *(trước: 30,1 g)* | **Nấm rơm rang muối 5,0 g** |
| `side_veg` | 3 | 2,5 g | Bí đỏ luộc 0,6 g |
| `soup` | 2 | **5,8 g** *(trước: 11,9 g)* | **Canh mướp nấu nấm rơm 2,9 g** |
| `dessert` | 1 | 0,4 g | Bưởi 0,4 g |
| `drink` | 1 | 0,4 g | Nước ép bưởi 0,4 g |
| | | **34,5 g** *(trước: 59,6 g)* | |

**Sàn rơi từ 59,6 g xuống 34,5 g, và ngưỡng 48 g trở thành khả thi.** Kết luận
"bất khả thi" trước đó đã sai ngay khi danh mục đổi — và nó sai vì tôi quy một
hạn chế **dữ liệu** thành hạn chế **thiết kế**.

**Nhưng pha 5 vẫn chỉ đạt 4/12.** Khả thi không có nghĩa là tìm được. Đạm trung
bình rơi đúng 48 g, tức nằm sát ngay mép ngưỡng. Thử tăng trần số vòng sửa:

| Vòng tối đa | Đạm | Natri | Thỏa | Số lần đổi thật |
|---|---|---|---|---|
| 12 | 48 g | 1856 mg | 4/12 | 9,8 |
| 20 | 48 g | 1846 mg | 4/12 | 10,3 |
| 30 | 48 g | 1846 mg | 4/12 | 10,3 |
| 50 | 48 g | 1846 mg | 4/12 | 10,3 |

**Bão hòa ở 10,3 lần đổi** — không phải hết ngân sách mà là **cực trị cục bộ**.
Pha 5 chỉ đổi **một món mỗi bước** và chỉ nhận phép đổi làm vi phạm nặng nhất
nhỏ lại; những cấu hình cần đổi **hai món cùng lúc** mới xuống dưới ngưỡng thì
nó không tới được. Nới trần vòng lặp không sửa được loại hạn chế này.

Phân biệt cho rõ, vì ba thứ này đòi ba cách chữa khác nhau:

| Loại hạn chế | Biểu hiện | Cách chữa |
|---|---|---|
| **Dữ liệu** | sàn cứng cao hơn ngưỡng | thêm món — đã làm, 59,6 → 34,5 g |
| **Thuật toán** | sàn thấp hơn ngưỡng mà vẫn không tìm ra | cho phép đổi đôi, hoặc nhận bước đi ngang (luyện thép mô phỏng) |
| **Thiết kế** | ngưỡng mâu thuẫn với cấu trúc bài toán | đổi cấu trúc bữa, hoặc thêm hệ số khẩu phần |

Hiện tại là loại **thuật toán**. Hai hạn chế thiết kế vẫn còn và vẫn đáng nêu
trong báo cáo:

* **Cấu trúc bữa cố định.** `_mealStructure` bắt bữa trưa và bữa tối mỗi bữa
  một suất `side_protein`.
* **Khẩu phần cố định.** Chế độ giảm đạm trong thực tế giảm **lượng** món đạm
  chứ không bỏ hẳn món. Mỗi món chỉ có một `serving_size_g` nên không biểu
  diễn được "nửa suất thịt".

Hành vi hiện tại là **báo ra chứ không ỉm đi**: `DailyPlan.nutrientViolations`
liệt kê ngưỡng chưa thỏa kèm lượng thực tế. Thực đơn vi phạm mà trông như bình
thường là kiểu lỗi nguy hiểm nhất với người có bệnh.

### 7.0.2 `purine_mg` nằm ngoài tầm thi hành

Quy tắc cứng cho bệnh gút là purin ≤ 400 mg/ngày, nhưng lớp `Food` không mang
trường purin và bảng thành phần chỉ công bố purin cho **70/318 món**, nên thêm
vào cũng chỉ phủ 22 % danh mục. Phần bảo vệ cho bệnh gút vì vậy vẫn dựa vào
quy tắc `exclude_tag 'Giàu purin'` ở Bước 2 — nhãn đó phủ 91 món.

Ràng buộc purin truyền vào Bước 4 vẫn hợp lệ, nhưng hiện ra ở
`DailyPlan.unenforceableTargets` chứ **không** gộp vào `nutrientViolations`.
Lý do: tổng purin đọc ra bằng 0, nên gộp chung sẽ làm một thực đơn **chưa từng
được kiểm purin** hiện ra như đã đạt ngưỡng gút. Đó là kiểu sai tệ hơn cả báo
vi phạm.

### 7.1 Vì sao xếp theo mật độ điểm chứ không theo điểm thuần

Nếu xếp theo điểm thuần, một món 650 kcal điểm 0,9 sẽ **luôn** thắng món
300 kcal điểm 0,8, và bữa ăn cạn hạn mức chỉ sau một món. Mật độ `score/kcal`
ưu tiên món mang lại nhiều điểm nhất **trên mỗi đơn vị năng lượng tiêu tốn**.

Mật độ còn được cân thêm bởi độ khớp với hạn mức của suất, nếu không thì món
nhẹ nhất luôn thắng vì mẫu số nhỏ.

### 7.2 Vì sao cần pha 4

Pha 3 tối ưu **từng bữa riêng lẻ**, nên nó có thể kéo tổng năng lượng cả ngày
xa hạn mức dù mỗi bữa đều khá hơn: đổi một món chính nhẹ hơn vào bữa trưa làm
bữa đó khớp macro hơn, nhưng cả ngày hụt thêm.

Đây là một lỗi thật đã gặp trong quá trình phát triển: một hạt giống cho độ
lệch **−11,1%**, vượt cam kết 10% của đề cương, với bữa trưa chỉ đạt 760/953
kcal và **trống vai trò món canh** trong khi còn ba món canh chưa dùng. Thêm
pha 4 đưa về **−2,8%**.

Pha 4 an toàn vì nó chỉ thêm món khi món đó làm khoảng lệch cấp ngày **nhỏ
lại** — chạy thêm một lượt không bao giờ làm xấu đi.

### 7.3 `usedIds` phải cập nhật sau mỗi bữa

Lỗi thứ hai cùng loại: pha 3 chạy lần lượt từng bữa, và nếu `usedIds` không
được cập nhật sau mỗi bữa thì món vừa được đổi **vào** bữa sáng không nằm
trong tập đã dùng, nên bữa trưa thấy nó còn trống và lấy luôn — **cùng một món
hai lần trong một ngày**.

Món bị đổi **ra** cũng phải được trả lại tập ứng viên, vì nó không còn trong
thực đơn nữa.

---

## 8. Chống bong bóng lọc — cơ chế 70-30

Nếu luôn chọn món điểm cao nhất, vector `p_u` càng bị củng cố về hướng cũ và
vòng lặp phản hồi tự bóp nghẹt chính nó. Mô hình không hề **sai** — nó chỉ
không bao giờ **biết thêm**.

Hệ thống này dễ dính hơn bình thường vì **cơ chế vuốt chỉ chạy một lần** lúc
tạo tài khoản. Từ đó trở đi, nguồn dữ liệu mới duy nhất là chính thực đơn. Nên
hệ thống **phải tự thăm dò**.

```
p_u'  =  chuẩn_hóa( p_u + δ · n )      n = vector nhiễu ngẫu nhiên đơn vị

   70% số suất  →  xếp hạng theo cos(p_u,  vᵢ)   — KHAI THÁC
   30% số suất  →  xếp hạng theo cos(p_u', vᵢ)   — THĂM DÒ
```

### 8.1 Tỷ lệ thăm dò là thuộc tính **cấp thực đơn**

```sql
exploration_ratio DECIMAL(4,3) NULL
CONSTRAINT chk_expl_ratio CHECK (exploration_ratio IS NULL
                                 OR exploration_ratio BETWEEN 0 AND 0.5)
```

Đây là một lỗi thật đã gặp: ban đầu chia theo từng bữa, và
`(số_suất_của_bữa × 0.3)` làm tròn xuống cho ra **0** với mọi bữa — thăm dò
không bao giờ chạy. Phải phân bổ hạn mức thăm dò ở **cấp ngày** rồi rải vào
các suất.

Trần cứng 0,5 vì thăm dò quá nửa thực đơn thì nó không còn là gợi ý cá nhân
hóa nữa.

`meal_plan_items.exploration_delta` ghi biên độ nhiễu của từng suất, để sau
này phân tích được: *suất thăm dò có tỷ lệ được giữ lại là bao nhiêu so với
suất khai thác?* Đó là một con số đáng đưa vào Chương 3.

---

## 9. Dữ liệu huấn luyện — bảy nguồn, có trọng số

`ml_training_samples` gom tín hiệu từ bảy nguồn. Mỗi nguồn một nhãn và một
**trọng số theo độ tin cậy**:

| `source` | Bảng gốc | `label` | `sample_weight` |
|---|---|---|---|
| `feedback` 5★ | `feedbacks` | 1.000 | **1.0** |
| `feedback` 4★ | `feedbacks` | 0.750 | 1.0 |
| `feedback` 3★ | `feedbacks` | 0.500 | 1.0 |
| `feedback` 2★ | `feedbacks` | 0.250 | 1.0 |
| `feedback` 1★ | `feedbacks` | 0.000 | 1.0 |
| `diary` | `food_diary` | 0.800 | 0.9 |
| `swipe` (like) | `interactions` | 0.900 | 0.7 |
| `swipe` (neutral) | `interactions` | 0.500 | 0.7 |
| `swipe` (dislike) | `interactions` | 0.000 | 0.7 |
| `plan_kept` | `meal_plan_items` | 0.700 | 0.6 |
| `plan_replaced` | `meal_plan_items` | 0.150 | 0.6 |
| `plan_skipped` | `meal_plan_items` | 0.300 | **0.3** |
| `random_neg` | Lấy ngẫu nhiên từ món chưa hiển thị | 0.100 | 0.2 |
| — | `interactions` (`action = 'unknown'`) | **Loại khỏi tập** | — |

### 9.1 Trọng số mã hóa độ tin cậy, không phải mức độ thích

Đây là chi tiết đáng nêu khi bảo vệ. Hai cột `label` và `sample_weight` trả
lời hai câu khác nhau:

- `label` — *người dùng thích món này đến mức nào?*
- `sample_weight` — *ta tin con số đó đến mức nào?*

Một đánh giá 5 sao sau khi ăn (trọng số 1,0) đáng tin hơn hẳn một suất bị bỏ
không ăn (0,3), vì bỏ bữa là tín hiệu **nhập nhằng**: có thể do không thích,
có thể do hôm đó không có thời gian nấu. Nhãn 0,300 phản ánh phỏng đoán
"hơi không thích", còn trọng số 0,3 nói rằng đừng tin phỏng đoán đó quá.

### 9.2 Vì sao `unknown` bị loại thay vì gán 0.5

Giống lý do ở Mục 5.1, nhưng ở đây hậu quả nặng hơn: gán 0,5 là **bịa ra một
nhãn** mà người dùng chưa từng cung cấp, rồi huấn luyện mô hình trên nhãn bịa
đó. Loại khỏi tập là cách trung thực duy nhất.

### 9.3 Chống nhân đôi mẫu

```sql
UNIQUE KEY uq_sample (dataset_version, user_id, food_id, source)
```

Tập dữ liệu sẽ được sinh lại nhiều lần trong quá trình làm. Không có ràng buộc
này thì mỗi lần chạy lại sẽ nhân đôi toàn bộ mẫu, và mô hình huấn luyện trên
dữ liệu trùng lặp mà không ai biết.

Khóa gồm `source` vì cùng một cặp (người dùng, món) **có thể** sinh nhiều mẫu
từ các nguồn khác nhau — họ vuốt thích món đó, rồi ăn thật, rồi đánh giá 4
sao. Ba tín hiệu độc lập, ba dòng hợp lệ.

### 9.4 `profile_snapshot` — tránh rò rỉ dữ liệu

```sql
profile_snapshot JSON NULL
```

Cột này lưu vector sở thích **tại thời điểm thu tín hiệu**, không phải vector
hiện tại.

Lý do: đặc trưng chéo `cos(p_u, vᵢ)` là đầu vào của mô hình. Nếu khi dựng tập
huấn luyện ta dùng `p_u` **hiện tại** — vector đã được cập nhật *bởi chính tín
hiệu đang xét* — thì đặc trưng đã chứa thông tin về nhãn. Đó là **rò rỉ dữ
liệu** (data leakage): mô hình sẽ cho kết quả đánh giá rất đẹp mà vô dụng khi
chạy thật.

---

## 10. Đánh giá — chỗ làm nên một đồ án

`ml_evaluations` là bảng quan trọng nhất của phần học máy.

```sql
variant ENUM('ml','content_based','rule_based','popularity','hybrid')
metric  ENUM('precision','recall','ndcg','map','mae','rmse','f1','auc')
k_value TINYINT UNSIGNED NULL
fold    TINYINT UNSIGNED NULL
UNIQUE KEY uq_eval (model_id, variant, metric, k_value, fold)
```

### 10.1 Cột `variant` là lý do bảng này tồn tại

Bảng được thiết kế để **so sánh với các phương án đối chứng**, không chỉ để
báo cáo một con số. Đó là thứ phân biệt một đồ án nghiên cứu với một ứng dụng:

> Không phải *"mô hình đạt nDCG@10 = 0,72"*
> mà *"mô hình đạt 0,72 so với 0,51 của phương án xếp theo độ phổ biến"*

Bốn phương án đối chứng, xếp theo độ khó vượt qua:

| `variant` | Là gì | Ý nghĩa nếu không vượt được |
|---|---|---|
| `popularity` | Xếp theo `popularity_score`, bỏ qua cá nhân hóa | Toàn bộ phần học máy **chưa chứng minh được giá trị** |
| `rule_based` | Giai đoạn 0 — luật thuần | Cá nhân hóa không hơn luật dinh dưỡng |
| `content_based` | Giai đoạn 1 — Rocchio | Mô hình phức tạp không hơn cosin đơn giản |
| `hybrid` | Pha trộn theo α | — |

`popularity` là phương án tầm thường **bắt buộc phải vượt qua**. Nếu xếp món
theo độ phổ biến cũng cho kết quả tương đương, thì không có gì để báo cáo.

### 10.2 Các chỉ số và vì sao cần `k_value`

| Chỉ số | Dùng cho |
|---|---|
| `precision@k`, `recall@k` | Chất lượng top-k gợi ý |
| `ndcg@k`, `map` | Có tính tới **thứ tự** trong danh sách |
| `mae`, `rmse` | Sai số dự đoán điểm ưa thích |
| `f1`, `auc` | Phân loại thích / không thích |

`k_value` tồn tại vì người dùng chỉ thấy 4–6 suất mỗi ngày. `precision@5` nói
đúng điều ta quan tâm; `precision` trên toàn bộ 500 món thì không.

`ndcg@k` quan trọng hơn `precision@k` với hệ này: gợi ý đúng món nhưng xếp
cuối danh sách thì người dùng không bao giờ thấy.

### 10.3 `fold` — kiểm định chéo

Cam kết của đề cương là hiệu quả với **mọi** người dùng, không phải may mắn ở
một lần chia tập. `fold` cho phép lưu kết quả từng lần gập và báo cáo trung
bình ± độ lệch chuẩn.

Chia tập theo **người dùng**, không theo mẫu: nếu cùng một người xuất hiện ở
cả tập huấn luyện và tập kiểm tra, mô hình đã thấy khẩu vị của họ và con số
đánh giá bị thổi phồng.

---

## 11. Phạm vi thực nghiệm — hướng B

**Giai đoạn 2 cần người dùng thật, mà đồ án thì không có.** `ml_models.n_train`
và `n_test` đều `NOT NULL` — phải là số thật, không bịa được.

**Quyết định: tập trung đánh giá vào Giai đoạn 1, trình bày Giai đoạn 2 là đã
cài đặt nhưng hạn chế dữ liệu.**

### 11.1 Việc này nghĩa là gì trong thực tế

| Phần | Làm gì |
|---|---|
| Giai đoạn 0 (`rule_based`) | Cài đặt đầy đủ, đánh giá đầy đủ — là baseline |
| Giai đoạn 1 (`content_based`) | **Trọng tâm thực nghiệm.** Đánh giá ngoại tuyến đầy đủ với kiểm định chéo |
| Giai đoạn 2 (`ml`) | Cài đặt đầy đủ pipeline, chạy được, báo cáo kết quả kèm ghi rõ cỡ mẫu |
| So sánh | `content_based` vs `rule_based` vs `popularity` — bộ ba này đủ để kết luận |

Phần so sánh cốt lõi của đồ án do đó là: **khuyến nghị theo nội dung có hơn
luật thuần và hơn độ phổ biến hay không**. Đây là một câu hỏi nghiên cứu hoàn
chỉnh, trả lời được với dữ liệu thật ít ỏi, và không cần tới mô hình toàn cục.

### 11.2 Vì sao hướng này trung thực hơn

Phương án mô phỏng người dùng có một cái bẫy: sinh hồ sơ giả với khẩu vị đã
biết rồi cho chúng "vuốt" và "ăn" theo khẩu vị đó, thì mô hình sẽ học lại
**đúng quy luật mình vừa bịa ra**. Con số đánh giá sẽ rất đẹp và hoàn toàn vô
nghĩa.

Ghi rõ giới hạn cỡ mẫu trong báo cáo là cách xử lý đúng. Hội đồng đánh giá cao
sự trung thực về hạn chế hơn là một con số đẹp không giải thích được nguồn gốc.

### 11.3 Cách thu dữ liệu thật

Nguồn khả thi nhất là **chính người làm đồ án và một nhóm nhỏ dùng thử**: mỗi
người một phiên vuốt 30–40 món, rồi dùng app vài tuần để sinh tín hiệu
`diary`, `plan_kept`, `plan_replaced`, `feedback`.

Với 20–30 người dùng, Giai đoạn 1 có đủ dữ liệu để đánh giá có ý nghĩa, vì
Rocchio chỉ cần ~30 mẫu **trên mỗi người**. Giai đoạn 2 thì không — nhưng theo
hướng B thì không cần.

#### Bộ công cụ thu phiên vuốt, không cần chờ ứng dụng

Phiên vuốt onboarding không phải chờ app chạy mới thu được — nó là 40 câu hỏi
bốn lựa chọn. Hai công cụ dưới đây làm trọn việc đó:

```
python tools/make_survey_deck.py --so 40 --ghi
    → data/survey/survey_deck.json      (bộ món kèm vector, để tái lập)
    → data/survey/phieu_khao_sat.csv    (phiếu trống để chép cho từng người)

cp data/survey/phieu_khao_sat.csv data/survey/da_dien/nguoi-01.csv
# người tham gia điền cột `lua_chon` và phần thông tin ở đầu tệp

python tools/import_swipes.py --phieu data/survey/da_dien/nguoi-01.csv
python tools/import_swipes.py --phieu data/survey/da_dien/nguoi-01.csv --apply
    → users, health_profiles, user_conditions, interactions,
      user_preference_profiles (vector Rocchio tính luôn)
```

**Chọn bộ món bằng duyệt điểm xa nhất**, không chọn ngẫu nhiên. Mỗi người chỉ
vuốt ~40 món nên mỗi lượt phải mang về nhiều thông tin nhất có thể; nếu bộ món
gom cụm ở một góc của không gian đặc trưng thì mọi vector sở thích thu được
cũng nằm quanh góc đó, và hệ thống không phân biệt được hai người khác khẩu
vị. Vòng đầu chọn một món đại diện cho mỗi nhóm trong 12 nhóm (nếu để thuật
toán tự do, nó bỏ qua các nhóm nằm giữa không gian như `Cơm` — thứ người ta ăn
hằng ngày); vòng sau rải món ra khắp không gian. Điểm khởi đầu là món gần tâm
danh mục nhất, không ngẫu nhiên, vì hai người được khảo sát bằng hai bộ món
khác nhau thì vector của họ không so được với nhau.

**Hạn chế phải ghi vào báo cáo:** bộ 40 món thu được có **37 món ở mức cay 0**,
vì cả danh mục chỉ có 24/318 món cay. Vector sở thích vì vậy **yếu ở chiều
"Mức cay"**. Đây là hạn chế của dữ liệu, không của thuật toán, và
`make_survey_deck.py` in cảnh báo này ra cùng bộ món.

**Phiếu đã điền không được commit.** Chúng chứa họ tên, email, ngày sinh, chiều
cao, cân nặng và bệnh lý của người thật — dữ liệu sức khỏe cá nhân — và repo
này là repo công khai. `data/survey/da_dien/` đã có trong `.gitignore`; phiếu
trống thì vẫn commit vì nó là sản phẩm phải nộp.

`import_swipes.py` **kiểm hết rồi mới ghi**, và cả lần nhập là một giao dịch:
một phiếu nhập dở — có người dùng nhưng thiếu lượt vuốt, hoặc có lượt vuốt
nhưng thiếu hồ sơ sở thích — tệ hơn hẳn một phiếu chưa nhập, vì nó vẫn chạy
qua mọi script phía sau và âm thầm góp một người dùng khuyết vào tập huấn
luyện.

---

## 12. Danh sách việc cần làm

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Bộ lọc F1 đối chiếu `condition_rules` | **Xong** — `ml/f1_filter.py` |
| 2 | Trích xuất đặc trưng phía server (Python) | **Xong** — `ml/features.py`, có kiểm chứng chéo |
| 3 | Bộ dựng tập dữ liệu: 7 nguồn → `ml_training_samples` | **Xong** — `ml/build_dataset.py` |
| 4 | Huấn luyện 3 thuật toán, ghi `ml_models` | **Xong** — `ml/train.py` |
| 5 | So sánh 4 phương án đối chứng → `ml_evaluations` | **Xong** — `ml/evaluate.py` |
| 6 | Phục vụ mô hình `is_active = 1` | **Xong** — `ml/serve.py` |
| 7 | Rocchio + cái túi đa chiều **5 pha** | **Xong** trong app Flutter |
| 8 | Cơ chế 70-30 cấp ngày | **Xong**, có test |
| 9 | Tính `foods.popularity_score` từ tín hiệu thật | **Xong** — `tools/update_popularity.py`, chờ dữ liệu |
| 10 | Thu dữ liệu từ người dùng thật | Bộ công cụ **xong**; **dữ liệu chờ thu** — xem §11.3 |
| 11 | Hạn mức theo ngày từ nhật ký + thực đơn | **Xong** — `ml/han_muc.py` |
| 12 | Lý do bị F1 loại, ba bậc | **Xong** — `f1_filter.ly_do_loai` |
| 13 | Thi hành ràng buộc mềm | **Xong** — `scoring.hinh_phat`; phạm vi `per_meal` **chưa có tầng nhận** |
| 14 | Giải thích gợi ý bằng câu | **Xong** — `serve.dong_gop`, `serve.cau_giai_thich` |
| 15 | Bốn màn giải thích trong Flutter | **Xong** — `mobile/lib/features/plan/`, `mobile/lib/data/rules/` |

**Mục 1–9 và 11–15 đã xong về mã. Mục 10 là thứ duy nhất còn chặn**, và nó
không phải việc lập trình: đường ống chạy đầy đủ nhưng trên 0 người dùng, nên
mọi con số nó sinh ra hiện giờ là của dữ liệu giả. Chạy
`python -m ml.build_dataset --version v1` lúc này trả về:

```
tổng                0
Chưa có tín hiệu nào trong CSDL — không có gì để dựng.
```

Toàn bộ phần Python nằm ở thư mục `ml/`, chạy theo thứ tự:

```
ml/features.py  →  ml/build_dataset.py  →  ml/train.py  →  ml/evaluate.py
  (vector)          (ml_training_samples)   (ml_models)     (ml_evaluations)
                                                 │
                                                 ▼
                                            ml/serve.py
                                      (chấm điểm cho người dùng)

ml/f1_filter.py  — tầng an toàn, chạy TRƯỚC mọi phép chấm điểm
ml/rocchio.py    — hồ sơ Rocchio: dựng tập, đánh giá và phục vụ đều dùng
ml/scoring.py    — công thức chấm điểm bốn giai đoạn, **một chỗ duy nhất**
ml/dataset.py    — ghép ba khối đặc trưng thành ma trận đầu vào
```

### 12.0 Hai bộ kiểm, và vì sao cần cả hai

```
tools/check_ml.py       262 mục · hàm thuần   · KHÔNG cần CSDL
tools/check_ml_e2e.py   190 mục · cả đường ống · tự dựng CSDL riêng rồi tự xóa
tools/check_contrast.py  20 cặp · tương phản bảng màu theo WCAG 2.1 AA
cd mobile && flutter test  92 mục, gồm 6 mục đối chiếu Dart ↔ Python
```

`check_ml.py` kiểm **ca biên** mà dữ liệu thật không có: cả tập chỉ một mức
năng lượng, người dùng vuốt toàn `neutral`, một người không có món nào đáng
gợi ý, `k` lớn hơn số món. Các chỉ số xếp hạng được đối chiếu với **giá trị
tính bằng tay**, không đối chiếu với kết quả của chính đoạn mã đang kiểm —
một bài kiểm so mã với chính nó chỉ phát hiện được thay đổi, không phát hiện
được sai.

`check_ml_e2e.py` chạy cả bốn script nối tiếp trên một CSDL riêng: sao dữ
liệu món thật sang để vector vẫn là vector thật, dựng người dùng giả phủ cả
bốn giai đoạn, chạy hết rồi xóa CSDL. Nó **không bao giờ ghi vào
`nutrition_rec`**.

Nhãn của dữ liệu giả được gắn **ngẫu nhiên**, và đó là chủ ý: nó tạo ra một
**chốt canh rò rỉ dữ liệu**. Nếu đường ống không rò rỉ thì mô hình buộc phải
cho kết quả quanh mức tình cờ — một AUC đẹp ở đây là *bằng chứng có rò rỉ*,
không phải tin tốt. Đây cũng là lý do không sinh hồ sơ giả với khẩu vị đã
biết: làm vậy thì mô hình học lại đúng quy luật mình vừa bịa ra, và chốt canh
mất tác dụng (§11.2).

### 12.0.1 Bốn chỗ hai bản cài đặt có thể lệch nhau trong im lặng

Phần học máy có bốn chỗ mà **cùng một công thức bị cài ở hai nơi**. Lệch nhau
ở bất kỳ chỗ nào trong bốn chỗ này đều không báo lỗi: cả hai bên vẫn chạy,
vẫn trả về số trong [0, 1], chỉ là chúng mô tả hai hệ thống khác nhau. Mỗi
chỗ được khóa lại bằng một cơ chế riêng:

| Hai bản | Rủi ro nếu lệch | Khóa bằng |
|---|---|---|
| Vector món: Dart ↔ Python | Huấn luyện trên một không gian, suy luận trên một không gian khác | `food_vector_parity_test.dart` — đối chiếu từng chiều |
| Chấm điểm: đánh giá ↔ phục vụ | Con số báo cáo không nói về hệ thống đang chạy | Cả hai gọi `ml/scoring.py`, không bên nào tự cài |
| Ghép hàng đặc trưng: huấn luyện ↔ suy luận | Mô hình nhận sai thứ tự cột | Cả hai gọi `dataset.dung_hang_dac_trung` |
| Phiên bản đặc trưng: mô hình ↔ mã | Mô hình cũ được nạp với vector mới | `feature_version` kiểm ở 3 chỗ trong `ml/serve.py` |

### 12.0.2 Tầng phục vụ hạ cấp **có công bố**

`ml/serve.py` chọn giai đoạn theo `n_signals`, không theo mô hình nào đang
có. Khi giai đoạn đòi mô hình mà không dùng được, nó lùi về giai đoạn thấp
hơn và **nói ra lý do** trong `KetQuaGoiY.canh_bao`:

- không có mô hình nào `is_active = 1`;
- có **nhiều hơn một** mô hình `is_active = 1` — từ chối chọn bừa, vì chọn
  bừa là một quyết định không tái lập được (`is_active` không có ràng buộc
  duy nhất ở mức lược đồ);
- `feature_version` của mô hình khác của mã hiện tại;
- `ten_dac_trung` lưu trong tệp mô hình không khớp không gian hiện tại — tức
  là danh mục món đã đổi và phải huấn luyện lại;
- vector trong `user_preference_profiles` sai phiên bản hoặc thiếu chiều.

Âm thầm trả về điểm trung tính thì thực đơn vẫn sinh ra được, trông vẫn bình
thường, và không ai biết phần học máy đã ngừng hoạt động từ bao giờ.

### 12.1 Nút cổ chai hóa ra không phải mã

Việc **2** từng được xem là nút cổ chai, và phần kỹ thuật của nó đúng là khó:
hai bản trích đặc trưng **phải cho ra cùng một vector**, vì lệch nhau là mô
hình huấn luyện trên một không gian và suy luận trên một không gian khác — một
lỗi không bao giờ báo ra, vì mô hình vẫn chạy và vẫn trả về số.

Đã xử lý bằng kiểm chứng chéo: `tools/check_feature_parity.py` sinh tệp mẫu từ
CSDL (đầu vào + vector mong đợi), và `mobile/test/food_vector_parity_test.dart`
đối chiếu danh sách nhóm món, sáu tham số min–max và **từng chiều của từng
món**. Đã thử phủ định bằng cách làm lệch một chiều đi `1e-6`: bài kiểm đổ và
chỉ ra đúng món nào, chiều nào.

Ba cái bẫy gặp khi dịch, ghi ở đầu `ml/features.py`: `kcal` làm tròn khác nhau
giữa Dart và Python; ba chiều macro là tỷ lệ **năng lượng** chứ không phải tỷ
lệ gam; thứ tự sắp xếp tên nhóm món.

Việc **6** đã xong ở `ml/serve.py` — xem §12.0.2. `ml/train.py --kich-hoat`
đặt `is_active = 1` và hạ cờ của mọi mô hình khác **trong cùng giao dịch**,
còn `scaler_params` lưu đủ tham số để nạp lại mà không tính lại gì: tính lại
trung bình và độ lệch trên dữ liệu mới là một lỗi âm thầm làm điểm số lệch
dần theo thời gian.

Nhưng **nút cổ chai thật là việc 10**. Năm việc mã đã xong và chạy được;
chúng chỉ chưa cho ra con số nào, vì bảy nguồn tín hiệu đều trống. Việc 10 là
việc duy nhất có độ trễ tính theo tuần, nên nó phải chạy song song với mã, chứ
không chờ mã xong.

### 12.2 `popularity_score` — mốc so sánh từng suy biến

Phát hiện khi chạy `ml/evaluate.py` lần đầu: **cả 318 món đều có
`popularity_score = 0`**, vì cột này mới chỉ có `DEFAULT 0` mà chưa ai tính.

Hậu quả nghiêm trọng hơn vẻ ngoài của nó. §10.1 đặt `popularity` làm phương án
**bắt buộc phải vượt qua**, nên nếu nó bằng nhau ở mọi món thì nó không sắp
được thứ tự nào: mọi món hòa điểm, và `precision@5` thu được chỉ phản ánh
**cách phá hòa**. Con số vẫn in ra bình thường — đó mới là chỗ nguy hiểm, vì
nó biến câu hỏi nghiên cứu cốt lõi thành một phép so với nhiễu.
`ml/evaluate.py` giờ phát hiện và ghi rõ *"phép so này CHƯA có hiệu lực"* thay
vì in một con số trông có vẻ dùng được.

`ml/popularity.py` tính nó bằng **chặn dưới khoảng tin cậy Wilson** trên tỷ
lệ người thích, đếm **người dùng phân biệt** chứ không đếm lượt:

    n_thấy(món)  = số người có bất kỳ tín hiệu nào về món
    n_thích(món) = số người có ít nhất một tín hiệu dương

Đếm người vì một người ăn cùng một món hai mươi lần sẽ một mình đẩy món đó
lên đầu bảng nếu đếm lượt, trong khi "phổ biến" phải nghĩa là *nhiều người*
thích. Dùng Wilson vì tỷ lệ thuần cho kết luận sai với cỡ mẫu nhỏ: món 2/2 ra
1,00 và đứng trên món 90/100. Wilson trả lời đúng câu cần hỏi — *tỷ lệ thật
sự ít nhất là bao nhiêu* — nên 2/2 → 0,3424 còn 90/100 → 0,8256, và món ít
dữ liệu bị kéo về 0 một cách tự nhiên mà không cần đặt tay ngưỡng "tối thiểu
N người".

Món chưa có tín hiệu nhận 0. Đó là một lựa chọn, không phải sự thật: 0 ở đây
nghĩa là "chưa chứng minh được là phổ biến". Lấy trung bình danh mục cho
chúng thì sẽ **bịa ra** một độ phổ biến mà không ai từng thể hiện.

Mã đã xong, nhưng **giá trị vẫn là 0 cho tới khi có dữ liệu thật** — nó là
đại lượng suy ra từ hành vi, nên phụ thuộc việc 10.

### 12.3 Giao thức đánh giá ngoại tuyến — hai lần rò rỉ đã tìm ra

Hai lỗi dưới đây do **chốt canh rò rỉ** của `tools/check_ml_e2e.py` phát hiện
(§12.0). Cả hai đều không gây lỗi, không làm sai số chiều, và đều làm kết quả
**đẹp hơn thực tế** — tức là đúng loại lỗi mà một bài kiểm thông thường không
bắt được.

**Rò rỉ 1 — độ phổ biến tính trên cả fold kiểm tra.** Với nhãn ngẫu nhiên
hoàn toàn, `popularity` đạt nDCG@5 = 0,796 và AUC của mô hình nhảy từ 0,48
lên 0,67. Nguyên nhân: `foods.popularity_score` tính từ **mọi** tín hiệu, nên
một món mà chính người bị kiểm đã thích đã góp phần đẩy điểm phổ biến của nó
lên — "độ phổ biến" khi đó mang sẵn thông tin về nhãn của tập kiểm tra. Rò rỉ
vào cả phương án đối chứng *và* đặc trưng `mon.do_pho_bien` của mô hình.

Khi **phục vụ** thì không có rò rỉ: độ phổ biến tính từ quá khứ, dùng cho
tương lai. Rò rỉ chỉ xuất hiện trong đánh giá ngoại tuyến, nơi "quá khứ" và
"tương lai" bị cắt theo *người dùng* chứ không theo *thời gian*. Nên
`ml/evaluate.py` **dựng lại độ phổ biến từ riêng các fold huấn luyện** cho
từng fold, và ghi đè luôn vào cột đặc trưng tương ứng.

**Rò rỉ 2 — mẫu âm ngẫu nhiên nằm trong tập đánh giá.** Sau khi sửa rò rỉ 1,
`popularity` vẫn đạt nDCG@5 = 0,549 trên nhãn ngẫu nhiên. Nguyên nhân:
`random_neg` là món **chưa từng hiển thị** cho người đó, nên độ phổ biến của
nó bằng 0, và *bất cứ* phương án nào dùng độ phổ biến đều tách được mẫu âm
ngẫu nhiên khỏi tín hiệu thật mà **không cần biết gì về khẩu vị**.

Nên `random_neg` chỉ dùng để **huấn luyện**, không dùng để **đánh giá**. Nó
vốn không phải sở thích đã quan sát được mà là một phỏng đoán — §9 cho nó
trọng số 0,200, thấp nhất trong bảy nguồn, đúng vì vậy. Nhưng nó vẫn phải ở
trong tập huấn luyện: không có mẫu âm, mô hình chỉ thấy những món hệ thống đã
chọn để hiển thị và sẽ học cách tái tạo lại chính bộ lọc của hệ thống thay vì
học khẩu vị.

**Kiểm bằng AUC, không kiểm bằng nDCG.** Sau hai lần sửa, cả năm phương án
đều về AUC 0,46–0,50 trên nhãn ngẫu nhiên. nDCG@5 của chúng vẫn trải từ 0,35
đến 0,61 — và đó **không** phải dấu hiệu còn rò rỉ: nDCG@5 không có mức tình
cờ xác định, nó phụ thuộc độ dài danh sách của từng người và số món hòa điểm.
AUC thì có mức tình cờ là 0,5 bất kể phân bố nhãn. Đây là điều phải nhớ khi
đọc bảng kết quả thật: **chênh lệch nDCG giữa hai phương án chỉ có nghĩa khi
đọc cùng với AUC.**

---

## 13. Những gì KHÔNG làm, và vì sao

| Không làm | Lý do |
|---|---|
| Lọc cộng tác (collaborative filtering) | Cần nhiều người dùng. Đề cương xếp vào hướng phát triển |
| Phân cụm nhóm khẩu vị | Hướng phát triển — rút ngắn khởi đầu nguội khi đã có dữ liệu |
| Mạng nơ-ron | Dữ liệu bảng cỡ nhỏ; cây tăng cường gradient tốt hơn và giải thích được |
| Mô hình riêng từng người ở Giai đoạn 2 | Quá khớp, và vận hành hàng trăm mô hình không khả thi |
| Nhận diện món ăn từ ảnh | Hướng phát triển đã nêu trong đề cương |

Ghi rõ danh sách này trong báo cáo có ích: nó cho thấy các lựa chọn là **có
chủ ý**, không phải do thiếu sót.
