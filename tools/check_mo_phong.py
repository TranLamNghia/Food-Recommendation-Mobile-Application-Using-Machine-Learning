# -*- coding: utf-8 -*-
"""Kiểm tập lượt vuốt mô phỏng **có tín hiệu học được** hay không.

Tệp này tồn tại vì lần trước không có nó. `f1_user_food_behaviors_50x45.csv`
đi qua mọi phép kiểm đang có — đúng 2250 dòng, 45 `ma_mon` khớp deck, bốn giá
trị `lua_chon` hợp lệ, không ô trống — mà vẫn là nhiễu đều. Không phép kiểm
nào soát **nội dung thống kê** của dữ liệu, chỉ soát hình thức, nên một tập
hoàn toàn vô dụng vẫn báo xanh.

Năm phép kiểm dưới đây so tập cần kiểm với **chính nó sau khi xáo ngẫu
nhiên**. Xáo đánh giá của từng người giữa 45 món thì mọi liên hệ món↔người bị
phá, nhưng mọi đại lượng biên — số lượt mỗi mức của từng người, của từng
món — giữ nguyên. Vậy nên hiệu giữa giá trị thật và giá trị sau khi xáo chính
là phần tín hiệu, không lẫn phần biên.

Phép kiểm 5 là phép kiểm mà chỉ dữ liệu mô phỏng mới làm được: so hồ sơ
Rocchio khôi phục được với **vector khẩu vị ẩn đã dùng để sinh**. Dữ liệu
người thật không có đại lượng này — không ai biết vector thật của một người —
nên đây đúng là chỗ mô phỏng trả được giá trị của nó.

Chạy
────
    python tools/check_mo_phong.py                    # tệp mô phỏng
    python tools/check_mo_phong.py --so-sanh-goc      # kèm tệp gốc để đối chiếu
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import in_utf8  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ml.rocchio import TRONG_SO, dung_ho_so  # noqa: E402

DECK = ROOT / "data" / "survey" / "survey_deck.json"
MO_PHONG = ROOT / "data" / "survey" / "mo_phong" / "hanh_vi.csv"
SU_THAT = ROOT / "data" / "survey" / "mo_phong" / "khau_vi_that.json"
GOC = ROOT / "data" / "survey" / "da_dien" / "f1_user_food_behaviors_50x45.csv"

#: `lua_chon` trong phiếu → `interactions.action`. Giữ ở một chỗ, vì
#: `survey_deck.json` cũng mang chính ánh xạ này và hai bên lệch thì phép
#: kiểm đo một thứ khác với thứ trình nhập ghi vào CSDL.
SANG_ACTION = {
    "thich": "like",
    "khong_thich": "dislike",
    "binh_thuong": "neutral",
    "chua_biet": "unknown",
}

#: Số lần xáo để lấy dải nhiễu. 40 lần cho sai số chuẩn của trung bình nhiễu
#: khoảng 1/√40 ≈ 16% độ lệch của chính nó — đủ để nói "trong dải" hay
#: "ngoài dải" mà vẫn chạy trong vài giây.
SO_LAN_XAO = 40


class KhongGianDeck:
    """Vỏ mỏng để `ml.rocchio.dung_ho_so` chạy trên vector sẵn có trong deck.

    `dung_ho_so` chỉ gọi `kg.length` và `kg.encode(m)`, nên không cần dựng
    `KhongGianDacTrung` thật — tức là không cần CSDL. Phần **đang được
    kiểm** vẫn là mã Rocchio thật: công thức trọng số, cách loại `unknown`,
    cách xử mẫu số bằng 0. Chỉ phép mã hóa món là lấy sẵn, và nó đã được
    `check_feature_parity.py` kiểm riêng.
    """

    def __init__(self, vec: dict[str, list[float]], d: int) -> None:
        self._vec = vec
        self.length = d

    def encode(self, m: Any) -> list[float]:
        return self._vec[m]


# ── đại số và thống kê ────────────────────────────────────────────────────


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def trung_binh(v: Sequence[float]) -> float:
    return sum(v) / len(v)


def do_lech(v: Sequence[float]) -> float:
    if len(v) < 2:
        return 0.0
    tb = trung_binh(v)
    return math.sqrt(sum((x - tb) ** 2 for x in v) / (len(v) - 1))


def auc(duong: Sequence[float], am: Sequence[float]) -> float:
    """Diện tích dưới ROC bằng thống kê Mann–Whitney, có xử lý giá trị bằng nhau.

    0,5 là mức ngẫu nhiên. Dùng AUC chứ không dùng độ chính xác vì độ chính
    xác phụ thuộc ngưỡng, và một mô hình xếp hạng hoàn hảo vẫn có thể cho độ
    chính xác thấp nếu ngưỡng đặt sai — hai chuyện khác nhau, và chỉ chuyện
    thứ nhất là chuyện đang đo.
    """
    if not duong or not am:
        return float("nan")
    tong = 0.0
    for x in duong:
        for y in am:
            tong += 1.0 if x > y else 0.5 if x == y else 0.0
    return tong / (len(duong) * len(am))


# ── nạp ───────────────────────────────────────────────────────────────────


def nap_hanh_vi(duong_dan: Path) -> dict[str, dict[str, str]]:
    if not duong_dan.exists():
        raise SystemExit(
            f"không thấy {duong_dan}.\n"
            "Sinh trước bằng: python tools/sinh_khau_vi.py --ghi"
        )
    with duong_dan.open(encoding="utf-8-sig", newline="") as f:
        hang = list(csv.DictReader(f))
    mat: dict[str, dict[str, str]] = {}
    for h in hang:
        lc = h["lua_chon"].strip()
        if lc not in SANG_ACTION:
            raise SystemExit(f"`lua_chon` = {lc!r} không hợp lệ trong {duong_dan.name}")
        mat.setdefault(h["user_id"], {})[h["ma_mon"]] = lc
    return mat


# ── các phép đo ───────────────────────────────────────────────────────────

DIEM = {"thich": 1.0, "binh_thuong": 0.0, "khong_thich": -1.0, "chua_biet": None}


def cosine_nguoi_nguoi(mat: dict[str, dict[str, str]], mon: list[str]) -> float:
    """Cosine trung bình giữa mọi cặp người, chỉ trên món cả hai đã đánh."""
    users = sorted(mat)
    gt: list[float] = []
    for i, a in enumerate(users):
        for b in users[i + 1 :]:
            ks = [
                k
                for k in mon
                if DIEM[mat[a][k]] is not None and DIEM[mat[b][k]] is not None
            ]
            if len(ks) < 5:
                continue
            x = [DIEM[mat[a][k]] for k in ks]
            y = [DIEM[mat[b][k]] for k in ks]
            if any(x) and any(y):
                gt.append(cosine(x, y))
    return trung_binh(gt) if gt else float("nan")


def ti_so_phuong_sai(mat: dict[str, dict[str, str]], mon: list[str], muc: str) -> float:
    """Phương sai số lượt `muc` mỗi món, chia cho phương sai nhị thức.

    1,0 nghĩa là các món không khác nhau gì hơn mức tình cờ — tức không có
    món nào được thích hơn món nào.
    """
    n = len(mat)
    dem = [sum(1 for u in mat if mat[u][k] == muc) for k in mon]
    p = sum(dem) / (len(mon) * n)
    nhi_thuc = n * p * (1 - p)
    if nhi_thuc == 0:
        return float("nan")
    return (do_lech(dem) ** 2) / nhi_thuc


def xao(
    mat: dict[str, dict[str, str]], mon: list[str], rnd: random.Random
) -> dict[str, dict[str, str]]:
    """Xáo đánh giá của **từng người** giữa các món. Giữ mọi đại lượng biên."""
    return {
        u: dict(zip(mon, rnd.sample([mat[u][k] for k in mon], len(mon))))
        for u in mat
    }


def auc_rocchio(
    mat: dict[str, dict[str, str]], vec: dict[str, list[float]], mon: list[str]
) -> tuple[float, int]:
    """AUC của hồ sơ Rocchio, kiểm chéo bỏ-một.

    Với mỗi món đã đánh, dựng `p_u` từ **44 món còn lại** rồi chấm món bị
    giữ lại. Không bỏ-một thì món cần đoán đã nằm trong vector đi chấm chính
    nó, và AUC sẽ cao vì rò rỉ nhãn, không vì mô hình đúng.
    """
    kg = KhongGianDeck(vec, len(next(iter(vec.values()))))
    duong: list[float] = []
    am: list[float] = []
    for u, chon in mat.items():
        da_danh = [k for k in mon if chon[k] != "chua_biet"]
        for giu in da_danh:
            if chon[giu] == "binh_thuong":
                continue  # trung tính không thuộc lớp nào trong phép so này
            luot = [(k, SANG_ACTION[chon[k]]) for k in da_danh if k != giu]
            ho_so = dung_ho_so(kg, luot)
            if ho_so.is_empty:
                continue
            s = cosine(ho_so.weights, vec[giu])
            (duong if chon[giu] == "thich" else am).append(s)
    return auc(duong, am), len(duong) + len(am)


def khoi_phuc_vector_an(
    mat: dict[str, dict[str, str]],
    vec: dict[str, list[float]],
    mon: list[str],
    su_that: dict[str, Any],
) -> dict[str, float]:
    """`cos(p_u, t_u)` cho từng người: Rocchio khôi phục vector ẩn tới đâu."""
    kg = KhongGianDeck(vec, len(next(iter(vec.values()))))
    ra: dict[str, float] = {}
    for u, chon in mat.items():
        t = su_that["nguoi"].get(u)
        if t is None:
            continue
        luot = [(k, SANG_ACTION[chon[k]]) for k in mon]
        ho_so = dung_ho_so(kg, luot)
        if not ho_so.is_empty:
            ra[u] = cosine(ho_so.weights, t["vector_khau_vi"])
    return ra


def cum_trong_ngoai(
    mat: dict[str, dict[str, str]], mon: list[str], su_that: dict[str, Any]
) -> tuple[float, float]:
    """Cosine trung bình của cặp cùng nguyên mẫu chính, và của cặp khác."""
    users = sorted(mat)
    cung: list[float] = []
    khac: list[float] = []
    for i, a in enumerate(users):
        for b in users[i + 1 :]:
            ks = [
                k
                for k in mon
                if DIEM[mat[a][k]] is not None and DIEM[mat[b][k]] is not None
            ]
            x = [DIEM[mat[a][k]] for k in ks]
            y = [DIEM[mat[b][k]] for k in ks]
            if not any(x) or not any(y):
                continue
            c = cosine(x, y)
            cung_mau = (
                su_that["nguoi"][a]["nguyen_mau"] == su_that["nguoi"][b]["nguyen_mau"]
            )
            (cung if cung_mau else khac).append(c)
    return (
        trung_binh(cung) if cung else float("nan"),
        trung_binh(khac) if khac else float("nan"),
    )


# ── chạy ──────────────────────────────────────────────────────────────────


def bao_cao(
    ten: str,
    mat: dict[str, dict[str, str]],
    vec: dict[str, list[float]],
    mon: list[str],
    su_that: dict[str, Any] | None,
    *,
    seed: int,
) -> list[tuple[bool, str]]:
    """In các phép đo, trả về danh sách (đạt, mô tả)."""
    ket: list[tuple[bool, str]] = []
    rnd = random.Random(seed)
    print(f"\n── {ten} ── {len(mat)} người × {len(mon)} món")

    dem = collections.Counter(v for chon in mat.values() for v in chon.values())
    tong = sum(dem.values())
    print(
        "  phân bố: "
        + "  ".join(f"{k}={dem[k]} ({dem[k]/tong:.1%})" for k in DIEM if dem[k])
    )

    # 1. cosine người–người đối lại dải nhiễu
    that = cosine_nguoi_nguoi(mat, mon)
    nhieu = [cosine_nguoi_nguoi(xao(mat, mon, rnd), mon) for _ in range(SO_LAN_XAO)]
    tb_n, sd_n = trung_binh(nhieu), do_lech(nhieu)
    z = (that - tb_n) / sd_n if sd_n else float("nan")
    dat = z > 3.0
    print(
        f"  1. cosine người–người      {that:+.4f}  "
        f"nhiễu {tb_n:+.4f} ± {sd_n:.4f}  →  z = {z:+.1f}"
    )
    ket.append((dat, "cosine người–người vượt dải nhiễu (z > 3)"))

    # 2. phương sai mỗi món đối lại nhị thức
    for muc in ("thich", "khong_thich"):
        r = ti_so_phuong_sai(mat, mon, muc)
        sd_ts = math.sqrt(2.0 / (len(mon) - 1))
        z2 = (r - 1.0) / sd_ts
        print(
            f"  2. phương sai `{muc}`/nhị thức  {r:.2f}  "
            f"(1,00 = tình cờ, sd {sd_ts:.2f})  →  z = {z2:+.1f}"
        )
        ket.append((z2 > 3.0, f"các món khác nhau thật ở `{muc}` (z > 3)"))

    # 3. AUC Rocchio bỏ-một
    a, n = auc_rocchio(mat, vec, mon)
    print(f"  3. AUC Rocchio (bỏ-một)    {a:.3f}  trên {n} lượt thích/không thích")
    ket.append((a > 0.60, "Rocchio xếp hạng hơn mức ngẫu nhiên (AUC > 0,60)"))

    # 4. `chua_biet` không được phụ thuộc khẩu vị
    if su_that is not None:
        s_cb: list[float] = []
        s_kh: list[float] = []
        for u, chon in mat.items():
            t = su_that["nguoi"][u]["vector_khau_vi"]
            for k in mon:
                (s_cb if chon[k] == "chua_biet" else s_kh).append(cosine(t, vec[k]))
        lech = trung_binh(s_cb) - trung_binh(s_kh)
        hop = do_lech(s_cb) / math.sqrt(len(s_cb)) + do_lech(s_kh) / math.sqrt(len(s_kh))
        print(
            f"  4. độ gần của món `chua_biet` lệch {lech:+.4f} "
            f"(± {hop:.4f}) so với món đã đánh"
        )
        ket.append(
            (abs(lech) < 3 * hop, "`chua_biet` độc lập với khẩu vị (thiếu ngẫu nhiên)")
        )

        # 5. khôi phục vector ẩn
        theo_nguoi = khoi_phuc_vector_an(mat, vec, mon, su_that)
        kp = sorted(theo_nguoi.values())
        print(
            f"  5. cos(p_u, t_u)           trung bình {trung_binh(kp):.3f}  "
            f"(thấp nhất {kp[0]:.3f} · trung vị {kp[len(kp)//2]:.3f} · "
            f"cao nhất {kp[-1]:.3f})"
        )
        ket.append((trung_binh(kp) > 0.50, "Rocchio khôi phục được vector ẩn (> 0,50)"))

        # 6. Cấu trúc cụm — đại lượng mà lọc cộng tác sống nhờ vào.
        #
        # Cần đo riêng chứ không suy từ phép kiểm 1: cosine trung bình toàn
        # cục có thể cao chỉ vì mọi vector khẩu vị đều lệch về một phía
        # (chẳng hạn khi λ nguyên mẫu phụ lớn), mà vẫn không có cụm nào. Chỉ
        # hiệu giữa "cùng nguyên mẫu" và "khác nguyên mẫu" mới là cấu trúc.
        cung, khac = cum_trong_ngoai(mat, mon, su_that)
        print(
            f"  6. cosine cùng nguyên mẫu  {cung:+.4f}  "
            f"đối lại khác nguyên mẫu {khac:+.4f}  →  {cung/khac:.1f}×"
        )
        ket.append((cung > 2 * khac, "có cấu trúc cụm cho lọc cộng tác (> 2×)"))

        # Khôi phục theo từng nguyên mẫu, kèm số món của cụm. In ra vì đây là
        # con số có ích nhất cho Chương 3: nó cho thấy Rocchio khôi phục
        # được khẩu vị ĐÚNG THEO MỨC bộ món đại diện cho khẩu vị đó.
        print("     khôi phục theo nguyên mẫu (số món của cụm → cos trung bình):")
        gom: dict[int, list[float]] = {}
        for u, c in theo_nguoi.items():
            gom.setdefault(su_that["nguoi"][u]["nguyen_mau"], []).append(c)
        co = {nm["chi_so"]: nm["so_mon_trong_cum"] for nm in su_that["nguyen_mau"]}
        for z in sorted(gom, key=lambda k: -co[k]):
            dai_dien = next(
                nm["mon_dai_dien"][0]
                for nm in su_that["nguyen_mau"]
                if nm["chi_so"] == z
            )
            print(
                f"       #{z} · {co[z]:>2} món · {trung_binh(gom[z]):.3f}"
                f"   ({dai_dien}…)"
            )

    return ket


def main() -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument(
        "--so-sanh-goc",
        action="store_true",
        dest="so_sanh",
        help="đo cả tệp khảo sát gốc để đối chiếu",
    )
    bo.add_argument("--seed", type=int, default=7)
    t = bo.parse_args()

    deck = json.loads(DECK.read_text(encoding="utf-8"))
    vec = {m["id"]: m["vector"] for m in deck["mon"]}
    mon = [m["id"] for m in sorted(deck["mon"], key=lambda m: m["thu_tu"])]

    if not SU_THAT.exists():
        raise SystemExit(
            f"không thấy {SU_THAT}.\n"
            "Sinh trước bằng: python tools/sinh_khau_vi.py --ghi"
        )
    su_that = json.loads(SU_THAT.read_text(encoding="utf-8"))
    if su_that.get("feature_version") != deck.get("feature_version"):
        raise SystemExit(
            f"lệch phiên bản đặc trưng: mô phỏng sinh trên "
            f"{su_that.get('feature_version')}, deck hiện là "
            f"{deck.get('feature_version')}.\nSinh lại: "
            "python tools/sinh_khau_vi.py --ghi"
        )

    mat = nap_hanh_vi(MO_PHONG)
    thieu = set(mat) - set(su_that["nguoi"])
    if thieu:
        raise SystemExit(
            f"{len(thieu)} người trong hanh_vi.csv không có vector ẩn "
            f"trong khau_vi_that.json ({', '.join(sorted(thieu)[:3])}…) — "
            "hai tệp không cùng một lần sinh."
        )

    ket = bao_cao("MÔ PHỎNG", mat, vec, mon, su_that, seed=t.seed)

    if t.so_sanh and GOC.exists():
        ket_goc = bao_cao(
            "KHẢO SÁT GỐC (để đối chiếu)", nap_hanh_vi(GOC), vec, mon, None, seed=t.seed
        )
        print(
            "\n  Tệp gốc không có vector ẩn nên phép kiểm 4, 5, 6 không áp "
            "được cho nó."
        )
        # Phép thử phủ định, và nó là phần quan trọng nhất của tệp này. Một
        # bộ kiểm chỉ báo xanh trên dữ liệu tốt thì chưa chứng minh được gì:
        # nó có thể báo xanh trên mọi thứ. Tệp gốc là nhiễu đã biết, nên nó
        # PHẢI trượt — và nếu nó không trượt thì ngưỡng đang quá lỏng, tức
        # lần sau một tập nhiễu khác sẽ lại lọt qua đúng như lần này.
        truot_goc = sum(1 for ok, _ in ket_goc if not ok)
        if truot_goc >= 3:
            print(
                f"  Phép thử phủ định ĐẠT: tệp nhiễu trượt {truot_goc}/"
                f"{len(ket_goc)} phép kiểm áp được."
            )
        else:
            print(
                f"  Phép thử phủ định TRƯỢT: tệp nhiễu chỉ trượt {truot_goc}/"
                f"{len(ket_goc)} phép kiểm — ngưỡng đang quá lỏng, siết lại "
                "trước khi tin vào phần MÔ PHỎNG ở trên."
            )
            ket.append((False, "phép thử phủ định trên tệp nhiễu đã biết"))

    print(f"\n{'─' * 62}")
    truot = [m for ok, m in ket if not ok]
    for ok, m in ket:
        print(f"  {'đạt ' if ok else 'TRƯỢT'}  {m}")
    if truot:
        print(f"\n{len(truot)}/{len(ket)} phép kiểm trượt — tập mô phỏng chưa dùng được.")
        print("Tăng --beta (tín hiệu rõ hơn) hoặc giảm --sigma (các nguyên mẫu")
        print("tách hơn) ở tools/sinh_khau_vi.py rồi sinh lại.")
        return 1
    print(f"\n{len(ket)}/{len(ket)} phép kiểm đạt. Tập mô phỏng có tín hiệu học được.")
    print("Nhắc lại: đây là dữ liệu MÔ PHỎNG, phải ghi đúng như vậy ở Chương 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
