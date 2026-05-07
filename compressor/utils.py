from __future__ import annotations
import hashlib, json, logging, math, os, signal, sys, time
from pathlib import Path
from typing import List, Optional

import filetype
from PIL import Image
from tqdm import tqdm
from compressor import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("compressor.utils")

_temp_files: List[Path] = []

def register_temp(p: Path) -> None: _temp_files.append(p)

def _cleanup(*_) -> None:
    for f in _temp_files:
        try: f.unlink(missing_ok=True)
        except OSError: pass
    print("\n🧹 Временные файлы очищены. Выход.")
    sys.exit(1)

signal.signal(signal.SIGINT, _cleanup)
signal.signal(signal.SIGTERM, _cleanup)

def calc_shannon_entropy(filepath: Path) -> float:
    counts = [0] * 256
    total = 0
    try:
        with open(filepath, "rb") as f:
            while total < config.ENTROPY_WINDOW:
                chunk = f.read(min(1024 * 1024, config.ENTROPY_WINDOW - total))
                if not chunk: break
                for b in chunk: counts[b] += 1
                total += len(chunk)
    except OSError as e:
        logger.warning(f"Entropy read failed: {e}")
        return 0.0
    if total == 0: return 0.0
    return -sum((c/total) * math.log2(c/total) for c in counts if c > 0) / 8.0

def get_file_type(filepath: Path) -> str:
    try:
        kind = filetype.guess(filepath)
        return kind.mime if kind else "unknown"
    except Exception: return "unknown"

def stream_sha256(filepath: Path, desc: str = "Hash") -> str:
    h = hashlib.sha256()
    size = os.path.getsize(filepath)
    pbar = tqdm(total=size, unit="B", unit_scale=True, desc=desc, leave=False)
    with open(filepath, "rb") as f:
        while chunk := f.read(config.CHUNK_SIZE):
            h.update(chunk)
            pbar.update(len(chunk))
    pbar.close()
    return h.hexdigest()

def find_file_on_disk(filename: str) -> Optional[Path]:
    local = Path(filename)
    if local.exists() and local.is_file(): return local.resolve()
    print(f"🔍 '{filename}' не в текущей папке. Сканирую диск (таймаут {int(config.SEARCH_TIMEOUT)}с)...")
    start = time.time()
    dots = 0
    roots = [f"{d}:\\" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")] if sys.platform == "win32" else ["/"]
    for root in roots:
        try:
            for dirpath, dirnames, files in os.walk(root, onerror=lambda e: None):
                if time.time() - start > config.SEARCH_TIMEOUT: print("\n⏱️ Таймаут поиска."); return None
                dirnames[:] = [d for d in dirnames if d not in config.SKIP_SEARCH_DIRS]
                if filename in files: return Path(dirpath, filename).resolve()
                dots += 1
                if dots % 500 == 0: print(".", end="", flush=True)
        except Exception: continue
    print("\n❌ Файл не найден.")
    return None

def save_metadata(src: Path, dst: Path, checksum: str, pixel_hash: str = "") -> Path:
    meta_path = dst.with_suffix(dst.suffix + ".meta.json")
    st = src.stat()
    meta = {
        "original_name": src.name,
        "mode": oct(st.st_mode), "atime": st.st_atime, "mtime": st.st_mtime,
        "uid": st.st_uid, "gid": st.st_gid,
        "sha256": checksum, "pixel_sha256": pixel_hash
    }
    with open(meta_path, "w") as f: json.dump(meta, f, indent=2)
    return meta_path

def restore_metadata(compressed: Path, restored: Path) -> None:
    meta_path = compressed.with_suffix(compressed.suffix + ".meta.json")
    if not meta_path.exists(): return
    try:
        with open(meta_path) as f: meta = json.load(f)
        os.chmod(restored, int(meta["mode"], 8))
        os.utime(restored, (meta["atime"], meta["mtime"]))
        if hasattr(os, 'chown'):
            try: os.chown(restored, meta["uid"], meta["gid"])
            except Exception: pass
    except Exception as e:
        logger.warning(f"⚠️ Метаданные частично: {e}")

def verify_image_lossless(src: Path, compressed: Path) -> bool:
    try:
        with Image.open(src) as img1, Image.open(compressed) as img2:
            if img1.size != img2.size: return False
            mode = "RGBA" if img1.mode in ("RGBA", "P", "LA") else "RGB"
            if img1.mode != mode: img1 = img1.convert(mode)
            if img2.mode != mode: img2 = img2.convert(mode)
            return hashlib.sha256(img1.tobytes()).hexdigest() == hashlib.sha256(img2.tobytes()).hexdigest()
    except Exception as e:
        logger.error(f"Image pixel verification failed: {e}")
        return False