"""Движки сжатия и распаковки."""
from __future__ import annotations
import io
from pathlib import Path
from typing import IO

import brotli
import lzma
import zstandard as zstd
from PIL import Image
from compressor import config
from compressor.utils import logger

def compress_zstd(inp: IO[bytes], out: IO[bytes], level: int, threads: int = 0) -> None:
    cctx = zstd.ZstdCompressor(level=level, threads=threads)
    with cctx.stream_writer(out, closefd=False) as w:
        while chunk := inp.read(config.CHUNK_SIZE): w.write(chunk)

def compress_brotli(inp: IO[bytes], out: IO[bytes], level: int, threads: int = 0) -> None:
    comp = brotli.Compressor(quality=level)
    while chunk := inp.read(config.CHUNK_SIZE):
        out.write(comp.process(chunk))
    out.write(comp.finish())

def compress_lzma(inp: IO[bytes], out: IO[bytes], level: int, threads: int = 0) -> None:
    comp = lzma.LZMACompressor(preset=level)
    while chunk := inp.read(config.CHUNK_SIZE): out.write(comp.compress(chunk))
    out.write(comp.flush())

def compress_image(inp: IO[bytes], out: IO[bytes], level: int, threads: int = 0) -> None:
    """Автоматическое уменьшение изображения в 2 раза + оптимизация формата."""
    data = inp.read()
    size = len(data)
    if size > config.IMAGE_MAX_RAM_MB * 1024 * 1024:
        out.write(data)
        return
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format or "PNG"

        # 🔑 Уменьшаем ширину и высоту ровно в 2 раза
        new_w = max(1, img.width // 2)
        new_h = max(1, img.height // 2)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        out_bytes = io.BytesIO()
        if fmt == "JPEG":
            img.save(out_bytes, format="JPEG", quality=92, optimize=True, progressive=True)
        elif fmt == "WEBP":
            method = min(6, max(0, level // 3))
            img.save(out_bytes, format="WEBP", lossless=True, method=method, quality=100)
        else:
            img.save(out_bytes, format="WEBP", lossless=True, method=6, quality=100)

        opt_data = out_bytes.getvalue()
        out.write(opt_data if len(opt_data) < size else data)
    except Exception as e:
        logger.warning(f"⚠️ Image optimization failed: {e}. Fallback to raw copy.")
        out.write(data)

ALGO_COMPRESSORS = {"zstd": compress_zstd, "brotli": compress_brotli, "lzma": compress_lzma, "image": compress_image}

def decompress_stream(inp: IO[bytes], out: IO[bytes], algo: str) -> bool:
    try:
        if algo == "zstd":
            with zstd.ZstdDecompressor().stream_reader(inp, read_across_frames=True) as r:
                while chunk := r.read(config.CHUNK_SIZE): out.write(chunk)
        elif algo == "lzma":
            with lzma.LZMAFile(inp) as r:
                while chunk := r.read(config.CHUNK_SIZE): out.write(chunk)
        elif algo == "brotli":
            dec = brotli.Decompressor()
            while chunk := inp.read(config.CHUNK_SIZE):
                out.write(dec.process(chunk))
        elif algo == "image":
            out.write(inp.read())
        return True
    except Exception as e:
        logger.error(f"Decompression failed: {e}")
        return False