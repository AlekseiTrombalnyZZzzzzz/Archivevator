"""CLI-интерфейс: сжатие и распаковка."""
from __future__ import annotations
import argparse, sys, os
from pathlib import Path
from compressor.core import compress_file, decompress_file, compress_hybrid_office
from compressor.utils import logger, find_file_on_disk

def prompt_for_file(action: str = "сжатия") -> Path:
    print(f"\n📁 Введите ИМЯ файла для {action} (поиск по диску) или полный путь. 'exit' для выхода.")
    while True:
        try:
            raw = input("👉 Имя/Путь: ").strip().strip('"').strip("'")
            if raw.lower() in ("exit", "quit", "q"): sys.exit(0)
            if not raw: continue
            path = find_file_on_disk(raw)
            if path and os.access(path, os.R_OK): return path
            elif path: logger.warning(f"❌ Нет прав на чтение: {path}")
            else: logger.warning("💡 Файл не найден.")
        except (EOFError, KeyboardInterrupt): sys.exit(0)

def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Entropy-Driven File Compressor")
    parser.add_argument("-i", "--input", help="Имя/путь файла (опционально)")
    parser.add_argument("-o", "--output", help="Путь сохранения/распаковки (опционально)")
    parser.add_argument("-d", "--decompress", action="store_true", help="CLI-режим распаковки")
    parser.add_argument("--office", action="store_true", help="Оптимизировать .docx/.xlsx/.pptx")
    parser.add_argument("--hybrid", action="store_true", help="Гибридный режим: Office Opt + Entropy Compression")
    parser.add_argument("--lossy", action="store_true", help="Агрессивное сжатие изображений в Office")
    parser.add_argument("--aggressive", action="store_true", help="Уменьшить изображения в Office до 1200px")
    parser.add_argument("--rm", "--delete-source", dest="delete_source", action="store_true", help="Удалить исходный файл после операции")
    parser.add_argument("--level", type=int, choices=range(0, 23), help="Уровень сжатия (0-22)")
    parser.add_argument("--verify", action="store_true", default=True)
    parser.add_argument("--no-verify", action="store_false", dest="verify")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--threads", type=int, default=0)
    args = parser.parse_args()

    if not args.input:
        print("\n🔧 Выберите режим:")
        print("1. Сжатие / Оптимизация Office")
        print("2. Распаковка")
        mode = input("👉 Введите 1 или 2: ").strip()

        if mode == "1":
            src_path = prompt_for_file("обработки")
            dst_path = Path(args.output).resolve() if args.output else None
            is_office = src_path.suffix.lower() in ('.docx', '.xlsx', '.pptx')
            use_office = args.office or (is_office and not args.office)

            if use_office and args.hybrid:
                print(f"\n🔗 Гибридный режим: {src_path.name}")
                res = compress_hybrid_office(
                    src_path, dst_path,
                    office_kwargs={"lossy": args.lossy, "aggressive": args.aggressive, "verify": args.verify},
                    compress_kwargs={"verify": args.verify, "force": args.force, "threads": args.threads, "override_level": args.level}
                )
            elif use_office:
                from compressor.office import optimize_office
                print(f"\n📄 Office Optimizer: {src_path.name}")
                res = optimize_office(
                    src_path, dst_path, lossy=args.lossy, aggressive=args.aggressive,
                    verify=args.verify, delete_source=args.delete_source
                )
            else:
                print(f"\n🚀 Сжатие: {src_path.name}")
                res = compress_file(
                    src_path, dst_path, verify=args.verify, force=args.force,
                    threads=args.threads, override_level=args.level
                )
        elif mode == "2":
            src_path = prompt_for_file("распаковки")
            dst_path = Path(args.output).resolve() if args.output else None
            rm = input("🗑️ Удалить исходный файл после распаковки? (y/n): ").strip().lower() == 'y'
            print(f"\n📦 Распаковка: {src_path.name}")
            res = decompress_file(src_path, dst_path, verify=args.verify, delete_source=rm or args.delete_source)
        else:
            print("❌ Неверный выбор. Завершение.")
            sys.exit(1)
    else:
        src_path = Path(args.input).resolve()
        dst_path = Path(args.output).resolve() if args.output else None
        if args.decompress:
            print(f"\n📦 Распаковка: {src_path.name}")
            res = decompress_file(src_path, dst_path, verify=args.verify, delete_source=args.delete_source)
        else:
            is_office = src_path.suffix.lower() in ('.docx', '.xlsx', '.pptx')
            use_office = args.office or (is_office and not args.office)
            
            if use_office and args.hybrid:
                print(f"\n🔗 Гибридный режим: {src_path.name}")
                res = compress_hybrid_office(
                    src_path, dst_path,
                    office_kwargs={"lossy": args.lossy, "aggressive": args.aggressive, "verify": args.verify},
                    compress_kwargs={"verify": args.verify, "force": args.force, "threads": args.threads, "override_level": args.level}
                )
            elif use_office:
                from compressor.office import optimize_office
                print(f"\n📄 Office Optimizer: {src_path.name}")
                res = optimize_office(
                    src_path, dst_path, lossy=args.lossy, aggressive=args.aggressive,
                    verify=args.verify, delete_source=args.delete_source
                )
            else:
                print(f"\n🚀 Сжатие: {src_path.name}")
                res = compress_file(
                    src_path, dst_path, verify=args.verify, force=args.force,
                    threads=args.threads, override_level=args.level
                )

    print(f"\n📊 {res}")
    sys.exit(0 if res["status"] == "ok" else 1)