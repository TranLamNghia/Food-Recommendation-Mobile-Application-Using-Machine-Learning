# -*- coding: utf-8 -*-
"""Bố cục và đo chữ cho flowchart — dùng chung cho bộ sinh và bộ vẽ.

Vì sao tách ra. `them_flowchart.py` ghi toạ độ vào `.mdj`, còn
`ve_flowchart.py` vẽ lại ra PNG để soi bằng mắt. Nếu hai bên tự đo chữ theo
hai cách thì ảnh PNG không còn nói gì về tệp `.mdj`: hình trông vừa khít
trong ảnh mà vẫn tràn chữ khi mở bằng StarUML. Cả hai gọi đúng các hàm ở
đây.

QUY ƯỚC Ô LƯỚI
--------------
Mỗi khối khai một ô `(cot, hang)`, không khai toạ độ. Cột 0 là trục chính
chạy dọc; cột dương là nhánh bên phải (thường là nhánh lỗi), cột âm là nhánh
bên trái. Hàng tăng dần xuống dưới.

Khai theo ô thay vì theo pixel vì ô đọc được: xem dữ liệu là biết sơ đồ có
mấy nhánh, còn 250 cặp toạ độ pixel thì không ai soát được.

BẢY LOẠI KHỐI, MỖI LOẠI ỨNG VỚI MỘT THỨ PHẢI VIẾT
-------------------------------------------------
    term   FCTerminator        bắt đầu / kết thúc
    input  FCManualInput       người dùng nhập tay trên app
    disp   FCDisplay           app vẽ ra màn hình
    proc   FCProcess           xử lý trong Backend API  -> một method service
    call   FCPredefinedProcess gọi sang thành phần khác -> một lời gọi HTTP
    db     FCDatabase          đọc/ghi MySQL            -> một câu SQL
    dec    FCDecision          nhánh quyết định         -> một phép kiểm

Phân loại không phải để hình cho đẹp: đọc một sơ đồ là đếm được bao nhiêu
endpoint, bao nhiêu truy vấn và bao nhiêu phép kiểm phải viết.
"""
from __future__ import annotations

import sys

# ── Lưới ──
LE = 60          # lề quanh sơ đồ
COT = 70         # khoảng hở giữa hai cột
HANG = 46        # khoảng hở giữa hai hàng, chỗ cho mũi tên
LAN = 30         # khoảng cách giữa hai làn đường vòng

#: Loại khối -> (tên lớp StarUML, bề ngang khung chữ).
#:
#: Bề ngang khai ở đây là bề ngang DÀNH CHO CHỮ, không phải bề ngang khối.
#: Bề ngang khối suy ra từ nó theo đúng công thức của từng hình, xem
#: `do_khoi`.
KHOI = {
    "term":  ("FCTerminator",        250),
    "input": ("FCManualInput",       195),
    "disp":  ("FCDisplay",           150),
    "proc":  ("FCProcess",           205),
    "call":  ("FCPredefinedProcess", 200),
    "db":    ("FCDatabase",          205),
    "dec":   ("FCDecision",          125),
}

FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
FONT_CO = 13
_font = None


def font():
    """Phông Arial 13 — đúng phông StarUML ghi vào view (`Arial;13;0`)."""
    global _font
    if _font is None:
        from PIL import ImageFont
        try:
            _font = ImageFont.truetype(FONT_PATH, FONT_CO)
        except OSError:  # pragma: no cover
            _font = ImageFont.load_default()
    return _font


def _rong(s: str) -> float:
    f = font()
    try:
        return f.getlength(s)
    except AttributeError:  # pragma: no cover
        return f.getsize(s)[0]


def ngat_dong(text: str, rong: float) -> list[str]:
    """Ngắt chữ cho vừa bề ngang `rong`, giống `wordWrap` của StarUML."""
    dong: list[str] = []
    for doan in text.split("\n"):
        cur = ""
        for tu in doan.split():
            thu = f"{cur} {tu}".strip()
            if _rong(thu) <= rong or not cur:
                cur = thu
            else:
                dong.append(cur)
                cur = tu
        dong.append(cur)
    return dong


CAO_DONG = 16
CAO_TOI_THIEU = 44

# Lề mà `FCGeneralNodeView.arrangeObject` chừa quanh nhãn: 10 px mỗi bên.
LE_NGANG = 10
LE_DOC = 10


def do_khoi(loai: str, text: str) -> tuple[int, int, list[str]]:
    """Bề ngang, bề cao và các dòng chữ đã ngắt của một khối.

    Kích thước phải THỎA SẴN kích thước tối thiểu mà StarUML tự tính cho
    từng hình. StarUML chỉ nới khối ra chứ không bao giờ thu lại: ghi một
    khối nhỏ hơn mức tối thiểu của nó thì lúc mở tệp StarUML nở khối đó ra,
    và mọi đường nối đã tính sẵn quanh nó trỏ lệch. Lỗi này không báo gì —
    sơ đồ chỉ đơn giản là xấu đi khi mở.

    Công thức lấy từ `arrangeObject`/`sizeObject` của từng lớp trong
    `extensions/essential/flowchart/elements.js`:

        FCDecision  khung chữ chỉ là phần GIỮA: rộng w/2, cao h/2
                    -> khối phải rộng và cao gấp đôi khung chữ
        FCDatabase  hai vòng ellipse ăn mất 3/8 bề cao (g = h/8)
        FCManualInput  mép trên xiên ăn mất 1/6 bề cao
        FCDisplay   hai mũi nhọn ăn mất 1/3 bề ngang (g = w/6)
        FCPredefinedProcess  hai vạch dọc, chữ thụt thêm 5 px
        FCTerminator  bo tròn bán kính h/2, hai đầu bo ăn mất h bề ngang
    """
    _, rong_chu = KHOI[loai]
    dong = ngat_dong(text, rong_chu)
    tw = max(int(_rong(d)) for d in dong) + 2
    th = len(dong) * CAO_DONG

    if loai == "dec":
        return (max(2 * tw + 10, 150), max(2 * th + 10, CAO_TOI_THIEU), dong)

    cao = th + LE_DOC * 2
    rong = tw + LE_NGANG * 2
    if loai == "db":
        cao = -(-cao * 8 // 5)          # h - 20 - 3h/8 >= th
    elif loai == "input":
        cao = -(-cao * 6 // 5)          # h - 20 - h/6  >= th
    elif loai == "disp":
        rong = -(-rong * 3 // 2)        # w - 20 - 2w/6 >= tw
    elif loai == "call":
        rong += 5
    elif loai == "term":
        cao = max(cao, CAO_TOI_THIEU)
        rong += cao                     # chừa chỗ cho hai đầu bo tròn
    return rong, max(cao, CAO_TOI_THIEU), dong


def khung_chu(h: "Hop") -> tuple[int, int, int, int]:
    """Khung chữ bên trong một khối, đúng như StarUML đặt nó.

    Bộ vẽ PNG dùng hàm này để đặt chữ, nhờ vậy ảnh cho thấy đúng chỗ chữ sẽ
    nằm khi mở bằng StarUML — kể cả chỗ chữ sát vào vành hình trụ.
    """
    if h.loai == "dec":
        return (h.left + h.width // 4, h.top + h.height // 4,
                h.width // 2, h.height // 2)
    if h.loai == "db":
        g = h.height // 8
        return (h.left + LE_NGANG, h.top + LE_DOC + g * 2,
                h.width - LE_NGANG * 2, h.height - LE_DOC * 2 - g * 3)
    if h.loai == "input":
        g = h.height // 6
        return (h.left + LE_NGANG, h.top + LE_DOC + g,
                h.width - LE_NGANG * 2, h.height - LE_DOC * 2 - g)
    if h.loai == "disp":
        g = h.width // 6
        return (h.left + LE_NGANG + g, h.top + LE_DOC,
                h.width - LE_NGANG * 2 - g * 2, h.height - LE_DOC * 2)
    if h.loai == "call":
        return (h.left + LE_NGANG + 5, h.top + LE_DOC,
                h.width - LE_NGANG * 2 - 5, h.height - LE_DOC * 2)
    return (h.left + LE_NGANG, h.top + LE_DOC,
            h.width - LE_NGANG * 2, h.height - LE_DOC * 2)


def chu_tran(h: "Hop") -> str | None:
    """Chữ có tràn ra ngoài khung của nó không — '' nếu không tràn."""
    _, _, w, ht = khung_chu(h)
    rong = max(_rong(d) for d in h.dong)
    if rong > w:
        return f"chữ rộng {rong:.0f} > khung {w}"
    if len(h.dong) * CAO_DONG > ht:
        return f"chữ cao {len(h.dong) * CAO_DONG} > khung {ht}"
    return None


class Hop:
    """Một khối đã được đặt chỗ: biết ô lưới, toạ độ và kích thước."""

    __slots__ = ("ma", "loai", "text", "cot", "hang",
                 "left", "top", "width", "height", "dong")

    def __init__(self, ma, loai, cot, hang, text):
        self.ma, self.loai, self.text = ma, loai, text
        self.cot, self.hang = cot, hang
        self.width, self.height, self.dong = do_khoi(loai, text)
        self.left = self.top = 0

    # Mép và tâm — dùng khắp nơi khi tính đường nối.
    @property
    def right(self):
        return self.left + self.width

    @property
    def bottom(self):
        return self.top + self.height

    @property
    def cx(self):
        return self.left + self.width // 2

    @property
    def cy(self):
        return self.top + self.height // 2

    def __repr__(self):  # pragma: no cover
        return f"<{self.loai} {self.ma} ({self.cot},{self.hang})>"


def dat_cho(khoi) -> dict[str, Hop]:
    """Đổi ô lưới thành toạ độ pixel.

    Mỗi hàng cao bằng khối cao nhất trong hàng đó, không cao bằng nhau:
    một hàng chỉ có khối hai dòng chữ không nên chiếm chỗ bằng hàng có khối
    bốn dòng. Khối được căn giữa theo tâm cột và theo giữa hàng.
    """
    hop = [Hop(*k) for k in khoi]

    # Bề ngang mỗi cột bằng khối rộng nhất trong cột đó, không cố định: một
    # khối quyết định phải rộng gấp đôi khung chữ của nó, nên cột chứa nó
    # rộng hơn hẳn cột chỉ có khối chữ nhật. Dùng một bề ngang chung cho mọi
    # cột thì hoặc sơ đồ thừa chỗ trống, hoặc hai khối cạnh nhau đè lên nhau.
    rong_cot: dict[int, int] = {}
    cao_hang: dict[int, int] = {}
    for h in hop:
        rong_cot[h.cot] = max(rong_cot.get(h.cot, 0), h.width)
        cao_hang[h.hang] = max(cao_hang.get(h.hang, 0), h.height)

    x = LE
    tam: dict[int, int] = {}
    for c in sorted(rong_cot):
        tam[c] = x + rong_cot[c] // 2
        x += rong_cot[c] + COT

    y = LE
    dinh: dict[int, int] = {}
    for r in sorted(cao_hang):
        dinh[r] = y
        y += cao_hang[r] + HANG

    for h in hop:
        h.left = tam[h.cot] - h.width // 2
        h.top = dinh[h.hang] + (cao_hang[h.hang] - h.height) // 2
    return {h.ma: h for h in hop}


# ── Đường nối ──────────────────────────────────────────────────────────────
#
# Cách định tuyến: SINH NHIỀU PHƯƠNG ÁN RỒI CHỌN, không dùng một công thức
# duy nhất.
#
# Lần đầu viết hàm này theo kiểu một công thức chọn theo vị trí tương đối —
# cùng cột thì đi thẳng, lệch cột thì rẽ chữ L, và cứ thế. Đo trên đúng 18 sơ
# đồ này thì nó cho 46 chỗ đường nối đi xuyên qua một khối ở giữa đường, vì
# vị trí tương đối của hai đầu KHÔNG nói gì về chỗ trống giữa chúng: hai khối
# cùng cột cách nhau mười hàng thì đoạn thẳng đứng nối chúng cắt cả mười
# khối nằm giữa.
#
# Nên mỗi đường nối sinh ra một dãy phương án theo thứ tự từ gọn tới vòng,
# rồi lấy phương án ĐẦU TIÊN không cắt khối nào. Phương án cuối cùng — đi
# vòng hẳn ra ngoài rìa sơ đồ — gần như luôn dùng được, nên hàm hiếm khi bó
# tay; và nếu bó tay thật thì `xuyen_khoi` báo ra chứ không ỉm đi.


def _canh_ra(a: Hop, b: Hop):
    """Mép của `a` hướng về phía `b`, cùng với mép đối diện của `b`."""
    return (a.right if b.cx >= a.cx else a.left,
            b.left if b.cx >= a.cx else b.right)


def _phuong_an(a: Hop, b: Hop, lan_phai: int, lan_trai: int,
               x_min: int, x_max: int):
    """Dãy phương án đi dây, từ gọn nhất tới vòng nhất."""
    ra_a, vao_b = _canh_ra(a, b)
    pa = []

    if a.cx == b.cx and b.top > a.bottom:
        pa.append([(a.cx, a.bottom), (b.cx, b.top)])
    if a.cy == b.cy:
        pa.append([(ra_a, a.cy), (vao_b, b.cy)])

    if b.hang > a.hang:
        # Ra cạnh bên, sang ngang, xuống đỉnh.
        pa.append([(ra_a, a.cy), (b.cx, a.cy), (b.cx, b.top)])
        # Xuống trong cột mình, rồi rẽ vào cạnh bên đích.
        pa.append([(a.cx, a.bottom), (a.cx, b.cy), (vao_b, b.cy)])
        # Xuống nửa đường, sang ngang, xuống đỉnh đích.
        giua = (a.bottom + b.top) // 2
        pa.append([(a.cx, a.bottom), (a.cx, giua), (b.cx, giua),
                   (b.cx, b.top)])

    # Đi vòng ra rìa: bên gần hơn trước.
    ben = (1, -1) if (a.cx + b.cx) / 2 >= (x_min + x_max) / 2 else (-1, 1)
    for s in ben:
        if s > 0:
            x = x_max + 34 + lan_phai * LAN
            pa.append([(a.right, a.cy), (x, a.cy), (x, b.cy),
                       (b.right, b.cy)])
        else:
            x = x_min - 34 - lan_trai * LAN
            pa.append([(a.left, a.cy), (x, a.cy), (x, b.cy), (b.left, b.cy)])
    return pa


def _cat_ai(pts, hop, tru) -> bool:
    for ma, h in hop.items():
        if ma in tru:
            continue
        if any(_cat(pts[i], pts[i + 1], h) for i in range(len(pts) - 1)):
            return True
    return False


def dung_canh(canh, hop):
    """Chọn đường đi cho mọi đường nối của một sơ đồ.

    Làn ngoài rìa được cấp lần lượt: mỗi khi một đường nối phải đi vòng ra
    rìa, nó nhận làn kế tiếp bên phía đó. Hai đường vòng dùng cùng một giá
    trị x thì trùng nhau hoàn toàn và người đọc không biết đường nào đi đâu,
    nên làn phải khác nhau — kể cả khi nhờ vậy sơ đồ rộng thêm.

    Đường nối được xét theo nhịp ngắn trước: đường ngắn chọn được lối gọn thì
    đường dài còn nguyên các làn ngoài để đi vòng.
    """
    x_min = min(h.left for h in hop.values())
    x_max = max(h.right for h in hop.values())
    lan_phai = lan_trai = 0

    thu_tu = sorted(
        range(len(canh)),
        key=lambda i: abs(hop[canh[i][1]].hang - hop[canh[i][0]].hang))
    ket: dict[int, list] = {}
    for i in thu_tu:
        c = canh[i]
        a, b = hop[c[0]], hop[c[1]]
        pa = _phuong_an(a, b, lan_phai, lan_trai, x_min, x_max)
        chon = None
        for p in pa:
            if not _cat_ai(p, hop, (c[0], c[1])):
                chon = p
                break
        if chon is None:
            chon = pa[-1]
        if len(chon) == 4 and chon[1][0] > x_max:
            lan_phai += 1
        elif len(chon) == 4 and chon[1][0] < x_min:
            lan_trai += 1
        ket[i] = chon

    return [(c[0], c[1], (c[2] if len(c) > 2 else ""), ket[i])
            for i, c in enumerate(canh)]


# ── Soát bố cục ────────────────────────────────────────────────────────────

def chong_nhau(hop) -> list[tuple[str, str]]:
    """Cặp khối phủ lên nhau. Lề 8 px để hai khối không dính sát cạnh."""
    h = list(hop.values())
    va = []
    for i in range(len(h)):
        for j in range(i + 1, len(h)):
            a, b = h[i], h[j]
            if (a.left - 8 < b.right and b.left - 8 < a.right
                    and a.top - 8 < b.bottom and b.top - 8 < a.bottom):
                va.append((a.ma, b.ma))
    return va


def _cat(p1, p2, h: Hop) -> bool:
    """Đoạn thẳng vuông góc p1-p2 có đi xuyên qua khối `h` không."""
    x1, y1 = p1
    x2, y2 = p2
    l, r, t, bo = h.left - 4, h.right + 4, h.top - 4, h.bottom + 4
    if x1 == x2:
        return l < x1 < r and min(y1, y2) < bo and t < max(y1, y2)
    if y1 == y2:
        return t < y1 < bo and min(x1, x2) < r and l < max(x1, x2)
    return False  # pragma: no cover — mọi đoạn đều vuông góc


def xuyen_khoi(canh, hop) -> list[tuple[str, str, str]]:
    """Đường nối đi xuyên qua một khối không phải đầu hay cuối của nó.

    Đây là lỗi bố cục duy nhất không thấy được khi đọc dữ liệu: ô lưới trông
    hợp lý mà đường nối vẫn cắt ngang một khối ở giữa đường. Phải soát bằng
    hình học, nếu không nó chỉ lộ ra khi mở StarUML.
    """
    xau = []
    for a, b, _, pts in canh:
        for ma, h in hop.items():
            if ma in (a, b):
                continue
            if any(_cat(pts[i], pts[i + 1], h) for i in range(len(pts) - 1)):
                xau.append((a, b, ma))
    return xau


def mot_dinh(khoi, canh) -> list[str]:
    """Lỗi về cấu trúc đồ thị, kiểm trước khi bàn tới bố cục."""
    ma = [k[0] for k in khoi]
    loi = []
    trung = {m for m in ma if ma.count(m) > 1}
    if trung:
        loi.append(f"mã khối trùng: {sorted(trung)}")
    for k in khoi:
        if k[1] not in KHOI:
            loi.append(f"khối {k[0]}: loại {k[1]!r} không có trong bảng")
    tap = set(ma)
    for c in canh:
        for d in c[:2]:
            if d not in tap:
                loi.append(f"đường nối trỏ tới khối {d!r} không tồn tại")
    vao = {m: 0 for m in ma}
    ra_ = {m: 0 for m in ma}
    for c in canh:
        ra_[c[0]] = ra_.get(c[0], 0) + 1
        vao[c[1]] = vao.get(c[1], 0) + 1
    goc = [m for m in ma if vao[m] == 0]
    if len(goc) != 1:
        loi.append(f"phải có đúng một khối không có đường vào, đang có {goc}")
    # Khối không có đường ra mà không phải khối kết thúc là một nhánh bị bỏ
    # dở: đọc sơ đồ thì tưởng đã xong, mà luồng thật ra cụt ở đó.
    loai_cua = {k[0]: k[1] for k in khoi}
    cut = [m for m, k in ra_.items() if k == 0 and loai_cua[m] != "term"]
    if cut:
        loi.append(f"khối không có đường ra mà không phải 'term': {cut}")
    for k in khoi:
        if k[1] == "dec":
            n = sum(1 for c in canh if c[0] == k[0])
            if n < 2:
                loi.append(f"khối quyết định {k[0]!r} chỉ có {n} đường ra")
            if any(not (len(c) > 2 and c[2]) for c in canh if c[0] == k[0]):
                loi.append(f"đường ra của {k[0]!r} thiếu nhãn")
    return loi


def in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252)."""
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass
