from main.utils.models.loader import embed

def save_memory(query: str) -> str:
    pass

def search_memory(query: str) -> list:
    pass

# automatic memory reranker and eraser done via schedulers in the prometheus_service.py taht will automatically evalujate the most used memories and delete those that are irrelevant to the system