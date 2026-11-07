#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm tỷ số tương phản của bảng màu theo WCAG 2.1.

Vì sao cần một bộ kiểm riêng. Tương phản không đủ là loại lỗi **không ai
nhìn thấy khi thiết kế**: người làm có màn hình tốt, phòng sáng vừa, mắt
bình thường, nên chữ xám nhạt trên nền trắng vẫn đọc được với họ. Nó chỉ
thành vấn đề với người dùng thật, ngoài trời, trên màn hình rẻ, hoặc mắt
kém — tức là đúng những người không bao giờ ngồi cạnh để phản hồi.

Hai lỗi mà bộ này bắt được ngay lần chạy đầu:

    textSecondary #8A8B90 trên trắng      3,40:1  cần 4,50:1
    accent        #2AD2EE trên trắng      1,82:1  cần 4,50:1

`accent` còn tệ hơn khi đặt trên `accentSoft` (1,65:1) — và đó chính là nền
của hai trong năm chỗ đang dùng nó làm màu chữ.

## Ngưỡng của WCAG 2.1

    4,5:1   chữ thường (dưới 18,66 px đậm, hoặc dưới 24 px thường)   AA
    3,0:1   chữ lớn, và **mọi** thành phần đồ họa phải nhận ra được  AA
            (biểu tượng, đường viền ô nhập, thanh tiến độ)

Chữ của thành phần đã vô hiệu hóa được WCAG miễn trừ, nên bảng dưới ghi
`mien_tru=True` cho những cặp đó kèm lý do — miễn trừ phải nêu ra, không
được im lặng bỏ qua.

## Danh sách cặp màu là bản khai tay

Không dò được tự động cặp (màu chữ, màu nền) từ mã Dart: nền có thể do một
widget cha đặt cách đó mười tầng. Nên bảng `CAC_CAP` là bản khai tay, và
mỗi dòng ghi rõ chỗ dùng. Thêm một cách dùng mới thì phải thêm một dòng —
`check_docs_sync.py` giữ tài liệu khỏi lệch lược đồ bằng đúng cách này.

Chạy:
    python tools/check_contrast.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

BANG_MAU = ROOT / "mobile" / "lib" / "core" / "theme" / "app_colors.dart"

#: Ngưỡng AA của WCAG 2.1.
NGUONG_CHU_THUONG = 4.5
NGUONG_CHU_LON = 3.0
NGUONG_DO_HOA = 3.0


@dataclass(frozen=True)
class Cap:
    """Một cặp (màu trước, màu nền) đang dùng thật, kèm chỗ dùng."""

    truoc: str
    sau: str
    nguong: float
    cho_dung: str
    mien_tru: bool = False
    ly_do_mien_tru: str = ""


#: Mọi cặp màu đang dùng. Xem docstring: đây là bản khai tay.
#:
#: Ngưỡng của mỗi dòng theo **cách dùng thật**, không theo loại màu. Bốn màu
#: chất sinh năng lượng chẳng hạn vừa là ruột thanh tiến độ (nền là
#: `surfaceMuted`, ngưỡng 3:1) vừa — riêng `carb` — là màu chữ của nhãn BMI
#: trên mặt thẻ (ngưỡng 4,5:1). Gán một ngưỡng cho cả nhóm sẽ bỏ sót đúng
#: trường hợp chặt hơn.
CAC_CAP: tuple[Cap, ...] = (
    # ── Chữ trên ba loại nền ──
    Cap("textPrimary", "surface", NGUONG_CHU_THUONG, "chữ chính trên mặt thẻ"),
    Cap("textPrimary", "background", NGUONG_CHU_THUONG, "chữ chính trên nền trang"),
    Cap("textSecondary", "surface", NGUONG_CHU_THUONG,
        "chữ phụ trên mặt thẻ — bodyLarge/bodyMedium của app_theme"),
    Cap("textSecondary", "background", NGUONG_CHU_THUONG, "chữ phụ trên nền trang"),
    Cap("textSecondary", "surfaceMuted", NGUONG_CHU_THUONG,
        "chữ phụ trên vùng xám nhạt"),
    Cap("textOnDark", "ink", NGUONG_CHU_THUONG, "chữ trên nút đen"),

    # ── Màu nhấn: chữ, biểu tượng, ruột thanh ──
    Cap("accentInk", "surface", NGUONG_CHU_THUONG,
        "số và nhãn nhấn trên mặt thẻ — motivation_step, option_card"),
    Cap("accentInk", "background", NGUONG_CHU_THUONG, "số nhấn trên nền trang"),
    Cap("accentInk", "accentSoft", NGUONG_CHU_THUONG,
        "nhãn nhấn trên nền lơ nhạt — survey_intro_screen"),
    Cap("accentInk", "surfaceMuted", NGUONG_DO_HOA,
        "ruột thanh tiến độ trên rãnh xám — calculating_screen, progress_screen"),
    Cap("ink", "accentSoft", NGUONG_CHU_THUONG,
        "chữ đen trên khối lơ — cách DUY NHẤT dùng được màu lơ gốc"),

    # ── Bốn hướng vuốt. Ba trong bốn màu này là màu CHỮ (`_Stat` ở
    #    diary_screen, nhãn BMI ở progress_screen), nên ngưỡng là 4,5:1
    #    chứ không phải 3:1 như một đường viền.
    Cap("like", "surface", NGUONG_CHU_THUONG, "chữ `Còn lại` và nhãn BMI `Bình thường`"),
    Cap("dislike", "surface", NGUONG_CHU_THUONG, "chữ `Vượt` và nhãn BMI `Béo phì`"),
    Cap("unknown", "surface", NGUONG_CHU_THUONG, "nhãn BMI `Thiếu cân`"),
    Cap("neutral", "surface", NGUONG_DO_HOA, "viền và biểu tượng hướng bình thường"),

    # ── Bốn màu chất sinh năng lượng: ruột thanh trên rãnh `surfaceMuted` ──
    Cap("kcal", "surfaceMuted", NGUONG_DO_HOA, "ruột thanh năng lượng ở diary_screen"),
    Cap("protein", "surfaceMuted", NGUONG_DO_HOA, "ruột thanh đạm ở energy_summary_card"),
    Cap("carb", "surfaceMuted", NGUONG_DO_HOA, "ruột thanh bột đường"),
    Cap("fat", "surfaceMuted", NGUONG_DO_HOA, "ruột thanh béo"),
    #    `carb` còn là màu CHỮ của nhãn BMI `Thừa cân`, nên nó phải qua cả
    #    ngưỡng chữ — dòng dưới là dòng chặt hơn trong hai cách dùng.
    Cap("carb", "surface", NGUONG_CHU_THUONG, "nhãn BMI `Thừa cân` ở progress_screen"),

    # ── Miễn trừ, có nêu lý do ──
    Cap(
        "accent",
        "surface",
        NGUONG_DO_HOA,
        "chỉ còn là `seedColor` và `secondary` của ColorScheme",
        mien_tru=True,
        ly_do_mien_tru=(
            "Không còn bề mặt nào vẽ bằng màu này. Nó chỉ gieo ColorScheme và "
            "sinh ra `accentSoft`; mọi chữ, biểu tượng và ruột thanh đã chuyển "
            "sang `accentInk`. Màu lơ gốc chỉ dùng được làm NỀN với chữ đen "
            "(11,55:1), không bao giờ làm tiền cảnh trên nền sáng."
        ),
    ),
    Cap(
        "textTertiary",
        "surface",
        NGUONG_CHU_THUONG,
        "chữ mờ của mục đã vô hiệu hóa và đơn vị sau con số",
        mien_tru=True,
        ly_do_mien_tru=(
            "WCAG 1.4.3 miễn trừ chữ của thành phần đã vô hiệu hóa. Nếu màu "
            "này có ngày dùng cho chữ đang hoạt động thì phải bỏ miễn trừ."
        ),
    ),
    Cap(
        "border",
        "surface",
        NGUONG_DO_HOA,
        "đường kẻ phân cách giữa hai dòng",
        mien_tru=True,
        ly_do_mien_tru=(
            "WCAG 1.4.11 không áp cho đường trang trí thuần — bỏ đường kẻ đi "
            "thì không mất thông tin nào, vì các dòng đã cách nhau bằng khoảng "
            "trắng. Viền ô NHẬP thì không được miễn trừ."
        ),
    ),
)


def doc_bang_mau() -> dict[str, tuple[int, int, int]]:
    """Đọc các hằng `Color(0xFFRRGGBB)` trong `app_colors.dart`."""
    text = BANG_MAU.read_text(encoding="utf-8")
    mau: dict[str, tuple[int, int, int]] = {}
    for m in re.finditer(
        r"static const (\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{8})\)", text
    ):
        ten, hex8 = m.group(1), m.group(2)
        gia_tri = int(hex8, 16)
        mau[ten] = (
            (gia_tri >> 16) & 0xFF,
            (gia_tri >> 8) & 0xFF,
            gia_tri & 0xFF,
        )
    # Bí danh trỏ sang hằng khác, ví dụ `primary = ink`.
    for m in re.finditer(r"static const (\w+)\s*=\s*(\w+);", text):
        ten, goc = m.group(1), m.group(2)
        if goc in mau and ten not in mau:
            mau[ten] = mau[goc]
    return mau


def _tuyen_tinh(kenh: int) -> float:
    c = kenh / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def do_sang(rgb: tuple[int, int, int]) -> float:
    """Độ sáng tương đối theo WCAG 2.1."""
    r, g, b = (_tuyen_tinh(k) for k in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def tuong_phan(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = do_sang(a), do_sang(b)
    sang, toi = max(la, lb), min(la, lb)
    return (sang + 0.05) / (toi + 0.05)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def main() -> int:
    _env.in_utf8()
    print("Kiểm tương phản bảng màu — WCAG 2.1 AA")
    print("=" * 72)

    mau = doc_bang_mau()
    print(f"Đọc được {len(mau)} màu từ {BANG_MAU.relative_to(ROOT)}\n")

    loi: list[str] = []
    thieu: list[str] = []
    dat = 0
    mien = 0

    for cap in CAC_CAP:
        if cap.truoc not in mau or cap.sau not in mau:
            con = [t for t in (cap.truoc, cap.sau) if t not in mau]
            thieu.append(f"{cap.truoc} trên {cap.sau}: chưa khai {', '.join(con)}")
            continue

        ty_so = tuong_phan(mau[cap.truoc], mau[cap.sau])
        nhan = f"{cap.truoc} trên {cap.sau}"
        so = f"{ty_so:5.2f}:1 cần {cap.nguong:.1f}:1"

        if ty_so >= cap.nguong:
            dat += 1
            print(f"  ✓ {nhan:34s} {so}")
        elif cap.mien_tru:
            mien += 1
            print(f"  ~ {nhan:34s} {so}  MIỄN TRỪ")
            print(f"      {cap.ly_do_mien_tru}")
        else:
            loi.append(
                f"{nhan} = {ty_so:.2f}:1, cần {cap.nguong:.1f}:1 "
                f"({_hex(mau[cap.truoc])} trên {_hex(mau[cap.sau])}) "
                f"— {cap.cho_dung}"
            )
            print(f"  ✗ {nhan:34s} {so}")
            print(f"      {cap.cho_dung}")

    print("\n" + "=" * 72)
    if thieu:
        print(f"{len(thieu)} cặp không kiểm được:")
        for x in thieu:
            print("  -", x)
    if loi:
        print(f"{dat} cặp đạt, {mien} miễn trừ, {len(loi)} CẶP SAI:")
        for x in loi:
            print("  -", x)
        return 1
    if thieu:
        return 1
    print(f"Tất cả {dat} cặp đạt chuẩn AA, {mien} cặp được miễn trừ có nêu lý do.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
