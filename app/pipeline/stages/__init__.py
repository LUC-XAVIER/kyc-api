"""Individual verification pipeline stages.

Each stage is an independent module exposing a small ``run``-style function
over the contracts in :mod:`app.pipeline.contracts`. Heavy ML imports
(OpenCV, Tesseract, DeepFace, MediaPipe, FAISS) are performed lazily inside
those functions so the API and non-ML tests import without the optional
``ml`` extra installed.
"""
