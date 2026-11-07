# -*- coding: utf-8 -*-
"""Hạn mức dinh dưỡng theo ngày — trạng thái thật của một người trong một ngày.

`f1_filter.han_muc_theo_ngay` trả về **các ngưỡng** đang áp cho một người
(`purine_mg ≤ 400`, `sodium_mg ≤ 2000`...). Nó không biết hôm nay người đó đã
ăn gì, nên không trả lời được câu mà giao diện cần: *còn lại bao nhiêu*. Tệp
này nối phần còn thiếu đó.

## Hai nguồn, và vì sao không được gộp

Lược đồ ghi lại việc ăn uống ở hai nơi khác nhau, với ý nghĩa khác nhau:

    food_diary                     đã ăn — bản ghi thật, không đổi được nữa
    meal_plan_items (suggested,    đã lên kế hoạch — còn đổi, còn bỏ được
                     kept)

Cộng hai thứ thành một con số thì mất đúng thông tin người dùng cần: khi một
món không vừa hạn mức, phải cho họ thấy họ đang chọn giữa *bỏ món đã lên kế
hoạch* và *chịu vượt ngưỡng*. Nếu chỉ hiện một tổng, họ sẽ tưởng cả hai phần
đều đã cố định. Nên `TrangThaiHanMuc` giữ `da_an` và `da_len_ke_hoach` tách
nhau, và chỉ cộng lại khi tính `con_lai`.

## Quy ước đếm — tránh đếm đôi

**`food_diary` là nguồn duy nhất của phần "đã ăn".** `meal_plan_items.status
= 'eaten'` KHÔNG được cộng vào: khi người dùng đánh dấu đã ăn, ứng dụng ghi
một dòng nhật ký, nên cộng cả hai là đếm hai lần cùng một suất. Hàm
`kiem_dem_doi` soát đúng điều kiện đó và báo ra chỗ lệch, vì quy ước này
không có ràng buộc nào trong CSDL bắt buộc.

**Một dòng `meal_plan_items` là một ô trong thực đơn**, không phải một lần
ăn. Nên khi ô bị đổi món (`status = 'replaced'`), phần dinh dưỡng tính theo
món **mới** (`replaced_by_food_id`), không phải món cũ — món cũ không còn
nằm trong thực đơn. Ô `skipped` không tính gì.

## Hai chiều của ngưỡng

## Số liệu khuyết — vì sao phải đếm, không được bỏ qua

`food_nutrition` có nhiều ô NULL, và ở một chất thì rất nhiều: **248 trong
318 món hoạt động không có `purine_mg`**. `SUM()` của SQL bỏ qua NULL, nên
nếu chỉ cộng rồi trả về một con số, hạn mức purin của người bị gút sẽ được
tính từ 70 món và trình bày như thể đã tính đủ — ăn năm món không có số liệu
ghi 0 mg trên trần 400 mg. Một bộ lọc an toàn thất bại theo hướng **mở** mà
không báo gì là loại lỗi tệ nhất ở đây.

Ba cách xử lý, và vì sao chọn cách thứ ba:

1. *Suy ra giá trị khuyết* như `features.py` làm cho vector. Không: suy một
   con số rồi dùng nó để kết luận an toàn thì tệ hơn thừa nhận là không
   biết. Vector chỉ xếp hạng, hạn mức thì chặn món.
2. *Coi khuyết là chặn*. Không: 248/318 món sẽ bị chặn với mọi người bị gút,
   hệ thống thành vô dụng.
3. *Cộng phần biết được, và đếm phần không biết.* `TongChat` mang theo số ô
   khuyết của từng chất, `MotHanMuc.so_mon_thieu_so` nói con số này dựa trên
   bao nhiêu món thiếu số liệu, và `mon_khong_vua` trả riêng nhóm **không xét
   được**. Giao diện nhờ đó nói được "hạn mức tính trên 3/5 món có số liệu
   purin" thay vì đưa ra một con số chắc chắn giả.

Bộ quy tắc đã lường trước chuyện này ở một chỗ khác: luật `exclude_tag`
`Giàu purin` của Gút có ghi chú *"dùng khi thiếu số liệu purine_mg"* — cái
nhãn là đường vòng cho đúng 248 món đó. Nhưng nhãn chỉ chặn được món giàu
purin đã biết; nó không làm cho tổng theo ngày đầy đủ hơn.

## Hai chiều của ngưỡng

`comparator` trong lược đồ nhận cả `lte` và `gte`, và hai thứ này không đối
xứng. `lte` là **trần**: còn lại bao nhiêu thì ăn thêm được bấy nhiêu, và một
món có thể *vượt*. `gte` là **sàn**: nó nói còn **thiếu** bao nhiêu, và không
món nào "vượt" một cái sàn. Dữ liệu hiện chỉ có `lte` ở mức cứng theo ngày,
nhưng gán cả hai vào cùng một phép trừ rồi gọi chung là "còn lại" thì một
ngưỡng sàn thêm vào sau này sẽ âm thầm chặn món — nên hai chiều được tách
ngay từ đầu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence

from .f1_filter import COT_DINH_DUONG, DieuKien, han_muc_theo_ngay

#: Trạng thái ô thực đơn được tính vào phần "đã lên kế hoạch".
#:
#: `eaten` cố tình vắng mặt — xem quy ước đếm ở docstring của tệp.
#: `replaced` có mặt vì ô đó vẫn chiếm một suất, chỉ là bằng món khác.
TRANG_THAI_CON_TRONG_KE_HOACH = ("suggested", "kept", "replaced")

#: Trạng thái thực đơn được tính. `completed` là thực đơn của ngày đã khép lại.
TRANG_THAI_THUC_DON = ("draft", "active")


@dataclass(frozen=True)
class TongChat:
    """Tổng từng chất của một nhóm suất ăn, kèm số ô thiếu số liệu.

    `tong` chỉ cộng những ô có số. `thieu` nói mỗi chất có bao nhiêu suất
    không có số liệu — không có nó thì `tong` là một con số chắc chắn giả.
    """

    tong: dict[str, float]
    thieu: dict[str, int]
    so_suat: int

    def du_lieu_du(self, chat: str) -> bool:
        return self.thieu.get(chat, 0) == 0


@dataclass(frozen=True)
class MotHanMuc:
    """Một ngưỡng cứng theo ngày, kèm trạng thái tiêu thụ của hôm nay."""

    benh: str
    chat: str
    comparator: str
    nguong: float
    da_an: float
    da_len_ke_hoach: float
    note: str = ""
    #: Số suất đã ăn / đã lên kế hoạch KHÔNG có số liệu cho chất này.
    thieu_da_an: int = 0
    thieu_ke_hoach: int = 0

    @property
    def so_mon_thieu_so(self) -> int:
        """Tổng số suất không có số liệu cho chất này."""
        return self.thieu_da_an + self.thieu_ke_hoach

    @property
    def du_lieu_du(self) -> bool:
        """Mọi suất tính vào hạn mức này đều có số liệu.

        Sai nghĩa là `tong` thấp hơn thực tế, nên `con_lai` CAO hơn thực tế
        — hạn mức đang nới ra. Giao diện phải nói điều đó, không được hiện
        con số trần trụi.
        """
        return self.so_mon_thieu_so == 0

    @property
    def tong(self) -> float:
        """Phần đã dùng — ăn rồi cộng với đang nằm trong thực đơn."""
        return self.da_an + self.da_len_ke_hoach

    @property
    def la_tran(self) -> bool:
        return self.comparator == "lte"

    @property
    def con_lai(self) -> float:
        """Còn ăn thêm được bao nhiêu. Chỉ có nghĩa với ngưỡng trần.

        Không kẹp về 0: một số âm nghĩa là đã vượt ngưỡng, và giao diện cần
        biết vượt bao nhiêu để nói ra, chứ không phải thấy đúng số 0.
        """
        if not self.la_tran:
            raise ValueError(
                f"{self.chat}: ngưỡng `gte` là sàn, hỏi `con_thieu` chứ không "
                "phải `con_lai`"
            )
        return self.nguong - self.tong

    @property
    def con_thieu(self) -> float:
        """Còn phải ăn thêm bao nhiêu mới đạt sàn. Chỉ có nghĩa với `gte`."""
        if self.la_tran:
            raise ValueError(
                f"{self.chat}: ngưỡng `lte` là trần, hỏi `con_lai` chứ không "
                "phải `con_thieu`"
            )
        return max(0.0, self.nguong - self.tong)

    @property
    def da_vuot(self) -> bool:
        """Đã vượt trần chưa. Ngưỡng sàn thì không bao giờ `vượt`."""
        return self.la_tran and self.tong > self.nguong

    @property
    def ty_le(self) -> float:
        """Phần đã dùng trên ngưỡng, dùng để vẽ thanh tiến độ. Không kẹp."""
        if self.nguong <= 0:
            return 0.0
        return self.tong / self.nguong

    def vua_khong(self, them: float) -> bool:
        """Thêm `them` đơn vị chất này thì còn trong ngưỡng không?

        Ngưỡng sàn luôn trả `True`: ăn thêm không bao giờ làm hỏng một cái sàn.
        """
        if not self.la_tran:
            return True
        return self.tong + them <= self.nguong


@dataclass(frozen=True)
class TrangThaiHanMuc:
    """Toàn bộ hạn mức cứng theo ngày của một người trong một ngày."""

    user_id: str
    ngay: date
    han_muc: tuple[MotHanMuc, ...] = ()
    #: Đã ăn, kể cả chất không có ngưỡng nào — giao diện còn dùng để hiện
    #: năng lượng và chất sinh năng lượng.
    da_an: TongChat = field(
        default_factory=lambda: TongChat({}, {}, 0)
    )
    #: Đang nằm trong thực đơn hôm nay, chưa ăn.
    da_len_ke_hoach: TongChat = field(
        default_factory=lambda: TongChat({}, {}, 0)
    )

    @property
    def rong(self) -> bool:
        """Không có ngưỡng cứng theo ngày nào — người này không bị hạn mức."""
        return not self.han_muc

    def theo_chat(self, chat: str) -> list[MotHanMuc]:
        """Các ngưỡng đang áp cho một chất.

        Trả về danh sách vì hai bệnh có thể cùng hạn chế một chất với hai
        ngưỡng khác nhau — Tăng huyết áp và Bệnh thận đều giới hạn natri ở
        2 000 mg. Lấy cái chặt nhất bằng `han_muc_chat_nhat`.
        """
        return [h for h in self.han_muc if h.chat == chat]

    def han_muc_chat_nhat(self, chat: str) -> MotHanMuc | None:
        """Ngưỡng trần còn ít dư địa nhất cho một chất, `None` nếu không có."""
        tran = [h for h in self.theo_chat(chat) if h.la_tran]
        return min(tran, key=lambda h: h.con_lai) if tran else None

    def da_vuot(self) -> list[MotHanMuc]:
        """Các ngưỡng đã bị vượt."""
        return [h for h in self.han_muc if h.da_vuot]


# ── Đọc tiêu thụ ──────────────────────────────────────────────────────

#: Các chất được cộng. Dùng lại khai báo của F1 để hai nơi không lệch nhau.
CAC_CHAT: tuple[str, ...] = tuple(COT_DINH_DUONG)


def _chon_tong() -> str:
    """Mệnh đề SELECT: tổng từng chất đã nhân khẩu phần, kèm số ô khuyết.

    Hai cột cho mỗi chất. Cột `thieu_*` là thứ giữ cho `tong` khỏi thành một
    con số chắc chắn giả: `SUM` bỏ qua NULL nên nếu không đếm, một chất
    khuyết ở 248/318 món vẫn cho ra một tổng trông rất bình thường.
    """
    phan = []
    for chat in CAC_CHAT:
        phan.append(f"COALESCE(SUM(fn.{chat} * {{he_so}}), 0) AS {chat}")
        phan.append(f"SUM(fn.{chat} IS NULL) AS thieu_{chat}")
    return ",\n       ".join(phan)


_SQL_DA_AN = f"""
SELECT COUNT(*) AS so_suat,
       {_chon_tong().format(he_so='fd.portion_multiplier')}
FROM food_diary fd
JOIN food_nutrition fn ON fn.food_id = fd.food_id
WHERE fd.user_id = %s
  AND fd.ate_on  = %s
"""

# Ô bị đổi món tính theo món MỚI: nối `food_nutrition` qua COALESCE chứ không
# qua `mpi.food_id`, nếu không thì phần dinh dưỡng của ô là của món đã bị bỏ.
_SQL_DA_LEN_KE_HOACH = f"""
SELECT COUNT(*) AS so_suat,
       {_chon_tong().format(he_so='mpi.portion_multiplier')}
FROM meal_plans mp
JOIN meal_plan_items mpi ON mpi.meal_plan_id = mp.id
JOIN food_nutrition fn
  ON fn.food_id = COALESCE(mpi.replaced_by_food_id, mpi.food_id)
WHERE mp.user_id   = %s
  AND mp.plan_date = %s
  AND mp.status    IN ({", ".join(["%s"] * len(TRANG_THAI_THUC_DON))})
  AND mpi.status   IN ({", ".join(["%s"] * len(TRANG_THAI_CON_TRONG_KE_HOACH))})
"""


def _mot_dong_tong(cn, sql: str, tham_so: Sequence[Any]) -> TongChat:
    with cn.cursor() as cur:
        cur.execute(sql, tuple(tham_so))
        dong = cur.fetchone()
    if not dong:
        return TongChat({chat: 0.0 for chat in CAC_CHAT}, dict.fromkeys(CAC_CHAT, 0), 0)
    return TongChat(
        tong={chat: float(dong[chat] or 0.0) for chat in CAC_CHAT},
        thieu={chat: int(dong[f"thieu_{chat}"] or 0) for chat in CAC_CHAT},
        so_suat=int(dong["so_suat"] or 0),
    )


def da_an(cn, user_id: str, ngay: date) -> TongChat:
    """Tổng từng chất người này **đã ăn** trong ngày, theo `food_diary`."""
    return _mot_dong_tong(cn, _SQL_DA_AN, (user_id, ngay))


def da_len_ke_hoach(cn, user_id: str, ngay: date) -> TongChat:
    """Tổng từng chất đang nằm trong thực đơn của ngày, **chưa ăn**."""
    return _mot_dong_tong(
        cn,
        _SQL_DA_LEN_KE_HOACH,
        (user_id, ngay, *TRANG_THAI_THUC_DON, *TRANG_THAI_CON_TRONG_KE_HOACH),
    )


def trang_thai(
    cn,
    user_id: str,
    *,
    dieu_kien: Sequence[DieuKien] = (),
    ngay: date | None = None,
) -> TrangThaiHanMuc:
    """Trạng thái hạn mức theo ngày của một người.

    `dieu_kien` rỗng thì không có ngưỡng nào, nhưng phần tiêu thụ vẫn được
    đọc: giao diện còn dùng nó để hiện năng lượng và chất sinh năng lượng
    cho người không có bệnh lý nào.
    """
    hom_nay = ngay or date.today()
    an = da_an(cn, user_id, hom_nay)
    ke_hoach = da_len_ke_hoach(cn, user_id, hom_nay)

    cac_han_muc: list[MotHanMuc] = []
    for luat in han_muc_theo_ngay(cn, dieu_kien):
        chat = luat["nutrient"]
        if chat not in CAC_CHAT:
            # Lược đồ có thể thêm chất mới; bỏ qua lặng lẽ sẽ làm mất một
            # ngưỡng an toàn, nên báo ra.
            raise ValueError(
                f"`condition_rules` có ngưỡng cho chất `{chat}` mà "
                "`COT_DINH_DUONG` không khai — cập nhật `ml/f1_filter.py`"
            )
        cac_han_muc.append(
            MotHanMuc(
                benh=luat["name_vi"],
                chat=chat,
                comparator=luat["comparator"],
                nguong=float(luat["threshold"]),
                da_an=an.tong[chat],
                da_len_ke_hoach=ke_hoach.tong[chat],
                note=luat.get("note") or "",
                thieu_da_an=an.thieu[chat],
                thieu_ke_hoach=ke_hoach.thieu[chat],
            )
        )

    return TrangThaiHanMuc(
        user_id=user_id,
        ngay=hom_nay,
        han_muc=tuple(cac_han_muc),
        da_an=an,
        da_len_ke_hoach=ke_hoach,
    )


# ── Món nào không vừa hạn mức còn lại ─────────────────────────────────


@dataclass(frozen=True)
class MonVuotHanMuc:
    """Một món không vừa phần hạn mức còn lại của hôm nay."""

    food_id: str
    name: str
    chat: str
    benh: str
    gia_tri_mon: float
    con_lai: float
    nguong: float
    note: str = ""

    @property
    def vuot_bao_nhieu(self) -> float:
        return self.gia_tri_mon - self.con_lai


@dataclass(frozen=True)
class KetQuaHanMuc:
    """Phân loại một tập món theo hạn mức còn lại của hôm nay."""

    #: `{food_id: [lý do...]}` — chắc chắn không vừa. Một món có thể vướng
    #: nhiều ngưỡng cùng lúc.
    khong_vua: dict[str, list[MonVuotHanMuc]]
    #: `{food_id: [tên chất...]}` — không có số liệu nên **không kết luận
    #: được**. Đây không phải nhóm "vừa": nó là nhóm chưa biết, và gộp vào
    #: nhóm vừa là để bộ lọc an toàn thất bại theo hướng mở.
    khong_xet_duoc: dict[str, list[str]]

    def vua(self, food_id: str) -> bool:
        """Món này vừa mọi hạn mức, và mọi chất đều có số liệu."""
        return food_id not in self.khong_vua and food_id not in self.khong_xet_duoc


def mon_khong_vua(
    tt: TrangThaiHanMuc,
    mon: Iterable[dict[str, Any]],
) -> KetQuaHanMuc:
    """Phân loại `mon` theo hạn mức còn lại — ba nhóm, không phải hai.

    `mon` là các dòng do `f1_filter.loc_f1` trả về: đã qua mọi ràng buộc
    cứng theo suất, nên lý do duy nhất còn lại để bỏ một món ở đây là **hôm
    nay đã dùng gần hết hạn mức**. Phân biệt hai lý do này là điều giao diện
    bắt buộc phải làm: món bị loại vì bản chất thì không bao giờ hợp, còn
    món bị loại ở đây thì **hôm khác vẫn chọn được**.

    Nhóm thứ ba, `khong_xet_duoc`, là món thiếu số liệu ở chất bị hạn chế.
    Với `purine_mg` đó là 248/318 món, nên gộp nhóm này vào nhóm "vừa" sẽ
    làm trần purin của người bị gút gần như không bao giờ chạm tới. Quyết
    định cuối cùng với nhóm này là của tầng trên — hiện món kèm ghi chú,
    hay bỏ — nhưng nó phải là một quyết định được nói ra.
    """
    tran = [h for h in tt.han_muc if h.la_tran]
    if not tran:
        return KetQuaHanMuc({}, {})

    khong_vua: dict[str, list[MonVuotHanMuc]] = {}
    khong_xet: dict[str, list[str]] = {}
    for m in mon:
        ly_do: list[MonVuotHanMuc] = []
        thieu: list[str] = []
        for h in tran:
            gia_tri = m.get(h.chat)
            if gia_tri is None:
                thieu.append(h.chat)
                continue
            gia_tri = float(gia_tri)
            if not h.vua_khong(gia_tri):
                ly_do.append(
                    MonVuotHanMuc(
                        food_id=m["id"],
                        name=m.get("name", ""),
                        chat=h.chat,
                        benh=h.benh,
                        gia_tri_mon=gia_tri,
                        con_lai=h.con_lai,
                        nguong=h.nguong,
                        note=h.note,
                    )
                )
        # Vướng một ngưỡng đã biết thì kết luận được ngay, kể cả khi một
        # ngưỡng khác thiếu số liệu: đã chắc chắn không vừa.
        if ly_do:
            khong_vua[m["id"]] = ly_do
        elif thieu:
            khong_xet[m["id"]] = thieu
    return KetQuaHanMuc(khong_vua=khong_vua, khong_xet_duoc=khong_xet)


# ── Soát quy ước đếm ──────────────────────────────────────────────────


def kiem_dem_doi(cn, user_id: str, ngay: date) -> list[dict[str, Any]]:
    """Soát quy ước "`food_diary` là nguồn duy nhất của phần đã ăn".

    Không ràng buộc nào trong CSDL bắt ứng dụng ghi nhật ký khi người dùng
    đánh dấu đã ăn, nên quy ước có thể bị vi phạm mà không ai biết — và hậu
    quả là hạn mức tính thiếu, tức là bộ lọc an toàn nới ra âm thầm. Hàm này
    trả về các ô `status = 'eaten'` **không** có dòng nhật ký tương ứng.

    Danh sách rỗng nghĩa là quy ước đang được tôn trọng.
    """
    sql = """
SELECT mpi.id          AS item_id,
       mpi.meal_type,
       f.name          AS food_name,
       COALESCE(mpi.replaced_by_food_id, mpi.food_id) AS food_id
FROM meal_plans mp
JOIN meal_plan_items mpi ON mpi.meal_plan_id = mp.id
JOIN foods f ON f.id = COALESCE(mpi.replaced_by_food_id, mpi.food_id)
WHERE mp.user_id   = %s
  AND mp.plan_date = %s
  AND mpi.status   = 'eaten'
  AND NOT EXISTS (
        SELECT 1 FROM food_diary fd
        WHERE fd.user_id = mp.user_id
          AND fd.ate_on  = mp.plan_date
          AND fd.food_id = COALESCE(mpi.replaced_by_food_id, mpi.food_id)
      )
ORDER BY mpi.meal_type, f.name
"""
    with cn.cursor() as cur:
        cur.execute(sql, (user_id, ngay))
        return list(cur.fetchall())
