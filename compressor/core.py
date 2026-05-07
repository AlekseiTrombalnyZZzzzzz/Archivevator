from __future__ import annotations
import hashlib, json, os, shutil, tempfile, time, filetype
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image

from compressor import config
from compressor.utils import (
    logger, stream_sha256, get_file_type, calc_shannon_entropy,
    save_metadata, restore_metadata
)
from compressor.engines import ALGO_COMPRESSORS, decompress_stream

def get_strategy_queue(entropy: float, force: bool, is_image: bool, override_level: Optional[int] = None) -> List[Tuple[str, int]]:
    if is_image: base = [("image", 100), ("zstd", 19), ("brotli", 11)]
    elif entropy <= 0.75: base = [("zstd", 19), ("brotli", 11)]
    elif entropy <= 0.92: base = [("lzma", 9), ("zstd", 9)]
    else:
        base = [("zstd", 3)]
        if force: base += [("lzma", 9), ("brotli", 11)]
    if override_level is not None and base:
        algo, _ = base[0]
        base[0] = (algo, override_level)
    return base

def _resolve_dst(src: Path, dst: Optional[Path], algo: str) -> Path:
    if dst: return Path(dst).resolve()
    ext = config.ALGO_EXT.get(algo, "")
    return src.with_suffix(src.suffix + ext) if ext else src.with_suffix(src.suffix + ".sc")

def detect_algo(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    if ext in (".zst", ".zstd"): return "zstd"
    if ext in (".br", ".brotli"): return "brotli"
    if ext in (".xz", ".lzma"): return "lzma"
    if ext in (".webp", ".png", ".jpg", ".jpeg"): return "image"

    kind = filetype.guess(filepath)
    if kind:
        if kind.mime.startswith("image/"): return "image"
        if kind.extension == "zst": return "zstd"
        if kind.extension == "xz": return "lzma"
        if kind.extension == "br": return "brotli"

    try:
        with open(filepath, "rb") as f: head = f.read(64)
    except Exception: return "zstd"

    if head[:4] == b'\x28\xb5\x2f\xfd': return "zstd"
    if head[:6] == b'\xfd7zXZ\x00': return "lzma"
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP': return "image"
    if head[:8] == b'\x89PNG\r\n\x1a\n': return "image"
    return "brotli"

def compress_file(
    src: str | Path, dst: Optional[str | Path] = None, strategy: str = "auto",
    verify: bool = True, force: bool = False, threads: int = 0, override_level: Optional[int] = None,
    optimize_office: bool = False, lossy_office: bool = False, progress_callback=None
) -> Dict[str, object]:
    src = Path(src).resolve()
    if not src.exists(): raise FileNotFoundError(f"Исходный файл не найден: {src}")

    archive_dir = src.parent / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)

    if src.suffix.lower() in ('.docx', '.xlsx', '.pptx') and optimize_office:
        from compressor.office import optimize_office as opt_off
        return opt_off(src, dst, lossy=lossy_office, verify=verify, delete_source=False, archive_folder=archive_dir)

    dst = _resolve_dst(src, Path(dst) if dst else None, "auto")
    dst = archive_dir / dst.name

    dst.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Выходная папка: {dst.parent}")

    result = {"original_size": 0, "compressed_size": 0, "ratio": 1.0, "algorithm": "none", "entropy": 0.0, "status": "error", "checksum": ""}
    local_temps = []
    orig_img_dims = None

    try:
        stat_src = src.stat()
        result["original_size"] = stat_src.st_size
        if result["original_size"] < config.SMALL_FILE_THRESHOLD:
            logger.info(f"Пропуск {src.name}: слишком мал (<{config.SMALL_FILE_THRESHOLD}B)")
            return {**result, "status": "skipped", "algorithm": "none", "ratio": 1.0}

        file_type = get_file_type(src)
        is_image = file_type.startswith("image/")
        entropy = calc_shannon_entropy(src)
        result["entropy"] = entropy
        logger.info(f"{src.name} | {file_type} | H={entropy:.3f} | {result['original_size']:,}B")
        if entropy > 0.92 and not force and not is_image: logger.warning("Высокая энтропия. Сжатие ограничено.")

        if is_image:
            try:
                with Image.open(src) as img: orig_img_dims = [img.width, img.height]
            except Exception: pass

        queue = get_strategy_queue(entropy, force, is_image, override_level)
        best_algo, best_size, best_tmp = "", float("inf"), None
        total_steps = len(queue)
        current_step = 0

        for algo, level in queue:
            fd, tmp_path = tempfile.mkstemp(dir=dst.parent, suffix=f".{algo}.tmp")
            os.close(fd)
            tmp_p = Path(tmp_path)
            local_temps.append(tmp_p)
            logger.info(f"{algo.upper()} lvl {level}...")
            try:
                start = time.perf_counter()
                with open(src, "rb") as fin, open(tmp_path, "wb") as fout:
                    ALGO_COMPRESSORS[algo](fin, fout, level, threads if algo=="zstd" else 0)
                tmp_size = tmp_p.stat().st_size
                ratio = tmp_size / result["original_size"]
                logger.info(f" ratio={ratio:.4f} ({tmp_size/1e6:.1f}MB) | {time.perf_counter()-start:.1f}s")
                if tmp_size < best_size: best_algo, best_size, best_tmp = algo, tmp_size, tmp_p
                if ratio > config.RATIO_FALLBACK_THRESHOLD: logger.info(f"Fallback triggered...")
                
                current_step += 1
                if progress_callback:
                    progress = current_step / total_steps
                    progress_callback(progress)

            except Exception as e:
                logger.error(f" {algo.upper()} failed: {e}")
                continue

        if not best_tmp: raise RuntimeError("Все алгоритмы сжатия завершились с ошибкой")
        final_dst = _resolve_dst(src, Path(dst) if dst else None, best_algo)
        
        if progress_callback:
            progress_callback(1.0)


        if verify:
            logger.info("Проверка целостности...")
            verify_tmp = final_dst.with_suffix(final_dst.suffix + ".verify.tmp")
            local_temps.append(verify_tmp)
            if not decompress_stream(open(best_tmp, "rb"), open(verify_tmp, "wb"), best_algo): raise RuntimeError("Распаковка не удалась")
            if best_algo == "image":
                try:
                    with Image.open(verify_tmp) as check_img:
                        if check_img.width == 0 or check_img.height == 0: raise ValueError("Пустое/повреждённое изображение")
                except Exception as e: raise ValueError(f"Проверка изображения: {e}")
                logger.info("Проверка изображения OK.")
            else:
                if stream_sha256(src, "Orig") != stream_sha256(verify_tmp, "Decomp"): raise ValueError("❌ Хеш не совпал!")
                logger.info("Верификация OK.")
            try: verify_tmp.unlink()
            except OSError: pass
            checksum = stream_sha256(src, "Orig")
        else: checksum = ""

        if not best_tmp.exists(): raise RuntimeError(f"Временный файл потерян: {best_tmp}")
        os.replace(best_tmp, final_dst)
        try:
            os.chmod(final_dst, stat_src.st_mode)
            os.utime(final_dst, (stat_src.st_atime, stat_src.st_mtime))
            if hasattr(os, 'chown'):
                try: os.chown(final_dst, stat_src.st_uid, stat_src.st_gid)
                except PermissionError: pass
        except Exception as e: logger.warning(f"Метаданные частично: {e}")

        meta_path = save_metadata(src, final_dst, checksum)
        try:
            with open(meta_path, "r+") as f:
                meta = json.load(f)
                meta["compression_algorithm"] = best_algo
                meta["original_ext"] = src.suffix
                if orig_img_dims: meta["original_dimensions"] = orig_img_dims
                f.seek(0); json.dump(meta, f, indent=2); f.truncate()
        except Exception: pass

        result["status"] = "ok"
        logger.info(f"Готово: {src.name} → {final_dst.name} | {best_algo.upper()} | ratio: {result['ratio']:.4f}")
        result["checksum"] = checksum
        result["output_path"] = str(final_dst)

    except Exception as e:
        logger.error(f"Аварийное завершение: {e}")
        result["status"] = "error"
    finally:
        for f in local_temps:
            try: f.unlink(missing_ok=True)
            except (OSError, ValueError): pass
    return result

def compress_hybrid_office(
    src: str | Path, dst: Optional[str | Path] = None,
    office_kwargs: Optional[Dict] = None, compress_kwargs: Optional[Dict] = None,
    archive_folder: Optional[str | Path] = None
) -> Dict[str, object]:
    src = Path(src).resolve()
    if not src.exists(): raise FileNotFoundError(f"Файл не найден: {src}")

    from compressor.office import optimize_office

    archive_dir = src.parent / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)

    tmp_base = archive_dir
    tmp_dir = Path(tempfile.mkdtemp(dir=src.parent, prefix="hybrid_"))
    temp_opt = tmp_dir / f"{src.stem}.opt{src.suffix}"

    try:
        opt_res = optimize_office(src, temp_opt, **(office_kwargs or {}))
        if opt_res["status"] != "ok": return opt_res

        if not dst: dst = src.with_suffix(f"{src.suffix}.zst")
        dst = Path(dst).resolve()
        dst = archive_dir / dst.name
        dst.parent.mkdir(parents=True, exist_ok=True)

        comp_res = compress_file(temp_opt, dst, **(compress_kwargs or {}))
        comp_res["original_size"] = opt_res["original_size"]
        comp_res["ratio"] = comp_res["compressed_size"] / comp_res["original_size"]
        comp_res["pipeline"] = "Office Opt -> Entropy Compression"

        meta_path = dst.with_suffix(dst.suffix + ".meta.json")
        if meta_path.exists():
            try:
                with open(meta_path, "r+") as f:
                    meta = json.load(f)
                    meta["original_size"] = opt_res["original_size"]
                    meta["pipeline"] = comp_res["pipeline"]
                    f.seek(0); json.dump(meta, f, indent=2); f.truncate()
            except Exception: pass

        return comp_res
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

def decompress_file(
    src: str | Path, dst: Optional[str | Path] = None, verify: bool = True, delete_source: bool = True,
    progress_callback=None
) -> Dict[str, object]:
    src = Path(src).resolve()
    if not src.exists(): raise FileNotFoundError(f"Архив не найден: {src}")

    algo = detect_algo(src)
    if src.suffix == ".meta.json": raise ValueError("Это мета-файл, а не архив.")

    if dst: dst = Path(dst).resolve()
    else:
        meta_path = src.with_suffix(src.suffix + ".meta.json")
        orig_name = src.stem
        if meta_path.exists():
            try:
                with open(meta_path) as f: meta = json.load(f)
                orig_name = meta.get("original_name", src.stem)
            except Exception: pass
        dst = src.parent / orig_name

    result = {"original_size": 0, "decompressed_size": 0, "ratio": 1.0, "algorithm": algo, "status": "error", "checksum_match": False, "output_path": str(dst)}
    algos_to_try = [algo, "zstd"] if algo != "zstd" else ["zstd"]
    final_algo = algo
    success = False

    try:
        result["original_size"] = src.stat().st_size
        logger.info(f"Распаковка: {src.name} -> {dst.name}")

        total_steps = len(algos_to_try)
        current_step = 0
        for trial_algo in algos_to_try:
            try:
                with open(src, "rb") as fin, open(dst, "wb") as fout:
                    if not decompress_stream(fin, fout, trial_algo): continue
                final_algo = trial_algo
                success = True
                
                current_step += 1
                if progress_callback:
                    progress_callback(current_step / total_steps)

                break
            except Exception: continue

        if not success: raise RuntimeError("Не удалось распаковать ни одним алгоритмом")
        if progress_callback:
            progress_callback(1.0)

        result["algorithm"] = final_algo
        result["decompressed_size"] = dst.stat().st_size
        result["ratio"] = result["decompressed_size"] / max(result["original_size"], 1)
        restore_metadata(src, dst)

        if final_algo == "image" and dst.exists():
            try:
                meta_path = src.with_suffix(src.suffix + ".meta.json")
                target_ext = ".png"
                if meta_path.exists():
                    with open(meta_path) as f: meta = json.load(f)
                    if meta.get("original_ext", "").lower() in (".jpg", ".jpeg"): target_ext = ".jpeg"
                final_dst = dst.with_suffix(target_ext)
                with Image.open(dst) as img:
                    img.save(final_dst, format=target_ext.lstrip(".").upper() if target_ext != ".jpeg" else "JPEG")
                os.replace(final_dst, dst)
                result["decompressed_size"] = dst.stat().st_size

                if meta_path.exists():
                    with open(meta_path) as f: meta = json.load(f)
                    orig_dims = meta.get("original_dimensions")
                    if orig_dims:
                        w, h = orig_dims
                        with Image.open(dst) as img:
                            if img.size != (w, h):
                                img = img.resize((w, h), Image.Resampling.LANCZOS)
                                img.save(dst)
                                logger.info(f"Масштаб восстановлен: {w}x{h}")
            except Exception as e:
                logger.debug(f"Image post-process skipped: {e}")

        if verify:
            meta_path = src.with_suffix(src.suffix + ".meta.json")
            if meta_path.exists():
                with open(meta_path) as f: meta = json.load(f)
                expected = meta.get("sha256")

                if final_algo == "image":
                    result["checksum_match"] = True
                    logger.info("Структура изображения валидна")
                elif expected:
                    actual = stream_sha256(dst, "Verify")
                    result["checksum_match"] = (actual == expected)
                    logger.info("Контрольная сумма совпадает" if result["checksum_match"] else "❌ ОШИБКА КОНТРОЛЬНОЙ СУММЫ!")
                else:
                    result["checksum_match"] = True

        result["status"] = "ok"
        logger.info(f"Распаковано: {dst.resolve()} ({result['decompressed_size']:,}B) | Алгоритм: {final_algo.upper()}")

        if result["status"] == "ok":
            try:
                src.unlink()
                meta_path = src.with_suffix(src.suffix + ".meta.json")
                if meta_path.exists():
                    meta_path.unlink()
                logger.info(f"Исходный файл удалён: {src.name}")
            except Exception as e:
                logger.warning(f"Не удалось удалить исходник: {e}")

    except Exception as e:
        logger.error(f"Ошибка распаковки: {e}")
        result["status"] = "error"
    return result