# -*- coding: utf-8 -*-
"""Server-side machine learning package.

`docs/ML_PIPELINE.md` is the design document for this directory. The files
are listed in the order the pipeline runs them:

    db.py             database connection, reuses `tools/_env.py`
    time_vn.py        the single clock: Asia/Ho_Chi_Minh
    features.py       feature extraction — Python twin of `food_vector.dart`
    f1_filter.py      medical safety filter (Step F1)
    build_dataset.py  seven signal sources  -> `ml_training_samples`
    train.py          three algorithms      -> `ml_models`
    evaluate.py       four baselines        -> `ml_evaluations`
    serve.py          scoring for one user
    api.py            the four internal HTTP endpoints
"""
