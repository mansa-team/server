from imports import *

def log(tag: str, message: str):
    if Config.DEBUG_MODE == "TRUE":
        print(f"[{tag.upper()}] {message}")