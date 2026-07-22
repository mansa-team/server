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
        if not (MODEL_DIR / "onnx" / "model_qint8_avx512_vnni.onnx").exists():
            snapshot_download(
                MODEL_ID,
                local_dir=str(MODEL_DIR),
                revision="main",
                ignore_patterns=["*.bin", "*.h5", "*.ot", "*.openvino*"],
            )
        model = SentenceTransformer(
            str(MODEL_DIR),
            backend="onnx",
            model_kwargs={"file_name": "onnx/model_qint8_avx512_vnni.onnx"},
        )
    return model
