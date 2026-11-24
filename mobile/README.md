# nutrition_app

Ứng dụng khuyến nghị thực đơn dinh dưỡng cá nhân hóa — phần giao diện Flutter.

## Hai chế độ, và cách phân biệt mã

App chạy được ở **hai chế độ**, và đó là chủ ý:

| Chế độ | Dữ liệu từ đâu | Dùng khi nào |
|---|---|---|
| **Trực tuyến** | backend ASP.NET Core → MySQL → ML service | chạy thật |
| **Ngoại tuyến** | thuật toán bản Dart + dữ liệu giả, ngay trên máy | không có server: demo, bảo vệ, chạy test |

Chế độ ngoại tuyến **không phải mã chết**. `test/step1_parity_test.dart` và
`test/step4_parity_test.dart` so từng con số của bản Dart với bản Python, nên
nó là một trong ba bản cài đặt của thuật toán được giữ ngang bằng — và là cái
phao cho hôm bảo vệ nếu máy không ra được mạng.

### Quy ước nhãn

Mỗi tệp hoặc mỗi phương thức thuộc **logic nội bộ** mở đầu bằng **một dòng**:

```dart
// OFFLINE: the Dart copy of step 4, held in parity with ml/menu_builder.py.
```

Mã gọi server được dán nhãn đối xứng, để ở những tệp có cả hai thì nhìn là thấy:

```dart
// ONLINE: POST /auth/login — specification §7.1.2.
```

Liệt kê toàn bộ vùng ngoại tuyến bằng một câu lệnh:

```bash
grep -rn "// OFFLINE:" mobile/lib
grep -rn "// ONLINE:"  mobile/lib
```

Quy tắc: `data/recommender/`, `data/rules/` và `data/mock/` là **ngoại tuyến
toàn bộ** — nhãn đặt ở đầu tệp. `data/api/` là **trực tuyến toàn bộ**.
`data/session.dart` có cả hai, nên nhãn đặt trên từng phương thức.

## Chạy

```bash
flutter pub get
flutter test                  # 245 test
flutter run                   # mặc định: chế độ ngoại tuyến
```

Trỏ vào server thật bằng biến môi trường lúc biên dịch:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5055/api/v1
```

`10.0.2.2` là địa chỉ máy chủ nhìn từ máy ảo Android — `localhost` trong máy
ảo là chính nó. Không truyền `API_BASE_URL` thì app ở chế độ ngoại tuyến.

Khởi động hai service phía sau:

```bash
python tools/run_ml_service.py
python tools/run_backend.py
```

## Kiểm chứng tầng mạng trên socket thật

`flutter test` dùng bộ vận chuyển giả, nên nó chỉ chứng minh app tự nhất quán
với chính mình. Để chứng minh app và server **đồng ý với nhau**, có một công
cụ dòng lệnh chạy chính tầng API của app qua socket thật:

```bash
cd mobile && dart run tool/smoke_api.dart   # 117 phép kiểm
```

Lưu ý một ràng buộc dễ phá mà khó thấy: `dart run` biên dịch **Dart thuần**, không thấy engine của Flutter. Nên `data/api/` và các model nó dùng (`FoodBrief`) **không được import `package:flutter/...`** — chỉ một trường `Color` trong model là công cụ này hết biên dịch được. Phần trình bày (màu, emoji) nằm ở `core/dish_look.dart` dưới dạng extension.

Nó **để lại một tài khoản** mỗi lần chạy, `dart-*@example.test`, vì §7.1
không có endpoint nào xóa tài khoản. Dọn bằng:

```bash
python -c "import sys; sys.path.insert(0, 'tools'); from smoke_backend import delete_accounts; delete_accounts('dart-xxxx@example.test')"
```
