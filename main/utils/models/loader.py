from pathlib import Path
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download

MODELS_DIR = Path(__file__).resolve().parent
MODEL_DIR = MODELS_DIR / "all-MiniLM-L6-v2"
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

model: SentenceTransformer | None = None


def getEmbeddingModel() -> SentenceTransformer:
    global model
    if model is None:
        if not (MODEL_DIR / "model.safetensors").exists():
            # Revision pinned to a verified commit for supply-chain reproducibility
            # (bandit B615: "main" is a moving target). Bump deliberately when
            # intentionally updating the embedding model.
            snapshot_download(
                MODEL_ID,
                local_dir=str(MODEL_DIR),
                revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
                ignore_patterns=["*.bin", "*.h5", "*.ot", "*.onnx", "*.openvino*"],
            )
        model = SentenceTransformer(str(MODEL_DIR))
    return model
