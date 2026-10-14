from pathlib import Path
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download

MODELS_DIR = Path(__file__).resolve().parent

model: SentenceTransformer | None = None


def getEmbeddingModel() -> SentenceTransformer:
    global model
    if model is None:
        if not (MODELS_DIR / "all-MiniLM-L6-v2" / "model.safetensors").exists():
            snapshot_download(
                "sentence-transformers/all-MiniLM-L6-v2",
                local_dir=str("sentence-transformers/all-MiniLM-L6-v2"),
                revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
                ignore_patterns=["*.bin", "*.h5", "*.ot", "*.onnx", "*.openvino*"],
            )
        model = SentenceTransformer(str("sentence-transformers/all-MiniLM-L6-v2"))
    return model
