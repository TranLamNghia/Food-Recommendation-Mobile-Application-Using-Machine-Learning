# -*- coding: utf-8 -*-
"""Điền Tóm tắt, Nhiệm vụ đồ án, Mở đầu và các mục 1.1 – 1.3 vào báo cáo.

Bốn khối, mỗi khối thay đúng phần chỗ trống của biểu mẫu:

    TÓM TẮT        thay hai đoạn "{Ví dụ mẫu…}" và "{Em mong muốn…}"
    NHIỆM VỤ ĐATN  thay đoạn "{Trang trắng này dùng để dán…}"
    MỞ ĐẦU         thay từ đoạn "{Trong phần này…}" tới hết mục mẫu cuối
    Chương 1       thay hai mục mẫu "Mục nội dung" bằng 1.1, 1.2, 1.3

Dùng đúng style sẵn có của biểu mẫu, không tạo style mới:

    Heading2 / Heading3   mục 1.x và 1.x.y, Word tự đánh số
    Mu / Mca              mục Mở đầu, tự đánh số 1. 2. 3. và a. b.
    NormalBullet          danh sách gạch đầu dòng
    Heading7              chú thích bảng, tự đánh số "Bảng 1.n:"

Vì mục User story nằm NGAY SAU 1.3 và cũng dùng Heading2, chèn ba mục mới
vào trước là nó tự lùi từ 1.3 xuống 1.4 — không phải sửa gì thêm.

Style `Mu` không có outlineLvl nên mặc định không vào mục lục. Script thêm
<w:outlineLvl w:val="1"/> cho từng đoạn để sáu mục Mở đầu hiện ra trong MỤC
LỤC đúng như đồ án mẫu, mà không phải sửa định nghĩa style.

Chạy lại được nhiều lần: lần sau tìm thấy nội dung đã sinh thì thay tiếp
lên chính nó.
"""
import pathlib
import re
import shutil
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_us import FONT, W, esc, para, table  # noqa: E402
from noidung_data import CHUONG1, MO_DAU, NHIEM_VU, TOM_TAT  # noqa: E402

DOC = pathlib.Path("BAOCAO/BAOCAO_DATN_TranLamNghia.docx")

DOAN = re.compile(r"<w:p[ >](?:(?!<w:p[ >]).)*?</w:p>", re.S)


def chu(text: str) -> str:
    """Đoạn văn thường, giữ nguyên thụt dòng đầu của style Normal."""
    return para(text)


def dam(text: str) -> str:
    return para(text, bold=True)


def gach(items: list[str]) -> str:
    return "".join(para(t, "NormalBullet") for t in items)


def doan_tab(text: str) -> str:
    """Đoạn có ký tự tab trong chuỗi, dùng cho dòng 'Sinh viên… <tab> Mã SV…'."""
    phan = text.split("\t")
    runs = []
    for i, t in enumerate(phan):
        if i:
            runs.append(f"<w:r><w:rPr>{FONT}</w:rPr><w:tab/></w:r>")
        runs.append(f"<w:r><w:rPr>{FONT}</w:rPr>"
                    f'<w:t xml:space="preserve">{esc(t)}</w:t></w:r>')
    # Trong <w:pPr>, thẻ <w:tabs> phải đứng trước <w:ind> — thứ tự các thẻ
    # con do lược đồ quy định, đảo lại là Word báo tệp hỏng.
    return ('<w:p><w:pPr>'
            '<w:tabs><w:tab w:val="left" w:pos="5103"/></w:tabs>'
            '<w:ind w:firstLine="0"/>'
            f"</w:pPr>{''.join(runs)}</w:p>")


def bang(spec: dict) -> str:
    """Bảng có hàng tiêu đề in đậm, kèm chú thích style Heading7."""
    widths = spec["widths"]
    rows = [[(widths[i], [para(h, "BngNidung", bold=True, jc="center")])
             for i, h in enumerate(spec["head"])]]
    for r in spec["rows"]:
        rows.append([
            (widths[i],
             [para(c, "BngNidung", jc="center" if i == 0 or len(c) <= 3
                   else "left")])
            for i, c in enumerate(r)
        ])
    return table(widths, rows) + para(spec["caption"], "Heading7")


def dung(khoi: list) -> str:
    """Dựng XML cho một khối nội dung."""
    out = []
    for kieu, noi in khoi:
        if kieu == "h2":
            out.append(para(noi, "Heading2"))
        elif kieu == "h3":
            out.append(para(noi, "Heading3"))
        elif kieu == "md":
            out.append(para(noi, "Mu"))
        elif kieu == "mda":
            out.append(para(noi, "Mca"))
        elif kieu == "p":
            out.append(chu(noi))
        elif kieu == "p2":
            out.append(doan_tab(noi))
        elif kieu == "b":
            out.append(dam(noi))
        elif kieu == "ul":
            out.append(gach(noi))
        elif kieu == "bang":
            out.append(bang(noi))
        else:
            sys.exit(f"DỪNG — không hiểu kiểu phần tử {kieu!r}.")
    return "".join(out)


def bo_tab_cham(xml: str, moc: int) -> str:
    """Bỏ dấu chấm lửng cuối ba dòng định danh của trang Tóm tắt.

    Biểu mẫu để sẵn một điểm dừng tab có dấu chấm dẫn ở cuối mỗi dòng, cho
    người viết điền tay. Nay các dòng đã có nội dung nên hàng chấm kéo dài
    phía sau chỉ còn là rác; đồ án mẫu cũng không để lại.

    Chỉ bỏ tab CUỐI của mỗi đoạn: dòng "Mã SV … Lớp …" còn một tab ở giữa
    làm nhiệm vụ đẩy chữ "Lớp" sang cột bên phải, bỏ luôn là hai cụm dính
    vào nhau.
    """
    tab_run = re.compile(r"<w:r[ >](?:(?!</w:r>).)*?<w:tab/>"
                         r"(?:(?!</w:r>).)*?</w:r>", re.S)
    bo = 0
    for nhan in ("Tên đề tài: ", "Sinh viên thực hiện: ", "Mã SV: "):
        d = doan_khop(xml, moc, None, nhan)
        if not d:
            continue
        doan = xml[d[0]:d[1]]
        vet = list(tab_run.finditer(doan))
        if not vet:
            continue
        cuoi = vet[-1]
        # Chỉ bỏ run thuần tab. Phải dò "<w:t " hoặc "<w:t>" chứ không dò
        # "<w:t" — chuỗi đó khớp luôn cả chính thẻ <w:tab/>.
        if re.search(r"<w:t[ >]", cuoi.group(0)):
            continue
        xml = (xml[:d[0]] + doan[:cuoi.start()] + doan[cuoi.end():]
               + xml[d[1]:])
        bo += 1
    if bo:
        print(f"   [ok] Tóm tắt: bỏ {bo} hàng chấm lửng thừa")
    return xml


def mu_vao_muc_luc(styles: str) -> str:
    """Cho style `Mu` một cấp dàn bài, để mục lục gom được sáu mục Mở đầu.

    Trường mục lục của biểu mẫu là TOC \\o "1-4": nó gom theo CẤP DÀN BÀI
    của style, không theo định dạng đặt riêng cho từng đoạn. Khai
    <w:outlineLvl> ngay trong đoạn văn không có tác dụng — đã thử và mục
    lục vẫn bỏ qua. Vì vậy phải khai ở chính định nghĩa style.

    Chỉ thêm một thẻ, không đụng gì khác: `Mu` chỉ dùng cho sáu mục của Mở
    đầu nên thay đổi này không lan sang chỗ nào khác trong báo cáo.
    """
    m = re.search(r'(<w:style [^>]*w:styleId="Mu">.*?</w:style>)',
                  styles, re.S)
    if not m:
        sys.exit("DỪNG — không thấy style “Mu” trong styles.xml.")
    cu = m.group(1)
    if "<w:outlineLvl" in cu:
        print("   [ok] style Mu: đã có cấp dàn bài")
    else:
        # <w:outlineLvl> là thẻ cuối cùng của <w:pPr> theo lược đồ, nên chèn
        # ngay trước thẻ đóng </w:pPr>.
        moi = cu.replace("</w:pPr>", '<w:outlineLvl w:val="1"/></w:pPr>', 1)
        if moi == cu:
            sys.exit("DỪNG — style “Mu” không có <w:pPr> để chèn cấp dàn bài.")
        print("   [ok] style Mu: thêm cấp dàn bài 2 để mục lục gom được")
        styles = styles.replace(cu, moi, 1)

    # `Mca` (các mục a. b.) kế thừa từ `Mu` nên ăn theo luôn cấp dàn bài
    # vừa đặt, và mục lục in cả "a. Đối tượng nghiên cứu" — đồ án mẫu không
    # liệt kê tới mức đó. Đặt lại cấp 9 (văn bản thường) để cắt kế thừa.
    m = re.search(r'(<w:style [^>]*w:styleId="Mca">.*?</w:style>)',
                  styles, re.S)
    if not m:
        sys.exit("DỪNG — không thấy style “Mca” trong styles.xml.")
    cu = m.group(1)
    if "<w:outlineLvl" not in cu:
        moi = cu.replace("</w:pPr>", '<w:outlineLvl w:val="9"/></w:pPr>', 1)
        if moi == cu:
            sys.exit("DỪNG — style “Mca” không có <w:pPr>.")
        styles = styles.replace(cu, moi, 1)
        print("   [ok] style Mca: cắt kế thừa cấp dàn bài, để a./b. không "
              "lọt vào mục lục")
    return styles


def doan_khop(xml: str, tu: int, style: str | None, chuoi: str):
    """Biên của đoạn văn đầu tiên từ `tu` trở đi khớp style và chứa `chuoi`."""
    for m in DOAN.finditer(xml, tu):
        s = m.group(0)
        if style is not None:
            st = re.search(r'<w:pStyle w:val="([^"]+)"', s)
            if not st or st.group(1) != style:
                continue
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", s))
        if chuoi in txt:
            return m.start(), m.end()
    return None


def thay(xml: str, ten: str, moc_dau: int, dau_ung_vien: list,
         cuoi: tuple, moi: str) -> str:
    """Thay đoạn giữa mốc đầu và mốc cuối (không gồm mốc cuối) bằng `moi`.

    `dau_ung_vien` liệt kê nhiều cách nhận ra điểm bắt đầu: chỗ trống của
    biểu mẫu khi chạy lần đầu, và nội dung script tự sinh khi chạy lại.
    Nhờ vậy chạy lại không nhân đôi nội dung.
    """
    d = None
    for style, chuoi in dau_ung_vien:
        d = doan_khop(xml, moc_dau, style, chuoi)
        if d:
            break
    if not d:
        sys.exit(f"DỪNG — {ten}: không tìm thấy điểm bắt đầu "
                 f"(đã thử {len(dau_ung_vien)} cách).")
    c = doan_khop(xml, d[0], cuoi[0], cuoi[1])
    if not c:
        sys.exit(f"DỪNG — {ten}: không tìm thấy mốc cuối {cuoi[1]!r}.")
    if c[0] <= d[0]:
        sys.exit(f"DỪNG — {ten}: mốc cuối nằm trước điểm bắt đầu.")
    print(f"   [ok] {ten}: thay {c[0] - d[0]} ký tự")
    return xml[:d[0]] + moi + xml[c[0]:]


def main() -> int:
    if not DOC.exists():
        sys.exit(f"Không thấy {DOC}")
    backup = DOC.with_suffix(".docx.bak4")
    if not backup.exists():
        shutil.copy2(DOC, backup)
        print(f"Đã sao lưu -> {backup.name}\n")

    with zipfile.ZipFile(DOC) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}
    xml = files["word/document.xml"].decode("utf-8")

    def moc(chuoi: str, tu: int = 0) -> int:
        """Vị trí tiêu đề lớn, dùng làm điểm xuất phát cho mỗi khối."""
        d = doan_khop(xml, tu, "ML-M-KLHPT", chuoi)
        if not d:
            sys.exit(f"DỪNG — không thấy tiêu đề “{chuoi}”.")
        return d[1]

    print("Điền nội dung:")

    # ── TÓM TẮT ──
    xml = bo_tab_cham(xml, moc("TÓM TẮT"))
    xml = thay(xml, "Tóm tắt", moc("TÓM TẮT"),
               [(None, "{Ví dụ mẫu"), (None, "Nội dung tóm tắt")],
               ("ML-M-KLHPT", "NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP"),
               dung(TOM_TAT))

    # ── NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP ──
    xml = thay(xml, "Nhiệm vụ đồ án", moc("NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP"),
               [(None, "{Trang trắng này dùng để dán bản Nhiệm vụ"),
                (None, "Giảng viên hướng dẫn:")],
               ("ML-M-KLHPT", "LỜI NÓI ĐẦU"),
               dung(NHIEM_VU))

    # ── MỞ ĐẦU ──
    # Mốc cuối là đoạn style TTat-NXet-NVu-LN ngay trước Chương 1; đoạn đó
    # giữ ngắt trang nên chỉ thay phần phía trước, không đụng tới nó.
    xml = thay(xml, "Mở đầu", moc("MỞ ĐẦU", moc("DANH MỤC CHỮ VIẾT TẮT TIẾNG ANH")),
               [(None, "{Trong phần này, cần trình bày về"),
                ("Mu", "Tổng quan đề tài")],
               ("TTat-NXet-NVu-LN", ""),
               dung(MO_DAU))

    # ── Chương 1: mục 1.1 – 1.3 ──
    # Tìm theo style Heading1 để không vớ phải dòng "Chương 1 CƠ SỞ LÝ
    # THUYẾT" trong phần mục lục đã lưu sẵn (những dòng đó mang style TOC1).
    d_ch1 = doan_khop(xml, 0, "Heading1", "CƠ SỞ LÝ THUYẾT")
    if not d_ch1:
        sys.exit("DỪNG — không thấy tiêu đề Chương 1.")
    xml = thay(xml, "Chương 1 — mục 1.1 đến 1.3", d_ch1[1],
               [("Heading2", "Mục nội dung (Cấp 1- heading 2)"),
                ("Heading2", "Giới thiệu")],
               ("Heading2", "User story"),
               dung(CHUONG1))

    files["word/document.xml"] = xml.encode("utf-8")
    files["word/styles.xml"] = mu_vao_muc_luc(
        files["word/styles.xml"].decode("utf-8")).encode("utf-8")

    settings = files["word/settings.xml"].decode("utf-8")
    if "w:updateFields" not in settings:
        m = re.search(r"(<w:settings[^>]*>)", settings)
        settings = (settings[:m.end()] + '<w:updateFields w:val="true"/>'
                    + settings[m.end():])
        files["word/settings.xml"] = settings.encode("utf-8")
        print("   settings.xml: bật cập nhật trường khi mở tài liệu")

    with zipfile.ZipFile(DOC, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, files[n])
    print("\nXong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
