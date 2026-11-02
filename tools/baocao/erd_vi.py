# -*- coding: utf-8 -*-
"""Tên tiếng Việt của từng bảng và từng cột trong CSDL.

QUY TẮC ĐẶT TÊN
---------------
Chuyển thẳng tên tiếng Anh sang tiếng Việt, rồi viết dính liền theo kiểu
lạc đà: chữ cái đầu KHÔNG viết hoa, không có khoảng trắng, không có gạch
dưới, và GIỮ NGUYÊN DẤU.

    users          -> ngườiDùng
    password_hash  -> mãBămMậtKhẩu
    vitamin_a_mcg  -> vitaminAMcg

Bảng tên này CHỈ dùng cho bản báo cáo tiếng Việt. Sơ đồ ERD nộp
(BAOCAO/Diagram.mdj) vẫn để tên tiếng Anh không dấu, vì yêu cầu của môn là
tên thực thể và tên thuộc tính không được có dấu tiếng Việt. Hai cách gọi
tồn tại song song và `build_erd_vi.py` in ra đúng cặp tên đó cạnh nhau.

QUY ƯỚC CHUNG, GIỮ GIỐNG NHAU Ở MỌI BẢNG
----------------------------------------
    id            -> mã              khóa chính
    *_id          -> mã<Bảng>        khóa ngoại
    created_at    -> thờiĐiểmTạo     DATETIME dùng "thờiĐiểm"
    *_on / date   -> ngày*           DATE chỉ dùng "ngày"
    note          -> ghiChú
    description   -> môTả
    is_*          -> đang* / là*

Phân biệt "thờiĐiểm" (DATETIME) với "ngày" (DATE) là cố ý: đọc tên cột là
biết cột đó có giờ phút hay không, khỏi phải tra lại kiểu dữ liệu.
"""

# Tên bảng. Thứ tự viết ra là thứ tự in trong báo cáo — theo tầng phụ thuộc
# giống db/schema.sql, không sắp theo bảng chữ cái.
BANG = {
    "users": ("ngườiDùng",
              "Tài khoản dùng chung cho ứng dụng Android và trang quản trị, "
              "phân biệt bằng vai trò."),
    "conditions": ("bệnhLý",
                   "Từ điển bệnh lý, dị ứng, chứng không dung nạp và chế "
                   "độ ăn."),
    "tags": ("nhãn",
             "Từ vựng có kiểm soát gắn cho món ăn: chất gây dị ứng, chế độ "
             "ăn, đặc điểm dinh dưỡng."),
    "food_categories": ("danhMụcMónĂn",
                        "Nhóm món ăn, dùng làm đặc trưng one-hot cho học "
                        "máy."),
    "ml_models": ("môHìnhHọcMáy",
                  "Mỗi dòng là một lần huấn luyện đã hoàn tất, kèm tham số "
                  "và đường dẫn tệp mô hình."),
    "rda_reference": ("nhuCầuKhuyếnNghị",
                      "Bảng tra cứu nhu cầu dinh dưỡng khuyến nghị theo "
                      "tuổi và giới."),

    "health_profiles": ("hồSơSứcKhỏe",
                        "Số đo cơ thể và mục tiêu dinh dưỡng của người "
                        "dùng, mỗi người một dòng."),
    "user_conditions": ("bệnhLýNgườiDùng",
                        "Người dùng khai mắc bệnh lý nào, ở mức độ nào."),
    "user_preference_profiles": ("hồSơKhẩuVị",
                                 "Véc-tơ khẩu vị của người dùng, cập nhật "
                                 "sau mỗi tín hiệu tương tác."),
    "body_logs": ("nhậtKýCơThể",
                  "Người dùng tự ghi cân nặng theo ngày để theo dõi tiến "
                  "triển."),
    "foods": ("mónĂn",
              "Món ăn trong hệ thống, gồm cả món do người dùng tự thêm."),
    "condition_rules": ("quyTắcBệnhLý",
                        "Ràng buộc mà mỗi bệnh lý đặt ra: cấm nhãn, buộc "
                        "có nhãn, hoặc giới hạn một chất."),

    "food_nutrition": ("dinhDưỡngMónĂn",
                       "Thành phần dinh dưỡng của một khẩu phần, mỗi món "
                       "một dòng."),
    "food_tags": ("nhãnCủaMónĂn",
                  "Bảng nối nhiều-nhiều giữa món ăn và nhãn."),
    "meal_plans": ("thựcĐơnNgày",
                   "Thực đơn hệ thống sinh cho một người trong một ngày."),
    "recommendations": ("khuyếnNghịMónĂn",
                        "Nhật ký từng món đã được gợi ý, giữ lại điểm số "
                        "để đánh giá về sau."),
    "food_diary": ("nhậtKýĂnUống",
                   "Người dùng tự ghi đã ăn món gì, vào buổi nào."),
    "feedbacks": ("phảnHồi",
                  "Người dùng chấm điểm và nhận xét về món ăn."),
    "interactions": ("tươngTác",
                     "Thao tác vuốt thích hoặc không thích trong phiên "
                     "thăm dò khẩu vị."),

    "ml_training_samples": ("mẫuHuấnLuyện",
                            "Tập mẫu đã đóng băng theo phiên bản dữ liệu "
                            "để huấn luyện lại cho ra cùng kết quả."),
    "ml_evaluations": ("đánhGiáMôHình",
                       "Kết quả đo chất lượng của từng mô hình theo từng "
                       "độ đo."),
    "meal_plan_items": ("mónTrongThựcĐơn",
                        "Từng món trong một thực đơn ngày, kèm việc người "
                        "dùng giữ hay đổi món."),
}

# Tên cột, gom theo bảng. Tên lặp lại ở nhiều bảng vẫn phải viết lại đủ cho
# từng bảng — `build_erd_vi.py` đối chiếu bảng này với CSDL và dừng ngay nếu
# thừa hoặc thiếu một cột, nên không có cách nào để sót.
COT = {
    "users": {
        "id": "mã",
        "email": "thưĐiệnTử",
        "role": "vaiTrò",
        "is_active": "đangHoạtĐộng",
        "password_hash": "mãBămMậtKhẩu",
        "display_name": "tênHiểnThị",
        "avatar_url": "đườngDẫnẢnhĐạiDiện",
        "onboarding_completed_at": "thờiĐiểmHoànTấtKhởiTạo",
        "created_at": "thờiĐiểmTạo",
        "updated_at": "thờiĐiểmCậpNhật",
    },
    "conditions": {
        "id": "mã",
        "name_vi": "tênTiếngViệt",
        "condition_type": "loạiBệnhLý",
        "description": "môTả",
    },
    "tags": {
        "id": "mã",
        "name_vi": "tênTiếngViệt",
        "tag_type": "loạiNhãn",
        "description": "môTả",
    },
    "food_categories": {
        "id": "mã",
        "name": "tên",
        "description": "môTả",
        "icon_url": "đườngDẫnBiểuTượng",
    },
    "ml_models": {
        "id": "mã",
        "version": "phiênBản",
        "algorithm": "thuậtToán",
        "feature_version": "phiênBảnĐặcTrưng",
        "dataset_version": "phiênBảnTậpDữLiệu",
        "hyperparams": "siêuThamSố",
        "scaler_params": "thamSốChuẩnHóa",
        "feature_importance": "độQuanTrọngĐặcTrưng",
        "n_train": "sốMẫuHuấnLuyện",
        "n_test": "sốMẫuKiểmTra",
        "artifact_path": "đườngDẫnTệpMôHình",
        "is_active": "đangHoạtĐộng",
        "trained_at": "thờiĐiểmHuấnLuyện",
        "note": "ghiChú",
    },
    "rda_reference": {
        "id": "mã",
        "gender": "giớiTính",
        "age_min": "tuổiTốiThiểu",
        "age_max": "tuổiTốiĐa",
        "nutrient": "chấtDinhDưỡng",
        "qualifier": "nhómPhụNguyênVăn",
        "rda_value": "giáTrịKhuyếnNghị",
        "unit": "đơnVị",
        "source": "nguồnTàiLiệu",
    },
    "health_profiles": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "gender": "giớiTính",
        "date_of_birth": "ngàySinh",
        "height_cm": "chiềuCaoCm",
        "weight_kg": "cânNặngKg",
        "bmi": "chỉSốKhốiCơThể",
        "activity_level": "mứcVậnĐộng",
        "goal": "mụcTiêu",
        "bmr_kcal": "nhuCầuChuyểnHóaCơBản",
        "tdee_kcal": "tổngNăngLượngTiêuHao",
        "daily_calories_target": "năngLượngMụcTiêuNgày",
        "target_protein_pct": "tỷLệĐạmMụcTiêu",
        "target_carbs_pct": "tỷLệTinhBộtMụcTiêu",
        "target_fat_pct": "tỷLệChấtBéoMụcTiêu",
        "created_at": "thờiĐiểmTạo",
        "updated_at": "thờiĐiểmCậpNhật",
    },
    "user_conditions": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "condition_id": "mãBệnhLý",
        "severity": "mứcĐộNặng",
        "note": "ghiChú",
        "created_at": "thờiĐiểmTạo",
    },
    "user_preference_profiles": {
        "user_id": "mãNgườiDùng",
        "feature_version": "phiênBảnĐặcTrưng",
        "weights": "véctơTrọngSố",
        "sum_abs_weight": "tổngTrịTuyệtĐốiTrọngSố",
        "n_signals": "sốTínHiệuĐãHọc",
        "stage": "giaiĐoạnGợiÝ",
        "alpha": "hệSốPhaTrộn",
        "updated_at": "thờiĐiểmCậpNhật",
    },
    "body_logs": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "logged_on": "ngàyGhi",
        "weight_kg": "cânNặngKg",
        "note": "ghiChú",
        "created_at": "thờiĐiểmTạo",
    },
    "foods": {
        "id": "mã",
        "category_id": "mãDanhMục",
        "name": "tên",
        "description": "môTả",
        "image_url": "đườngDẫnẢnh",
        "spice_level": "mứcĐộCay",
        "dish_role": "vaiTròMón",
        "popularity_score": "điểmPhổBiến",
        "is_active": "đangHoạtĐộng",
        "owner_id": "mãChủSởHữu",
        "created_at": "thờiĐiểmTạo",
        "updated_at": "thờiĐiểmCậpNhật",
    },
    "condition_rules": {
        "id": "mã",
        "condition_id": "mãBệnhLý",
        "rule_type": "loạiQuyTắc",
        "tag_id": "mãNhãn",
        "nutrient": "chấtDinhDưỡng",
        "comparator": "phépSoSánh",
        "threshold": "ngưỡng",
        "scope": "phạmViÁpDụng",
        "severity_min": "mứcĐộNặngTốiThiểu",
        "is_hard": "làRàngBuộcCứng",
        "penalty": "điểmPhạt",
        "note": "ghiChú",
    },
    "food_nutrition": {
        "id": "mã",
        "food_id": "mãMónĂn",
        "serving_size_g": "khẩuPhầnGam",
        "calories_kcal": "năngLượngKcal",
        "protein_g": "đạmGam",
        "carbs_g": "tinhBộtGam",
        "fat_g": "chấtBéoGam",
        "fiber_g": "chấtXơGam",
        "sugar_g": "đườngGam",
        "sodium_mg": "natriMiligam",
        "cholesterol_mg": "cholesterolMiligam",
        "purine_mg": "purinMiligam",
        "calcium_mg": "canxiMiligam",
        "iron_mg": "sắtMiligam",
        "zinc_mg": "kẽmMiligam",
        "vitamin_a_mcg": "vitaminAMicrogam",
        "vitamin_c_mg": "vitaminCMiligam",
        "updated_at": "thờiĐiểmCậpNhật",
    },
    "food_tags": {
        "food_id": "mãMónĂn",
        "tag_id": "mãNhãn",
    },
    "meal_plans": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "plan_date": "ngàyÁpDụng",
        "target_calories_kcal": "năngLượngMụcTiêuKcal",
        "target_protein_g": "đạmMụcTiêuGam",
        "target_carbs_g": "tinhBộtMụcTiêuGam",
        "target_fat_g": "chấtBéoMụcTiêuGam",
        "actual_calories_kcal": "năngLượngThựcTếKcal",
        "actual_protein_g": "đạmThựcTếGam",
        "actual_carbs_g": "tinhBộtThựcTếGam",
        "actual_fat_g": "chấtBéoThựcTếGam",
        "calorie_deviation_pct": "tỷLệLệchNăngLượng",
        "total_preference_score": "tổngĐiểmƯaThích",
        "exploration_ratio": "tỷLệThămDò",
        "generation_source": "nguồnSinhThựcĐơn",
        "model_id": "mãMôHình",
        "status": "trạngThái",
        "generated_at": "thờiĐiểmSinh",
    },
    "recommendations": {
        "id": "mã",
        "batch_id": "mãLượtGợiÝ",
        "user_id": "mãNgườiDùng",
        "food_id": "mãMónĂn",
        "context_meal_type": "buổiĂnNgữCảnh",
        "score": "điểmTổngHợp",
        "score_content": "điểmTheoNộiDung",
        "score_ml": "điểmTheoHọcMáy",
        "alpha": "hệSốPhaTrộn",
        "rank_position": "thứHạng",
        "source": "nguồnGợiÝ",
        "model_id": "mãMôHình",
        "was_selected": "đãĐượcChọn",
        "recommended_at": "thờiĐiểmGợiÝ",
    },
    "food_diary": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "food_id": "mãMónĂn",
        "ate_on": "ngàyĂn",
        "meal_type": "buổiĂn",
        "portion_multiplier": "hệSốKhẩuPhần",
        "created_at": "thờiĐiểmTạo",
    },
    "feedbacks": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "food_id": "mãMónĂn",
        "rating": "điểmĐánhGiá",
        "comment": "nhậnXét",
        "created_at": "thờiĐiểmTạo",
    },
    "interactions": {
        "id": "mã",
        "user_id": "mãNgườiDùng",
        "food_id": "mãMónĂn",
        "action": "hànhĐộng",
        "session_id": "mãPhiênVuốt",
        "interacted_at": "thờiĐiểmTươngTác",
    },
    "ml_training_samples": {
        "id": "mã",
        "dataset_version": "phiênBảnTậpDữLiệu",
        "user_id": "mãNgườiDùng",
        "food_id": "mãMónĂn",
        "label": "nhãnMụcTiêu",
        "sample_weight": "trọngSốMẫu",
        "source": "nguồnTínHiệu",
        "context_meal_type": "buổiĂnNgữCảnh",
        "split": "phầnChiaDữLiệu",
        "fold": "lượtKiểmChứngChéo",
        "collected_at": "thờiĐiểmThuThập",
        "profile_snapshot": "ảnhChụpHồSơ",
        "created_at": "thờiĐiểmTạo",
    },
    "ml_evaluations": {
        "id": "mã",
        "model_id": "mãMôHình",
        "variant": "phươngÁnSoSánh",
        "metric": "độĐo",
        "k_value": "giáTrịK",
        "value": "giáTrị",
        "fold": "lượtKiểmChứngChéo",
        "evaluated_at": "thờiĐiểmĐánhGiá",
    },
    "meal_plan_items": {
        "id": "mã",
        "meal_plan_id": "mãThựcĐơn",
        "food_id": "mãMónĂn",
        "meal_type": "buổiĂn",
        "portion_multiplier": "hệSốKhẩuPhần",
        "predicted_score": "điểmDựĐoán",
        "status": "trạngThái",
        "replaced_by_food_id": "mãMónThayThế",
        "replaced_at": "thờiĐiểmThayThế",
        "exploration_delta": "mứcThămDò",
        "position": "thứTựTrongBuổi",
        "note": "ghiChú",
        "created_at": "thờiĐiểmTạo",
    },
}
