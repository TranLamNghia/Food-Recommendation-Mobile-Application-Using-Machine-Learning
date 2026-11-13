# -*- coding: utf-8 -*-
"""ML Service — bốn endpoint nội bộ của `API_SPECIFICATION.md` mục 8.

Trước tệp này, `ml/serve.py` là một **thư viện Python**: chạy được từ dòng
lệnh, nhưng Backend viết bằng C# không có đường nào gọi tới. Đó là một trong
hai mối nối còn thiếu giữa ba tầng của hệ thống, và nó chặn các đợt 4, 5, 6
của Backend — khảo sát khẩu vị, sinh thực đơn, gợi ý — chứ không phải việc
thiếu endpoint công khai.

    POST /predict                     Bước 3 — chấm điểm tập ứng viên
    POST /profiles/{userId}/rebuild   dựng lại vector sở thích
    POST /train                       huấn luyện lại, bất đồng bộ
    GET  /health                      mô hình nào đang phục vụ

Chạy:  python tools/run_ml_service.py        → http://localhost:8000
Kiểm:  python tools/smoke_ml_api.py

## Xác thực bằng khóa dùng chung, và vì sao không có mặc định

Mọi endpoint đòi header `X-Internal-Key` khớp biến môi trường
`ML_INTERNAL_KEY`. Thiếu hoặc sai thì `401`.

**Không có khóa mặc định trong mã nguồn, có chủ ý** — cùng lý do với
`JWT_SIGNING_KEY` của Backend: repo này là repo công khai, một khóa nằm trong
tệp được commit thì mọi ai đọc được repo đều gọi được dịch vụ này. Và dịch vụ
này đọc thẳng cơ sở dữ liệu, kể cả bảng `users`.

Máy chủ **dừng ngay lúc khởi động** nếu thiếu khóa, chứ không chạy ở chế độ
mở. Chạy mở thì mọi thứ trông bình thường cho tới khi có người thử.

## Một kết nối cho mỗi yêu cầu

Các endpoint viết bằng `def` thường (không `async`), nên FastAPI chạy chúng
trong threadpool. Kết nối PyMySQL **không an toàn giữa các luồng**, nên mỗi
yêu cầu mở và đóng kết nối của riêng nó. Dùng một kết nối toàn cục sẽ cho ra
lỗi "Packet sequence number wrong" dưới tải — một lỗi chỉ hiện ra khi có
nhiều yêu cầu cùng lúc, tức không bao giờ hiện ra lúc thử tay.

## Suy giảm mềm là hợp đồng, không phải tai nạn

`/predict` trả `503` khi chưa có mô hình `is_active = 1`, và đặc tả mục 8.1
nói rõ Backend khi đó **vẫn sinh thực đơn** bằng quy tắc và đặt
`generationSource = "rule_based"`. Nhưng `serve.goi_y` còn đi xa hơn: nó tự
hạ cấp sang Giai đoạn 1 và vẫn trả điểm theo nội dung. Nên `503` ở đây chỉ
dành cho trường hợp **không chấm được gì cả**; còn hạ cấp thì trả `200` kèm
`stage` và `warnings` để Backend biết điểm này đến từ tầng nào.

Phân biệt này quan trọng: trả `503` mỗi khi thiếu mô hình sẽ làm Backend bỏ
luôn cả Giai đoạn 1 — tức bỏ phần cá nhân hóa **đang chạy được** — và tụt về
xếp theo độ phổ biến. Đo trên tập mô phỏng, đó là khoảng cách 0,862 đối lại
0,694 nDCG@5.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import ket_noi  # noqa: E402
from ml.features import FEATURE_VERSION, KhongGianDacTrung, nap_mon  # noqa: E402
from ml.rocchio import alpha, giai_doan  # noqa: E402
from ml.serve import (  # noqa: E402
    dung_lai_ho_so,
    goi_y,
    nap_mo_hinh_hoat_dong,
)
from ml.time_vn import bay_gio  # noqa: E402

TEN_KHOA = "ML_INTERNAL_KEY"

#: Thuật toán cho `POST /train`, đúng ba cái `ml/train.py` cài đặt.
THUAT_TOAN = ("logistic_regression", "random_forest", "gradient_boosting")


# ── Xác thực ──────────────────────────────────────────────────────────────


def khoa_noi_bo() -> str:
    khoa = os.environ.get(TEN_KHOA, "").strip()
    if not khoa:
        raise SystemExit(
            f"Thiếu {TEN_KHOA}. Dịch vụ này đọc thẳng cơ sở dữ liệu nên không "
            f"chạy ở chế độ mở.\nĐặt {TEN_KHOA} vào .env rồi chạy lại bằng "
            "python tools/run_ml_service.py"
        )
    return khoa


def kiem_khoa(x_internal_key: str | None = Header(default=None)) -> None:
    """Phụ thuộc chung cho mọi endpoint. Trả `401` theo vỏ lỗi mục 2.5."""
    mong_doi = os.environ.get(TEN_KHOA, "")
    # So sánh theo thời gian hằng: so bằng `!=` làm rò rỉ độ dài tiền tố
    # khớp qua thời gian phản hồi.
    import hmac

    if not x_internal_key or not hmac.compare_digest(x_internal_key, mong_doi):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Thiếu hoặc sai header X-Internal-Key.",
            },
        )


# ── Lược đồ thân yêu cầu và phản hồi ──────────────────────────────────────


class DacTrungNguoiDung(BaseModel):
    """Khối `userFeatures` của mục 8.1.

    **Nhận vào nhưng không dùng để chấm điểm, và điều đó là có chủ ý.** Dịch
    vụ này đọc hồ sơ sức khỏe thẳng từ `health_profiles` — cùng cơ sở dữ liệu
    mà Backend ghi — nên dữ liệu trong thân yêu cầu là bản sao của thứ đã có.
    Chấm điểm theo bản sao thì khi hai bên lệch nhau, điểm số và hồ sơ hiển
    thị cho người dùng không còn nói về cùng một người, và không gì báo ra.

    Giữ trong lược đồ để đúng đặc tả và để Backend không phải sửa, nhưng
    `/predict` **đối chiếu** nó với cơ sở dữ liệu và trả chỗ lệch trong
    `warnings` thay vì bỏ qua im lặng.
    """

    age: int | None = None
    gender: str | None = None
    bmi: float | None = None
    activityLevel: str | None = None
    goal: str | None = None
    remainingCaloriesKcal: float | None = None


class YeuCauPredict(BaseModel):
    userId: str = Field(min_length=1)
    candidateFoodIds: list[str] = Field(min_length=1)
    contextMealType: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    userFeatures: DacTrungNguoiDung | None = None


class DiemMon(BaseModel):
    foodId: str
    score: float
    scoreContent: float
    scoreMl: float | None
    scoreRule: float


class PhanHoiPredict(BaseModel):
    modelVersion: str | None
    featureVersion: str
    stage: str
    alpha: float
    generationSource: str
    scores: list[DiemMon]
    skippedFoodIds: list[str]
    warnings: list[str]
    elapsedMs: int


class PhanHoiRebuild(BaseModel):
    userId: str
    featureVersion: str
    nSignals: int
    sumAbsWeight: float
    stage: str
    alpha: float
    updatedAt: str


class YeuCauTrain(BaseModel):
    datasetVersion: str = Field(min_length=1)
    algorithm: Literal[
        "logistic_regression", "random_forest", "gradient_boosting"
    ] = "gradient_boosting"
    activate: bool = False


class PhanHoiTrain(BaseModel):
    jobId: str
    status: str
    startedAt: str


class MoHinhTrongHealth(BaseModel):
    version: str
    algorithm: str
    trainedAt: str | None


class PhanHoiHealth(BaseModel):
    status: str
    activeModel: MoHinhTrongHealth | None
    featureVersion: str
    reason: str | None = None


# ── Phiên huấn luyện ──────────────────────────────────────────────────────


class SoHuanLuyen:
    """Trạng thái phiên huấn luyện. Một phiên một lúc, theo mục 8.3 (`409`).

    Khóa bằng `threading.Lock` chứ không bằng một cờ boolean: hai yêu cầu
    `POST /train` tới cùng lúc đều đọc thấy cờ `False` rồi đều đặt nó lên,
    và khi đó hai phiên huấn luyện cùng ghi `ml_models` — đúng loại lỗi chỉ
    xảy ra dưới tải.
    """

    def __init__(self) -> None:
        self._khoa = threading.Lock()
        self.dang_chay: dict[str, Any] | None = None

    def nhan(self, job_id: str, bat_dau: str) -> bool:
        if not self._khoa.acquire(blocking=False):
            return False
        self.dang_chay = {"jobId": job_id, "startedAt": bat_dau}
        return True

    def tra(self) -> None:
        self.dang_chay = None
        try:
            self._khoa.release()
        except RuntimeError:
            pass


so_huan_luyen = SoHuanLuyen()


def _chay_huan_luyen(job_id: str, t: YeuCauTrain) -> None:
    """Chạy `ml.train` trong luồng nền. Lỗi được ghi ra, không làm sập app."""
    try:
        from ml import train as mo_dun_train

        doi_so = ["--dataset", t.datasetVersion, "--algorithm", t.algorithm, "--apply"]
        if t.activate:
            doi_so += ["--kich-hoat", t.algorithm]
        ma = mo_dun_train.main(doi_so)
        print(f"[train {job_id}] xong, mã trả về {ma}", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"[train {job_id}] LỖI: {type(e).__name__}: {e}", flush=True)
    finally:
        so_huan_luyen.tra()


# ── Ứng dụng ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="ML Service — nội bộ",
    description=__doc__,
    version=FEATURE_VERSION,
)


@app.exception_handler(HTTPException)
def vo_loi(_r: Request, e: HTTPException) -> JSONResponse:
    """Vỏ lỗi `{"error": {...}}` như mục 2.5 của đặc tả."""
    chi_tiet = e.detail
    if not isinstance(chi_tiet, dict):
        chi_tiet = {"code": "ERROR", "message": str(chi_tiet)}
    return JSONResponse(status_code=e.status_code, content={"error": chi_tiet})


@app.get("/health", response_model=PhanHoiHealth)
def health() -> PhanHoiHealth:
    """Không đòi khóa: `/health` là thứ bộ điều phối gọi, không phải Backend.

    Nó cũng không tiết lộ gì ngoài tên phiên bản mô hình. Đòi khóa ở đây làm
    mọi phép kiểm sống của hạ tầng phải mang bí mật của ứng dụng.
    """
    cn = ket_noi(None)
    try:
        mon, _ = nap_mon(cn)
        kg = KhongGianDacTrung.tu_mon(mon)
        mo_hinh, ly_do = nap_mo_hinh_hoat_dong(cn, kg)
        if mo_hinh is None:
            return PhanHoiHealth(
                status="degraded",
                activeModel=None,
                featureVersion=FEATURE_VERSION,
                reason=ly_do,
            )
        with cn.cursor() as cur:
            cur.execute(
                "SELECT trained_at FROM ml_models WHERE id = %s", (mo_hinh.model_id,)
            )
            d = cur.fetchone()
        return PhanHoiHealth(
            status="healthy",
            activeModel=MoHinhTrongHealth(
                version=mo_hinh.version,
                algorithm=mo_hinh.algorithm,
                trainedAt=(
                    d["trained_at"].isoformat() if d and d.get("trained_at") else None
                ),
            ),
            featureVersion=FEATURE_VERSION,
        )
    finally:
        cn.close()


def _doi_chieu_dac_trung(cn, user_id: str, gui: DacTrungNguoiDung | None) -> list[str]:
    """So `userFeatures` Backend gửi với `health_profiles`. Trả danh sách lệch."""
    if gui is None:
        return []
    with cn.cursor() as cur:
        cur.execute(
            "SELECT gender, activity_level, goal, bmi FROM health_profiles "
            "WHERE user_id = %s",
            (user_id,),
        )
        d = cur.fetchone()
    if d is None:
        return ["userFeatures được gửi nhưng người dùng chưa có health_profiles"]

    lech: list[str] = []
    for ten, a, b in (
        ("gender", gui.gender, d["gender"]),
        ("activityLevel", gui.activityLevel, d["activity_level"]),
        ("goal", gui.goal, d["goal"]),
    ):
        if a is not None and a != b:
            lech.append(f"userFeatures.{ten} = {a!r} nhưng CSDL ghi {b!r}")
    if gui.bmi is not None and d["bmi"] is not None:
        if abs(float(gui.bmi) - float(d["bmi"])) > 0.05:
            lech.append(
                f"userFeatures.bmi = {gui.bmi} nhưng CSDL tính {float(d['bmi'])}"
            )
    return lech


@app.post("/predict", response_model=PhanHoiPredict, dependencies=[Depends(kiem_khoa)])
def predict(t: YeuCauPredict) -> PhanHoiPredict:
    bat_dau = time.perf_counter()
    cn = ket_noi(None)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id = %s", (t.userId,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "USER_NOT_FOUND",
                        "message": f"Không có người dùng {t.userId}.",
                    },
                )

        canh_bao = _doi_chieu_dac_trung(cn, t.userId, t.userFeatures)

        # `gioi_han` phải bằng số ứng viên gửi lên. Mặc định của `goi_y` là
        # 20: để nguyên thì Backend gửi 50 món và nhận 20 điểm, và 30 món
        # còn lại bị coi như không có — một phép cắt im lặng ngay giữa Bước 3.
        kq = goi_y(
            cn,
            t.userId,
            gioi_han=len(t.candidateFoodIds),
            chi_ung_vien=t.candidateFoodIds,
        )

        cham_duoc = {u.mon.id for u in kq.ung_vien}
        bi_bo = [f for f in t.candidateFoodIds if f not in cham_duoc]

        if not kq.ung_vien:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "NO_SCOREABLE_CANDIDATE",
                    "message": (
                        "Bộ lọc F1 đã loại toàn bộ "
                        f"{len(t.candidateFoodIds)} món gửi lên — người dùng "
                        "này không được ăn món nào trong số đó."
                    ),
                },
            )

        return PhanHoiPredict(
            modelVersion=kq.model_version,
            featureVersion=FEATURE_VERSION,
            stage=kq.stage,
            alpha=round(kq.alpha, 3),
            generationSource=kq.generation_source,
            scores=[
                DiemMon(
                    foodId=u.mon.id,
                    score=round(u.diem, 4),
                    scoreContent=round(u.diem_noi_dung, 4),
                    scoreMl=(None if u.diem_ml is None else round(u.diem_ml, 4)),
                    scoreRule=round(u.diem_luat, 4),
                )
                for u in kq.ung_vien
            ],
            skippedFoodIds=bi_bo,
            warnings=canh_bao + list(kq.canh_bao),
            elapsedMs=int((time.perf_counter() - bat_dau) * 1000),
        )
    finally:
        cn.close()


@app.post(
    "/profiles/{user_id}/rebuild",
    response_model=PhanHoiRebuild,
    dependencies=[Depends(kiem_khoa)],
)
def rebuild(user_id: str) -> PhanHoiRebuild:
    cn = ket_noi(None)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "USER_NOT_FOUND",
                        "message": f"Không có người dùng {user_id}.",
                    },
                )

        ho_so = dung_lai_ho_so(cn, user_id)
        if ho_so.n_signals == 0:
            # `422` theo mục 8.2. Vector rỗng vẫn được ghi: Giai đoạn 0 chạy
            # được với nó, và một dòng rỗng khác hẳn một dòng không tồn tại —
            # dòng không tồn tại làm `serve` không biết đã dựng hay chưa.
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INSUFFICIENT_SIGNALS",
                    "message": (
                        "Người dùng chưa có lượt vuốt nào dùng được sau Bộ "
                        "lọc F1 — chưa dựng được vector sở thích."
                    ),
                },
            )
        return PhanHoiRebuild(
            userId=user_id,
            featureVersion=FEATURE_VERSION,
            nSignals=ho_so.n_signals,
            sumAbsWeight=float(ho_so.sum_abs_weight),
            stage=giai_doan(ho_so.n_signals),
            alpha=round(alpha(ho_so.n_signals), 3),
            updatedAt=bay_gio().isoformat(),
        )
    finally:
        cn.close()


@app.post(
    "/train",
    response_model=PhanHoiTrain,
    status_code=202,
    dependencies=[Depends(kiem_khoa)],
)
def train(t: YeuCauTrain) -> PhanHoiTrain:
    cn = ket_noi(None)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) n FROM ml_training_samples "
                "WHERE dataset_version = %s",
                (t.datasetVersion,),
            )
            n = int(cur.fetchone()["n"])
        if n == 0:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "DATASET_NOT_FOUND",
                    "message": (
                        f"Không có mẫu nào với dataset_version = "
                        f"{t.datasetVersion!r}. Dựng trước bằng "
                        f"`python -m ml.build_dataset --version "
                        f"{t.datasetVersion} --apply`."
                    ),
                },
            )
    finally:
        cn.close()

    gio = bay_gio()
    job_id = f"train-{gio:%Y%m%d-%H%M%S}"
    if not so_huan_luyen.nhan(job_id, gio.isoformat()):
        dang = so_huan_luyen.dang_chay or {}
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRAINING_IN_PROGRESS",
                "message": (
                    f"Đang có phiên huấn luyện chạy ({dang.get('jobId')}, bắt "
                    f"đầu {dang.get('startedAt')})."
                ),
            },
        )

    threading.Thread(
        target=_chay_huan_luyen, args=(job_id, t), name=job_id, daemon=True
    ).start()
    return PhanHoiTrain(jobId=job_id, status="queued", startedAt=gio.isoformat())
