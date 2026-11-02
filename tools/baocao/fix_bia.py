# -*- coding: utf-8 -*-
"""Điền thông tin sinh viên và tên đề tài vào gáy, bìa, đầu trang, chân trang.

Biểu mẫu nhận về vẫn mang tên một sinh viên khác cùng một loạt chỗ bỏ trống
dạng "……". Script thay đúng những chỗ đó bằng thông tin lấy từ
NHIEM_VU_DATN và DE_CUONG_DATN, không đụng tới phần nội dung.

Hai điểm dễ sai, đã xử lý:

* Trang gáy nằm trong một hộp văn bản, mà Word lưu hộp văn bản HAI lần —
  một bản <mc:Choice> và một bản <mc:Fallback>. Mọi chuỗi ở gáy vì thế phải
  thay đúng 2 lần; thay 1 lần thì bản còn lại vẫn in ra tên cũ.
* Chỗ ghi ngày và tên đề tài bị Word cắt thành nhiều run rời ("28", "/",
  "11/2025"), nên phải thay cả cụm run chứ không thay từng mẩu chữ.

Mỗi phép thay đều khẳng định số lần khớp: biểu mẫu đổi một chữ là script
dừng ngay thay vì âm thầm bỏ qua rồi báo thành công.
"""
import pathlib
import re
import shutil
import sys
import zipfile

DOC = pathlib.Path("BAOCAO/BAOCAO_DATN_TranLamNghia.docx")

HO_TEN = "Trần Lâm Nghĩa"
MA_SV = "22115053122231"
LOP = "22T2"
GVHD = "ThS. Nguyễn Tấn Thuận"
NAM = "2026"
NGAY = "Đà Nẵng, tháng 12/2026"
# Style Ba-Tnti và Ba-Gy của biểu mẫu đã bật <w:caps/>, nên bìa và gáy tự
# in hoa; ở đây giữ chữ thường để chỗ khác (đầu trang, tóm tắt) đọc tự nhiên.
DE_TAI = ("Ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa "
          "sử dụng học máy dựa trên lịch sử người dùng và mục tiêu sức khỏe")


def sub(xml: str, old: str, new: str, count: int, what: str) -> str:
    """Thay `old` bằng `new`, bắt buộc khớp đúng `count` lần."""
    seen = xml.count(old)
    if seen != count:
        sys.exit(f"DỪNG — {what}: cần {count} chỗ khớp, tìm thấy {seen}.")
    print(f"   [ok] {what} ({count} chỗ)")
    return xml.replace(old, new)


def fix_document(xml: str) -> str:
    print("word/document.xml")

    # ── Gáy sách ──
    # Biểu mẫu dàn gáy bằng những run toàn dấu cách (96 và 84 ký tự trắng).
    # Cách dàn đó chỉ vừa khít với tên đề tài ngắn như của biểu mẫu; tên đề
    # tài dài hơn là chữ tràn, xuống dòng và "NĂM" bị đẩy mất. Vì vậy dựng
    # lại cả đoạn: hai điểm dừng tab (giữa và phải) thay cho dấu cách, và
    # tên đề tài đặt cỡ 9 pt cho đủ chỗ trên dải gáy rộng 11 inch.
    #
    # Hộp văn bản được Word lưu HAI bản — <mc:Choice> và <mc:Fallback> —
    # nên đoạn này có đúng 2 bản giống hệt nhau, phải thay cả hai.
    gay_moi = (
        '<w:p w14:paraId="6A0BF007" w14:textId="2F54BBE2" '
        'w:rsidR="00123F69" w:rsidRPr="00852EEC" w:rsidRDefault="002A0E68" '
        'w:rsidP="002D1E10"><w:pPr><w:pStyle w:val="Ba-Gy"/><w:tabs>'
        '<w:tab w:val="center" w:pos="7800"/>'
        '<w:tab w:val="right" w:pos="15600"/></w:tabs></w:pPr>'
        f"<w:r><w:t>{HO_TEN}</w:t></w:r><w:r><w:tab/></w:r>"
        '<w:r><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>'
        f"<w:t>{DE_TAI}</w:t></w:r><w:r><w:tab/></w:r>"
        f"<w:r><w:t>NĂM {NAM}</w:t></w:r></w:p>"
    )
    cu = re.findall(r'<w:p w14:paraId="6A0BF007".*?</w:p>', xml, re.S)
    if len(cu) != 2:
        sys.exit(f"DỪNG — gáy: cần 2 bản đoạn văn, tìm thấy {len(cu)}.")
    if "HỌ TÊN SINH VIÊN" not in cu[0]:
        sys.exit("DỪNG — gáy: đoạn tìm được không phải đoạn chỗ trống.")
    for doan in cu:
        xml = xml.replace(doan, gay_moi)
    print("   [ok] gáy — họ tên, tên đề tài, năm (2 chỗ)")

    # ── Bìa ngoài: thông tin của sinh viên khác ──
    xml = sub(xml, "<w:t>Huỳnh Nguyên Vĩnh Nguyên</w:t>",
              f"<w:t>{HO_TEN}</w:t>", 1, "bìa — họ tên sinh viên")
    xml = sub(xml, "<w:t>22115053122233</w:t>", f"<w:t>{MA_SV}</w:t>", 1,
              "bìa — mã sinh viên")
    xml = sub(xml, "<w:t>125CDM01</w:t>", f"<w:t>{LOP}</w:t>", 1, "bìa — lớp")
    # Tên người hướng dẫn bị cắt làm ba run: "ThS. " / "Nguyễn Văn" / " Phát "
    xml = sub(
        xml,
        '<w:t xml:space="preserve">ThS. </w:t></w:r>'
        '<w:r w:rsidR="00F41FE0"><w:rPr><w:rStyle w:val="Ba-Ngihngdn-Inm"/>'
        "</w:rPr><w:t>Nguyễn Văn</w:t></w:r>"
        '<w:r w:rsidR="00A70DA7"><w:rPr><w:rStyle w:val="Ba-Ngihngdn-Inm"/>'
        '</w:rPr><w:t xml:space="preserve"> Phát </w:t></w:r>',
        f'<w:t xml:space="preserve">{GVHD}</w:t></w:r>',
        1, "bìa — người hướng dẫn")

    # ── Tên đề tài trên hai trang bìa ──
    xml = sub(xml, "<w:t>……………………………….</w:t>", f"<w:t>{DE_TAI}</w:t>", 1,
              "bìa ngoài — tên đề tài")
    xml = sub(xml,
              '<w:t>………………………</w:t></w:r><w:r w:rsidR="00B95EDE">'
              "<w:t>….</w:t></w:r>",
              f"<w:t>{DE_TAI}</w:t></w:r>", 1, "bìa trong — tên đề tài")

    # ── Ngày tháng trên hai trang bìa ──
    xml = sub(
        xml,
        '<w:t xml:space="preserve">Đà Nẵng, </w:t></w:r>'
        '<w:r w:rsidR="006E03D2"><w:t>28</w:t></w:r>'
        '<w:r w:rsidRPr="00880304"><w:t>/</w:t></w:r>'
        '<w:bookmarkEnd w:id="0"/><w:bookmarkEnd w:id="1"/>'
        '<w:r w:rsidR="006E03D2"><w:t>11/2025</w:t></w:r>',
        f'<w:t xml:space="preserve">{NGAY}</w:t></w:r>'
        '<w:bookmarkEnd w:id="0"/><w:bookmarkEnd w:id="1"/>',
        1, "bìa ngoài — ngày tháng")
    xml = sub(
        xml,
        '<w:t xml:space="preserve">Đà Nẵng, </w:t></w:r>'
        '<w:r w:rsidR="00252E2F"><w:t>…/……</w:t></w:r>',
        f'<w:t xml:space="preserve">{NGAY}</w:t></w:r>',
        1, "bìa trong — ngày tháng")

    # ── Trang TÓM TẮT: điền phần định danh, phần nội dung để sinh viên viết ──
    for nhan, gia_tri in (("Tên đề tài", DE_TAI),
                          ("Sinh viên thực hiện", HO_TEN),
                          ("Mã SV", MA_SV),
                          ("Lớp", LOP)):
        xml = sub(xml,
                  f'<w:t xml:space="preserve">{nhan}: </w:t>',
                  f'<w:t xml:space="preserve">{nhan}: {gia_tri} </w:t>',
                  1, f"tóm tắt — {nhan.lower()}")
    return xml


def main() -> int:
    if not DOC.exists():
        sys.exit(f"Không thấy {DOC}")
    backup = DOC.with_suffix(".docx.bak2")
    if not backup.exists():
        shutil.copy2(DOC, backup)
        print(f"Đã sao lưu -> {backup.name}\n")

    with zipfile.ZipFile(DOC) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}

    files["word/document.xml"] = fix_document(
        files["word/document.xml"].decode("utf-8")).encode("utf-8")

    # ── Đầu trang: biểu mẫu để chữ "Tên đề tài" làm chỗ trống ──
    print("word/header1.xml")
    h = files["word/header1.xml"].decode("utf-8")
    h = sub(h, "<w:t>Tên đề tài</w:t>", f"<w:t>{DE_TAI}</w:t>", 1,
            "đầu trang — tên đề tài")
    files["word/header1.xml"] = h.encode("utf-8")

    # ── Chân trang: "SVTH: ……." ──
    for name in ("word/footer3.xml", "word/footer4.xml", "word/footer5.xml"):
        print(name)
        f = files[name].decode("utf-8")
        f = sub(f, "<w:t>…….</w:t>", f"<w:t>{HO_TEN}</w:t>", 1,
                "chân trang — SVTH")
        files[name] = f.encode("utf-8")

    with zipfile.ZipFile(DOC, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, files[n])
    print("\nXong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
