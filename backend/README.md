# Backend — ASP.NET Core Web API

Hiện thực đặc tả `docs/API_SPECIFICATION.md`. Đợt 1 và 2 của thứ tự ở §10.2 đã xong: **9 endpoint**.

| Mục | Endpoint | |
|---|---|---|
| 7.1.1 | `POST /auth/register` | 🌐 |
| 7.1.2 | `POST /auth/login` | 🌐 |
| 7.1.3 | `POST /auth/refresh` | 🌐 |
| 7.1.4 | `GET /auth/me` | 🔒 |
| 7.2.1 | `GET /profile` | 🔒 |
| 7.2.2 | `PUT /profile` | 🔒 |
| 7.2.3 | `GET /profile/nutrition-targets` | 🔒 |
| 7.2.4 | `GET /profile/conditions` | 🔒 |
| 7.2.5 | `PUT /profile/conditions` | 🔒 |

Còn 34 endpoint công khai và 4 endpoint nội bộ chưa làm — xem `docs/API_SPECIFICATION.md` §6.

---

## Chạy

```bash
python tools/run_backend.py            # http://localhost:5000/api/v1
```

Tệp đó nối `.env` vào tiến trình `dotnet`, và sinh `JWT_SIGNING_KEY` vào `.env` nếu chưa có.

**Không có khóa ký mặc định trong mã nguồn, có chủ ý.** Repo này là repo công khai; một khóa nằm trong tệp được commit thì mọi ai đọc được repo đều ký được token hợp lệ cho mọi tài khoản. Máy chủ **dừng ngay lúc khởi động** nếu thiếu khóa hoặc khóa ngắn hơn 32 ký tự, chứ không chạy với khóa rỗng — chạy được với khóa rỗng thì mọi thứ trông bình thường cho tới khi có người thử.

Cần MySQL đang chạy, CSDL `nutrition_rec` đã dựng theo `db/schema.sql`.

---

## Ba lớp phép kiểm, và vì sao cần cả ba

```
python tools/check_be_parity.py     Bước 1: C# ↔ Dart ↔ Python     76 phép kiểm
python tools/smoke_backend.py       9 endpoint trên MySQL thật     93 phép kiểm
python tools/gen_entities.py        thực thể + ENUM C# ↔ db/schema.sql
```

Ba lớp này bắt ba loại lỗi khác nhau, và không lớp nào thay được lớp khác.

**`check_be_parity.py` — số học.** Bước 1 được hiện thực **ba lần**: `Api/Nutrition/NutritionTargets.cs`, `mobile/lib/data/models/health_profile.dart`, và bản tham chiếu trong `tools/gen_buoc1_cases.py`. Ba bản chạy ở ba tầng và không bao giờ gặp nhau, nên khi chúng lệch thì không gì báo ra: ứng dụng hiện một hạn mức năng lượng, máy chủ sinh thực đơn theo một hạn mức khác, và cả hai con số đều trông hợp lý.

Bộ kiểm này bắt được ba chỗ lệch có thật ngay lần chạy đầu — macro 17/60/23 ở Dart đối lại 15/60/25 trong CSDL và đặc tả; `mealDistribution` 25/40/27/8 trong đặc tả đối lại điểm giữa 27.5/37.5/27.5/7.5 ở `meal_plan.dart`; và `bmiCategory: "normal"` cho BMI 23.15, sai theo chính ngưỡng châu Á 23/25 mà hệ thống dùng. Không chỗ nào trong ba chỗ đó trông sai khi đọc.

`tools/test_be_parity.py` thử phủ định chính bộ kiểm ấy: tiêm 14 lỗi vào tệp ca thử rồi đòi cả hai bộ phải thất bại. Nó chỉ sửa tệp **sinh ra**, không bao giờ chạm mã nguồn — bản đầu sửa thẳng hằng số trong `NutritionTargets.cs` rồi khôi phục trong `finally`, và khi phiên làm việc bị cắt giữa chừng, `finally` không chạy: lỗi tiêm nằm lại trong mã thật.

**`smoke_backend.py` — những gì chỉ sai khi có CSDL và có mạng.** Ánh xạ tên cột, kiểu dữ liệu, giao dịch, vỏ lỗi, claim trong JWT. Nó tạo một tài khoản với email ngẫu nhiên rồi xóa ở cuối; `ON DELETE CASCADE` dọn phần còn lại.

Nó đã bắt bốn lỗi mà trình biên dịch không thấy: `food_tags` thiếu khóa chính (khai ở cấp bảng, và thiếu nó thì **mọi** endpoint trả 500, không chỉ endpoint chạm vào bảng đó); `CHAR(36)` đọc ra `System.Guid` thay vì `string`; khóa ngoại tự trỏ `replaced_by` vỡ vì EF xếp `UPDATE` trước `INSERT`; và một phép kiểm trong chính tệp thử gán cứng ngày sinh nên đổi kết quả vào đúng một ngày trong năm.

**`gen_entities.py` — 24 lớp thực thể sinh từ `db/schema.sql`.** 225 cột; gõ tay thì một cột sai tên hoặc sai tính cho phép `NULL` không gây lỗi biên dịch nào — nó gây một `MySqlException` lúc chạy, ở một endpoint có thể không ai gọi tới trong nhiều tuần. Chạy không có cờ thì nó **soát** mã đang có; `--write` thì sinh lại.

Phép kiểm 5 của nó đối chiếu bốn mảng trong `Api/Profile/ProfileDtos.cs` — `Enums.Gender`, `.ActivityLevel`, `.Goal`, `.Severity` — với tập giá trị ENUM của `health_profiles` và `user_conditions`, **giữ cả thứ tự** vì MySQL lưu ENUM theo thứ số. Bốn mảng đó là tầng duy nhất trả `400 VALIDATION_FAILED` kèm tên trường, nên khi chúng lệch khỏi lược đồ thì API từ chối đúng thứ CSDL cho phép, và cả hai bên vẫn tự nhất quán nên không có gì báo ra. Phép kiểm soát **hai chiều**: thêm một mảng vào `Enums` mà không khai trong `ENUM_CS` cũng là lệch — nó trông như được soát mà thật ra không.

---

## Bốn quyết định ảnh hưởng tới mọi thứ về sau

### Một múi giờ duy nhất: Asia/Ho_Chi_Minh

`Api/Time/DongHo.cs` là chỗ duy nhất đọc đồng hồ. Mọi cột `DATETIME` lấy `DongHo.BayGio`, mọi cột `DATE` và mọi phép tính theo ngày lịch lấy `DongHo.HomNay`.

Trước đó ba tầng đọc ba đồng hồ: CSDL dùng `CURRENT_TIMESTAMP` ở 27 cột và `NOW()` trong mọi `tools/*.py`, cả hai trả theo `@@session.time_zone` mặc định là `SYSTEM` tức giờ Việt Nam; app Flutter dùng `DateTime.now()`, giờ địa phương; còn Backend dùng `DateTime.UtcNow`, **lệch 7 giờ so với cả hai**. Hậu quả im lặng: `users.created_at` do Backend ghi lùi 7 giờ so với dòng do `check_ml_e2e.py` ghi, nên sắp theo `created_at` là trộn hai đồng hồ. Và "hôm nay" tính bằng UTC lùi một **ngày** trong khoảng 00:00–07:00, nên đúng ngày sinh nhật app hiện 23 tuổi còn `GET /profile` trả `age: 22`.

Chọn giờ Việt Nam chứ không chọn UTC vì đó là thứ CSDL **đang** lưu — đổi sang UTC thì phải sửa 27 giá trị mặc định của lược đồ, mọi `NOW()` trong `tools/`, và dữ liệu đã ghi.

**Một ngoại lệ, và nó bắt buộc:** `nbf`/`exp` của JWT là số giây từ mốc Unix nên luôn theo UTC (RFC 7519 §2). `TokenService.CreateAccessToken` là chỗ duy nhất còn `DateTime.UtcNow`. Đưa giờ Việt Nam vào đó thì `nbf` nằm 7 giờ ở tương lai và với `ClockSkew = TimeSpan.Zero` thì **mọi** token bị từ chối ngay lúc vừa phát.

### Chặn tài khoản bị khóa bằng bộ lọc toàn cục, không bằng phép kiểm từng chỗ

`TaiKhoanConHoatDongFilter` đăng ký trong `MvcOptions.Filters`, nên endpoint mới được bảo vệ **mặc định**; bỏ bảo vệ phải tường minh bằng `[AllowAnonymous]`. Trước đó `is_active` được kiểm ở `/auth/login`, `/auth/refresh` và `/auth/me` nhưng **không** ở bất cứ endpoint nào của `/profile`, nên tài khoản bị khóa vẫn đọc ghi hồ sơ được tới một giờ. Còn 38 endpoint chưa làm, và một phép kiểm phải nhớ gõ lại ở từng chỗ là một phép kiểm sẽ bị quên.

`/auth/login` và `/auth/refresh` giữ phép kiểm riêng, và đó không phải trùng lặp: chúng `[AllowAnonymous]` và xác thực bằng mật khẩu hoặc refreshToken, nên không có claim `sub` để bộ lọc tra.

### Không dùng EF Core Migrations

`db/migrations/applied/README.md` ghi rõ: **`db/schema.sql` là trạng thái hiện hành của lược đồ.** Bật Migrations là tạo ra nguồn quyền lực thứ hai cho cùng một lược đồ, và hai cái sẽ lệch — `tools/check_schema_sql.py` bắt được, nhưng chỉ *sau khi* đã lệch.

Đổi lược đồ thì theo đúng ba bước:

```bash
# 1. viết db/migrations/00N_ten.sql, rồi chạy
python tools/run_sql.py db/migrations/00N_ten.sql --database nutrition_rec
# 2. gộp vào db/schema.sql, cập nhật con số ở đầu tệp
# 3. sinh lại thực thể
python tools/gen_entities.py --write
```

Thêm một bảng còn lan ra bốn tài liệu nữa — `DATABASE_DESIGN.md`, `database_erd.html`, `ERD_REVIEW.md`, và con số mong đợi trong `tools/test_schema_build.py`. `python tools/check_docs_sync.py` liệt kê đúng từng chỗ.

### `GuidFormat=None` trong chuỗi kết nối

Lược đồ có 45 cột `CHAR(36)`, cả 45 đều là UUID. MySqlConnector mặc định `GuidFormat=Char36`, nên nó trả `System.Guid` cho mọi cột `CHAR(36)` — còn thực thể khai `string`, và EF ném `InvalidCastException` ở lượt **đọc** đầu tiên. `Program.cs` chuẩn hóa chuỗi kết nối để buộc `GuidFormat=None`, kể cả chuỗi do người dùng tự khai qua `MYSQL_CONNECTION`.

Giữ `string` chứ không đổi thực thể sang `Guid`, vì đặc tả §2.3 nói khóa chính là "chuỗi UUID 36 ký tự" và mọi truy vấn trong hệ thống — kể cả `tools/*.py` và `ml/*.py` — so chúng như chuỗi.

---

## Cấu trúc

```
Api/
├── Program.cs              JWT, vỏ lỗi §2.5, chuỗi kết nối, bộ lọc toàn cục
├── Data/AppDbContext.cs    24 bảng          ← SINH TỰ ĐỘNG
├── Entities/               24 lớp           ← SINH TỰ ĐỘNG
├── Http/
│   ├── ApiError.cs         vỏ lỗi + danh mục 21 mã lỗi của §4
│   └── TaiKhoanConHoatDong.cs   chặn tài khoản bị khóa ở MỌI endpoint
├── Time/DongHo.cs          một múi giờ duy nhất: Asia/Ho_Chi_Minh
├── Nutrition/              Bước 1: BMI, BMR, TDEE, macro, phân bổ bữa
├── Auth/                   7.1.1 – 7.1.4
└── Profile/                7.2.1 – 7.2.5
Api.Tests/                  44 phép kiểm, không cần CSDL
```

Hai thư mục đánh dấu **SINH TỰ ĐỘNG** không sửa tay — sửa `db/schema.sql` rồi chạy lại `tools/gen_entities.py --write`.
