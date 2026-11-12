# -*- coding: utf-8 -*-
"""Sinh lượt vuốt mô phỏng từ một vector khẩu vị ẩn đã biết trước.

Vì sao tệp này tồn tại
──────────────────────
Tập `f1_user_food_behaviors_50x45.csv` không mang tín hiệu nào: cosine
người–người là +0,0359 trong khi cùng phép đo sau khi xáo ngẫu nhiên từng
người cho +0,0328, tức giá trị thật nằm **trong** dải nhiễu. Phương sai số
lượt `thich` mỗi món chỉ bằng 1,15 lần phương sai nhị thức (sd của tỉ số này
ở 45 món là 0,21). Không mô hình nào học được gì từ đó, nên Chương 3 sẽ chỉ
đo lại mức đa số 41,0%.

Tệp này thay nhiễu bằng **mô phỏng có ground truth**: mỗi người ảo nhận một
vector khẩu vị ẩn `t_u` trong chính không gian 20 chiều mà hệ thống dùng, rồi
lựa chọn được rút ra từ độ gần giữa `t_u` và vector món. Khác biệt với tệp cũ
không phải "có tín hiệu mạnh hơn" mà là **biết trước đáp án**: Chương 3 đo
được `cos(p_u, t_u)` — hồ sơ Rocchio khôi phục lại vector ẩn tới mức nào —
chứ không chỉ đo độ chính xác trên một tập kiểm chẳng ai biết nhãn đúng.

Đây là dữ liệu MÔ PHỎNG và phải được viết đúng như vậy trong báo cáo. Nó
chứng minh **mô hình chạy đúng** (khôi phục được cái đã biết), không chứng
minh **người Việt ăn gì**. Hai câu đó khác nhau, và chỉ câu đầu mới đo được
bằng dữ liệu sinh ra.

Mô hình sinh
────────────
1.  **5 khẩu vị nguyên mẫu** `c_1..c_5`: tâm của 5 cụm k-means trên chính 45
    vector món. Lấy từ dữ liệu món chứ không bốc tay, vì hồ sơ Rocchio
    `p_u = Σ w·v / Σ|w|` là một **trung bình có dấu của vector món** — nó chỉ
    biểu diễn được những hướng nằm trong vùng mà vector món phủ tới. Một
    `t_u` bốc đều trong [0,1]^20 sẽ nằm ngoài vùng đó, và cosine khôi phục sẽ
    thấp vì lý do hình học, không phải vì mô hình học kém.

2.  **Vector ẩn của từng người**: `t_u = c_{z1} + λ·c_{z2} + σ·N(0, I) + δ_u`,
    với `z1` là nguyên mẫu chính và `z2 ≠ z1` là nguyên mẫu phụ.
    `z1` chia vòng tròn nên đúng 10 người mỗi nguyên mẫu — bốc đa thức có
    thể để trống một nguyên mẫu ở n = 50, và khi đó phép đo cụm mất nghĩa.

    **Vì sao phải trộn hai nguyên mẫu.** Bản đầu dùng đúng một: `t_u = c_z`.
    Nhưng k-means chạy trên *món*, và một cụm món không phải một khẩu vị
    người. Cụm `Đồ uống` chỉ có 4 trong 45 món, nên 10 người thuộc cụm đó
    thành người "chỉ thích nước ép, không thích 16 món chính" — không có
    người thật nào như vậy. Và hệ quả đo được: `cos(p_u, t_u)` của chính 10
    người đó là 0,02–0,37 trong khi những người khác đạt 0,92–0,95, vì hồ sơ
    Rocchio khi ấy bị phần `không thích` chi phối và trỏ **ra xa** khẩu vị
    thật thay vì trỏ vào nó.

    Trộn một nguyên mẫu phụ với trọng số λ = 0,5 vừa đúng với người thật hơn
    — ai cũng có một gu món chính cộng một gu món phụ — vừa bỏ được trường
    hợp suy biến đó, mà **không** làm nhẹ bài toán: `z1` vẫn chia vòng tròn
    nên cấu trúc cụm cho lọc cộng tác vẫn còn nguyên.

3.  **`δ_u` — phần hồ sơ sức khỏe chi phối khẩu vị.** Chỉ hai cột của
    ObesityDataSet nói về *thức ăn*, nên chỉ hai cột đó được phép tác động:
    `FAVC` (ăn thức ăn nhiều năng lượng thường xuyên) đẩy chiều `Tỷ lệ béo`
    và `Năng lượng`; `FCVC` (tần suất ăn rau, 1–3) đẩy chiều `Chất xơ`. Các
    cột còn lại — `MTRANS`, `TUE`, `SMOKE`… — không liên quan tới khẩu vị,
    và nối chúng vào là tự tạo ra một phát hiện không có thật.

    Biên độ cố tình nhỏ (mặc định 0,10 trên thang [0,1]) để nguyên mẫu vẫn
    là phần chi phối. Nếu hồ sơ chi phối khẩu vị thì bài toán gợi ý biến
    thành bài toán hồi quy trên hồ sơ, và Bước 2 trở thành vô dụng — tức là
    mô phỏng đã tự trả lời mất câu hỏi mà đồ án đặt ra.

4.  **`chua_biet` độc lập với khẩu vị.** "Chưa từng ăn" là tính chất của
    *món* — món lạ thì nhiều người chưa ăn — nên mỗi món nhận một xu hướng
    `q_i ~ Beta` trung bình 0,16, rồi mỗi người rút Bernoulli(`q_i`). Cho
    `chua_biet` phụ thuộc khẩu vị là sai cả về nghĩa lẫn về hệ quả: nó biến
    dữ liệu thiếu thành *missing not at random*, và khi đó vector Rocchio
    lệch có hệ thống dù công thức đúng.

5.  **Ba mức còn lại rút bằng ordered logit.** `y* = β·z(s) + ε`, với
    `s = cos(t_u, v_i)`, `z` là chuẩn hóa toàn cục, `ε ~ Logistic(0,1)`. Hai
    điểm cắt lấy đúng tại phân vị của `y*` ứng với tỉ lệ biên của tệp gốc
    (`khong_thich` 25,8%, `binh_thuong` 33,2%, `thich` 41,0% trong số lượt đã
    đánh), nên phân bố biên **trùng tệp gốc** và hai tệp so được với nhau.

    `ε` chính là nhiễu nhãn, không cần thêm bước đảo nhãn: β điều khiển tỉ số
    giữa tín hiệu và nhiễu. β quá lớn thì bài toán thành tách tuyến tính
    hoàn hảo và mọi mô hình đều đạt ~100% — một kết quả không nói lên gì.

Chạy
────
    python tools/sinh_khau_vi.py                       # xem trước, không ghi
    python tools/sinh_khau_vi.py --ghi
    python tools/check_mo_phong.py                     # kiểm có tín hiệu thật

Không cần CSDL: vector món đã nằm trong `survey_deck.json`.
"""

from __future__ import annotations

import argparse
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
DECK = ROOT / "data" / "survey" / "survey_deck.json"
HO_SO = ROOT / "data" / "survey" / "f1_training_dataset_50_users.csv"
RA_THU_MUC = ROOT / "data" / "survey" / "mo_phong"
RA_HANH_VI = RA_THU_MUC / "hanh_vi.csv"
RA_SU_THAT = RA_THU_MUC / "khau_vi_that.json"

#: Tên 20 chiều, đúng thứ tự `KhongGianDacTrung.encode`: 8 chiều cố định rồi
#: one-hot nhóm món theo thứ tự `sorted()`. Phần one-hot được **suy lại từ
#: chính deck** trong `nhan_chieu()` chứ không gõ tay, vì thứ tự phụ thuộc
#: tập 318 món trong CSDL — gõ tay thì nó đúng tới lần ai đó thêm một nhóm.
NHAN_CO_DINH = (
    "Tỷ lệ đạm",
    "Tỷ lệ bột đường",
    "Tỷ lệ béo",
    "Năng lượng",
    "Vị ngọt",
    "Vị mặn",
    "Chất xơ",
    "Mức cay",
)

#: Chiều mà `FAVC`/`FCVC` được phép đẩy. Khóa là tên chiều, không phải chỉ số:
#: chỉ số 2 hôm nay là `Tỷ lệ béo`, và sẽ không còn là nó nếu tập chiều đổi.
CHIEU_FAVC = ("Tỷ lệ béo", "Năng lượng")
CHIEU_FCVC = ("Chất xơ",)

#: Tỉ lệ biên của tệp gốc, trong số lượt **đã đánh** (bỏ `chua_biet`):
#: 488 / 628 / 774 trên 1890. Giữ nguyên để hai tệp so được với nhau.
TI_LE_BIEN = {"khong_thich": 488 / 1890, "binh_thuong": 628 / 1890}

#: Tỉ lệ `chua_biet` của tệp gốc: 360 / 2250.
TI_LE_CHUA_BIET = 360 / 2250

#: Độ tập trung của `Beta` sinh xu hướng `chua_biet` từng món. Càng lớn thì
#: các món càng giống nhau; 6,0 cho khoảng xấp xỉ 0,03–0,40, tức có món hầu
#: như ai cũng từng ăn và có món hơn một phần ba chưa ăn.
BETA_CHUA_BIET = 6.0

MUC = ("khong_thich", "binh_thuong", "thich", "chua_biet")


# ── đại số vector, viết tay để tệp này không cần numpy ────────────────────


def cong(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x + y for x, y in zip(a, b)]


def nhan(a: Sequence[float], k: float) -> list[float]:
    return [x * k for x in a]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def khoang_cach_binh_phuong(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# ── nạp đầu vào ───────────────────────────────────────────────────────────


def nap_deck(duong_dan: Path) -> list[dict[str, Any]]:
    deck = json.loads(duong_dan.read_text(encoding="utf-8"))
    mon = sorted(deck["mon"], key=lambda m: m["thu_tu"])
    if not mon:
        raise SystemExit(f"{duong_dan} không có món nào.")
    d = len(mon[0]["vector"])
    for m in mon:
        if len(m["vector"]) != d:
            raise SystemExit(
                f"món {m['name']!r} có vector {len(m['vector'])} chiều, "
                f"các món khác {d} chiều — deck hỏng."
            )
    return mon


def nhan_chieu(mon: list[dict[str, Any]]) -> list[str]:
    """Tên 20 chiều, phần one-hot suy từ deck."""
    d = len(mon[0]["vector"])
    ten = list(NHAN_CO_DINH) + [f"nhóm #{i}" for i in range(len(NHAN_CO_DINH), d)]
    for m in mon:
        nong = [i for i in range(len(NHAN_CO_DINH), d) if m["vector"][i] == 1.0]
        if len(nong) == 1:
            ten[nong[0]] = f"Nhóm: {m['category']}"
    return ten


def nap_ho_so(duong_dan: Path) -> list[dict[str, str]]:
    """Một dòng mỗi người, lấy dòng đầu gặp của mỗi `user_id`."""
    with duong_dan.open(encoding="utf-8-sig", newline="") as f:
        hang = list(csv.DictReader(f))
    if not hang:
        raise SystemExit(f"{duong_dan} không có dòng dữ liệu nào.")
    thieu = {"user_id", "FAVC", "FCVC", "source_profile_row"} - set(hang[0])
    if thieu:
        raise SystemExit(f"{duong_dan} thiếu cột: {', '.join(sorted(thieu))}")
    theo_nguoi: dict[str, dict[str, str]] = {}
    for h in hang:
        theo_nguoi.setdefault(h["user_id"], h)
    return [theo_nguoi[u] for u in sorted(theo_nguoi)]


# ── k-means trên vector món, để lấy khẩu vị nguyên mẫu ────────────────────


def kmeans(
    diem: list[Sequence[float]], k: int, *, seed: int, so_lan: int = 30
) -> tuple[list[list[float]], list[int]]:
    """Lloyd với khởi tạo k-means++, chạy lại nhiều lần và giữ lần tốt nhất.

    Chạy lại là cần: Lloyd hội tụ về cực tiểu địa phương, nên một lần chạy
    duy nhất cho ra tâm khác nhau theo seed — và khi đó "5 khẩu vị nguyên
    mẫu" không còn là một đại lượng của dữ liệu mà là của hạt giống.
    """
    rnd = random.Random(seed)
    d = len(diem[0])
    tot: tuple[float, list[list[float]], list[int]] | None = None

    for _ in range(so_lan):
        # k-means++: tâm đầu bốc đều, các tâm sau bốc theo D² tới tâm gần nhất.
        tam = [list(diem[rnd.randrange(len(diem))])]
        while len(tam) < k:
            w = [min(khoang_cach_binh_phuong(p, c) for c in tam) for p in diem]
            tong = sum(w)
            if tong == 0.0:
                tam.append(list(diem[rnd.randrange(len(diem))]))
                continue
            moc = rnd.random() * tong
            acc = 0.0
            for p, wi in zip(diem, w):
                acc += wi
                if acc >= moc:
                    tam.append(list(p))
                    break

        gan: list[int] = [0] * len(diem)
        for _buoc in range(100):
            moi = [
                min(range(k), key=lambda j: khoang_cach_binh_phuong(p, tam[j]))
                for p in diem
            ]
            if moi == gan and _buoc:
                break
            gan = moi
            for j in range(k):
                thuoc = [p for p, g in zip(diem, gan) if g == j]
                if thuoc:
                    tam[j] = [sum(p[i] for p in thuoc) / len(thuoc) for i in range(d)]
                else:
                    # Cụm rỗng: dời tâm tới điểm xa tâm của nó nhất, thay vì
                    # bỏ cụm. Bỏ thì k thực tế nhỏ hơn k đã khai.
                    xa = max(
                        range(len(diem)),
                        key=lambda i: khoang_cach_binh_phuong(diem[i], tam[gan[i]]),
                    )
                    tam[j] = list(diem[xa])

        sse = sum(khoang_cach_binh_phuong(p, tam[g]) for p, g in zip(diem, gan))
        if tot is None or sse < tot[0]:
            tot = (sse, [list(c) for c in tam], list(gan))

    assert tot is not None
    return tot[1], tot[2]


# ── sinh ──────────────────────────────────────────────────────────────────


def day_theo_ho_so(
    h: dict[str, str], ten_chieu: list[str], bien_do: float
) -> list[float]:
    """`δ_u` — phần hồ sơ sức khỏe đẩy vector khẩu vị."""
    d = [0.0] * len(ten_chieu)
    chi_so = {t: i for i, t in enumerate(ten_chieu)}

    if (h.get("FAVC") or "").strip().lower() == "yes":
        for t in CHIEU_FAVC:
            d[chi_so[t]] += bien_do

    # FCVC chạy 1–3, mốc giữa là 2. Lệch khỏi mốc giữa bao nhiêu thì đẩy
    # chiều chất xơ bấy nhiêu — ăn ít rau (FCVC = 1) thì đẩy xuống.
    try:
        fcvc = float(h.get("FCVC") or 2.0)
    except ValueError:
        fcvc = 2.0
    for t in CHIEU_FCVC:
        d[chi_so[t]] += bien_do * max(-1.0, min(1.0, fcvc - 2.0))

    return d


def sinh(
    *,
    mon: list[dict[str, Any]],
    ho_so: list[dict[str, str]],
    so_nguyen_mau: int,
    lam_phu: float,
    sigma: float,
    beta: float,
    bien_do_ho_so: float,
    seed: int,
) -> dict[str, Any]:
    ten_chieu = nhan_chieu(mon)
    vec = [m["vector"] for m in mon]
    tam, gan_mon = kmeans(vec, so_nguyen_mau, seed=seed)

    # Nhãn cho từng nguyên mẫu: ba món gần tâm nhất. Một nguyên mẫu không đọc
    # được thì không viết được vào báo cáo.
    nhan_nguyen_mau = []
    for j, c in enumerate(tam):
        gan_nhat = sorted(mon, key=lambda m: khoang_cach_binh_phuong(m["vector"], c))
        nhan_nguyen_mau.append(
            {
                "chi_so": j,
                "so_mon_trong_cum": sum(1 for g in gan_mon if g == j),
                "mon_dai_dien": [m["name"] for m in gan_nhat[:3]],
                "tam": [round(x, 6) for x in c],
            }
        )

    rnd = random.Random(seed + 1)

    # Xu hướng `chua_biet` của từng món. Beta(a, b) với a + b = BETA_CHUA_BIET
    # và a / (a + b) = TI_LE_CHUA_BIET.
    a = TI_LE_CHUA_BIET * BETA_CHUA_BIET
    b = BETA_CHUA_BIET - a
    q = [rnd.betavariate(a, b) for _ in mon]

    # Chia vòng tròn trên danh sách đã xáo: cân bằng tuyệt đối giữa các
    # nguyên mẫu, mà vẫn không gán theo thứ tự `user_id`.
    thu_tu = list(range(len(ho_so)))
    rnd.shuffle(thu_tu)
    z = {}
    for vi_tri, i in enumerate(thu_tu):
        z[ho_so[i]["user_id"]] = vi_tri % so_nguyen_mau

    nguoi: dict[str, dict[str, Any]] = {}
    for h in ho_so:
        u = h["user_id"]
        phu = rnd.choice([j for j in range(so_nguyen_mau) if j != z[u]])
        t = cong(tam[z[u]], nhan(tam[phu], lam_phu))
        t = cong(t, [rnd.gauss(0.0, sigma) for _ in ten_chieu])
        t = cong(t, day_theo_ho_so(h, ten_chieu, bien_do_ho_so))
        nguoi[u] = {
            "nguyen_mau": z[u],
            "nguyen_mau_phu": phu,
            "vector_khau_vi": [round(x, 6) for x in t],
            "benh_ly": [],  # ObesityDataSet không có cột bệnh lý nào.
        }

    # Độ gần, rồi chuẩn hóa toàn cục. Chuẩn hóa toàn cục chứ không theo từng
    # người: chuẩn hóa theo người sẽ ép mọi người có cùng số lượt `thich`, và
    # mất luôn chuyện người kén ăn khác người dễ ăn.
    s: dict[tuple[str, int], float] = {}
    for h in ho_so:
        u = h["user_id"]
        t = nguoi[u]["vector_khau_vi"]
        for i, m in enumerate(mon):
            s[(u, i)] = cosine(t, m["vector"])
    gt = list(s.values())
    tb = sum(gt) / len(gt)
    sd = math.sqrt(sum((x - tb) ** 2 for x in gt) / (len(gt) - 1)) or 1.0

    # `chua_biet` rút trước và độc lập — nó không được xem `s`.
    chua_biet = {
        (h["user_id"], i): rnd.random() < q[i] for h in ho_so for i in range(len(mon))
    }

    # Ordered logit. Rút `ε` cho mọi cặp rồi lấy phân vị, nên tỉ lệ biên trùng
    # mục tiêu đúng bằng phép dựng, không phải sau vài lần thử seed.
    y: dict[tuple[str, int], float] = {}
    for khoa, gia_tri in s.items():
        if chua_biet[khoa]:
            continue
        # Logistic(0, 1) bằng phép biến đổi nghịch đảo của hàm phân phối.
        # `random()` trả [0, 1) nên 0 là giá trị có thể gặp; kẹp vào trong
        # khoảng mở để `log` không vỡ.
        p = min(max(rnd.random(), 1e-12), 1.0 - 1e-12)
        y[khoa] = beta * (gia_tri - tb) / sd + math.log(p / (1.0 - p))

    sap = sorted(y.values())
    c1 = sap[int(round(TI_LE_BIEN["khong_thich"] * len(sap)))]
    c2 = sap[
        int(round((TI_LE_BIEN["khong_thich"] + TI_LE_BIEN["binh_thuong"]) * len(sap)))
    ]

    hang: list[dict[str, str]] = []
    for h in ho_so:
        u = h["user_id"]
        for i, m in enumerate(mon):
            if chua_biet[(u, i)]:
                lc = "chua_biet"
            else:
                yv = y[(u, i)]
                lc = "khong_thich" if yv < c1 else "binh_thuong" if yv < c2 else "thich"
            hang.append(
                {
                    "user_id": u,
                    "source_profile_row": h["source_profile_row"],
                    "ma_mon": m["id"],
                    "ten_mon": m["name"],
                    "nhom": m["category"],
                    "muc_cay": str(m["spice_level"]),
                    "lua_chon": lc,
                }
            )

    return {
        "hang": hang,
        "su_that": {
            "_doc": (
                "DỮ LIỆU MÔ PHỎNG. `vector_khau_vi` là vector ẩn đã dùng để "
                "sinh lượt vuốt trong hanh_vi.csv; Chương 3 so hồ sơ Rocchio "
                "khôi phục được với chính nó. Không phải dữ liệu người thật."
            ),
            "feature_version": json.loads(DECK.read_text(encoding="utf-8"))[
                "feature_version"
            ],
            "ten_chieu": ten_chieu,
            "tham_so": {
                "seed": seed,
                "so_nguyen_mau": so_nguyen_mau,
                "lam_nguyen_mau_phu": lam_phu,
                "sigma": sigma,
                "beta": beta,
                "bien_do_ho_so": bien_do_ho_so,
                "diem_cat": [round(c1, 6), round(c2, 6)],
                "ti_le_bien_muc_tieu": TI_LE_BIEN,
                "ti_le_chua_biet": TI_LE_CHUA_BIET,
            },
            "nguyen_mau": nhan_nguyen_mau,
            "nguoi": nguoi,
        },
    }


# ── xem trước ─────────────────────────────────────────────────────────────


def xem_truoc(ket_qua: dict[str, Any], mon: list[dict[str, Any]]) -> None:
    hang = ket_qua["hang"]
    st = ket_qua["su_that"]
    print(f"{len(st['nguoi'])} người × {len(mon)} món = {len(hang)} lượt")

    dem = {k: 0 for k in MUC}
    for h in hang:
        dem[h["lua_chon"]] += 1
    print("  phân bố:", "  ".join(f"{k}={dem[k]} ({dem[k]/len(hang):.1%})" for k in MUC))

    print(f"\n{len(st['nguyen_mau'])} khẩu vị nguyên mẫu:")
    for nm in st["nguyen_mau"]:
        trong = [u for u, v in st["nguoi"].items() if v["nguyen_mau"] == nm["chi_so"]]
        print(
            f"  #{nm['chi_so']} · {nm['so_mon_trong_cum']:>2} món · "
            f"{len(trong):>2} người · gần: {', '.join(nm['mon_dai_dien'])}"
        )

    # Số lượt `thich` theo người: mô phỏng phải cho người kén và người dễ.
    theo_nguoi: dict[str, int] = {}
    for h in hang:
        if h["lua_chon"] == "thich":
            theo_nguoi[h["user_id"]] = theo_nguoi.get(h["user_id"], 0) + 1
    v = sorted(theo_nguoi.values())
    print(
        f"\nsố lượt `thich` mỗi người: {v[0]} … {v[-1]} "
        f"(trung vị {v[len(v)//2]}) — tệp gốc: 10 … 22"
    )


def main() -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--ghi", action="store_true", help="ghi ra tệp")
    bo.add_argument("--seed", type=int, default=20261112)
    bo.add_argument("--nguyen-mau", type=int, default=5, dest="nguyen_mau")
    bo.add_argument(
        "--nguyen-mau-phu", type=float, default=0.5, dest="lam_phu",
        help="trọng số λ của nguyên mẫu phụ (0 = chỉ một nguyên mẫu)",
    )
    bo.add_argument("--sigma", type=float, default=0.12)
    bo.add_argument("--beta", type=float, default=2.2)
    bo.add_argument(
        "--anh-huong-ho-so", type=float, default=0.10, dest="bien_do_ho_so"
    )
    t = bo.parse_args()

    if t.nguyen_mau < 2:
        raise SystemExit("--nguyen-mau phải từ 2 trở lên.")
    if t.sigma < 0 or t.beta < 0 or t.bien_do_ho_so < 0 or t.lam_phu < 0:
        raise SystemExit(
            "--sigma, --beta, --anh-huong-ho-so, --nguyen-mau-phu không được âm."
        )

    mon = nap_deck(DECK)
    ho_so = nap_ho_so(HO_SO)
    if t.nguyen_mau > len(mon):
        raise SystemExit(f"--nguyen-mau không vượt quá số món ({len(mon)}).")

    ket_qua = sinh(
        mon=mon,
        ho_so=ho_so,
        so_nguyen_mau=t.nguyen_mau,
        lam_phu=t.lam_phu,
        sigma=t.sigma,
        beta=t.beta,
        bien_do_ho_so=t.bien_do_ho_so,
        seed=t.seed,
    )
    xem_truoc(ket_qua, mon)

    if not t.ghi:
        print("\nXem trước. Thêm --ghi để ghi ra:")
        print(f"  {RA_HANH_VI.relative_to(ROOT)}")
        print(f"  {RA_SU_THAT.relative_to(ROOT)}")
        return 0

    RA_THU_MUC.mkdir(parents=True, exist_ok=True)
    cot = ("user_id", "source_profile_row", "ma_mon", "ten_mon", "nhom", "muc_cay", "lua_chon")
    with RA_HANH_VI.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cot)
        w.writeheader()
        w.writerows(ket_qua["hang"])
    RA_SU_THAT.write_text(
        json.dumps(ket_qua["su_that"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nĐã ghi {RA_HANH_VI.relative_to(ROOT)} và {RA_SU_THAT.relative_to(ROOT)}.")
    print("Kiểm bằng: python tools/check_mo_phong.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
