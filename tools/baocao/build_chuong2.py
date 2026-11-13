# -*- coding: utf-8 -*-
"""Chèn nội dung Chương 2 vào BAOCAO_DATN_TranLamNghia.docx.

Nội dung lấy từ `chuong2_data.py`: văn xuôi là hằng chuỗi, còn bốn bảng và
mười tám kịch bản **suy ra** từ `us_data.py` và `flowchart_data.py` — chính
hai tệp đã sinh mục User story và mười tám flowchart trong `Diagram.mdj`.

## Mặc định là SOÁT, không phải ghi

Giống `build_noidung.py`, và vì cùng một lý do: tác giả soạn tiếp trong Word,
nên một script ghi thẳng vào `.docx` là một script có thể xóa mất phần soạn
tay. Chạy không cờ thì nó chỉ **so và báo**; `--ghi` mới ghi.

Khác `build_noidung.py` ở chỗ phép canh ghi đè là **đo được**, không dựa vào
người dùng tự nhớ. Vùng Chương 2 chỉ nhận một trong ba trạng thái:

    · còn nguyên BIỂU MẪU   → nhận ra bằng chuỗi mẫu "Xem thông báo học bổng"
                              (ví dụ học bổng của biểu mẫu) → ghi được
    · đã do script này sinh → nhận ra bằng câu mở của mục 2.1.1 → ghi lại được
    · không phải hai cái trên → đã có người sửa tay → DỪNG, trừ khi thêm
                              `--chap-nhan-ghi-de`

Nhờ vậy lần chạy đầu và các lần chạy lại đều an toàn mà không cần cờ, còn
lần nào vùng đó đã bị sửa tay thì phải nói rõ là đã biết.

## Dùng đúng style sẵn có của biểu mẫu

    Heading2 / Heading3   mục 2.x và 2.x.y — Word tự đánh số
    Heading7              chú thích bảng — Word tự đánh số "Bảng 2.n:"
    Hnhnh                 chỗ dành cho ảnh, kèm đường dẫn tệp ảnh
    BngNidung             chữ trong ô bảng
    NormalBullet          danh sách gạch đầu dòng

Nhờ đánh số tự động, thêm hay bớt một bảng ở phía trước thì toàn bộ số bảng
và mục lục tự chạy lại.

## Ảnh không được nhúng, có chủ ý

Báo cáo hiện chỉ có đúng một ảnh (logo trang bìa) và **không script nào trong
`tools/baocao/` nhúng ảnh**. Nhúng ảnh cần ba mảnh khớp nhau — tệp trong
`word/media/`, một quan hệ trong `document.xml.rels`, và thẻ `<w:drawing>`
mang đúng mã quan hệ đó — nên một lỗi ở đây làm Word báo tài liệu hỏng chứ
không chỉ hiện sai một ảnh.

Vì vậy mỗi chỗ cần ảnh được chèn một đoạn style `Hnhnh` ghi **đường dẫn chính
xác** của tệp ảnh, đúng cách biểu mẫu vốn làm ("Chèn sơ đồ vào đây"). Kéo ảnh
vào trong Word mất vài giây mỗi ảnh và không có rủi ro nào.

Chạy
────
    python tools/baocao/build_chuong2.py           # soát
    python tools/baocao/build_chuong2.py --ghi
    python tools/baocao/chuong2_data.py            # đọc toàn văn trước khi ghi
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import chuong2_data as c2  # noqa: E402
from build_us import W, _in_utf8, para, table  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOC = ROOT / "BAOCAO" / "BAOCAO_DATN_TranLamNghia.docx"
SAO_LUU = DOC.with_suffix(".docx.bak_truoc_chuong2")

#: Đường dẫn ảnh, ghi vào đoạn `Hnhnh` để biết kéo tệp nào vào.
ANH_USECASE = "BAOCAO/png/UseCase!UseCaseDiagram1_2.png"
ANH_ERD = "BAOCAO/png/ERD_vi!ERDDiagram1_vi_3.png"
ANH_FLOWCHART = "BAOCAO/_render/flowchart/{ma}.png"

#: Nhận ra vùng còn nguyên biểu mẫu: ví dụ học bổng của biểu mẫu mẫu.
DAU_BIEU_MAU = "Xem thông báo học bổng"

#: Nhận ra vùng đã do script này sinh: câu mở của mục 2.1.1.
DAU_DA_SINH = "Hệ thống phục vụ hai nhóm người dùng với hai mục đích khác nhau."

TEN_CHUONG2 = "PHÂN TÍCH THIẾT KẾ HƯỚNG ĐỐI TƯỢNG"
TEN_CHUONG3 = "XÂY DỰNG CHƯƠNG TRÌNH"


# ── dựng XML ──────────────────────────────────────────────────────────────


def _o(chu: str, dam: bool = False) -> list[str]:
    """Một ô bảng một dòng chữ."""
    return [para(chu, "BngNidung", bold=dam, jc="left")]


def _o_nhieu(dong: list[str], dam: bool = False) -> list[str]:
    return [para(d, "BngNidung", bold=dam, jc="left") for d in dong] or [
        para("", "BngNidung")
    ]


def _anh(duong_dan: str) -> str:
    return para(f"[Chèn ảnh: {duong_dan}]", "Hnhnh")


def _van_xuoi(khoi: list[tuple]) -> list[str]:
    """Khối văn xuôi của `chuong2_data`: ("p", …) · ("b", …) · ("ul", [...])."""
    ra: list[str] = []
    for kieu, chu in khoi:
        if kieu == "p":
            ra.append(para(chu))
        elif kieu == "b":
            ra.append(para(chu, bold=True))
        elif kieu == "ul":
            ra += [para(x, "NormalBullet") for x in chu]
        else:
            raise ValueError(f"kiểu khối văn xuôi lạ: {kieu!r}")
    return ra


def _bang_quy_trinh() -> list[str]:
    """Bảng “Diễn giải quy trình nghiệp vụ” — 5 cột, đúng biểu mẫu."""
    cot = [620, 2300, 2300, 2300, 1552]
    assert sum(cot) == W, sum(cot)
    dau = ["STT", "Hoạt động", "Input Data", "Output Data", "End User"]
    hang = [[(c, _o(t, dam=True)) for c, t in zip(cot, dau)]]
    for stt, hd, vao, ra_dl, eu in c2.bang_dien_giai_quy_trinh():
        hang.append(
            [
                (cot[0], _o(stt)),
                (cot[1], _o(hd)),
                (cot[2], _o(vao)),
                (cot[3], _o(ra_dl)),
                (cot[4], _o(eu)),
            ]
        )
    return [table(cot, hang), para("Diễn giải quy trình nghiệp vụ", "Heading7")]


def _bang_nguoi_dung() -> list[str]:
    cot = [1600, 2700, 4772]
    assert sum(cot) == W, sum(cot)
    dau = ["Người dùng", "Chức năng", "Yêu cầu của người dùng"]
    hang = [[(c, _o(t, dam=True)) for c, t in zip(cot, dau)]]
    for tn, uc, yc in c2.bang_nguoi_dung_yeu_cau():
        hang.append([(cot[0], _o(tn)), (cot[1], _o(uc)), (cot[2], _o(yc))])
    return [table(cot, hang), para("Liệt kê người dùng và yêu cầu", "Heading7")]


def _bang_actor_usecase() -> list[str]:
    cot = [1800, 2800, 4472]
    assert sum(cot) == W, sum(cot)
    dau = ["Actor", "Use case", "Mô tả"]
    hang = [[(c, _o(t, dam=True)) for c, t in zip(cot, dau)]]
    for actor, uc, mo_ta in c2.bang_actor_usecase():
        hang.append([(cot[0], _o(actor)), (cot[1], _o(uc)), (cot[2], _o(mo_ta))])
    return [table(cot, hang), para("Liệt kê Actor và Use case", "Heading7")]


def _bang_kich_ban(actor: str, uc: str, mo_ta: str, ma: str) -> list[str]:
    """Một kịch bản = một bảng, như mỗi User story là một bảng ở mục 1.4."""
    nhan, gt = 2200, W - 2200
    chinh = [f"{i}. {b}" for i, b in enumerate(c2.luong_chinh(ma), 1)]
    khac = c2.luong_ngoai_le(ma)

    hang = [
        [(W, _o(f"{uc}  [{ma}]", dam=True), 2)],
        [(nhan, _o("Tác nhân", dam=True)), (gt, _o(actor))],
        [(nhan, _o("Mô tả", dam=True)), (gt, _o(mo_ta))],
        [(nhan, _o("Luồng chính", dam=True)), (gt, _o_nhieu(chinh))],
    ]
    if khac:
        hang.append(
            [
                (nhan, _o("Luồng thay thế và ngoại lệ", dam=True)),
                (gt, _o_nhieu(khac)),
            ]
        )
    return [
        table([nhan, gt], hang),
        para(f"Kịch bản use case {uc}", "Heading7"),
        _anh(ANH_FLOWCHART.format(ma=ma)),
        para(f"Sơ đồ hoạt động use case {uc}", "Heading7"),
    ]


def build() -> str:
    out: list[str] = []

    # ── 2.1 Khảo sát yêu cầu ──
    out.append(para("Khảo sát yêu cầu", "Heading2"))

    out.append(para("Hoạt động nghiệp vụ", "Heading3"))
    out += _van_xuoi(c2.HOAT_DONG_NGHIEP_VU)

    out.append(para("Sơ đồ nghiệp vụ thực tế", "Heading3"))
    out += _van_xuoi(c2.MO_DAU_SO_DO_NGHIEP_VU)
    out += _bang_quy_trinh()

    out.append(para("Liệt kê người dùng và yêu cầu", "Heading3"))
    out.append(
        para(
            "Hệ thống có hai nhóm người dùng. Bảng dưới đây liệt kê từng "
            "chức năng mà mỗi nhóm sử dụng, kèm yêu cầu của họ với chức năng "
            "đó. Cột yêu cầu lấy nguyên câu đã trình bày ở mục User story, "
            "nên hai mục không thể lệch nhau."
        )
    )
    out += _bang_nguoi_dung()

    # ── 2.2 Phân tích thiết kế hệ thống ──
    out.append(para("Phân tích thiết kế hệ thống", "Heading2"))

    out.append(para("Liệt kê Actor và Usecase", "Heading3"))
    out.append(
        para(
            "Hệ thống có hai Actor và mười tám Use case. Cột mô tả dùng chính "
            "câu “Tôi muốn …” của User story tương ứng: câu đó đã diễn đạt "
            "mục đích của Use case bằng lời người dùng."
        )
    )
    out += _bang_actor_usecase()

    out.append(para("Sơ đồ usecase", "Heading3"))
    out.append(_anh(ANH_USECASE))
    out.append(para("Sơ đồ Use case của hệ thống", "Heading7"))

    out.append(para("Kịch bản và sơ đồ hoạt động", "Heading3"))
    out.append(
        para(
            "Mỗi Use case được trình bày thành một kịch bản và một sơ đồ hoạt "
            "động. Kịch bản gồm luồng chính — dãy bước khi mọi điều kiện đều "
            "thỏa — và các luồng thay thế, ứng với từng nhánh rẽ trên sơ đồ. "
            "Hai phần này được lấy trực tiếp từ sơ đồ hoạt động tương ứng, "
            "nên kịch bản không thể mô tả một luồng khác với luồng đã vẽ."
        )
    )
    ma_theo_ten = c2.ma_so_do_theo_ten()
    for actor, uc, mo_ta in c2.bang_actor_usecase():
        out += _bang_kich_ban(actor, uc, mo_ta, ma_theo_ten[uc])

    out.append(para("Phác thảo giao diện", "Heading3"))
    out.append(para(c2.MUC_CHUA_CO["giao_dien"]))

    out.append(para("Sơ đồ Robustness (nếu có)", "Heading3"))
    out.append(para(c2.MUC_KHONG_DUNG["robustness"]))

    out.append(para("Thiết kế ERD", "Heading3"))
    out += _van_xuoi(c2.THIET_KE_ERD)
    out.append(_anh(ANH_ERD))
    out.append(para("Sơ đồ thực thể – liên kết của hệ thống", "Heading7"))

    out.append(para("Sơ đồ Class", "Heading3"))
    out.append(para(c2.MUC_CHUA_CO["class"]))

    out.append(para("Sơ đồ tuần tự (nếu có)", "Heading3"))
    out.append(para(c2.MUC_KHONG_DUNG["tuan_tu"]))

    return "".join(out)


# ── tìm vùng Chương 2 trong document.xml ──────────────────────────────────


def _cac_heading1(xml: str) -> list[tuple[int, int, str]]:
    """(vị trí đầu, vị trí cuối, chữ) của mọi đoạn Heading1."""
    ra = []
    for m in re.finditer(
        r"<w:p [^>]*>(?:(?!</w:p>).)*?Heading1(?:(?!</w:p>).)*?</w:p>", xml, re.S
    ):
        chu = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(0), re.S))
        ra.append((m.start(), m.end(), chu))
    return ra


def vung_chuong2(xml: str) -> tuple[int, int]:
    """Khoảng chữ của **nội dung** Chương 2, không gồm hai tiêu đề chương.

    Bắt đầu ngay sau đoạn Heading1 mang tên Chương 2, kết thúc ngay trước
    đoạn ngắt trang Heading1 rỗng mở đầu Chương 3 — nếu không có đoạn rỗng
    đó thì trước chính tiêu đề Chương 3.
    """
    h1 = _cac_heading1(xml)
    ten = [t for _s, _e, t in h1]
    if TEN_CHUONG2 not in ten:
        sys.exit(f"Không thấy tiêu đề {TEN_CHUONG2!r} — biểu mẫu đã đổi?")
    if TEN_CHUONG3 not in ten:
        sys.exit(f"Không thấy tiêu đề {TEN_CHUONG3!r} — biểu mẫu đã đổi?")
    i2 = ten.index(TEN_CHUONG2)
    i3 = ten.index(TEN_CHUONG3)
    if i3 <= i2:
        sys.exit("Chương 3 đứng trước Chương 2 — dừng.")
    cuoi = i3 - 1 if h1[i3 - 1][2] == "" and i3 - 1 > i2 else i3
    return h1[i2][1], h1[cuoi][0]


def trang_thai_vung(cu: str) -> str:
    """'bieu_mau' · 'da_sinh' · 'sua_tay' — xem phần đầu tệp."""
    if DAU_BIEU_MAU in cu:
        return "bieu_mau"
    if DAU_DA_SINH in cu:
        return "da_sinh"
    return "sua_tay"


def main() -> int:
    _in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--ghi", action="store_true", help="ghi vào .docx")
    bo.add_argument(
        "--chap-nhan-ghi-de",
        action="store_true",
        dest="ghi_de",
        help="ghi dù vùng Chương 2 đã bị sửa tay",
    )
    t = bo.parse_args()

    if not DOC.exists():
        sys.exit(f"Không thấy {DOC}")

    loi_luong = c2.kiem_luong_chinh()
    if loi_luong:
        print("Phép suy ra kịch bản đang lệch với sơ đồ — dừng:", file=sys.stderr)
        for x in loi_luong:
            print("  -", x, file=sys.stderr)
        return 1

    with zipfile.ZipFile(DOC) as z:
        ten_tep = z.namelist()
        tep = {n: z.read(n) for n in ten_tep}
    xml = tep["word/document.xml"].decode("utf-8")

    dau, cuoi = vung_chuong2(xml)
    cu = xml[dau:cuoi]
    moi = build()
    tt = trang_thai_vung(cu)

    print(f"Chương 2 trong {DOC.name}")
    print(f"  vùng nội dung hiện tại: {len(cu)} ký tự · trạng thái: {tt}")
    print(f"  nội dung sẽ chèn:       {len(moi)} ký tự")
    print(
        f"  {len(c2.bang_dien_giai_quy_trinh())} quy trình · "
        f"{len(c2.bang_nguoi_dung_yeu_cau())} dòng người dùng–yêu cầu · "
        f"{len(c2.bang_actor_usecase())} use case"
    )
    print(
        f"  bảng: 3 bảng liệt kê + {len(c2.bang_actor_usecase())} bảng kịch bản"
    )
    print(
        f"  chỗ chờ ảnh: {2 + len(c2.bang_actor_usecase())} "
        "(use case, ERD, 18 sơ đồ hoạt động)"
    )

    if tt == "sua_tay" and not t.ghi_de:
        print(
            "\nVùng Chương 2 không còn là biểu mẫu gốc và cũng không do script "
            "này\nsinh ra — tức đã có người soạn tay trong đó. Ghi bây giờ là "
            "xóa mất\nphần đó.\n\nĐọc lại đã rồi thêm --chap-nhan-ghi-de nếu "
            "thật sự muốn thay.",
            file=sys.stderr,
        )
        return 1

    if not t.ghi:
        print("\nChỉ soát. Thêm --ghi để ghi vào .docx.")
        print("Đọc toàn văn trước khi ghi: python tools/baocao/chuong2_data.py")
        return 0

    if not SAO_LUU.exists():
        shutil.copy2(DOC, SAO_LUU)
        print(f"\nĐã sao lưu → {SAO_LUU.name}")

    xml = xml[:dau] + moi + xml[cuoi:]
    tep["word/document.xml"] = xml.encode("utf-8")

    # Bắt Word cập nhật lại mọi trường khi mở, để mục lục và số bảng tự chạy.
    cai_dat = tep["word/settings.xml"].decode("utf-8")
    if "w:updateFields" not in cai_dat:
        m = re.search(r"(<w:settings[^>]*>)", cai_dat)
        cai_dat = (
            cai_dat[: m.end()] + '<w:updateFields w:val="true"/>' + cai_dat[m.end() :]
        )
        tep["word/settings.xml"] = cai_dat.encode("utf-8")
        print("settings.xml: bật cập nhật trường khi mở tài liệu")

    with zipfile.ZipFile(DOC, "w", zipfile.ZIP_DEFLATED) as z:
        for n in ten_tep:
            z.writestr(n, tep[n])

    print(f"Đã ghi Chương 2 vào {DOC.name}.")
    print(
        "Mở trong Word, bấm Có khi nó hỏi cập nhật trường, rồi kéo "
        f"{2 + len(c2.bang_actor_usecase())} ảnh vào các đoạn [Chèn ảnh: …]."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
