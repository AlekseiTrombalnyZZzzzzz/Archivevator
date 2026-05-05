"""Глобальные константы и пороги."""
CHUNK_SIZE = 16 * 1024 * 1024
ENTROPY_WINDOW = 10 * 1024 * 1024
SMALL_FILE_THRESHOLD = 64
RATIO_FALLBACK_THRESHOLD = 0.55
SEARCH_TIMEOUT = 30.0
IMAGE_MAX_RAM_MB = 512
IMAGE_WEBP_METHOD = 6
IMAGE_MAX_DIM = 0

ALGO_EXT = {"zstd": ".zst", "brotli": ".br", "lzma": ".xz", "image": ""}

SKIP_SEARCH_DIRS = {
    "Windows", "Program Files", "Program Files (x86)", "AppData",
    "$Recycle.Bin", "System Volume Information",
    "proc", "sys", "dev", "run", "snap", "tmp", "var",
    "node_modules", ".git", "venv", "__pycache__", "Library", "Applications"
}