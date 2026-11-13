# -*- coding: utf-8 -*-
"""Nội dung Chương 2 — Phân tích thiết kế hướng đối tượng.

## Nguyên tắc: phần nào SUY RA ĐƯỢC thì không gõ lại

Chương 2 gồm hai loại nội dung, và chúng được đối xử khác nhau:

**Văn xuôi** — mô tả nghiệp vụ, diễn giải ERD, lý do thiết kế — nằm thành
hằng chuỗi trong tệp này.

**Bảng** — diễn giải quy trình, danh sách người dùng và yêu cầu, danh sách
Actor và Use case, 18 kịch bản — được **suy ra từ `us_data.py` và
`flowchart_data.py`**, là chính hai tệp đã sinh ra phần User story của báo
cáo và 18 flowchart trong `Diagram.mdj`.

Gõ lại chúng ở đây là tạo nguồn thứ hai cho cùng một thứ. Và chỗ lệch đã
từng xảy ra thật: hai use case mang tên khác nhau giữa `us_data.py` và
`Diagram.mdj` trong nhiều tuần — "Khai báo thông tin cá nhân và tình trạng
sức khỏe" trên User story đối lại "Điền hoặc Chọn thông tin cá nhân phù hợp
với sức khỏe cá nhân" trên sơ đồ Use case. Không gây lỗi gì; chỉ làm hội
đồng đọc mục 1.4 rồi đọc mục 2.2.2 và thấy hai cái tên cho một chức năng.
`tools/check_flowchart.py` phép kiểm 6 nay soát cả ba nguồn.

## Kịch bản suy ra từ flowchart thế nào

`flowchart_lib.py` quy ước **cột 0 là trục chính, cột khác 0 là nhánh lỗi
hoặc nhánh phụ**. Nhờ quy ước đó, luồng chính và luồng ngoại lệ tách ra
được một cách máy móc:

    luồng chính    = đi từ khối `Bắt đầu`, ở mỗi khối quyết định luôn chọn
                     cạnh có đích nằm ở cột 0
    luồng ngoại lệ = mỗi cạnh có đích nằm ở cột khác 0, kèm nhãn điều kiện
                     và chỗ nó quay về

Vì vậy kịch bản trong báo cáo **không thể** mô tả một luồng khác với luồng
trên sơ đồ: cả hai đọc từ cùng một `SO_DO`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flowchart_data import SO_DO  # noqa: E402
from us_data import STORIES  # noqa: E402

#: Vị trí các trường trong một khối của `SO_DO`:
#: `(id, kiểu, CỘT, dòng, chữ)`. **Cột là phần tử 2, dòng là phần tử 3** — và
#: quy ước trục chính nằm ở CỘT 0 là thứ cả `luong_chinh` và `luong_ngoai_le`
#: dựa vào. Bản đầu tôi lấy phần tử 3, tức lọc theo DÒNG 0: chỉ khối `Bắt đầu`
#: có dòng 0, nên luồng chính ra rỗng và mọi cạnh đều bị tính là ngoại lệ —
#: kịch bản sinh ra vẫn trông như một danh sách câu hợp lệ, chỉ là của một
#: luồng không tồn tại.
COT, DONG, CHU = 2, 3, 4

#: Nhánh chính tại những khối quyết định mà **quy ước ô lưới không quyết
#: được**. Khóa là (mã sơ đồ, id khối quyết định), giá trị là nhãn cạnh.
#:
#: Chỉ có đúng một chỗ, và nó là chỗ sơ đồ có vòng lặp thật. FC12 "Theo dõi
#: tình trạng cơ thể" vẽ cả việc ghi thêm cân nặng: khối "Người dùng ghi cân
#: nặng mới?" có nhánh "có" đi xuống khối gửi (dòng 7) rồi quay ngược về khối
#: vẽ đồ thị (dòng 5), và nhánh "không" đi tới Kết thúc (dòng 11). Cả hai đều
#: ở cột 0 và cả hai đều có dòng lớn hơn, nên luật "dòng nhỏ nhất kế tiếp"
#: chọn nhánh "có" và luồng chính quay vòng mãi.
#:
#: Khai tay ở đây chứ không đoán bằng thêm một luật — chẳng hạn "ưu tiên
#: nhánh tới Kết thúc" sẽ hỏng ngay ở FC07, nơi nhánh ngắn "đã có thực đơn
#: sẵn" mới là nhánh phụ và nhánh dài mới là luồng chính. Chỗ nào lưới không
#: nói được thì người viết nói, và nói ở một nơi đọc được.
NHANH_CHINH: dict[tuple[str, str], str] = {
    ("FC12", "ghimoi"): "không",
}

#: Hai tác nhân, đúng hai `UMLActor` trong `Diagram.mdj`.
TAC_NHAN = ("Người dùng", "Quản trị viên")

#: Kiểu khối → cách gọi trong câu kịch bản. `term` không có mặt: nó là khối
#: Bắt đầu / Kết thúc, không phải một bước người hay hệ thống làm.
VAI_KHOI = {
    "input": "Người dùng",
    "disp": "Hệ thống",
    "proc": "Hệ thống",
    "db": "Hệ thống",
    "call": "Hệ thống",
    "dec": "Hệ thống",
}


# ── suy ra từ flowchart ───────────────────────────────────────────────────


def _tra_cuu(ma_so_do: str) -> tuple[str, dict[str, tuple], list[tuple]]:
    for ma, ten, khoi, canh in SO_DO:
        if ma == ma_so_do:
            return ten, {k[0]: k for k in khoi}, list(canh)
    raise KeyError(f"không có sơ đồ {ma_so_do!r} trong flowchart_data.SO_DO")


def _duong_truc(ma_so_do: str) -> tuple[list[str], set[tuple[str, str]]]:
    """Trả về (dãy id khối trên luồng chính, tập cạnh đã đi).

    Luật chọn nhánh ở một khối quyết định, theo đúng quy ước ô lưới:

    1. chỉ xét cạnh có đích nằm ở **cột 0** — cột khác 0 là nhánh lỗi;
    2. trong số đó chọn đích có **dòng nhỏ nhất mà vẫn lớn hơn dòng hiện
       tại** — tức bước kế tiếp đi xuống trục, không phải bước nhảy vượt.

    Luật 2 là cần, không phải để cho đẹp. Ở FC07 khối "Đã có thực đơn cho
    ngày này?" có **hai** nhánh cùng nằm ở cột 0: "có" nhảy thẳng xuống khối
    hiện thực đơn ở dòng 15, "chưa" đi tiếp xuống khối sinh thực đơn ở dòng
    4. Lấy cạnh đầu tiên gặp được thì luồng chính của use case quan trọng
    nhất trong đồ án chỉ còn bốn bước và bỏ mất toàn bộ bốn bước sinh thực
    đơn — mà vẫn trông như một kịch bản hoàn chỉnh.
    """
    _ten, khoi, canh = _tra_cuu(ma_so_do)
    ra_canh: dict[str, list[tuple]] = {}
    for c in canh:
        ra_canh.setdefault(c[0], []).append(c)

    dau = next((k for k, v in khoi.items() if v[1] == "term" and v[COT] == 0), None)
    if dau is None:
        raise ValueError(f"{ma_so_do}: không tìm thấy khối Bắt đầu")

    duong: list[str] = [dau]
    da_di: set[tuple[str, str]] = set()
    hien = dau
    while True:
        canh_ra = list(ra_canh.get(hien, ()))
        if not canh_ra:
            break
        # Chặn vòng lặp. Luật đi-theo-cạnh-duy-nhất ở khối không-quyết-định
        # có thể đi vào vòng: FC08 có "Hiện lỗi" → quay lại khối chọn món, và
        # không có chốt này thì `_duong_truc` quay mãi. Treo thì còn thấy;
        # tệ hơn là nó dừng ở một bước nào đó rồi cho ra một kịch bản ngắn
        # trông vẫn hợp lệ.
        if len(duong) > len(khoi) + 1:
            raise ValueError(
                f"{ma_so_do}: luồng chính đi quá {len(khoi)} khối — sơ đồ có "
                f"vòng mà luật chọn nhánh không thoát ra được. "
                f"Đường đã đi: {' → '.join(duong)}"
            )
        if khoi[hien][1] != "dec":
            # Khối không phải quyết định thì chỉ có một đường đi tiếp — đi
            # theo nó, KHÔNG xét cột.
            #
            # Phải vậy vì cột 0 không phải bất biến của luồng chính: ở FC15,
            # khối "Nhắc rõ: đây là XÓA MỀM…" là một ô ghi chú đặt bên phải
            # ở cột 1 nhưng nằm ngay giữa luồng chính. Lọc theo cột ở mọi
            # khối thì luồng chính của use case đó dừng ở bước 6 và mất ba
            # bước cuối — ghi cơ sở dữ liệu, ghi vết, hiện danh sách.
            chon = canh_ra[0]
        elif (ma_so_do, hien) in NHANH_CHINH:
            nhan_can = NHANH_CHINH[(ma_so_do, hien)]
            khop = [c for c in canh_ra if len(c) > 2 and c[2] == nhan_can]
            if not khop:
                raise ValueError(
                    f"{ma_so_do}: NHANH_CHINH khai nhánh {nhan_can!r} tại "
                    f"khối {hien!r}, nhưng khối đó không có cạnh nào mang "
                    f"nhãn ấy. Nhãn đang có: "
                    f"{[c[2] for c in canh_ra if len(c) > 2]}"
                )
            chon = khop[0]
        else:
            tiep = [
                c
                for c in canh_ra
                if khoi[c[1]][COT] == 0
                and khoi[c[1]][DONG] > khoi[hien][DONG]
                and c[1] not in duong
            ]
            if not tiep:
                break
            chon = min(tiep, key=lambda c: khoi[c[1]][DONG])
        da_di.add((chon[0], chon[1]))
        hien = chon[1]
        duong.append(hien)
        if khoi[hien][1] == "term":
            break
    return duong, da_di


def luong_chinh(ma_so_do: str) -> list[str]:
    """Các bước của luồng chính, bỏ hai khối Bắt đầu và Kết thúc."""
    _ten, khoi, _canh = _tra_cuu(ma_so_do)
    duong, _ = _duong_truc(ma_so_do)
    return [khoi[k][CHU] for k in duong if khoi[k][1] != "term"]


def luong_ngoai_le(ma_so_do: str) -> list[str]:
    """Mọi nhánh rẽ khỏi luồng chính, mỗi nhánh một câu.

    Lấy theo **cạnh mà luồng chính không đi**, không lấy theo cột: ở FC07
    nhánh "đã có thực đơn sẵn" nằm ngay trên cột 0 nhưng vẫn là một luồng
    thay thế, và lọc theo cột sẽ bỏ mất nó.
    """
    _ten, khoi, canh = _tra_cuu(ma_so_do)
    _duong, da_di = _duong_truc(ma_so_do)
    ra_canh: dict[str, list[tuple]] = {}
    for c in canh:
        ra_canh.setdefault(c[0], []).append(c)

    ra: list[str] = []
    for c in canh:
        nguon, dich = c[0], c[1]
        if (nguon, dich) in da_di:
            continue
        # Chỉ kể nhánh rẽ từ một khối QUYẾT ĐỊNH. Cạnh quay về của một khối
        # lỗi (ví dụ "Hiện lỗi …" → "Nhập lại") là phần đuôi của nhánh đã
        # kể, không phải một nhánh mới.
        if khoi[nguon][1] != "dec":
            continue
        nhan = c[2] if len(c) > 2 else ""
        dieu_kien = khoi[nguon][CHU].rstrip("?")
        viec = khoi[dich][CHU]
        ve = [x[1] for x in ra_canh.get(dich, ())]
        if ve and khoi[ve[0]][1] == "term":
            duoi = " rồi dừng luồng"
        elif ve:
            duoi = f" rồi quay lại bước “{khoi[ve[0]][CHU]}”"
        else:
            duoi = ""
        if nhan:
            ra.append(f"{dieu_kien} — {nhan}: {viec}{duoi}.")
        else:
            ra.append(f"{dieu_kien}: {viec}{duoi}.")
    return ra


def bang_dien_giai_quy_trinh() -> list[tuple[str, str, str, str, str]]:
    """Bảng “Diễn giải quy trình nghiệp vụ” — một dòng mỗi use case.

    Năm cột theo đúng biểu mẫu: STT · Hoạt động · Input Data · Output Data ·
    End User.

    `Input Data` lấy từ khối `input` đầu tiên của sơ đồ, hoặc từ khối `proc`
    đầu tiên nếu luồng không hỏi gì người dùng (ví dụ "Xem thực đơn ngày" —
    người dùng chỉ mở màn hình). `Output Data` lấy từ khối `disp` cuối cùng
    trên trục chính: nó là thứ người dùng thật sự nhận được. `End User` lấy
    từ tác nhân trong `us_data.py`.
    """
    theo_ten = {s[0]: s for s in STORIES}
    ra: list[tuple[str, str, str, str, str]] = []
    for stt, (ma, ten, khoi, _canh) in enumerate(SO_DO, start=1):
        tren_truc = [k for k in khoi if k[2] == 0]
        vao = next((k[4] for k in tren_truc if k[1] == "input"), "")
        if not vao:
            vao = next((k[4] for k in tren_truc if k[1] == "proc"), "")
        hien = [k[4] for k in tren_truc if k[1] == "disp"]
        ra_du_lieu = hien[-1] if hien else ""
        tac_nhan = theo_ten[ten][1] if ten in theo_ten else ""
        ra.append((str(stt), ten, vao, ra_du_lieu, tac_nhan))
    return ra


def bang_actor_usecase() -> list[tuple[str, str, str]]:
    """Bảng “Liệt kê Actor và Use case”: Actor · Use case · Mô tả.

    Mô tả dùng chính câu “Tôi muốn …” của User story — câu đó đã diễn đạt
    mục đích của use case bằng lời người dùng, nên viết lại một câu khác là
    vừa dư vừa tạo chỗ để lệch.
    """
    theo_ten = {s[0]: s for s in STORIES}
    ra: list[tuple[str, str, str]] = []
    for _ma, ten, _k, _c in SO_DO:
        s = theo_ten.get(ten)
        ra.append((s[1] if s else "", ten, (s[4] if s else "").strip()))
    return ra


def bang_nguoi_dung_yeu_cau() -> list[tuple[str, str, str]]:
    """Bảng “Liệt kê người dùng và yêu cầu”: Người dùng · Use case · Yêu cầu.

    Yêu cầu lấy nguyên câu “Yêu cầu người dùng” của User story (trường thứ
    bảy), đúng câu đã in ở mục 1.4 của báo cáo.
    """
    ra: list[tuple[str, str, str]] = []
    for tn in TAC_NHAN:
        for s in STORIES:
            if tn in s[1]:
                ra.append((tn, s[0], s[6]))
    return ra


def ma_so_do_theo_ten() -> dict[str, str]:
    """Tên use case → mã sơ đồ (`FC01`…), để chèn đúng ảnh vào đúng kịch bản."""
    return {ten: ma for ma, ten, _k, _c in SO_DO}


# ── văn xuôi ──────────────────────────────────────────────────────────────

#: 2.1.1 Hoạt động nghiệp vụ
HOAT_DONG_NGHIEP_VU: list[tuple[str, Any]] = [
    ("p",
     "Hệ thống phục vụ hai nhóm người dùng với hai mục đích khác nhau. Người "
     "dùng cuối dùng ứng dụng di động để nhận thực đơn cho từng ngày và ghi "
     "lại những gì mình đã ăn. Quản trị viên dùng phần quản trị để giữ cho "
     "danh mục món ăn và bộ quy tắc dinh dưỡng đúng và cập nhật."),
    ("p",
     "Toàn bộ nghiệp vụ chia thành ba quy trình nối tiếp nhau. Hai quy trình "
     "đầu thuộc người dùng cuối, quy trình thứ ba thuộc quản trị viên."),
    ("b", "Quy trình 1 — Tạo tài khoản và khai báo thể trạng"),
    ("p",
     "Người dùng đăng ký tài khoản, khai báo giới tính, ngày sinh, chiều "
     "cao, cân nặng, mức vận động và mục tiêu sức khỏe, rồi chọn các bệnh "
     "lý, dị ứng và chế độ ăn mà mình có. Từ những thông tin này hệ thống "
     "tính ra hạn mức năng lượng và tỷ lệ ba chất sinh năng lượng cho riêng "
     "người đó. Sau đó người dùng đi qua một phiên chọn món: hệ thống đưa ra "
     "một bộ món đã lọc theo bệnh lý đã khai và người dùng đánh dấu món mình "
     "thích, không thích, thấy bình thường hoặc chưa từng ăn. Phiên này tạo "
     "ra vector sở thích ban đầu."),
    ("b", "Quy trình 2 — Sinh và sử dụng thực đơn hằng ngày"),
    ("p",
     "Mỗi ngày người dùng mở ứng dụng và nhận thực đơn gồm bốn bữa. Nếu ngày "
     "đó chưa có thực đơn thì hệ thống sinh mới qua bốn bước: tính hạn mức, "
     "loại món không an toàn, xếp hạng món còn lại theo sở thích, rồi ghép "
     "các món đã xếp hạng thành một thực đơn thỏa hạn mức năng lượng và các "
     "ngưỡng vi chất. Người dùng có thể xem chi tiết từng món, đổi một món "
     "sang món khác, thêm món của riêng mình, đánh giá món đã ăn, ghi nhật "
     "ký ăn uống và ghi lại cân nặng theo thời gian. Mỗi hành động trong số "
     "đó là một tín hiệu sở thích, và hệ thống dùng chúng để cập nhật vector "
     "sở thích cho những ngày sau."),
    ("b", "Quy trình 3 — Quản trị danh mục và quy tắc"),
    ("p",
     "Quản trị viên cập nhật thông tin món ăn và số liệu dinh dưỡng, quản lý "
     "bảng bệnh lý cùng các ngưỡng dinh dưỡng đi kèm, khóa hoặc mở lại tài "
     "khoản người dùng, và xem số liệu phân tích về người dùng và về món ăn. "
     "Bộ quy tắc lọc nằm dưới dạng dữ liệu trong cơ sở dữ liệu chứ không "
     "viết cứng trong mã, nên thêm một bệnh lý là thêm dòng dữ liệu, không "
     "phải sửa và biên dịch lại chương trình."),
]

#: 2.1.2 — đoạn mở đầu trước bảng diễn giải.
MO_DAU_SO_DO_NGHIEP_VU: list[tuple[str, Any]] = [
    ("p",
     "Mười tám sơ đồ nghiệp vụ được vẽ cho mười tám use case của hệ thống, "
     "mỗi sơ đồ một luồng. Các sơ đồ được vẽ trước khi viết mã và được dùng "
     "làm bản chuẩn hóa cho phần máy chủ: mỗi khối xử lý trong sơ đồ ứng với "
     "một phương thức phải viết, mỗi khối truy vấn ứng với một câu SQL có ghi "
     "rõ tên bảng, mỗi khối quyết định ứng với một phép kiểm."),
    ("p",
     "Cách làm này đã bộc lộ mười ba đường dẫn còn thiếu ngay ở bước thiết "
     "kế. Khi vẽ xong, đặc tả giao diện lập trình lúc đó có ba mươi đường dẫn "
     "và chỉ phủ mười trong mười tám use case; tám use case còn lại — quên "
     "mật khẩu, đổi mật khẩu, ghi cân nặng, thêm món riêng và bốn màn quản "
     "trị — chưa có đường dẫn nào. Nếu phát hiện muộn hơn thì chúng sẽ lộ ra "
     "lúc đang viết mã giao diện, khi phần máy chủ đã đóng."),
    ("p",
     "Bảng dưới đây diễn giải mười tám quy trình theo dữ liệu vào, dữ liệu ra "
     "và người dùng cuối của từng quy trình. Toàn bộ sơ đồ chi tiết của từng "
     "quy trình được trình bày cùng kịch bản tương ứng ở mục 2.2.3."),
]

#: 2.2.6 Thiết kế ERD
THIET_KE_ERD: list[tuple[str, Any]] = [
    ("p",
     "Cơ sở dữ liệu gồm hai mươi bốn bảng, chia thành ba tầng theo chiều phụ "
     "thuộc khóa ngoại. Tầng một là các bảng gốc không phụ thuộc bảng nào: "
     "người dùng, món ăn, bệnh lý, nhãn món và các bảng cấu hình. Tầng hai "
     "phụ thuộc tầng một: hồ sơ sức khỏe, bệnh lý của người dùng, số liệu "
     "dinh dưỡng của món, lượt chọn món, thực đơn, nhật ký ăn uống và các "
     "bảng của phần học máy. Tầng ba chỉ còn các bảng phụ thuộc thực đơn."),
    ("p",
     "Hai thuộc tính dẫn xuất được khai bằng cột sinh tự động thay vì lưu "
     "thành dữ liệu: chỉ số khối cơ thể trong hồ sơ sức khỏe và phần trăm "
     "lệch năng lượng của thực đơn. Cả hai tính từ những cột đã có trong "
     "cùng một dòng, nên lưu lại là dư thừa và còn có thể lệch với cột gốc. "
     "Trong sơ đồ thực thể – liên kết, hai thuộc tính này được vẽ bằng nét "
     "đứt."),
    ("p",
     "Bộ quy tắc lọc được lưu dưới dạng dữ liệu trong bảng quy tắc bệnh lý "
     "chứ không viết cứng trong mã nguồn. Mỗi quy tắc ghi rõ bệnh lý nào, "
     "loại quy tắc nào, ngưỡng bao nhiêu, mức độ bệnh tối thiểu để quy tắc "
     "có hiệu lực, phạm vi áp dụng là từng món hay cả ngày, quy tắc là cứng "
     "hay mềm, và mức tin cậy của ngưỡng kèm đường dẫn tới nguồn công bố. "
     "Nhờ vậy thêm một bệnh lý mới là thêm dòng dữ liệu, và người đọc báo cáo "
     "tra được từng ngưỡng về nguồn của nó."),
]

#: 2.2.5 và 2.2.8 — hai mục biểu mẫu đánh dấu "(nếu có)".
MUC_KHONG_DUNG: dict[str, str] = {
    "robustness":
        "Hệ thống không dùng sơ đồ Robustness. Vai trò của sơ đồ này — bắc "
        "cầu giữa use case và sơ đồ lớp — ở đồ án này do mười tám sơ đồ "
        "nghiệp vụ ở mục 2.1.2 đảm nhiệm: mỗi khối trong các sơ đồ đó đã chỉ "
        "rõ đường dẫn, bảng dữ liệu và phép kiểm tương ứng, tức đã ở mức chi "
        "tiết thấp hơn Robustness.",
    "tuan_tu":
        "Sơ đồ tuần tự được lược bỏ vì phần lớn use case của hệ thống đi theo "
        "một chuỗi gọi thẳng giữa ba tầng: ứng dụng di động gọi dịch vụ máy "
        "chủ, dịch vụ máy chủ truy vấn cơ sở dữ liệu và trả kết quả. Trường "
        "hợp duy nhất có tương tác nhiều bước đáng vẽ là luồng sinh thực đơn, "
        "và luồng đó đã được trình bày đầy đủ bằng sơ đồ nghiệp vụ FC07 cùng "
        "kịch bản của nó.",
}


# ── tự kiểm ───────────────────────────────────────────────────────────────


def kiem_luong_chinh() -> list[str]:
    """Mọi luồng chính phải đi từ `Bắt đầu` tới `Kết thúc`.

    Phép kiểm này cần thiết vì cách suy ra luồng dựa trên **quy ước vẽ**, và
    quy ước có thể bị phá bởi một lần sửa sơ đồ hoàn toàn hợp lệ. Đã xảy ra
    hai lần trong lúc dựng:

    · FC15 có một ô ghi chú đặt ở cột 1 ngay giữa trục chính, nên luật
      "chỉ đi theo cột 0" làm luồng chính dừng ở bước 6 và mất ba bước cuối.
    · FC12 có vòng lặp thật (ghi thêm cân nặng rồi vẽ lại đồ thị), nên luật
      "dòng nhỏ nhất kế tiếp" quay vòng mãi.

    Cả hai lần, kịch bản sinh ra vẫn là một danh sách câu đọc được — chỉ là
    của một luồng không có trên sơ đồ. Đó đúng là kiểu hỏng mà không ai đọc
    ra được từ bản in.
    """
    loi: list[str] = []
    for ma, ten, khoi, _canh in SO_DO:
        kh = {k[0]: k for k in khoi}
        try:
            duong, _ = _duong_truc(ma)
        except ValueError as e:
            loi.append(f"{ma} ({ten}): {e}")
            continue
        cuoi = kh[duong[-1]]
        if cuoi[1] != "term":
            loi.append(
                f"{ma} ({ten}): luồng chính dừng ở khối {cuoi[CHU]!r}, "
                f"không tới khối Kết thúc — đi được {len(duong)}/{len(khoi)} khối"
            )
        if not luong_chinh(ma):
            loi.append(f"{ma} ({ten}): luồng chính rỗng")
    return loi


# ── in ra để đọc, không ghi vào .docx ─────────────────────────────────────


def _in_chuong() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    def doan(khoi: list[tuple[str, Any]]) -> None:
        for kieu, chu in khoi:
            if kieu == "b":
                print(f"\n  ** {chu} **")
            else:
                print(f"\n  {chu}")

    print("=" * 74)
    print("CHƯƠNG 2 — PHÂN TÍCH THIẾT KẾ HƯỚNG ĐỐI TƯỢNG")
    print("=" * 74)

    print("\n\n2.1 KHẢO SÁT YÊU CẦU")
    print("\n2.1.1 Hoạt động nghiệp vụ")
    doan(HOAT_DONG_NGHIEP_VU)

    print("\n\n2.1.2 Sơ đồ nghiệp vụ thực tế")
    doan(MO_DAU_SO_DO_NGHIEP_VU)
    print("\n  Bảng: Diễn giải quy trình nghiệp vụ")
    print(
        f"  {'STT':<4} {'Hoạt động':<46} {'End User':<26}"
    )
    for stt, hd, vao, ra, eu in bang_dien_giai_quy_trinh():
        print(f"  {stt:<4} {hd[:46]:<46} {eu:<26}")
        print(f"       vào : {vao}")
        print(f"       ra  : {ra}")

    print("\n\n2.1.3 Liệt kê người dùng và yêu cầu")
    cu = None
    for tn, uc, yc in bang_nguoi_dung_yeu_cau():
        if tn != cu:
            print(f"\n  ** {tn} **")
            cu = tn
        print(f"    · {uc}\n      {yc}")

    print("\n\n2.2 PHÂN TÍCH THIẾT KẾ HỆ THỐNG")
    print("\n2.2.1 Liệt kê Actor và Use case")
    for i, (actor, uc, mo_ta) in enumerate(bang_actor_usecase(), 1):
        print(f"  {i:>2}. {uc}\n      actor: {actor}\n      {mo_ta}")

    print("\n\n2.2.2 Sơ đồ use case")
    print("  (ảnh: BAOCAO/png/UseCase!UseCaseDiagram1_2.png — 2 actor, 18 use case)")

    print("\n\n2.2.3 Kịch bản và sơ đồ hoạt động")
    ma_theo_ten = ma_so_do_theo_ten()
    for i, (_actor, uc, _m) in enumerate(bang_actor_usecase(), 1):
        ma = ma_theo_ten[uc]
        print(f"\n  2.2.3.{i} {uc}   [{ma}]")
        print("    Luồng chính:")
        for j, b in enumerate(luong_chinh(ma), 1):
            print(f"      {j}. {b}")
        nl = luong_ngoai_le(ma)
        if nl:
            print("    Luồng thay thế và ngoại lệ:")
            for x in nl:
                print(f"      · {x}")
        print(f"    (sơ đồ hoạt động: BAOCAO/_render/flowchart/{ma}.png)")

    print("\n\n2.2.4 Phác thảo giao diện")
    print("  CHƯA CÓ — cần ảnh chụp màn hình ứng dụng.")

    print("\n2.2.5 Sơ đồ Robustness (nếu có)")
    print(f"\n  {MUC_KHONG_DUNG['robustness']}")

    print("\n\n2.2.6 Thiết kế ERD")
    doan(THIET_KE_ERD)
    print("\n  (ảnh: BAOCAO/png/ERD_vi!ERDDiagram1_vi_3.png — 24 bảng)")

    print("\n\n2.2.7 Sơ đồ Class")
    print("  CHƯA CÓ — sơ đồ Class 'Main' trong Diagram.mdj đang rỗng.")

    print("\n2.2.8 Sơ đồ tuần tự (nếu có)")
    print(f"\n  {MUC_KHONG_DUNG['tuan_tu']}")

    print("\n" + "=" * 74)
    loi = kiem_luong_chinh()
    if loi:
        print(f"{len(loi)} CHỖ LỆCH trong phép suy ra luồng:")
        for x in loi:
            print("  -", x)
    else:
        print("18/18 luồng chính đi từ Bắt đầu tới Kết thúc.")


if __name__ == "__main__":
    _in_chuong()


#: 2.2.4 và 2.2.7 — hai mục CHƯA LÀM ĐƯỢC, không phải hai mục lược bỏ.
#:
#: Khác `MUC_KHONG_DUNG` ở chỗ đó, và khác biệt này phải giữ cho rõ: lược bỏ
#: có lý do là một quyết định thiết kế, còn chưa có là một việc còn nợ. Viết
#: cái thứ hai bằng giọng của cái thứ nhất là che một chỗ trống.
MUC_CHUA_CO: dict[str, str] = {
    "giao_dien":
        "Phần phác thảo giao diện chưa hoàn thiện. Ứng dụng di động hiện chạy "
        "trên dữ liệu mẫu nội bộ và chưa kết nối với dịch vụ máy chủ, nên ảnh "
        "chụp màn hình thu được chưa phản ánh dữ liệu thật của hệ thống. Phần "
        "này sẽ được bổ sung sau khi tầng gọi dịch vụ của ứng dụng hoàn tất.",
    "class":
        "Sơ đồ lớp chưa được dựng. Cấu trúc dữ liệu của hệ thống hiện được "
        "mô tả bằng sơ đồ thực thể – liên kết ở mục trên, gồm hai mươi bốn "
        "bảng; sơ đồ lớp tương ứng với tầng thực thể của phần máy chủ sẽ được "
        "bổ sung sau.",
}
