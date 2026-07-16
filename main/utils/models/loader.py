from pathlib import Path
from sentence_transformers import SentenceTransformer

MODELS_DIR = Path(__file__).resolve().parent
MODEL_DIR = MODELS_DIR / "all-MiniLM-L6-v2"
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

model: SentenceTransformer | None = None


def _downloadModel():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_ID, local_dir=str(MODEL_DIR), ignore_patterns=["*.bin", "*.h5", "*.ot", "*.onnx", "*.openvino*"])


def getEmbeddingModel() -> SentenceTransformer:
    global model
    if model is None:
        if not (MODEL_DIR / "model.safetensors").exists():
            _downloadModel()
        model = SentenceTransformer(str(MODEL_DIR))
    return model


def embed(texts: list[str]) -> list[list[float]]:
    return getEmbeddingModel().encode(texts).tolist()
