# -*- coding: utf-8 -*-
"""Gỡ danh mục thừa còn sót ở trang DANH MỤC HÌNH VẼ.

Biểu mẫu cài sẵn bốn trường mục lục. Ba trường đúng việc:

    MỤC LỤC             TOC \\o "1-4" ... "TTat-NXet-NVu-LNĐ,1"
    DANH MỤC BẢNG BIỂU  TOC ... "Heading 7,1"      (chú thích bảng)
    DANH MỤC HÌNH VẼ    TOC ... "Heading 6,1"      (chú thích hình)

Trường thứ tư, nằm ngay sau danh mục hình, gom "Heading 6" CỘNG style
"ML-MĐ-KLHPT" nên in lại toàn bộ NHẬN XÉT, TÓM TẮT, MỤC LỤC, MỞ ĐẦU, KẾT
LUẬN... rồi in thêm danh sách hình một lần nữa. Nội dung đó đã nằm trong
MỤC LỤC, in lại dưới tiêu đề "danh mục hình vẽ" là sai chỗ.

Hai chỗ phải cẩn thận:

* Trường trải dài qua hàng chục đoạn (phần kết quả Word lưu sẵn), nên phải
  đếm cặp fldChar begin/end mới biết nó kết thúc ở đâu, không cắt theo số
  đoạn.
* Đoạn chứa fldChar end lại CHÍNH LÀ đoạn giữ <w:sectPr> của phần đầu báo
  cáo (khổ giấy, lề, đánh số La Mã thường). Xóa cả đoạn đó là mất luôn
  ngắt phần, nên chỉ bỏ run fldChar end và giữ nguyên đoạn.
"""
import pathlib
import re
import shutil
import sys
import zipfile

DOC = pathlib.Path("BAOCAO/BAOCAO_DATN_TranLamNghia.docx")

# Chuỗi nhận dạng trường thừa, cố ý không chứa dấu chéo ngược.
DAU_HIEU = 'KLHPT,1"'


def para_bounds(xml: str, pos: int) -> tuple[int, int]:
    """Biên của đoạn văn chứa vị trí `pos`."""
    start = xml.rfind("<w:p ", 0, pos)
    if start < 0 or "</w:p>" in xml[start:pos]:
        sys.exit("DỪNG — không khoanh được đoạn văn chứa trường.")
    end = xml.index("</w:p>", pos) + len("</w:p>")
    return start, end


def clean(xml: str) -> str:
    n = xml.count(DAU_HIEU)
    if n != 1:
        sys.exit(f"DỪNG — cần đúng 1 trường thừa, tìm thấy {n}.")

    begin_start, _ = para_bounds(xml, xml.index(DAU_HIEU))

    # ── Dò tới fldChar end khớp cặp ──
    depth = 0
    cur = begin_start
    end_para = None
    for m in re.finditer(r'<w:fldChar w:fldCharType="(begin|end)"/>',
                         xml[begin_start:]):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            cur = begin_start + m.start()
            end_para = para_bounds(xml, cur)
            break
    if end_para is None:
        sys.exit("DỪNG — không tìm thấy fldChar end khớp cặp.")

    # ── Bỏ run fldChar end, giữ lại đoạn vì nó mang <w:sectPr> ──
    p_start, p_end = end_para
    doan = xml[p_start:p_end]
    doan_moi, bo = re.subn(
        r'<w:r>(?:(?!</w:r>).)*?<w:fldChar w:fldCharType="end"/></w:r>',
        "", doan, flags=re.S)
    if bo != 1:
        sys.exit(f"DỪNG — đoạn cuối trường có {bo} run fldChar end, cần 1.")
    if "<w:sectPr" not in doan_moi:
        sys.exit("DỪNG — đoạn cuối trường không còn <w:sectPr>, dừng để "
                 "không làm hỏng ngắt phần.")

    # ── Ngắt trang và đoạn trống dẫn vào danh mục thừa cũng bỏ theo, nếu
    #    không sẽ còn lại một trang trắng giữa hai danh mục ──
    cat_tu = begin_start
    bo_them = 0
    while bo_them < 2:
        truoc_start = xml.rfind("<w:p ", 0, cat_tu)
        if truoc_start < 0:
            break
        truoc = xml[truoc_start:cat_tu]
        # Chỉ nuốt đoạn không chữ, không style riêng và không giữ ngắt phần.
        if ("<w:t" in truoc or "<w:sectPr" in truoc
                or "<w:pStyle" in truoc):
            break
        cat_tu = truoc_start
        bo_them += 1

    so_doan = xml[cat_tu:p_start].count("<w:p ")
    print(f"Gỡ danh mục thừa 1 — bản gom thêm style ML-MĐ-KLHPT: "
          f"{so_doan} đoạn ({bo_them} đoạn ngắt trang / trống dẫn vào), "
          f"giữ lại đoạn <w:sectPr>.")
    return gon_fldsimple(xml[:cat_tu] + doan_moi + xml[p_end:])


def gon_fldsimple(xml: str) -> str:
    """Gỡ trường danh mục viết dưới dạng <w:fldSimple>.

    Biểu mẫu còn một trường "TOC Heading 6,1" nữa nằm ngay cuối danh mục
    bảng biểu, viết gọn thành <w:fldSimple> và chưa từng được cập nhật nên
    KHÔNG in ra gì — mở tài liệu lên không hề thấy. Đến khi Word tính lại
    trường, nó in thêm một danh sách hình vẽ thứ hai ngay dưới danh mục
    bảng biểu.

    Vì nó vô hình, phải dò theo <w:fldSimple w:instr="..."> chứ không dò
    theo <w:instrText> như các trường khác, và cũng vì thế nó sót lại sau
    khi những danh mục thừa nhìn thấy được đã bị xóa.
    """
    mau = re.compile(r'<w:fldSimple w:instr="([^"]*)"[^>]*(?:/>|>.*?'
                     r"</w:fldSimple>)", re.S)
    bo = []
    for m in mau.finditer(xml):
        if "TOC" not in m.group(1):
            continue
        # Chỉ bỏ khi danh mục đó đã có một trường đầy đủ khác lo rồi, để
        # không lỡ tay xóa danh mục duy nhất của một loại nào đó.
        kieu = re.search(r"&quot;([^&]*)&quot;", m.group(1))
        if not kieu:
            sys.exit(f"DỪNG — không đọc được style của {m.group(1)!r}.")
        con_lai = re.findall(
            r"<w:instrText[^>]*>([^<]*)</w:instrText>", xml)
        if not any("TOC" in t and kieu.group(1) in t for t in con_lai):
            sys.exit(f"DỪNG — {kieu.group(1)} chỉ có trường fldSimple này, "
                     f"xóa đi là mất hẳn danh mục.")
        bo.append(m.group(0))
    for doan in bo:
        xml = xml.replace(doan, "", 1)
    print(f"Gỡ danh mục thừa 2 — bản <w:fldSimple> vô hình: {len(bo)} trường.")
    return xml



def _in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252).

    Không gọi thì script chết giữa lúc chạy với UnicodeEncodeError ngay khi
    đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức đúng lúc chạy trong CI.
    Bản sao của `tools/_env.in_utf8`; để ở đây vì `tools/baocao/` không chắc
    có `tools/` trên `sys.path`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass

def main() -> int:
    _in_utf8()
    if not DOC.exists():
        sys.exit(f"Không thấy {DOC}")
    backup = DOC.with_suffix(".docx.bak3")
    if not backup.exists():
        shutil.copy2(DOC, backup)
        print(f"Đã sao lưu -> {backup.name}")

    with zipfile.ZipFile(DOC) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}

    xml = files["word/document.xml"].decode("utf-8")
    xml = clean(xml)
    files["word/document.xml"] = xml.encode("utf-8")

    with zipfile.ZipFile(DOC, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, files[n])
    print("Xong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
