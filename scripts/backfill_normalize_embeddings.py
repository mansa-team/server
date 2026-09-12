"""One-shot: renormalize stored embeddings to unit norm. Usage: python scripts/backfill_normalize_embeddings.py"""

import numpy as np
from config import SessionLocal
from main.models.prometheus import PrometheusMemory as MemoryModel

BATCH = 500


def main():
    db = SessionLocal()
    try:
        offset = 0
        total = 0
        while True:
            rows = (
                db.query(MemoryModel)
                .filter(MemoryModel.embedding.isnot(None))
                .order_by(MemoryModel.id)
                .offset(offset)
                .limit(BATCH)
                .all()
            )
            if not rows:
                break
            for m in rows:
                vec = np.array(m.embedding, dtype=np.float32)
                norm = float(np.linalg.norm(vec))
                if norm > 0 and abs(norm - 1.0) > 1e-6:
                    m.embedding = (vec / norm).tolist()
                    total += 1
            db.commit()
            offset += BATCH
        print(f"renormalized={total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
