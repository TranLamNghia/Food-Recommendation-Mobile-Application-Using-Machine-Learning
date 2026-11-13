#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thử đầu-cuối 4 endpoint nội bộ của ML Service, trên CSDL thật.

Bản song song của `tools/smoke_backend.py` cho tầng ML, và cần thiết vì cùng
một lẽ: `tools/check_ml.py` kiểm công thức bằng số thuần không cần máy chủ,
còn tệp này kiểm những thứ **chỉ sai khi có HTTP và có CSDL** — xác thực bằng
khóa dùng chung, vỏ lỗi, ánh xạ tên trường giữa `snake_case` của Python và
`camelCase` của đặc tả, mã trạng thái, và cơ chế suy giảm mềm.

Không tạo dữ liệu mới: nó đọc một người dùng đã có trong CSDL và chấm điểm
trên món công khai. `POST /profiles/{id}/rebuild` có ghi — nhưng nó ghi lại
đúng giá trị mà `import_swipes` / `import_mo_phong` đã tính, nên chạy lại
không làm lệch dữ liệu. Phép kiểm đối chiếu chính điều đó.

Chạy (cần ML Service đang chạy):
    python tools/run_ml_service.py       # cửa sổ khác
    python tools/smoke_ml_api.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _env  # noqa: E402

from ml.db import connect  # noqa: E402
from ml.features import FEATURE_VERSION  # noqa: E402

GOC = "http://127.0.0.1:8000"
TEN_KHOA = "ML_INTERNAL_KEY"

_so_kiem = 0
_loi: list[str] = []


def goi(method: str, duong: str, than=None, khoa: str | None = None, cho: int = 30):
    """Gọi API, trả `(mã HTTP, thân đã giải mã JSON hoặc None)`."""
    data = json.dumps(than).encode() if than is not None else None
    req = urllib.request.Request(GOC + duong, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if khoa:
        req.add_header("X-Internal-Key", khoa)
    try:
        with urllib.request.urlopen(req, timeout=cho) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, {"_raw": raw.decode("utf-8", "replace")[:300]}
    except urllib.error.URLError as e:
        print(
            f"\nKhông gọi được {GOC} — ML Service chưa chạy?\n"
            f"  {e}\nChạy trước: python tools/run_ml_service.py",
            file=sys.stderr,
        )
        raise SystemExit(2)


def kiem(nhan: str, dat: bool, chi_tiet: str = "") -> bool:
    global _so_kiem
    _so_kiem += 1
    print(
        f"  {'[ok]' if dat else '[SAI]'} {nhan}"
        + (f"  {chi_tiet}" if chi_tiet and not dat else "")
    )
    if not dat:
        _loi.append(f"{nhan} — {chi_tiet}" if chi_tiet else nhan)
    return dat


def bang(nhan: str, duoc, mong) -> bool:
    return kiem(nhan, duoc == mong, f"được {duoc!r}, mong {mong!r}")


def ma_loi(than) -> str | None:
    if isinstance(than, dict):
        return (than.get("error") or {}).get("code")
    return None


def _cac_mo_hinh() -> dict[int, dict]:
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT id, version, algorithm, is_active, artifact_path "
                "FROM ml_models"
            )
            return {int(d["id"]): d for d in cur.fetchall()}
    finally:
        cn.close()


def _ban_dang_phuc_vu() -> str | None:
    for d in _cac_mo_hinh().values():
        if int(d["is_active"]) == 1:
            return str(d["version"])
    return None


def _cho_mo_hinh_moi(truoc: dict[int, dict], giay: int) -> dict | None:
    """Đợi một dòng `ml_models` mới xuất hiện, tối đa `giay` giây."""
    het = time.time() + giay
    while time.time() < het:
        for ma, d in _cac_mo_hinh().items():
            if ma not in truoc:
                return d
        time.sleep(1.0)
    return None


def _xoa_mo_hinh(d: dict) -> bool:
    """Xóa dòng `ml_models` và tệp artifact của nó."""
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute("DELETE FROM ml_models WHERE id = %s", (d["id"],))
            xoa = cur.rowcount
        cn.commit()
    finally:
        cn.close()
    tep = ROOT / str(d.get("artifact_path") or "")
    if d.get("artifact_path") and tep.exists():
        tep.unlink()
    return xoa == 1


def main(argv: list[str] | None = None) -> int:
    global GOC
    _env.use_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--goc", default=GOC, help="địa chỉ ML Service")
    t = ap.parse_args(argv)
    GOC = t.goc.rstrip("/")

    khoa = _env.get(TEN_KHOA, "")
    if not khoa:
        print(
            f"Thiếu {TEN_KHOA} trong .env. Chạy "
            "`python tools/run_ml_service.py` một lần để nó sinh khóa.",
            file=sys.stderr,
        )
        return 1

    # ── Lấy dữ liệu thật để thử ──
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT p.user_id, p.n_signals, p.stage, p.sum_abs_weight "
                "FROM user_preference_profiles p "
                "ORDER BY p.n_signals DESC LIMIT 1"
            )
            hs = cur.fetchone()
            cur.execute(
                "SELECT id FROM foods WHERE owner_id IS NULL AND is_active = 1 "
                "ORDER BY id LIMIT 8"
            )
            mon = [d["id"] for d in cur.fetchall()]
            cur.execute(
                "SELECT dataset_version v, COUNT(*) n FROM ml_training_samples "
                "GROUP BY dataset_version ORDER BY n DESC LIMIT 1"
            )
            tap = cur.fetchone()
    finally:
        cn.close()

    if hs is None or len(mon) < 4:
        print(
            "CSDL chưa có hồ sơ sở thích hoặc chưa đủ món để thử.\n"
            "Nạp trước: python tools/import_mo_phong.py --apply",
            file=sys.stderr,
        )
        return 1

    uid = hs["user_id"]
    print(f"ML Service: {GOC}")
    print(
        f"Dữ liệu thử: người dùng {uid[:8]}… (n_signals={hs['n_signals']}, "
        f"{hs['stage']}) · {len(mon)} món"
    )

    # ── GET /health ──
    print("\n§8.4  GET /health")
    ma, than = goi("GET", "/health")
    bang("health trả 200", ma, 200)
    kiem(
        "không đòi khóa — phép kiểm sống của hạ tầng không mang bí mật ứng dụng",
        ma == 200,
    )
    bang("featureVersion khớp mã nguồn", (than or {}).get("featureVersion"), FEATURE_VERSION)
    kiem(
        "status thuộc {healthy, degraded}",
        (than or {}).get("status") in ("healthy", "degraded"),
        f"được {(than or {}).get('status')!r}",
    )
    co_mo_hinh = (than or {}).get("activeModel") is not None
    if co_mo_hinh:
        am = than["activeModel"]
        kiem(
            "activeModel có version và algorithm",
            bool(am.get("version")) and bool(am.get("algorithm")),
            f"được {am!r}",
        )
        bang("status = healthy khi có mô hình", than["status"], "healthy")
    else:
        bang("status = degraded khi không có mô hình", than["status"], "degraded")
        kiem("degraded kèm lý do đọc được", bool((than or {}).get("reason")))

    # ── Xác thực ──
    print("\n§8     Xác thực bằng X-Internal-Key")
    ma, than = goi("POST", "/predict", {"userId": uid, "candidateFoodIds": mon})
    bang("thiếu khóa → 401", ma, 401)
    bang("mã lỗi UNAUTHORIZED", ma_loi(than), "UNAUTHORIZED")
    ma, than = goi(
        "POST", "/predict", {"userId": uid, "candidateFoodIds": mon}, khoa="sai-khoa"
    )
    bang("sai khóa → 401", ma, 401)
    kiem(
        "vỏ lỗi {\"error\": {code, message}} như mục 2.5",
        isinstance(than, dict) and "error" in than,
        f"được {than!r}",
    )

    # ── POST /predict ──
    print("\n§8.1  POST /predict")
    ma, than = goi(
        "POST",
        "/predict",
        {"userId": uid, "candidateFoodIds": mon, "contextMealType": "lunch"},
        khoa=khoa,
    )
    bang("predict trả 200", ma, 200)
    diem = (than or {}).get("scores") or []
    bang("chấm điểm đủ số món gửi lên", len(diem), len(mon))
    kiem(
        "mọi foodId trả về đều nằm trong danh sách gửi lên",
        all(d["foodId"] in mon for d in diem),
    )
    kiem(
        "điểm nằm trong [0, 1]",
        all(0.0 <= d["score"] <= 1.0 for d in diem),
        f"được {[d['score'] for d in diem][:5]}",
    )
    kiem(
        "đã sắp giảm dần theo điểm",
        all(diem[i]["score"] >= diem[i + 1]["score"] for i in range(len(diem) - 1)),
    )
    kiem(
        "mỗi món có cả ba thành phần điểm, tách ra để phân tích ngược được",
        all(
            "scoreContent" in d and "scoreRule" in d and "scoreMl" in d for d in diem
        ),
    )
    bang("featureVersion trong phản hồi", than.get("featureVersion"), FEATURE_VERSION)
    kiem(
        "stage thuộc bốn giai đoạn",
        than.get("stage") in ("cold", "content", "hybrid", "ml"),
        f"được {than.get('stage')!r}",
    )
    kiem(
        "alpha trong [0, 1]",
        0.0 <= float(than.get("alpha", -1)) <= 1.0,
        f"được {than.get('alpha')!r}",
    )
    kiem(
        "elapsedMs có mặt và dưới ngưỡng 2 giây của Backend",
        isinstance(than.get("elapsedMs"), int) and than["elapsedMs"] < 2000,
        f"được {than.get('elapsedMs')!r} ms",
    )
    # Giai đoạn `hybrid`/`ml` phải có điểm ML; `cold`/`content` thì không.
    if than.get("stage") in ("hybrid", "ml"):
        kiem(
            "giai đoạn hybrid/ml có scoreMl khác null",
            all(d["scoreMl"] is not None for d in diem),
        )
        kiem("modelVersion khác null khi đã dùng mô hình", bool(than.get("modelVersion")))
    else:
        kiem(
            "giai đoạn cold/content thì scoreMl là null",
            all(d["scoreMl"] is None for d in diem),
            f"được {[d['scoreMl'] for d in diem][:3]}",
        )

    print("\n§8.1  predict — các ca lỗi")
    ma, than = goi("POST", "/predict", {"userId": uid, "candidateFoodIds": []}, khoa=khoa)
    bang("candidateFoodIds rỗng → 422", ma, 422)
    ma, than = goi(
        "POST",
        "/predict",
        {"userId": "00000000-0000-4000-8000-000000000000", "candidateFoodIds": mon},
        khoa=khoa,
    )
    bang("userId không tồn tại → 404", ma, 404)
    bang("mã lỗi USER_NOT_FOUND", ma_loi(than), "USER_NOT_FOUND")
    ma, than = goi("POST", "/predict", {"candidateFoodIds": mon}, khoa=khoa)
    bang("thiếu userId → 422", ma, 422)

    print("\n§8.1  predict — Bộ lọc F1 vẫn chạy TRƯỚC, dù Backend đã gửi ứng viên")
    ma, than = goi(
        "POST",
        "/predict",
        {
            "userId": uid,
            "candidateFoodIds": mon + ["00000000-0000-4000-8000-0000000000ff"],
            "userFeatures": {"gender": "other", "goal": "gain_weight"},
        },
        khoa=khoa,
    )
    bang("món không tồn tại không làm vỡ yêu cầu", ma, 200)
    kiem(
        "món không chấm được nằm trong skippedFoodIds",
        "00000000-0000-4000-8000-0000000000ff" in (than.get("skippedFoodIds") or []),
        f"được {than.get('skippedFoodIds')!r}",
    )
    kiem(
        "userFeatures lệch CSDL được báo trong warnings, không bỏ qua im lặng",
        any("userFeatures" in w for w in (than.get("warnings") or [])),
        f"được {than.get('warnings')!r}",
    )

    # ── POST /profiles/{id}/rebuild ──
    print("\n§8.2  POST /profiles/{userId}/rebuild")
    ma, than = goi("POST", f"/profiles/{uid}/rebuild", {}, khoa=khoa)
    bang("rebuild trả 200", ma, 200)
    bang("userId trả về đúng", (than or {}).get("userId"), uid)
    bang(
        "nSignals khớp giá trị trình nhập đã tính",
        (than or {}).get("nSignals"),
        int(hs["n_signals"]),
    )
    kiem(
        "sumAbsWeight khớp giá trị đã lưu",
        abs(float(than["sumAbsWeight"]) - float(hs["sum_abs_weight"])) < 1e-6,
        f"được {than['sumAbsWeight']}, đã lưu {float(hs['sum_abs_weight'])}",
    )
    bang("stage khớp", (than or {}).get("stage"), hs["stage"])
    kiem(
        "updatedAt mang múi giờ +07:00, không phải UTC",
        "+07:00" in str((than or {}).get("updatedAt")),
        f"được {(than or {}).get('updatedAt')!r}",
    )
    ma, than = goi(
        "POST", "/profiles/00000000-0000-4000-8000-000000000000/rebuild", {}, khoa=khoa
    )
    bang("userId không tồn tại → 404", ma, 404)
    ma, _ = goi("POST", f"/profiles/{uid}/rebuild", {})
    bang("rebuild đòi khóa", ma, 401)

    # ── POST /train ──
    print("\n§8.3  POST /train")
    ma, than = goi(
        "POST",
        "/train",
        {"datasetVersion": "khong-ton-tai-abc", "algorithm": "random_forest"},
        khoa=khoa,
    )
    bang("datasetVersion không có mẫu nào → 404", ma, 404)
    bang("mã lỗi DATASET_NOT_FOUND", ma_loi(than), "DATASET_NOT_FOUND")
    ma, than = goi(
        "POST", "/train", {"datasetVersion": "v1", "algorithm": "khong-co"}, khoa=khoa
    )
    bang("algorithm lạ → 422", ma, 422)
    ma, _ = goi("POST", "/train", {"datasetVersion": "v1"})
    bang("train đòi khóa", ma, 401)

    if tap:
        print(
            f"\n§8.3  train thật trên dataset_version = {tap['v']!r} "
            f"({tap['n']} mẫu)"
        )
        truoc_train = _cac_mo_hinh()
        dang_phuc_vu_truoc = _ban_dang_phuc_vu()
        ma, than = goi(
            "POST",
            "/train",
            {
                "datasetVersion": tap["v"],
                "algorithm": "logistic_regression",
                "activate": False,
            },
            khoa=khoa,
        )
        bang("train trả 202 Accepted, không chặn", ma, 202)
        kiem("có jobId", bool((than or {}).get("jobId")), f"được {than!r}")
        bang("status = queued", (than or {}).get("status"), "queued")
        kiem(
            "startedAt mang múi giờ +07:00",
            "+07:00" in str((than or {}).get("startedAt")),
            f"được {(than or {}).get('startedAt')!r}",
        )
        # Phiên thứ hai ngay lập tức phải bị từ chối: mục 8.3 nói `409` khi
        # đang có phiên chạy. Đây là phép kiểm của chính cái khóa — không có
        # nó thì hai phiên cùng ghi `ml_models`.
        ma2, than2 = goi(
            "POST",
            "/train",
            {"datasetVersion": tap["v"], "algorithm": "random_forest"},
            khoa=khoa,
        )
        bang("phiên thứ hai khi phiên đầu chưa xong → 409", ma2, 409)
        bang("mã lỗi TRAINING_IN_PROGRESS", ma_loi(than2), "TRAINING_IN_PROGRESS")

        # Đợi phiên huấn luyện xong rồi DỌN mô hình nó sinh ra.
        #
        # Phải kiểm điều này, vì `202 Accepted` chỉ nói "đã nhận", không nói
        # "đã làm". Một `/train` nhận yêu cầu rồi lặng lẽ chết trong luồng
        # nền vẫn qua được mọi phép kiểm phía trên.
        #
        # Và phải dọn, vì ngược với `smoke_backend.py` — tệp đó tạo một tài
        # khoản rồi xóa — một lần chạy ở đây sinh thêm một dòng `ml_models`
        # cùng một tệp `.joblib`. Chạy bộ kiểm mười lần thì có mười mô hình
        # rác, và `load_active_model` từ chối phục vụ khi có nhiều hơn
        # một dòng `is_active = 1`.
        print("\n§8.3  phiên huấn luyện phải thật sự chạy, rồi được dọn")
        moi = _cho_mo_hinh_moi(truoc_train, giay=90)
        kiem(
            "mô hình mới xuất hiện trong ml_models — 202 không phải lời hứa suông",
            moi is not None,
            "sau 90 giây vẫn không thấy dòng mới",
        )
        if moi is not None:
            bang("thuật toán đúng cái đã yêu cầu", moi["algorithm"], "logistic_regression")
            bang("activate=false nên KHÔNG được bật", int(moi["is_active"]), 0)
            kiem(
                "mô hình đang phục vụ không bị đổi",
                _ban_dang_phuc_vu() == dang_phuc_vu_truoc,
                f"trước {dang_phuc_vu_truoc!r}, sau {_ban_dang_phuc_vu()!r}",
            )
            kiem("đã dọn mô hình do bộ kiểm sinh ra", _xoa_mo_hinh(moi))
    else:
        print("\n§8.3  bỏ qua phần train thật — chưa có ml_training_samples")

    # ── Kết ──
    print("\n" + "=" * 68)
    if _loi:
        print(f"{len(_loi)}/{_so_kiem} phép kiểm TRƯỢT:")
        for x in _loi:
            print("  -", x)
        return 1
    print(f"{_so_kiem}/{_so_kiem} phép kiểm đạt — 4 endpoint nội bộ chạy đúng đặc tả.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
