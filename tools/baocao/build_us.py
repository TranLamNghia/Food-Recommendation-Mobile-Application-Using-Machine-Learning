# -*- coding: utf-8 -*-
"""Chèn mục User story vào BAOCAO_DATN_TranLamNghia.docx.

Mỗi User story trình bày thành MỘT bảng ba dòng, đúng khối của đồ án mẫu:

    +-------------------------------------------+
    | Với tư cách la / Tôi muốn / Để            |  một ô, gộp hai cột
    +------------------+------------------------+
    | Tên User story   | Độ ưu tiên: ...        |
    +------------------+------------------------+
    | Yêu cầu người    | Tiêu chuẩn chấp nhận   |
    | dùng: ...        | Ràng buộc dữ liệu: ... |
    +------------------+------------------------+

Ba câu "Với tư cách là..." nằm TRONG bảng chứ không phải đoạn văn phía
trên, nhờ vậy cả khối năm phần đi liền một mạch và không bị ngắt trang ở
giữa.

Dùng đúng các style sẵn có của biểu mẫu, không tạo style mới:

    Heading2    -> tự đánh số "1.x."      (mục User story)
    Heading3    -> tự đánh số "1.x.y."    (từng User story)
    Heading7    -> tự đánh số "Bảng 1.n:" (chú thích bảng)
    BngNidung   -> chữ trong ô bảng

Nhờ vậy số mục và số bảng do Word tự sinh, không gõ cứng: thêm hay bớt một
mục ở phía trước thì toàn bộ đánh số và mục lục tự chạy lại.

Chạy lại được nhiều lần: nếu tài liệu đã có mục User story thì mục cũ được
gỡ sạch trước khi chèn mục mới.
"""
import pathlib
import re
import shutil
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from us_data import STORIES  # noqa: E402

DOC = pathlib.Path("BAOCAO/BAOCAO_DATN_TranLamNghia.docx")

# Biểu mẫu khai font ở từng run dù docDefaults đã khai sẵn. Thiếu dòng này
# thì chữ trong ô bảng nhảy sang font theme, không còn là Times New Roman.
FONT = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'

W = 9072          # bề ngang bảng, bằng bề ngang vùng chữ
HALF = W // 2     # đồ án mẫu chia đôi hai cột


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


def ma(stt: int) -> str:
    """Mã User story, đánh theo đúng thứ tự trong us_data.STORIES.

    Đánh tự động chứ không ghi tay trong us_data: chèn một User story vào
    giữa danh sách thì mọi mã phía sau tự dồn xuống, khỏi phải sửa tay
    mười mấy chỗ và khỏi nguy cơ trùng mã.
    """
    return f"ID_US{stt:02d}"


def para(text: str = "", style: str | None = None, bold: bool = False,
         jc: str | None = None, extra: str = "") -> str:
    """Một đoạn văn. `jc` đặt căn lề riêng cho đoạn đó.

    Style Normal của biểu mẫu căn đều hai bên; trong ô bảng hẹp, căn đều
    kéo giãn khoảng trắng thành "Người      dùng," nên mọi ô đều ép về
    căn trái hoặc căn giữa.

    `extra` chèn thêm thẻ vào <w:pPr>, dùng cho những thứ không có sẵn
    trong style — ví dụ <w:outlineLvl> để mục Mở đầu hiện ra trong mục lục.
    Thẻ trong <w:pPr> phải theo đúng thứ tự lược đồ quy định, nên `extra`
    luôn đặt sau pStyle và jc.
    """
    bits = []
    if style:
        bits.append(f'<w:pStyle w:val="{style}"/>')
    if jc:
        bits.append(f'<w:jc w:val="{jc}"/>')
    if extra:
        bits.append(extra)
    ppr = f"<w:pPr>{''.join(bits)}</w:pPr>" if bits else ""
    if not text:
        return f"<w:p>{ppr}</w:p>"
    rpr = f"<w:rPr>{FONT}{'<w:b/>' if bold else ''}</w:rPr>"
    return (f"<w:p>{ppr}<w:r>{rpr}"
            f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>')


def cell(width: int, paras: list[str], span: int = 1) -> str:
    grid = f'<w:gridSpan w:val="{span}"/>' if span > 1 else ""
    body = "".join(paras) or para("", "BngNidung")
    return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{grid}'
            f"</w:tcPr>{body}</w:tc>")


def table(widths: list[int], rows: list[list[tuple]]) -> str:
    """Mỗi ô là (bề ngang, [đoạn văn]) hoặc (bề ngang, [đoạn văn], số cột gộp)."""
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    body = ""
    for row in rows:
        body += "<w:tr>" + "".join(cell(*c) for c in row) + "</w:tr>"
    return (
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
        f'<w:tblW w:w="{W}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
        '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" '
        'w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
        f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl>"
    )


def build() -> str:
    out = [para("User story", "Heading2")]

    out.append(para(
        "Mục này mô tả yêu cầu của hệ thống theo góc nhìn người sử dụng. Mỗi "
        "User story ứng với một Use case trong sơ đồ Use case ở Chương 2, được "
        "viết theo cú pháp “Với tư cách là … Tôi muốn … Để "
        "…” và kèm bộ tiêu chuẩn chấp nhận làm căn cứ kiểm thử."
    ))

    # ── Bảng tổng hợp ──
    out.append(para("Bảng các User story", "Heading3"))
    head = ["STT", "ID_US", "NAME_US", "Tác nhân", "Độ ưu tiên"]
    widths = [709, 1276, 3600, 1984, 1503]
    rows = [[(widths[i], [para(h, "BngNidung", bold=True, jc="center")])
             for i, h in enumerate(head)]]
    for i, s in enumerate(STORIES, 1):
        us_id, (name, actor, prio) = ma(i), (s[0], s[1], s[2])
        rows.append([
            (widths[0], [para(str(i), "BngNidung", jc="center")]),
            (widths[1], [para(us_id, "BngNidung", jc="center")]),
            (widths[2], [para(f"User story {name.lower()}", "BngNidung",
                              jc="left")]),
            (widths[3], [para(actor, "BngNidung", jc="left")]),
            (widths[4], [para(prio, "BngNidung", jc="center")]),
        ])
    out.append(table(widths, rows))
    out.append(para("Bảng các User story của hệ thống", "Heading7"))

    # ── Từng User story: một bảng ba dòng ──
    for s in STORIES:
        (name, actor, prio, role, want, value, need, criteria, rules) = s

        out.append(para(f"User story {name}", "Heading3"))

        # Dòng 1 — ba câu kể, gộp hai cột.
        story = [
            para(f"Với tư cách là {role}", "BngNidung", jc="left"),
            para(f"Tôi muốn {want}", "BngNidung", jc="left"),
            para(f"Để {value}", "BngNidung", jc="left"),
        ]

        # Dòng 3, ô phải — tiêu chuẩn chấp nhận, rồi ràng buộc nếu có.
        right = [para("Tiêu chuẩn chấp nhận", "BngNidung", jc="left")]
        right += [para(f"– {c}", "BngNidung", jc="left")
                  for c in criteria]
        if rules:
            right.append(para("Ràng buộc dữ liệu:", "BngNidung", jc="left"))
            right += [para(f"– {r}", "BngNidung", jc="left")
                      for r in rules]

        out.append(table([HALF, HALF], [
            [(W, story, 2)],
            [(HALF, [para(name, "BngNidung", jc="center")]),
             (HALF, [para(f"Độ ưu tiên: {prio}", "BngNidung", jc="center")])],
            [(HALF, [para(f"Yêu cầu người dùng: {need}", "BngNidung",
                          jc="left")]),
             (HALF, right)],
        ]))
        out.append(para(f"User story {name.lower()}", "Heading7"))

    return "".join(out)


def find_anchor(xml: str) -> int:
    """Vị trí chèn: ngay trước đoạn ngắt trang mở đầu Chương 2."""
    heads = [
        (m.start(), "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(0),
                                       re.S)))
        for m in re.finditer(
            r"<w:p [^>]*>(?:(?!</w:p>).)*?Heading1(?:(?!</w:p>).)*?</w:p>",
            xml, re.S)
    ]
    titles = [t for _, t in heads]
    if "PHÂN TÍCH THIẾT KẾ HƯỚNG ĐỐI TƯỢNG" not in titles:
        sys.exit("Không thấy tiêu đề Chương 2 — biểu mẫu đã đổi?")
    idx = titles.index("PHÂN TÍCH THIẾT KẾ HƯỚNG ĐỐI TƯỢNG")
    # Đoạn Heading1 rỗng ngay trước đó là ngắt trang mở đầu chương, phải chèn
    # TRƯỚC nó để nội dung mới vẫn nằm trong Chương 1.
    return heads[idx - 1][0] if idx > 0 and heads[idx - 1][1] == "" \
        else heads[idx][0]


def strip_old(xml: str) -> str:
    """Gỡ mục User story đã chèn lần trước, để chạy lại không nhân đôi.

    Mục cũ nằm gọn giữa đoạn Heading2 "User story" và điểm chèn, nên cắt
    đúng đoạn đó. Phải tính điểm chèn TRƯỚC khi cắt rồi mới cắt một lần:
    cắt trước thì mọi vị trí phía sau lệch đi đúng bằng độ dài phần đã bỏ.
    """
    m = re.search(
        r'<w:p[ >](?:(?!</w:p>).)*?<w:pStyle w:val="Heading2"/>'
        r"(?:(?!</w:p>).)*?<w:t[^>]*>User story</w:t>"
        r"(?:(?!</w:p>).)*?</w:p>",
        xml, re.S)
    if not m:
        return xml
    end = find_anchor(xml)
    if end <= m.start():
        sys.exit("Mục User story cũ không nằm trước Chương 2 — dừng.")
    print(f"Đã gỡ mục User story cũ ({end - m.start()} ký tự).")
    return xml[:m.start()] + xml[end:]


def main() -> int:
    if not DOC.exists():
        sys.exit(f"Không thấy {DOC}")

    backup = DOC.with_suffix(".docx.bak")
    if not backup.exists():
        shutil.copy2(DOC, backup)
        print(f"Đã sao lưu -> {backup.name}")

    with zipfile.ZipFile(DOC) as z:
        names = z.namelist()
        files = {n: z.read(n) for n in names}

    xml = files["word/document.xml"].decode("utf-8")
    xml = strip_old(xml)
    at = find_anchor(xml)
    xml = xml[:at] + build() + xml[at:]
    files["word/document.xml"] = xml.encode("utf-8")

    # ── Bắt Word cập nhật lại mọi trường khi mở, để mục lục tự chạy lại ──
    settings = files["word/settings.xml"].decode("utf-8")
    if "w:updateFields" not in settings:
        m = re.search(r"(<w:settings[^>]*>)", settings)
        settings = (settings[:m.end()] +
                    '<w:updateFields w:val="true"/>' +
                    settings[m.end():])
        files["word/settings.xml"] = settings.encode("utf-8")
        print("settings.xml: bật cập nhật trường khi mở tài liệu")

    with zipfile.ZipFile(DOC, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, files[n])

    print(f"Đã chèn mục User story: {len(STORIES)} User story, "
          f"{1 + len(STORIES)} bảng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
