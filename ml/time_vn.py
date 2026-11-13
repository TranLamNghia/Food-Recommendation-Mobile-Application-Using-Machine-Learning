# -*- coding: utf-8 -*-
"""Một đồng hồ duy nhất cho phần Python: Asia/Ho_Chi_Minh.

Bản Python của `backend/Api/Time/DongHo.cs`, và tồn tại vì cùng một lý do.
Ba tầng của hệ thống từng đọc ba đồng hồ khác nhau: cơ sở dữ liệu dùng
`CURRENT_TIMESTAMP` và `NOW()` ở 27 cột, cả hai trả theo
`@@session.time_zone` mặc định là `SYSTEM` tức giờ Việt Nam; ứng dụng Flutter
dùng `DateTime.now()`, giờ địa phương; còn Backend dùng `DateTime.UtcNow`,
**lệch 7 giờ so với cả hai**. Hậu quả im lặng: `users.created_at` do Backend
ghi lùi 7 giờ so với dòng do script Python ghi, nên sắp theo `created_at` là
trộn hai đồng hồ.

Phần Python tới giờ vẫn tránh được chuyện đó vì nó **chưa bao giờ tự đọc
đồng hồ** — mọi dấu thời gian đều do MySQL sinh bằng `NOW()`. `ml/api.py` là
chỗ đầu tiên cần một dấu thời gian ở phía ứng dụng (`updatedAt` trong phản
hồi JSON, mã phiên huấn luyện), nên nó phải có một chỗ duy nhất để đọc giờ,
chứ không phải mỗi nơi gọi `datetime.now()` một kiểu.

**Vì sao không dùng `datetime.now()` thuần:** nó trả giờ địa phương của máy
đang chạy. Trên máy làm đồ án thì đúng, trên một máy chủ đặt ở múi giờ khác
thì sai, và cái sai đó không lộ ra ở đâu — chỉ là các dấu thời gian lệch đi
vài giờ so với dữ liệu MySQL ghi cùng lúc.

**Vì sao không dùng UTC:** đổi sang UTC phải sửa 27 giá trị mặc định của lược
đồ, mọi `NOW()` trong `tools/`, và cả dữ liệu đã ghi. Giờ Việt Nam là thứ cơ
sở dữ liệu **đang** lưu.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _mui_gio() -> ZoneInfo:
    """`Asia/Ho_Chi_Minh`, hoặc dừng hẳn kèm cách sửa.

    Trên Windows, `zoneinfo` cần gói `tzdata` vì hệ điều hành không mang sẵn
    cơ sở dữ liệu múi giờ IANA. Thiếu nó thì `ZoneInfo` ném
    `ZoneInfoNotFoundError`, và lùi về giờ địa phương ở đây là đúng kiểu hỏng
    mà cả tệp này sinh ra để chặn.
    """
    try:
        return ZoneInfo("Asia/Ho_Chi_Minh")
    except ZoneInfoNotFoundError as e:  # pragma: no cover
        raise RuntimeError(
            "Không tìm thấy múi giờ Asia/Ho_Chi_Minh. Trên Windows cần gói "
            "cơ sở dữ liệu múi giờ: pip install tzdata"
        ) from e


MUI_GIO = _mui_gio()


def bay_gio() -> datetime:
    """Thời điểm hiện tại theo Asia/Ho_Chi_Minh, có mang thông tin múi giờ."""
    return datetime.now(MUI_GIO)


def hom_nay() -> date:
    """Ngày lịch hiện tại theo Asia/Ho_Chi_Minh.

    Phải tính từ `bay_gio()` chứ không phải `date.today()`: `date.today()`
    đọc giờ địa phương của máy, nên trong khoảng 00:00–07:00 giờ Việt Nam,
    một máy chạy theo UTC sẽ trả về **ngày hôm trước**. Đúng ngày sinh nhật
    thì tuổi tính ra lệch một năm.
    """
    return bay_gio().date()
