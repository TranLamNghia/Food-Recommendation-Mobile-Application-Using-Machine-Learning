# -*- coding: utf-8 -*-
"""Soát — và chỉ khi được yêu cầu, điền — Tóm tắt, Mở đầu, mục 1.1 – 1.3.

## Vì sao mặc định là SOÁT, không phải ghi

Script này vốn dùng để điền một lần vào biểu mẫu còn trống. Từ đó tới nay
tác giả soạn tiếp trong Word, và hai bên đã lệch nhau theo CẢ HAI chiều.
Đo được trên bản báo cáo hiện tại:

    · 9 chỗ sửa chữ trong Tóm tắt và Chương 1
      ("khởi đầu nguội" -> "cold-start", "cô-sin" -> "cosin", bỏ "về", …)
    · 1 khẳng định bị XÓA khỏi Tóm tắt vì chưa có cơ sở: cụm "chất lượng gợi
      ý được đánh giá bằng Precision@K, Recall@K và NDCG" — chưa thu dữ liệu
      nên chưa có phép đánh giá nào
    · 2 đoạn bị xóa khỏi Chương 1 ("Khảo sát các ứng dụng tương tự" và gạch
      đầu dòng của nó)
    · 2 BẢNG được thêm bằng Word, không có trong `noidung_data.py`
    · nhãn "Nội dung tóm tắt" bị thay bằng ba dòng định danh
    · trang NHIỆM VỤ ĐỒ ÁN bị bỏ hẳn khỏi báo cáo — nó là tệp riêng

Chạy script ở chế độ ghi lúc này sẽ **ghi đè toàn bộ những thay đổi đó**.
Nên mặc định nó chỉ so và báo; muốn ghi thì phải thêm `--ghi`, và nếu còn
chỗ lệch thì vẫn phải thêm `--chap-nhan-ghi-de` để nói rõ là đã biết.

Giữ script lại dưới dạng công cụ soát vẫn có ích: nó nói cho biết báo cáo và
`noidung_data.py` đã rời nhau ở đâu, mà không đe dọa tài liệu.

## Khi nào thì nên ghi

Khi thêm một mục HOÀN TOÀN MỚI vào `noidung_data.py` và chưa sửa gì bằng tay
ở khối đó. Lúc đó chạy `--ghi --chap-nhan-ghi-de`, rồi mở Word soát lại — và
quan trọng hơn: kéo mọi chỗ lệch mà script báo về `noidung_data.py` TRƯỚC
khi ghi, nếu không lần ghi này xóa chúng.

## Phần điền (chỉ chạy với --ghi)

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
import argparse
import difflib
import html
import re
import shutil
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_us import FONT, W, esc, para, table  # noqa: E402
from noidung_data import (  # noqa: E402
    CHUONG1,
    MO_DAU,
    TAI_LIEU,
    TOM_TAT,
)

DOC = pathlib.Path("BAOCAO/BAOCAO_DATN_TranLamNghia.docx")

DOAN = re.compile(r"<w:p[ >](?:(?!<w:p[ >]).)*?</w:p>", re.S)


def chu(text: str) -> str:
    """Đoạn văn thường, giữ nguyên thụt dòng đầu của style Normal."""
    return para(text)


def dam(text: str) -> str:
    return para(text, bold=True)


#: Danh sách đánh số của phần Tài liệu tham khảo trong biểu mẫu.
#:
#: Phải giữ đúng `numId` của tài liệu, nếu không Word coi đây là một danh
#: sách khác và đánh số lại từ 1 — hoặc nối tiếp số của một danh sách không
#: liên quan ở nơi khác trong bài.
NUM_TAI_LIEU = ('<w:numPr><w:ilvl w:val="0"/>'
                '<w:numId w:val="32"/></w:numPr>')


def muc_tai_lieu(text: str) -> str:
    """Một mục tài liệu tham khảo, style `ListParagraph` có đánh số."""
    return para(text, "ListParagraph", extra=NUM_TAI_LIEU)


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
        elif kieu == "tl":
            out.append(muc_tai_lieu(noi))
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


def doan_khop(xml: str, tu: int, style: str | None, chuoi: str | None):
    """Biên của đoạn văn đầu tiên từ `tu` trở đi khớp style và chứa `chuoi`.

    `chuoi=None` đòi đoạn **rỗng đúng nghĩa**, khác hẳn `chuoi=""`.

    Phân biệt này cần vì `"" in bất_kỳ_chuỗi` luôn đúng: dùng `""` làm mốc
    cuối thì nó khớp ngay chính đoạn bắt đầu, hoặc đoạn kế tiếp có chữ. Lỗi
    đó chỉ không lộ ở hai khối Tóm tắt và Mở đầu vì ở đó đoạn mốc cuối mang
    style riêng, không đoạn nào khác trong vùng có. Khối Tài liệu tham khảo
    thì mọi đoạn đều là `ListParagraph`, nên phải đòi rỗng thật.
    """
    for m in DOAN.finditer(xml, tu):
        s = m.group(0)
        if style is not None:
            st = re.search(r'<w:pStyle w:val="([^"]+)"', s)
            if not st or st.group(1) != style:
                continue
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", s))
        if chuoi is None:
            if not txt.strip():
                return m.start(), m.end()
            continue
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



def _in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252).

    Không gọi thì script chết giữa lúc chạy với UnicodeEncodeError ngay khi
    đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức đúng lúc chạy trong CI.
    Bản sao của `tools/_env.use_utf8`; để ở đây vì `tools/baocao/` không chắc
    có `tools/` trên `sys.path`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


# ── Soát: báo cáo và noidung_data.py đã rời nhau ở đâu ────────────────────


def _chu_doan(p_xml: str) -> str:
    """Chữ của một đoạn, dấu tab trả về thành "\t".

    Phải lấy cả `<w:tab/>` chứ không chỉ `<w:t>`: `doan_tab` mã hóa dấu tab
    trong dữ liệu thành "\t", nên bỏ qua nó ở phía báo cáo sẽ làm dòng
    "Mã SV: … <tab> Lớp: …" bị báo là lệch mãi mãi.
    """
    phan = re.findall(r"<w:t[^>]*>([^<]*)</w:t>|(<w:tab/>)", p_xml)
    tho = "".join("	" if tab else t for t, tab in phan)
    # Giải mã thực thể XML, nếu không thì mọi đoạn có dấu "<", ">" hay "&"
    # sẽ bị báo lệch mãi mãi: văn bản "0 < n < 30" nằm trong tệp dưới dạng
    # "0 &lt; n &lt; 30", và tiêu đề "KẾT LUẬN &amp; HƯỚNG PHÁT TRIỂN" cũng
    # vậy. Tài liệu đúng, chỉ phép so là sai.
    return html.unescape(tho).strip()


def _phang(khoi) -> list[str]:
    """Mọi chuỗi văn bản của một khối dữ liệu, theo thứ tự."""
    ra: list[str] = []
    for kieu, noi in khoi:
        if kieu == "ul":
            ra.extend(noi)
        elif kieu == "bang":
            # Phải phẳng bảng ra theo ĐÚNG thứ tự `bang()` sinh: ô tiêu đề,
            # rồi từng hàng, rồi chú thích. Bỏ qua bảng ở bước soát từng là
            # một lỗi có hậu quả: hai bảng vốn đã có trong dữ liệu bị báo là
            # "chỉ có trong báo cáo, ghi sẽ xóa", và con số lệch bị thổi lên.
            ra.extend(noi["head"])
            for hang in noi["rows"]:
                ra.extend(hang)
            ra.append(noi["caption"])
        elif isinstance(noi, str) and noi:
            ra.append(noi)
    # Lọc chuỗi rỗng để khớp `_vung`, vốn bỏ đoạn không có chữ. Ô trống của
    # bảng so sánh (những ô không có dấu "X") từng bị báo là đoạn thiếu
    # trong báo cáo — năm chỗ lệch giả.
    return [t for t in ra if t]


def _vung(txt: list[str], dau: str, cuoi: str | None) -> list[str] | None:
    """Các đoạn có chữ nằm giữa hai tiêu đề, không gồm hai tiêu đề.

    `cuoi=None` nghĩa là lấy tới hết tài liệu — dùng cho khối cuối cùng,
    vốn không có tiêu đề nào phía sau.
    """
    try:
        i = next(j for j, t in enumerate(txt) if t == dau)
    except StopIteration:
        return None
    if cuoi is None:
        return [t for t in txt[i + 1:] if t]
    try:
        k = next(j for j, t in enumerate(txt) if j > i and t == cuoi)
    except StopIteration:
        return None
    return [t for t in txt[i + 1:k] if t]


def soat(xml: str, khoi_can_soat) -> int:
    """So từng khối dữ liệu với báo cáo. Trả về số chỗ lệch.

    Căn chỉnh theo **thứ tự đoạn** bằng `SequenceMatcher`, không theo độ
    giống từng cặp. Lý do: báo cáo có đoạn bị đổi tên ("khởi đầu nguội" ->
    "cold-start") lẫn đoạn bị xóa hẳn, và phép so theo độ giống sẽ ghép một
    đoạn đã xóa với một đoạn khác rồi báo sai hoàn toàn.
    """
    txt = [_chu_doan(m.group(0)) for m in DOAN.finditer(xml)]
    tong = 0

    for ten, khoi, dau, cuoi in khoi_can_soat:
        a = _phang(khoi)
        b = _vung(txt, dau, cuoi)
        if b is None:
            print(f"\n  [?] {ten}: không xác định được vùng "
                  f"({dau!r} … {cuoi!r}) — bỏ qua")
            continue

        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        lech = [op for op in sm.get_opcodes() if op[0] != "equal"]
        if not lech:
            print(f"\n  [ok] {ten}: khớp hoàn toàn ({len(a)} đoạn)")
            continue

        print(f"\n  [!] {ten}: {len(lech)} chỗ lệch "
              f"(data {len(a)} đoạn, báo cáo {len(b)} đoạn)")
        for tag, i1, i2, j1, j2 in lech:
            tong += 1
            if tag == "delete":
                print(f"        chỉ có trong noidung_data.py — ghi sẽ THÊM lại:")
                for x in a[i1:i2]:
                    print(f"          + {x[:68]!r}")
            elif tag == "insert":
                print(f"        chỉ có trong báo cáo — ghi sẽ XÓA:")
                for y in b[j1:j2]:
                    print(f"          - {y[:68]!r}")
            else:
                print("        khác nội dung — ghi sẽ ghi đè bản trong báo cáo:")
                for x, y in zip(a[i1:i2], b[j1:j2]):
                    # So tới từng ký tự chỉ có nghĩa khi hai đoạn thật sự là
                    # một đoạn đã bị sửa. Ghép "Nội dung tóm tắt" với "Tên đề
                    # tài: …" rồi so ký tự thì ra một mớ vụn vô nghĩa, nên
                    # dưới ngưỡng này thì in cả hai đoạn nguyên vẹn.
                    if difflib.SequenceMatcher(None, x, y).ratio() < 0.70:
                        print(f"          data    : {x[:66]!r}")
                        print(f"          báo cáo : {y[:66]!r}")
                        continue
                    for t, i_1, i_2, j_1, j_2 in difflib.SequenceMatcher(
                            None, x, y).get_opcodes():
                        if t == "equal":
                            continue
                        print(f"          data    : {x[i_1:i_2][:56]!r}")
                        print(f"          báo cáo : {y[j_1:j_2][:56]!r}")
                chung = min(i2 - i1, j2 - j1)
                for x in a[i1 + chung:i2]:
                    print(f"          + {x[:68]!r}  (chỉ có trong data)")
                for y in b[j1 + chung:j2]:
                    print(f"          - {y[:68]!r}  (chỉ có trong báo cáo)")
    return tong


def main() -> int:
    _in_utf8()
    bo = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    bo.add_argument(
        "--ghi", action="store_true",
        help="thực sự ghi vào .docx; không có thì chỉ soát và báo")
    bo.add_argument(
        "--chap-nhan-ghi-de", action="store_true",
        help="cho phép ghi dù còn chỗ lệch — mọi sửa tay ở các khối đó sẽ MẤT")
    tham_so = bo.parse_args()

    if not DOC.exists():
        sys.exit(f"Không thấy {DOC}")

    with zipfile.ZipFile(DOC) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}
    xml = files["word/document.xml"].decode("utf-8")

    # ── Soát trước, luôn luôn ──
    print(f"Soát {DOC.name} với noidung_data.py")
    print("=" * 72)
    so_lech = soat(xml, (
        ("Tóm tắt", TOM_TAT, "TÓM TẮT", "LỜI CẢM ƠN"),
        ("Mở đầu", MO_DAU, "MỞ ĐẦU", "CƠ SỞ LÝ THUYẾT"),
        ("Chương 1 (1.1–1.3)", CHUONG1, "CƠ SỞ LÝ THUYẾT", "User story"),
        ("Tài liệu tham khảo", TAI_LIEU, "TÀI LIỆU THAM KHẢO", None),
    ))
    print("\n" + "=" * 72)

    if not tham_so.ghi:
        if so_lech:
            print(f"{so_lech} chỗ lệch. KHÔNG ghi gì — đây là chế độ soát.")
            print("Muốn ghi: thêm --ghi --chap-nhan-ghi-de, nhưng hãy kéo mọi")
            print("chỗ lệch ở trên về noidung_data.py TRƯỚC, nếu không lần ghi")
            print("này sẽ xóa chúng.")
            return 1
        print("Không có chỗ nào lệch. Thêm --ghi nếu muốn ghi lại y nguyên.")
        return 0

    if so_lech and not tham_so.chap_nhan_ghi_de:
        sys.exit(
            f"\nDỪNG — còn {so_lech} chỗ lệch mà chưa khai "
            "--chap-nhan-ghi-de.\nGhi lúc này sẽ xóa những sửa tay nêu trên.")

    backup = DOC.with_suffix(".docx.bak4")
    if not backup.exists():
        shutil.copy2(DOC, backup)
        print(f"Đã sao lưu -> {backup.name}\n")

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
               # Ứng viên thứ ba cho bản đã sửa tay: nhãn "Nội dung tóm
               # tắt" bị thay bằng ba dòng định danh, nên mốc đầu giờ là
               # dòng "Tên đề tài:".
               [(None, "{Ví dụ mẫu"), (None, "Nội dung tóm tắt"),
                (None, "Tên đề tài:")],
               # Mốc cuối từng là tiêu đề "NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP",
               # nay không còn trong báo cáo. Đoạn ML-M-KLHPT rỗng ngay sau
               # phần Tóm tắt GIỮ NGẮT TRANG, nên lấy chính nó làm mốc cuối
               # để chỉ thay phần phía trước — đúng cách khối Mở đầu đang
               # làm với `TTat-NXet-NVu-LN`. Lấy "LỜI CẢM ƠN" làm mốc cuối
               # thì đoạn giữ ngắt trang nằm trong vùng bị thay và mất.
               ("ML-M-KLHPT", ""),
               dung(TOM_TAT))

    # ── NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP — KHÔNG điền nữa ──
    #
    # Tiêu đề "NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP" không còn trong báo cáo: thứ tự
    # hiện tại là NHẬN XÉT → NHẬN XÉT → TÓM TẮT → LỜI CẢM ƠN. Trang đó vốn
    # để dán bản nhiệm vụ đã ký, và nó đã thành tệp riêng
    # `BAOCAO/NHIEM_VU_DATN_TranLamNghia.docx`. `NHIEM_VU` trong
    # `noidung_data.py` giữ lại làm nguồn cho tệp đó, không chèn vào đây.

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

    # ── TÀI LIỆU THAM KHẢO ──
    #
    # Là khối CUỐI tài liệu, nên không có tiêu đề nào phía sau làm mốc. Mốc
    # cuối là đoạn `ListParagraph` rỗng mà biểu mẫu để lại ngay sau danh sách
    # mẫu; giữ nó thì phần `sectPr` và đoạn trống cuối bài không bị đụng tới.
    d_tl = doan_khop(xml, 0, "ML-M-KLHPT", "TÀI LIỆU THAM KHẢO")
    if not d_tl:
        sys.exit("DỪNG — không thấy tiêu đề TÀI LIỆU THAM KHẢO.")
    xml = thay(xml, "Tài liệu tham khảo", d_tl[1],
               [("ListParagraph", "Tên tác giả"),
                ("ListParagraph", "Viện Dinh dưỡng Quốc gia")],
               # Đoạn `ListParagraph` RỖNG mà biểu mẫu để lại sau danh
               # sách mẫu. Phải là `None` chứ không phải "": mọi đoạn trong
               # vùng này đều cùng style, nên chuỗi rỗng sẽ khớp ngay đoạn
               # đầu tiên và không thay được gì.
               ("ListParagraph", None),
               dung(TAI_LIEU))

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
