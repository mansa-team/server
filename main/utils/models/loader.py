from pathlib import Path
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODELS_DIR = Path(__file__).resolve().parent
MODEL_DIR = MODELS_DIR / MODEL_NAME.split("/")[-1]

model: SentenceTransformer | None = None


def getEmbeddingModel() -> SentenceTransformer:
    global model
    if model is None:
        if not (MODEL_DIR / "config.json").exists():
            snapshot_download(MODEL_NAME, local_dir=str(MODEL_DIR))
        model = SentenceTransformer(str(MODEL_DIR))
    return model


def embed(texts: list[str]) -> list[list[float]]:
    return getEmbeddingModel().encode(texts).tolist()
