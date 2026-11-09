# -*- coding: utf-8 -*-
"""Chấm điểm một món cho một người — bốn giai đoạn, một chỗ duy nhất.

Vì sao tệp này tách riêng. Điểm ưa thích được tính ở **hai nơi khác nhau**:

    ml/evaluate.py  — khi đánh giá, để báo cáo con số trong Chương 3
    ml/serve.py     — khi phục vụ, để sinh thực đơn cho người dùng thật

Nếu hai nơi tự cài công thức riêng thì con số báo cáo không còn nói về hệ
thống đang chạy. Và đó là loại lệch **không ai phát hiện ra**: cả hai bên đều
chạy, đều trả về số trong [0, 1], chỉ là chúng mô tả hai hệ thống khác nhau.
Nên mọi công thức chấm điểm nằm ở đây, và cả hai bên đều gọi vào.

Mọi hàm ở đây là **hàm thuần**: nhận số, trả số, không chạm CSDL. Nhờ vậy
`tools/check_ml.py` kiểm được chúng mà không cần CSDL, và kiểm được cả những
ca biên mà dữ liệu thật không có.

Thang điểm chung là [0, 1] cho cả bốn giai đoạn. Đây là điều kiện để công
thức trộn `α·ML + (1−α)·cosin` có nghĩa — hai số cùng thang thì trộn được,
khác thang thì phép trộn là vô nghĩa dù vẫn ra một con số.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .f1_filter import LuatMem
from .features import cosine_similarity
from .rocchio import alpha

#: Tỷ lệ trộn giữa độ phổ biến và độ khớp macro ở Giai đoạn 0.
#:
#: Một tỷ lệ **đặt tay**, nêu ra thành hằng số có tên thay vì giấu trong một
#: biểu thức. Nửa–nửa vì ở Giai đoạn 0 hệ thống chưa biết gì về người này:
#: không có cơ sở nào để tin độ phổ biến hơn độ khớp dinh dưỡng hay ngược lại.
TRONG_SO_PHO_BIEN_GIAI_DOAN_0 = 0.5

#: Điểm trung tính. Trả về khi không có cơ sở nào để xếp món này trên hay
#: dưới món khác — hồ sơ sở thích rỗng, hoặc không có mô hình nào hoạt động.
#: Dùng 0,5 chứ không dùng 0: điểm 0 nghĩa là "không thích", khác hoàn toàn
#: với "chưa biết", và hạ mọi món xuống 0 sẽ làm Bước 4 mất hết thông tin xếp
#: hạng.
DIEM_TRUNG_TINH = 0.5


def diem_pho_bien(do_pho_bien: float) -> float:
    """Giai đoạn đối chứng tầm thường — chỉ độ phổ biến, bỏ qua cá nhân hóa.

    `foods.popularity_score` vốn đã nằm trong [0, 1] (`DECIMAL(5,4)`), nên
    không cần quy đổi gì. Kẹp lại để một dòng dữ liệu lỗi không đẩy điểm ra
    ngoài thang chung.
    """
    return min(1.0, max(0.0, do_pho_bien))


def do_khop_macro(
    v_mon: Sequence[float], muc_tieu_macro_pct: Sequence[float]
) -> float:
    """Món này khớp tỷ lệ macro mục tiêu của người dùng đến đâu, trong [0, 1].

        khớp = 1 − (tổng sai lệch tuyệt đối) / 2

    Chia 2 vì hai vector tỷ lệ đều cộng lại bằng 1, nên tổng sai lệch tuyệt
    đối giữa chúng tối đa là 2 — chia 2 đưa về đúng [0, 1] mà không phải kẹp.

    Ba chiều đầu của vector món là tỷ lệ **năng lượng** từ đạm / bột đường /
    béo, và `health_profiles.target_*_pct` cũng là tỷ lệ năng lượng, nên hai
    bên so được trực tiếp sau khi chia 100.
    """
    if len(v_mon) < 3:
        raise ValueError("vector món phải có ít nhất 3 chiều macro")
    if len(muc_tieu_macro_pct) != 3:
        raise ValueError("mục tiêu macro phải gồm đúng 3 phần trăm")

    tong_pct = sum(muc_tieu_macro_pct)
    if tong_pct <= 0:
        return DIEM_TRUNG_TINH
    # Chuẩn hóa về tổng 1 thay vì chia cứng cho 100: `chk_macro_sum` bắt tổng
    # phải bằng 100, nhưng nếu ràng buộc đó có ngày bị nới thì phép so vẫn
    # đúng thay vì lệch âm thầm.
    mt = [x / tong_pct for x in muc_tieu_macro_pct]
    lech = sum(abs(a - b) for a, b in zip(v_mon[:3], mt))
    return max(0.0, 1 - lech / 2)


def diem_luat(
    v_mon: Sequence[float],
    muc_tieu_macro_pct: Sequence[float],
    do_pho_bien: float,
) -> float:
    """Giai đoạn 0 — chưa có tín hiệu nào về khẩu vị.

    Trộn độ phổ biến với độ khớp macro mục tiêu. Phần lọc bệnh lý **không**
    nằm ở đây: `F1` áp cho mọi giai đoạn như nhau nên nó không phân biệt được
    giai đoạn nào hơn, và gộp nó vào hàm chấm điểm sẽ trộn lẫn một quyết định
    về **an toàn** với một quyết định về **sở thích**. Hai thứ đó phải tách
    nhau, nếu không thì khi phải giải thích vì sao một món bị bỏ sẽ không gỡ
    ra được là do bệnh lý hay do khẩu vị.
    """
    w = TRONG_SO_PHO_BIEN_GIAI_DOAN_0
    return w * diem_pho_bien(do_pho_bien) + (1 - w) * do_khop_macro(
        v_mon, muc_tieu_macro_pct
    )


def diem_noi_dung(p_u: Sequence[float], v_mon: Sequence[float]) -> float:
    """Giai đoạn 1 — `(1 + cos(p_u, vᵢ)) / 2`.

    Hồ sơ rỗng trả về điểm trung tính, đúng như `PreferenceProfile.score`
    phía Dart: khi mọi trọng số bằng 0 thì góc không xác định, và mọi món
    phải nhận cùng một điểm để thứ tự do các tiêu chí khác quyết định.
    """
    if not any(p_u):
        return DIEM_TRUNG_TINH
    return (1 + cosine_similarity(p_u, v_mon)) / 2


def tron(diem_ml: float, diem_noi_dung_: float, n_signals: int) -> float:
    """Chuyển tiếp mượt — `α·ML + (1−α)·cosin`, α theo `n_signals`.

    Không chuyển đột ngột khi vừa vượt ngưỡng, vì người dùng sẽ thấy thực đơn
    đổi bất thường ngay trong một ngày.
    """
    a = alpha(n_signals)
    return a * diem_ml + (1 - a) * diem_noi_dung_


# ── Ràng buộc mềm — hình phạt theo suất ───────────────────────────────
#
# `penalty` là **HỆ SỐ NHÂN**, không phải lượng trừ.
#
# Lược đồ chỉ nói `DECIMAL(4,3)` và `docs/DATABASE_DESIGN.md` từng gọi nó là
# "hệ số trừ điểm". Chính dữ liệu phản bác cách đọc đó:
#
#     Tăng huyết áp · natri ≤ 700 mg/suất · mức nhẹ  · penalty 0,600
#     Tăng huyết áp · natri ≤ 500 mg/suất · mức nặng · penalty 0,400
#         ghi chú: "Ràng buộc MỀM, phạt nặng hơn cho mức nặng"
#
# Nếu là phép trừ thì 0,400 trừ ít hơn 0,600, nghĩa là mức nặng bị phạt
# NHẸ hơn — ngược hẳn ghi chú của chính dòng đó. Là hệ số nhân thì ×0,400
# nặng hơn ×0,600, khớp. Phép nhân còn giữ điểm trong [0, 1], còn trừ 0,750
# sẽ đẩy một điểm [0, 1] xuống âm.


@dataclass(frozen=True)
class ViPhamMem:
    """Một ràng buộc mềm bị món này vượt."""

    benh: str
    nutrient: str
    comparator: str
    nguong: float
    gia_tri: float
    penalty: float
    note: str = ""

    @property
    def lech(self) -> float:
        """Lệch khỏi ngưỡng bao nhiêu, luôn là số dương."""
        if self.comparator == "lte":
            return self.gia_tri - self.nguong
        return self.nguong - self.gia_tri


@dataclass(frozen=True)
class KetQuaHinhPhat:
    """Hệ số phạt của một món, kèm lý do để giao diện nói ra."""

    he_so: float
    vi_pham: tuple[ViPhamMem, ...] = ()
    #: Chất mà món này không có số đo, nên không xét được luật mềm nào của
    #: nó. Không phạt, nhưng cũng không được coi là đã kiểm.
    thieu_so_lieu: tuple[str, ...] = ()

    @property
    def bi_tru_diem(self) -> bool:
        return self.he_so < 1.0

    def ap(self, diem: float) -> float:
        """Áp hệ số vào một điểm trong [0, 1].

        Giữ `diem` gốc ở phía gọi: giao diện cần nói "khớp khẩu vị 0,78,
        bị trừ vì mặn" chứ không phải chỉ hiện 0,47 mà không giải thích.
        """
        return diem * self.he_so


def hinh_phat(
    so_do: Mapping[str, float | None],
    luat: Sequence[LuatMem],
) -> KetQuaHinhPhat:
    """Hệ số phạt của một món theo các ràng buộc mềm **theo suất**.

    `so_do` là số dinh dưỡng của một suất, `{tên chất: giá trị}`; giá trị
    `None` nghĩa là không có số liệu.

    **Chỉ nhận `scope = 'per_serving'`.** Một luật `per_meal` hay `per_day`
    truyền vào đây là lỗi lập trình, không phải dữ liệu lạ: áp nó cho từng
    món sai cả hai chiều — bỏ sót trường hợp tổng bữa vượt dù không món nào
    vượt, và phạt oan một món lớn trong một bữa còn dư địa. Nên hàm nổ thay
    vì âm thầm tính ra một con số trông hợp lý.

    **Cộng hình phạt.** Hai luật cùng (bệnh, chất) là hai dải lồng nhau, ví
    dụ natri ≤ 700 mg và ≤ 500 mg của cùng Tăng huyết áp: một món 800 mg
    vượt cả hai, nhưng đó là **một** mối lo, không phải hai. Nhân cả hai sẽ
    ra ×0,24 thay vì ×0,40 — đếm đôi. Nên trong mỗi nhóm (bệnh, chất) lấy
    hệ số NẶNG NHẤT, rồi nhân qua các nhóm khác nhau.

    Thiếu số liệu thì **không phạt**, nhưng được ghi lại. Ràng buộc mềm là
    quyết định về xếp hạng, không phải về an toàn, nên hạ điểm một món vì
    danh mục thiếu số liệu là phạt sai đối tượng. Chiều này ngược với
    `f1_filter.loc_f1`, nơi thiếu số liệu thì loại — ở đó câu hỏi là "món
    này có an toàn không".
    """
    nang_nhat: dict[tuple[str, str], ViPhamMem] = {}
    thieu: list[str] = []

    for l in luat:
        if l.scope != "per_serving":
            raise ValueError(
                f"`hinh_phat` chỉ nhận luật per_serving, nhận {l.scope!r} "
                f"({l.benh} · {l.nutrient}). Luật per_meal thuộc Bước 4, "
                f"per_day thuộc ml/han_muc.py"
            )
        gia_tri = so_do.get(l.nutrient)
        if gia_tri is None:
            if l.nutrient not in thieu:
                thieu.append(l.nutrient)
            continue
        gia_tri = float(gia_tri)
        if not l.vi_pham(gia_tri):
            continue
        vp = ViPhamMem(
            benh=l.benh,
            nutrient=l.nutrient,
            comparator=l.comparator,
            nguong=l.nguong,
            gia_tri=gia_tri,
            penalty=l.penalty,
            note=l.note,
        )
        khoa = (l.benh, l.nutrient)
        cu = nang_nhat.get(khoa)
        if cu is None or vp.penalty < cu.penalty:
            nang_nhat[khoa] = vp

    he_so = 1.0
    for vp in nang_nhat.values():
        he_so *= vp.penalty

    return KetQuaHinhPhat(
        he_so=he_so,
        vi_pham=tuple(
            sorted(nang_nhat.values(), key=lambda v: (v.penalty, v.benh, v.nutrient))
        ),
        thieu_so_lieu=tuple(sorted(thieu)),
    )
