# Anti-spoofing dataset

Training data for the liveness LBP-SVM classifier
(`ml/train_antispoof.py`, Design doc §6.3.2). **Images are gitignored** —
only this folder skeleton is tracked. Drop your images into the folders
below; git will not commit them.

## Layout

```
data/antispoof/
├── train/          # cross-validated for hyperparameter selection
│   ├── live/       # genuine selfies (a real person in front of the camera)
│   └── spoof/      # print / replay attacks (photo of a photo, phone screen…)
└── test/           # scored once, for an unbiased final estimate
    ├── live/
    └── spoof/
```

Supported image types: `.png`, `.jpg`, `.jpeg`, `.bmp`.

## How the split is used

- **train/** — k-fold cross-validation runs *inside* this set to pick the
  SVM `C`/`gamma`. The CV folds are the validation signal, so there is no
  separate `val/` folder.
- **test/** — held out and evaluated once at the end (accuracy + ROC-AUC).

**Important — split subject/device-independently:** the same person or the
same capture device must not appear in both `train/` and `test/`, or the
scores will be optimistic. Keep `live/` and `spoof/` roughly balanced.

## Train

```
python ml/train_antispoof.py \
    --train-dir data/antispoof/train \
    --test-dir  data/antispoof/test
```

The model is written to `ml/models/antispoof_lbp_svm.joblib` (also
gitignored), which `app/pipeline/stages/liveness.py` loads at inference.
