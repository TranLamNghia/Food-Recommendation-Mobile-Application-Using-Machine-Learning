# -*- coding: utf-8 -*-
"""Phần học máy chạy phía máy chủ.

`docs/ML_PIPELINE.md` là tài liệu đặc tả của thư mục này. Thứ tự các tệp
đúng bằng thứ tự chạy của quy trình:

    db.py        kết nối CSDL, dùng lại `tools/_env.py`
    features.py  trích chọn đặc trưng — bản Python của `food_vector.dart`
    f1_filter.py bộ lọc an toàn theo bệnh lý (Bước F1)
    build_dataset.py  bảy nguồn tín hiệu  → `ml_training_samples`
    train.py          ba thuật toán       → `ml_models`
    evaluate.py       bốn phương án đối chứng → `ml_evaluations`
"""
