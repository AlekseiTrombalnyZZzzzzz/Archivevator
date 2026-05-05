#!/usr/bin/env python3
"""Точка входа. Добавляет корень проекта в sys.path для корректных абсолютных импортов."""
import sys
from pathlib import Path

# Гарантируем, что родительская директория (где лежит compressor/) доступна
sys.path.insert(0, str(Path(__file__).parent))

from compressor.cli import main

if __name__ == "__main__":
    main()
