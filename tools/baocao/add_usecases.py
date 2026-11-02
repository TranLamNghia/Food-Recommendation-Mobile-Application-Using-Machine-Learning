# -*- coding: utf-8 -*-
"""Thêm Use case mới vào BAOCAO/Diagram.mdj (sơ đồ Use case của StarUML).

Tệp .mdj là JSON thuần: một cây phần tử, mọi liên kết trỏ nhau bằng
{"$ref": "<_id>"}. Thêm một Use case vào sơ đồ cần BỐN mảnh, thiếu mảnh nào
StarUML cũng mở ra sai:

    1. UMLUseCase        — phần tử mô hình, nằm trong UMLModel "UseCase"
    2. UMLAssociation    — liên kết tác nhân ↔ use case, nằm TRONG tác nhân
    3. UMLUseCaseView    — hình bầu dục trên sơ đồ, kèm 6 ngăn con bắt buộc
    4. UMLAssociationView— đường nối trên sơ đồ, kèm 9 nhãn và 2 ngăn con

Mảnh 1–2 là mô hình, mảnh 3–4 là hình vẽ. Có mô hình mà không có hình vẽ
thì use case chỉ hiện ở cây bên trái, không hiện trên sơ đồ.

Toạ độ phải tự tính: StarUML lưu sẵn đường đi của mọi đường nối
("points": "x:y;x:y"), không tự vẽ lại khi mở tệp. Vì vậy script KHÔNG dời
hai tác nhân — dời là toàn bộ đường nối cũ trỏ lệch ra chỗ trống.

Chạy lại được nhiều lần: use case đã có thì bỏ qua.
"""
import json
import pathlib
import shutil
import sys

MDJ = pathlib.Path("BAOCAO/Diagram.mdj")

# ── Use case cần thêm: (tên, tác nhân, left, top, width, height) ──
THEM = [
    ("Ghi nhật ký ăn uống", "Người dùng", 230, 1240, 270, 72),
    ("Theo dõi tình trạng cơ thể", "Người dùng", 540, 1240, 350, 72),
    ("Thêm món ăn của tôi vào thực đơn", "Người dùng", 230, 1352, 410, 72),
    ("Quản lý bệnh lý và ngưỡng dinh dưỡng", "Quản trị viên",
     850, 1040, 460, 72),
]

# ── Liên kết thêm vào use case ĐÃ CÓ sẵn: (tác nhân, tên use case) ──
NOI_THEM = [
    ("Quản trị viên", "Đổi mật khẩu"),
]

# Khung hệ thống phải cao thêm cho vừa hàng mới.
SUBJECT_HEIGHT = 1400

_dem = 0


def mid(s: str) -> str:
    """Sinh _id mới, dùng tiền tố riêng để chắc chắn không đụng _id có sẵn."""
    global _dem
    _dem += 1
    return f"DATNUSECASE{_dem:04d}{s}="


def nhan(parent: str, model: str, **kw) -> dict:
    d = {"_type": "LabelView", "_id": mid("L"),
         "_parent": {"$ref": parent}, "font": "Arial;13;0"}
    d.update(kw)
    return d


def ngan(loai: str, parent: str, model: str) -> dict:
    """Ngăn con ẩn. StarUML vẫn đòi đủ sáu ngăn dù không ngăn nào hiện."""
    return {"_type": loai, "_id": mid("C"), "_parent": {"$ref": parent},
            "model": {"$ref": model}, "visible": False,
            "font": "Arial;13;0", "left": 184, "top": -208,
            "width": 10, "height": 10}


def view_usecase(dia: str, model: str, ten: str,
                 l: int, t: int, w: int, h: int) -> dict:
    vid = mid("V")
    ncid = mid("N")
    # Ngăn tên nằm thụt vào trong hình bầu dục đúng như các view sẵn có.
    nc_l, nc_t, nc_w = l + 22.5, t + 23, w - 45
    labels = [
        nhan(ncid, model, visible=False, left=l, top=t - 528, height=13),
        nhan(ncid, model, font="Arial;13;1", left=nc_l + 5, top=nc_t + 7,
             width=nc_w - 10, height=13, text=ten),
        nhan(ncid, model, visible=False, left=l, top=t - 528,
             width=91.736328125, height=13, text="(from UseCase)"),
        nhan(ncid, model, visible=False, left=l, top=t - 528, height=13,
             horizontalAlignment=1),
    ]
    namecomp = {
        "_type": "UMLNameCompartmentView", "_id": ncid,
        "_parent": {"$ref": vid}, "model": {"$ref": model},
        "subViews": labels, "font": "Arial;13;0",
        "left": nc_l, "top": nc_t, "width": nc_w, "height": 25,
        "stereotypeLabel": {"$ref": labels[0]["_id"]},
        "nameLabel": {"$ref": labels[1]["_id"]},
        "namespaceLabel": {"$ref": labels[2]["_id"]},
        "propertyLabel": {"$ref": labels[3]["_id"]},
    }
    ngans = [ngan(k, vid, model) for k in (
        "UMLAttributeCompartmentView", "UMLOperationCompartmentView",
        "UMLReceptionCompartmentView",
        "UMLTemplateParameterCompartmentView",
        "UMLExtensionPointCompartmentView")]
    return {
        "_type": "UMLUseCaseView", "_id": vid, "_parent": {"$ref": dia},
        "model": {"$ref": model}, "subViews": [namecomp] + ngans,
        "font": "Arial;13;0", "containerChangeable": True,
        "left": l, "top": t, "width": w, "height": h,
        "nameCompartment": {"$ref": ncid},
        "suppressAttributes": True, "suppressOperations": True,
        "attributeCompartment": {"$ref": ngans[0]["_id"]},
        "operationCompartment": {"$ref": ngans[1]["_id"]},
        "receptionCompartment": {"$ref": ngans[2]["_id"]},
        "templateParameterCompartment": {"$ref": ngans[3]["_id"]},
        "extensionPointCompartment": {"$ref": ngans[4]["_id"]},
    }


def cat_bien(hop: dict, hx: float, hy: float) -> tuple[float, float]:
    """Điểm mà đoạn thẳng từ tâm `hop` tới (hx, hy) cắt viền của `hop`.

    Đường nối phải chạm viền hình chứ không chạm tâm, nếu không StarUML vẽ
    đường đâm xuyên qua giữa hình bầu dục.
    """
    cx = hop["left"] + hop["width"] / 2
    cy = hop["top"] + hop["height"] / 2
    dx, dy = hx - cx, hy - cy
    if dx == 0 and dy == 0:
        return cx, cy
    # Tỷ lệ cần co lại để chạm cạnh đứng hoặc cạnh ngang, lấy cạnh nào tới
    # trước.
    tx = (hop["width"] / 2) / abs(dx) if dx else float("inf")
    ty = (hop["height"] / 2) / abs(dy) if dy else float("inf")
    k = min(tx, ty)
    return round(cx + dx * k), round(cy + dy * k)


def view_lienket(dia: str, assoc: dict, view_tail: str, view_head: str,
                 hop_tail: dict, hop_head: dict) -> dict:
    vid = mid("E")
    e1, e2 = assoc["end1"]["_id"], assoc["end2"]["_id"]
    tx = hop_tail["left"] + hop_tail["width"] / 2
    ty = hop_tail["top"] + hop_tail["height"] / 2
    hx = hop_head["left"] + hop_head["width"] / 2
    hy = hop_head["top"] + hop_head["height"] / 2
    p1 = cat_bien(hop_tail, hx, hy)
    p2 = cat_bien(hop_head, tx, ty)

    def elab(model_id, alpha, dist, pos=None):
        d = {"_type": "EdgeLabelView", "_id": mid("G"),
             "_parent": {"$ref": vid}, "model": {"$ref": model_id},
             "visible": False, "font": "Arial;13;0",
             "left": round((p1[0] + p2[0]) / 2),
             "top": round((p1[1] + p2[1]) / 2), "height": 13,
             "alpha": alpha, "distance": dist,
             "hostEdge": {"$ref": vid}}
        if pos is not None:
            d["edgePosition"] = pos
        return d

    labs = [
        elab(assoc["_id"], 1.5707963267948966, 15, 1),
        elab(assoc["_id"], 1.5707963267948966, 30, 1),
        elab(assoc["_id"], -1.5707963267948966, 15, 1),
        elab(e1, 0.5235987755982988, 30, 2),
        elab(e1, 0.7853981633974483, 40, 2),
        elab(e1, -0.5235987755982988, 25, 2),
        elab(e2, -0.5235987755982988, 30),
        elab(e2, -0.7853981633974483, 40),
        elab(e2, 0.5235987755982988, 25),
    ]
    quals = [{"_type": "UMLQualifierCompartmentView", "_id": mid("Q"),
              "_parent": {"$ref": vid}, "model": {"$ref": m},
              "visible": False, "font": "Arial;13;0",
              "width": 10, "height": 10} for m in (e1, e2)]
    return {
        "_type": "UMLAssociationView", "_id": vid, "_parent": {"$ref": dia},
        "model": {"$ref": assoc["_id"]}, "subViews": labs + quals,
        "font": "Arial;13;0",
        "head": {"$ref": view_head}, "tail": {"$ref": view_tail},
        "lineStyle": 1,
        "points": f"{p1[0]}:{p1[1]};{p2[0]}:{p2[1]}",
        "showVisibility": True,
        "nameLabel": {"$ref": labs[0]["_id"]},
        "stereotypeLabel": {"$ref": labs[1]["_id"]},
        "propertyLabel": {"$ref": labs[2]["_id"]},
        "showEndOrder": "hide",
        "tailRoleNameLabel": {"$ref": labs[3]["_id"]},
        "tailPropertyLabel": {"$ref": labs[4]["_id"]},
        "tailMultiplicityLabel": {"$ref": labs[5]["_id"]},
        "headRoleNameLabel": {"$ref": labs[6]["_id"]},
        "headPropertyLabel": {"$ref": labs[7]["_id"]},
        "headMultiplicityLabel": {"$ref": labs[8]["_id"]},
        "tailQualifiersCompartment": {"$ref": quals[0]["_id"]},
        "headQualifiersCompartment": {"$ref": quals[1]["_id"]},
    }


def lien_ket(actor: dict, uc: dict) -> dict:
    aid = mid("A")
    return {"_type": "UMLAssociation", "_id": aid,
            "_parent": {"$ref": actor["_id"]},
            "end1": {"_type": "UMLAssociationEnd", "_id": mid("E1"),
                     "_parent": {"$ref": aid},
                     "reference": {"$ref": actor["_id"]}},
            "end2": {"_type": "UMLAssociationEnd", "_id": mid("E2"),
                     "_parent": {"$ref": aid},
                     "reference": {"$ref": uc["_id"]}}}


def kiem_tra(goc) -> None:
    """Mọi {"$ref": ...} phải trỏ tới một _id có thật."""
    co, can = set(), []

    def di(o, duong="$"):
        if isinstance(o, dict):
            if "_id" in o:
                co.add(o["_id"])
            if set(o) == {"$ref"}:
                can.append((o["$ref"], duong))
            for k, v in o.items():
                di(v, f"{duong}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                di(v, f"{duong}[{i}]")

    di(goc)
    hong = [(r, d) for r, d in can if r not in co]
    if hong:
        for r, d in hong[:10]:
            print(f"   ✗ {d} trỏ tới {r} — không có phần tử nào mang _id này")
        sys.exit(f"DỪNG — {len(hong)} tham chiếu hỏng.")
    print(f"   [ok] {len(can)} tham chiếu, tất cả đều trỏ đúng")


def chong_nhau(hop) -> list:
    va = []
    for i in range(len(hop)):
        for j in range(i + 1, len(hop)):
            a, b = hop[i], hop[j]
            if (a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                    and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]):
                va.append((a[0], b[0]))
    return va


def main() -> int:
    if not MDJ.exists():
        sys.exit(f"Không thấy {MDJ}")
    backup = MDJ.with_suffix(".mdj.bak")
    if not backup.exists():
        shutil.copy2(MDJ, backup)
        print(f"Đã sao lưu -> {backup.name}")

    goc = json.loads(MDJ.read_text(encoding="utf-8"))

    ucm = next(e for e in goc["ownedElements"]
               if e["_type"] == "UMLModel" and e["name"] == "UseCase")
    dia = next(e for e in ucm["ownedElements"]
               if e["_type"] == "UMLUseCaseDiagram")
    actors = {e["name"]: e for e in ucm["ownedElements"]
              if e["_type"] == "UMLActor"}
    ucs = {e["name"]: e for e in ucm["ownedElements"]
           if e["_type"] == "UMLUseCase"}
    views = {v["model"]["$ref"]: v for v in dia["ownedViews"]
             if v["_type"] in ("UMLUseCaseView", "UMLActorView")}

    print("\nThêm use case:")
    for ten, ta, l, t, w, h in THEM:
        if ten in ucs:
            print(f"   - {ten}: đã có, bỏ qua")
            continue
        actor = actors[ta]
        uc = {"_type": "UMLUseCase", "_id": mid("U"),
              "_parent": {"$ref": ucm["_id"]}, "name": ten}
        ucm["ownedElements"].append(uc)
        ucs[ten] = uc

        v = view_usecase(dia["_id"], uc["_id"], ten, l, t, w, h)
        dia["ownedViews"].append(v)
        views[uc["_id"]] = v

        a = lien_ket(actor, uc)
        actor.setdefault("ownedElements", []).append(a)
        dia["ownedViews"].append(view_lienket(
            dia["_id"], a, views[actor["_id"]]["_id"], v["_id"],
            views[actor["_id"]], v))
        print(f"   + {ten}  <- {ta}   ({l},{t}) {w}×{h}")

    print("\nNối thêm vào use case sẵn có:")
    for ta, ten in NOI_THEM:
        actor, uc = actors[ta], ucs[ten]
        da_co = any(
            e["_type"] == "UMLAssociation"
            and e["end2"]["reference"]["$ref"] == uc["_id"]
            for e in actor.get("ownedElements", []))
        if da_co:
            print(f"   - {ta} -> {ten}: đã nối, bỏ qua")
            continue
        a = lien_ket(actor, uc)
        actor.setdefault("ownedElements", []).append(a)
        dia["ownedViews"].append(view_lienket(
            dia["_id"], a, views[actor["_id"]]["_id"], views[uc["_id"]]["_id"],
            views[actor["_id"]], views[uc["_id"]]))
        print(f"   + {ta} -> {ten}")

    # ── Nới khung hệ thống cho vừa hàng mới ──
    subj = next(v for v in dia["ownedViews"]
                if v["_type"] == "UMLUseCaseSubjectView")
    if subj["height"] < SUBJECT_HEIGHT:
        print(f"\nKhung hệ thống: cao {subj['height']} -> {SUBJECT_HEIGHT}")
        subj["height"] = SUBJECT_HEIGHT

    # ── Kiểm tra trước khi ghi ──
    print("\nKiểm tra:")
    kiem_tra(goc)

    hop = [(v["subViews"][0]["subViews"][1].get("text", "?"),
            v["left"], v["top"], v["width"], v["height"])
           for v in dia["ownedViews"] if v["_type"] == "UMLUseCaseView"]
    va = chong_nhau(hop)
    if va:
        for a, b in va:
            print(f"   ✗ chồng hình: “{a}” và “{b}”")
        sys.exit("DỪNG — có hình chồng lên nhau.")
    print(f"   [ok] {len(hop)} hình use case, không hình nào chồng nhau")

    trong = [t for t in hop
             if not (subj["left"] <= t[1] and subj["top"] <= t[2]
                     and t[1] + t[3] <= subj["left"] + subj["width"]
                     and t[2] + t[4] <= subj["top"] + subj["height"])]
    if trong:
        for t in trong:
            print(f"   ✗ nằm ngoài khung hệ thống: “{t[0]}”")
        sys.exit("DỪNG — có hình nằm ngoài khung.")
    print("   [ok] mọi hình nằm trong khung hệ thống")

    MDJ.write_text(json.dumps(goc, ensure_ascii=False, indent="	"),
                   encoding="utf-8")
    print(f"\nĐã ghi {MDJ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
