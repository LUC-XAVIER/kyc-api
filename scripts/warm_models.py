"""Pre-download the pipeline's model weights so the first verify isn't slow.

The BlazeFace detector ships with the code. ArcFace (face matching), FasNet
(anti-spoofing) and EasyOCR (text reading) auto-download on first use — about
250 MB total. Running this once right after a deploy pulls them ahead of time,
into the persistent model volume, so the first real /kyc/verify returns
quickly instead of hanging while it fetches them.

    python -m scripts.warm_models
"""


def main() -> None:
    """Trigger each model download the pipeline relies on."""
    print("Downloading ArcFace (face matching)...", flush=True)
    from deepface import DeepFace

    DeepFace.build_model("ArcFace")

    print("Downloading FasNet (anti-spoofing)...", flush=True)
    from deepface.models.spoofing import FasNet

    FasNet.Fasnet()

    print("Downloading EasyOCR (fr, en)...", flush=True)
    import easyocr

    easyocr.Reader(["fr", "en"], gpu=False)

    print("All pipeline models are ready.", flush=True)


if __name__ == "__main__":
    main()
