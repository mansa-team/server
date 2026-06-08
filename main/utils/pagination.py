from fastapi import Query


class PaginationParams:
    def __init__(
        self,
        limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
    ):
        self.limit = limit
        self.offset = offset
