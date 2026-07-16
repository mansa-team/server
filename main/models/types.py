import numpy as np
from sqlalchemy.types import TypeDecorator, LargeBinary


class VectorType(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def __init__(self, dims: int = 384):
        self.dims = dims
        super().__init__()

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        arr = np.array(value, dtype=np.float32)
        if arr.shape != (self.dims,):
            raise ValueError(f"Vector must be {self.dims}-dim, got {arr.shape}")
        return arr.tobytes()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return np.frombuffer(value, dtype=np.float32).tolist()
