from __future__ import annotations
import io, json, os, re, shutil, tempfile, zipfile, zlib
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from PIL import Image
import brotli
import zstandard as zstd
from compressor.utils import logger, stream_sha256, register_temp, save_metadata
from compressor import config

def _is_ooxml(filepath: Path) -> bool:
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            return '[Content_Types].xml' in z.namelist()
    except Exception:
        return False

def _optimize_image(img_data: bytes, ext: str, lossy: bool, aggressive: bool) -> bytes:
    try:
        img = Image.open(io.BytesIO(img_data))
        out = io.BytesIO()
        ext_lower = ext.lower()

        if aggressive:
            if img.size[0] > 3840 or img.size[1] > 3840:
                img.thumbnail((3840, 3840), Image.Resampling.LANCZOS)

        if ext_lower in ('.jpg', '.jpeg'):
            img.save(out, format='JPEG', quality=95, optimize=True, exif=None, progressive=True)
        elif ext_lower == '.png':
            img.save(out, format='WEBP', lossless=True, method=6, quality=100)
        elif ext_lower == '.webp':
            img.save(out, format='WEBP', lossless=True, method=6, quality=100, exact=True)
        elif ext_lower == '.bmp':
            img.save(out, format='PNG', optimize=True, compress_level=9)
        elif ext_lower == '.tiff':
            img.save(out, format='PNG', optimize=True, compress_level=9)
        else:
            img.save(out, format=img.format or 'PNG', optimize=True, compress_level=9)

        result = out.getvalue()
        return result if len(result) < len(img_data) else img_data
    except Exception as e:
        logger.debug(f"Image opt skipped: {e}")
        return img_data

def _clean_xml(xml_data: bytes) -> bytes:
    try:
        text = xml_data.decode('utf-8', errors='ignore')

        text = re.sub(r'\s*(?:w:rsid\w*|wp14:anchorId|wp14:editId|mc:Ignorable|w14:paraId|w14:textId)="[^"]*"', '', text)

        text = re.sub(r'<[^>]+:metadata[^>]*>.*?</[^>]+:metadata>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+:(?:core|extended|custom)Properties[^>]*>.*?</[^>]+:\1Properties>', '', text, flags=re.DOTALL)

        text = re.sub(r'<[^>]+:Digitalsignatures?[^>]*>.*?</[^>]+:Digitalsignatures?>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+:SignatureInfo[^>]*>.*?</[^>]+:SignatureInfo>', '', text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r'<[^>]+:cachedFormula[^>]*>.*?</[^>]+:cachedFormula>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'\s*sv:t="[^"]*"', '', text)

        text = re.sub(r'\s+xmlns:[a-z0-9]+="http://schemas\.openxmlformats\.org/(?:markupCompatibility|drawingml)/alternateContent"', '', text, flags=re.IGNORECASE)

        text = re.sub(r'>\s+<', '><', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)

        return text.encode('utf-8')
    except Exception as e:
        logger.debug(f"XML clean skipped: {e}")
        return xml_data


def _deep_clean_structure(tmp_dir: Path) -> Tuple[int, List[str]]:
    saved = 0
    removed = []

    remove_patterns = [
        'docProps/thumbnail.jpeg', 'docProps/thumbnail.png', 'docProps/thumbnail.emf',
        'docProps/icon.png', 'docProps/icon.ico',
        'word/printerSettings/', 'ppt/printerSettings/', 'xl/printerSettings/',
        'word/printSettings/', 'ppt/printSettings/', 'xl/printSettings/',
        '**/embeddings/tmp*', '**/media/tmp*', '**/*.tmp',
        'docProps/custom.xml', 'docProps/app2.xml',
        '**/_rels/*.bak', '**/*.bak', 'word/backup/', 'xl/backup/',
        'ppt/handoutMasters/', 'ppt/slideMasters/_rels/',
        'ppt/notesSlides/', 'ppt/notesMaster/',
        'xl/externalLinks/', 'xl/externalLinkSources/',
        'word/revisionHeaders/', 'word/revisionLog/',
    ]

    for pattern in remove_patterns:
        if pattern.endswith('/'):
            targets = list(tmp_dir.glob(pattern + '*')) + ([tmp_dir / pattern.rstrip('/')] if '*' not in pattern else [])
            for target in targets:
                if target.is_dir():
                    size = sum(f.stat().st_size for f in target.rglob('*') if f.is_file())
                    if size > 0:
                        saved += size
                        removed.append(f"{target.relative_to(tmp_dir)} ({size}B)")
                        shutil.rmtree(target, ignore_errors=True)
        else:
            for target in tmp_dir.glob(pattern):
                if target.is_file():
                    size = target.stat().st_size
                    saved += size
                    removed.append(f"{target.relative_to(tmp_dir)} ({size}B)")
                    target.unlink(missing_ok=True)

    return saved, removed

def optimize_office(
    src: str | Path,
    dst: Optional[str | Path] = None,
    lossy: bool = False,
    aggressive: bool = False,
    verify: bool = True,
    delete_source: bool = False,
    ultra_compress: bool = True
) -> Dict[str, object]:
    src = Path(src).resolve()
    if not src.exists(): raise FileNotFoundError(f"Файл не найден: {src}")
    if not _is_ooxml(src): raise ValueError(f"{src.name} не является валидным OOXML документом.")
        
    archive_dir = src.parent / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)

    dst = Path(dst).resolve() if dst else src.with_suffix(f".opt{src.suffix}")

    dst = archive_dir / dst.name
    
    dst.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "original_size": 0, "compressed_size": 0, "ratio": 1.0,
        "algorithm": "office_optimizer_v2", "entropy": 0.0,
        "status": "error", "checksum": "", "output_path": str(dst),
        "breakdown": {"structure": 0, "xml": 0, "media": 0, "removed_items": [], "zstd_extra": 0}
    }
    local_temps = []

    tmp_dir = Path(tempfile.mkdtemp(dir=dst.parent, prefix="office_opt_"))
    local_temps.append(tmp_dir)
    register_temp(tmp_dir)

    try:
        result["original_size"] = src.stat().st_size
        logger.info(f"📄 Оптимизация Office: {src.name} ({result['original_size']:,}B)")

        with zipfile.ZipFile(src, 'r') as z:
            z.extractall(tmp_dir)

        struct_saved, removed_items = _deep_clean_structure(tmp_dir)
        result["breakdown"]["structure"] = struct_saved
        result["breakdown"]["removed_items"] = removed_items[:20]
        logger.info(f"  🗑️ Удалено элементов: {len(removed_items)}")

        media_dirs = [d for d in tmp_dir.rglob('*') if d.is_dir() and d.name == 'media']
        for media_dir in media_dirs:
            for img_path in media_dir.iterdir():
                if img_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'):
                    orig_data = img_path.read_bytes()
                    opt_data = _optimize_image(orig_data, img_path.suffix, lossy, aggressive)
                    if len(opt_data) < len(orig_data):
                        img_path.write_bytes(opt_data)
                        result["breakdown"]["media"] += len(orig_data) - len(opt_data)
        logger.info(f"  🖼️ Оптимизация медиа: -{result['breakdown']['media']/1024:.1f}KB")

        xml_files = list(tmp_dir.rglob('*.xml'))
        for xml_path in xml_files:
            try:
                orig = xml_path.read_bytes()
                cleaned = _clean_xml(orig)
                if len(cleaned) < len(orig):
                    xml_path.write_bytes(cleaned)
                    result["breakdown"]["xml"] += len(orig) - len(cleaned)
            except Exception: continue
        logger.info(f"  📝 Очистка XML: -{result['breakdown']['xml']/1024:.1f}KB")

        zip_tmp = tmp_dir / "optimized.zip"
        with zipfile.ZipFile(zip_tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z_out:
            text_files = []
            binary_files = []
            for root, _, files in os.walk(tmp_dir):
                for fname in files:
                    fpath = Path(root) / fname
                    if fpath.name == "optimized.zip": continue
                    rel = fpath.relative_to(tmp_dir)
                    if fpath.suffix.lower() in ('.xml', '.rels', '.txt', '.json', '.vml'):
                        text_files.append((fpath, rel))
                    elif fpath.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.avi', '.gif'):
                        binary_files.append((fpath, rel, zipfile.ZIP_STORED))
                    else:
                        binary_files.append((fpath, rel, zipfile.ZIP_DEFLATED))

            for fpath, rel in sorted(text_files, key=lambda x: str(x[1])):
                z_out.write(fpath, rel)
            for fpath, rel, ctype in sorted(binary_files, key=lambda x: str(x[1])):
                z_out.write(fpath, rel, compress_type=ctype)

        if ultra_compress:
            logger.info("  🚀 Применяем Zstandard компрессию поверх ZIP...")
            final_dst = dst.with_suffix(dst.suffix + ".zst")
            with open(zip_tmp, 'rb') as fin, open(final_dst, 'wb') as fout:
                cctx = zstd.ZstdCompressor(level=19, threads=-1) 
                cctx.copy_stream(fin, fout)
            result["breakdown"]["zstd_extra"] = zip_tmp.stat().st_size - final_dst.stat().st_size
            result["output_path"] = str(final_dst)
            logger.info(f"  📦 Zstd дополнительно: -{result['breakdown']['zstd_extra']/1024:.1f}KB")
        else:
            final_dst = dst
            shutil.copy2(zip_tmp, final_dst)

        result["compressed_size"] = final_dst.stat().st_size
        result["ratio"] = result["compressed_size"] / result["original_size"]

        total_saved = sum(v for k, v in result["breakdown"].items() if isinstance(v, (int, float)))
        logger.info(f"  📊 Breakdown: Struct={result['breakdown']['structure']/1024:.1f}KB | XML={result['breakdown']['xml']/1024:.1f}KB | Media={result['breakdown']['media']/1024:.1f}KB | Zstd={result['breakdown']['zstd_extra']/1024:.1f}KB")
        logger.info(f"  💾 Всего сэкономлено: {total_saved/1024:.1f}KB")
        logger.info(f"  📦 Итоговый ratio: {result['ratio']:.4f} ({(1-result['ratio'])*100:.1f}% сжатие)")

        if verify:
            logger.info("✅ Проверка целостности...")
            result["checksum"] = stream_sha256(final_dst, "Optimized")
            if ultra_compress:
                with open(final_dst, 'rb') as fin:
                    decompressed = io.BytesIO()
                    dctx = zstd.ZstdDecompressor()
                    dctx.copy_stream(fin, decompressed)
                    decompressed.seek(0)
                    with zipfile.ZipFile(decompressed, 'r') as z_check:
                        namelist = z_check.namelist()
                        required_files = ['[Content_Types].xml', '_rels/.rels']
                        for req_file in required_files:
                            if req_file not in namelist:
                                logger.warning(f"⚠️ Отсутствует элемент: {req_file}")
                        has_content = any('document.xml' in f or 'workbook.xml' in f or 'presentation.xml' in f for f in namelist)
                        if not has_content:
                            raise ValueError("Архив повреждён после оптимизации! Отсутствует основной контент.")
            else:
                with zipfile.ZipFile(final_dst, 'r') as z:
                    namelist = z.namelist()
                    required_files = ['[Content_Types].xml', '_rels/.rels']
                    for req_file in required_files:
                        if req_file not in namelist:
                            logger.warning(f"⚠️ Отсутствует элемент: {req_file}")
                    has_content = any('document.xml' in f or 'workbook.xml' in f or 'presentation.xml' in f for f in namelist)
                    if not has_content:
                        raise ValueError("Архив повреждён после оптимизации! Отсутствует основной контент.")
            logger.info("🛡️ OOXML структура валидна.")

        save_metadata(src, final_dst, result["checksum"])
        result["status"] = "ok"
        logger.info(f"🎉 Готово: {src.name} → {final_dst.name} | ratio: {result['ratio']:.4f} ({(1-result['ratio'])*100:.1f}% экономии)")

        if delete_source:
            try: src.unlink(); logger.info(f"🗑️ Исходник удалён: {src.name}")
            except Exception as e: logger.warning(f"⚠️ Удаление исходника: {e}")

    except Exception as e:
        logger.error(f"💥 Ошибка оптимизации Office: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        result["status"] = "error"
    finally:
        for f in local_temps:
            try:
                if f.is_dir(): shutil.rmtree(f, ignore_errors=True)
                else: f.unlink(missing_ok=True)
            except Exception: pass
    return result