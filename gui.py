"""
GUI интерфейс для Archiwator на базе Tkinter
Позволяет сжимать и распаковывать файлы через графический интерфейс.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import os

from compressor.core import compress_file, decompress_file


class ArchiwatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Archiwator - Компрессор файлов")
        self.root.geometry("700x500")
        self.root.resizable(True, True)

        # Переменные
        self.file_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status_var = tk.StringVar(value="Готов к работе")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._setup_ui()

    def _setup_ui(self):
        """Создание пользовательского интерфейса"""
        # Основной фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Настройка растягивания
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Заголовок
        title_label = ttk.Label(main_frame, text="🗜️ Archiwator", font=("Helvetica", 20, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # Фрейм для перетаскивания файла
        drop_frame = ttk.LabelFrame(main_frame, text="Перетащите файл сюда или выберите вручную", padding="20")
        drop_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        drop_frame.columnconfigure(0, weight=1)

        # Поле для отображения выбранного файла
        self.file_entry = ttk.Entry(drop_frame, textvariable=self.file_path, width=60)
        self.file_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))

        # Кнопка выбора файла
        browse_btn = ttk.Button(drop_frame, text="Обзор...", command=self._browse_file)
        browse_btn.grid(row=0, column=1)

        # Настройка drag & drop
        self._setup_drag_drop(drop_frame)

        # Фрейм для настроек
        settings_frame = ttk.LabelFrame(main_frame, text="Настройки", padding="10")
        settings_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)

        # Опции
        self.verify_var = tk.BooleanVar(value=True)
        verify_check = ttk.Checkbutton(settings_frame, text="Проверять целостность", variable=self.verify_var)
        verify_check.grid(row=0, column=0, sticky=tk.W, padx=(0, 20))

        self.force_var = tk.BooleanVar(value=False)
        force_check = ttk.Checkbutton(settings_frame, text="Принудительное сжатие", variable=self.force_var)
        force_check.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))

        self.office_var = tk.BooleanVar(value=True)
        office_check = ttk.Checkbutton(settings_frame, text="Оптимизировать Office", variable=self.office_var)
        office_check.grid(row=1, column=0, sticky=tk.W, padx=(0, 20), pady=(5, 0))

        # Фрейм для кнопок действий
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=3, column=0, columnspan=3, pady=(0, 10))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        # Кнопка сжать
        compress_btn = ttk.Button(action_frame, text="📦 Сжать", command=self._compress)
        compress_btn.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))

        # Кнопка распаковать
        decompress_btn = ttk.Button(action_frame, text="📂 Распаковать", command=self._decompress)
        decompress_btn.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0))

        # Прогресс бар
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, mode='determinate')
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # Статус
        status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground="gray")
        status_label.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E))

        # Фрейм для результатов
        result_frame = ttk.LabelFrame(main_frame, text="Результат", padding="10")
        result_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        result_frame.columnconfigure(1, weight=1)
        result_frame.rowconfigure(0, weight=1)

        # Метки результатов
        ttk.Label(result_frame, text="Исходный размер:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.orig_size_label = ttk.Label(result_frame, text="-")
        self.orig_size_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        ttk.Label(result_frame, text="Конечный размер:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.final_size_label = ttk.Label(result_frame, text="-")
        self.final_size_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))

        ttk.Label(result_frame, text="Коэффициент сжатия:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.ratio_label = ttk.Label(result_frame, text="-")
        self.ratio_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0))

        ttk.Label(result_frame, text="Алгоритм:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.algo_label = ttk.Label(result_frame, text="-")
        self.algo_label.grid(row=3, column=1, sticky=tk.W, padx=(10, 0))

        ttk.Label(result_frame, text="Статус:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.status_result_label = ttk.Label(result_frame, text="-")
        self.status_result_label.grid(row=4, column=1, sticky=tk.W, padx=(10, 0))

        # Кнопка открыть папку
        open_folder_btn = ttk.Button(result_frame, text="📁 Открыть папку результата", command=self._open_result_folder)
        open_folder_btn.grid(row=5, column=0, columnspan=2, pady=(10, 0))

        self.result_path = None

    def _setup_drag_drop(self, frame):
        """Настройка drag & drop для файла"""
        # Используем нативную реализацию через Tcl/Tk команды
        self._setup_native_dnd(frame)

        # Добавляем визуальную подсказку
        hint_label = ttk.Label(frame, text="(перетащите файл мышью)", foreground="gray", font=("Helvetica", 9))
        hint_label.grid(row=1, column=0, columnspan=2, pady=(5, 0))

    def _setup_native_dnd(self, frame):
        """Нативная настройка Drag & Drop через Tcl/Tk"""
        try:
            # Регистрируем фрейм как цель для drop файлов
            # Это работает на Windows, Linux и Mac с Tk 8.6+
            frame.tk.eval('''
                package require tkdnd 2.0
                tkdnd::drop_target register %s {text/uri-list}
            ''' % frame)

            # Bind на событие Drop
            frame.bind('<<Drop>>', self._on_drop)
        except (tk.TclError, AttributeError):
            # Если tkdnd не установлен, пробуем альтернативный метод для Windows
            try:
                # Для Windows без tkdnd используем специфичные события
                frame.drop_target_register(tk.DND_FILES)
                frame.bind('<Drop>', self._on_drop)
            except (AttributeError, TypeError, tk.TclError):
                # DnD не поддерживается - просто игнорируем
                pass

    def _on_drop(self, event):
        """Обработчик события перетаскивания файла"""
        try:
            # Получаем путь к файлу из события
            # Формат зависит от ОС и типа события
            file_path = None

            # Проверяем разные атрибуты события
            if hasattr(event, 'data'):
                file_path = event.data
            elif hasattr(event, 'string'):
                file_path = event.string

            if not file_path:
                return

            # Обработка разных форматов путей
            # Windows: {C:\path\to\file} или C:\path\to\file
            # Linux/Mac: file:///path/to/file

            # Убираем фигурные скобки если есть
            if file_path.startswith('{') and file_path.endswith('}'):
                file_path = file_path[1:-1]
            elif file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]

            # Обрабатываем URI формат
            if file_path.startswith('file://'):
                from urllib.parse import unquote
                file_path = unquote(file_path[7:])  # убираем file://
                # Убираем ведущий слэш для Windows путей типа /C:/...
                if file_path.startswith('/') and len(file_path) > 2 and file_path[2] == ':':
                    file_path = file_path[1:]

            # Очищаем от лишних символов (иногда бывают \r\n)
            file_path = file_path.strip()

            # Проверяем что файл существует
            if Path(file_path).exists():
                self.file_path.set(file_path)
                self.status_var.set(f"Файл выбран: {Path(file_path).name}")
            else:
                messagebox.showwarning("Предупреждение", f"Файл не найден: {file_path}")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать перетаскивание: {e}")

    def _browse_file(self):
        """Открытие диалога выбора файла"""
        filename = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=[
                ("Все файлы", "*.*"),
                ("Office документы", "*.docx *.xlsx *.pptx"),
                ("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("Архивы", "*.zst *.br *.xz"),
            ]
        )
        if filename:
            self.file_path.set(filename)
            self.status_var.set(f"Файл выбран: {Path(filename).name}")

    def _compress(self):
        """Запуск процесса сжатия"""
        file_path = self.file_path.get()
        if not file_path or not Path(file_path).exists():
            messagebox.showerror("Ошибка", "Пожалуйста, выберите существующий файл")
            return

        # Запускаем в отдельном потоке чтобы не блокировать GUI
        thread = threading.Thread(target=self._run_compress, args=(file_path,))
        thread.daemon = True
        thread.start()

    def _run_compress(self, file_path):
        """Выполнение сжатия в фоне"""
        try:
            self.status_var.set("Сжатие...")
            self.progress_var.set(0.5)  # Индикатор процесса

            src = Path(file_path)
            optimize_office = self.office_var.get() and src.suffix.lower() in ('.docx', '.xlsx', '.pptx')

            result = compress_file(
                src=src,
                dst=None,
                verify=self.verify_var.get(),
                force=self.force_var.get(),
                optimize_office=optimize_office
            )

            self.root.after(0, self._update_result, result)
            self.root.after(0, lambda: self.status_var.set("Сжатие завершено"))
            self.root.after(0, lambda: self.progress_var.set(1.0))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка сжатия", str(e)))
            self.root.after(0, lambda: self.status_var.set("Ошибка при сжатии"))
            self.root.after(0, lambda: self.progress_var.set(0.0))

    def _decompress(self):
        """Запуск процесса распаковки"""
        file_path = self.file_path.get()
        if not file_path or not Path(file_path).exists():
            messagebox.showerror("Ошибка", "Пожалуйста, выберите существующий файл")
            return

        # Запускаем в отдельном потоке
        thread = threading.Thread(target=self._run_decompress, args=(file_path,))
        thread.daemon = True
        thread.start()

    def _run_decompress(self, file_path):
        """Выполнение распаковки в фоне"""
        try:
            self.status_var.set("Распаковка...")
            self.progress_var.set(0.5)

            result = decompress_file(
                src=Path(file_path),
                dst=None,
                verify=self.verify_var.get(),
                delete_source=True  # Всегда удаляем сжатый файл
            )

            self.root.after(0, self._update_result, result)
            self.root.after(0, lambda: self.status_var.set("Распаковка завершена"))
            self.root.after(0, lambda: self.progress_var.set(1.0))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка распаковки", str(e)))
            self.root.after(0, lambda: self.status_var.set("Ошибка при распаковке"))
            self.root.after(0, lambda: self.progress_var.set(0.0))

    def _update_result(self, result):
        """Обновление интерфейса с результатами"""
        if result.get("status") == "ok":
            orig_size = result.get("original_size", 0)
            final_size = result.get("compressed_size") or result.get("decompressed_size", 0)
            ratio = result.get("ratio", 0)
            algo = result.get("algorithm", "unknown")

            self.orig_size_label.config(text=f"{orig_size:,} байт")
            self.final_size_label.config(text=f"{final_size:,} байт")
            self.ratio_label.config(text=f"{ratio:.2%}" if ratio < 1 else f"{ratio:.2f}x")
            self.algo_label.config(text=algo.upper())
            self.status_result_label.config(text="✅ Успешно", foreground="green")

            self.result_path = result.get("output_path")
        else:
            self.status_result_label.config(text="❌ Ошибка", foreground="red")

    def _open_result_folder(self):
        """Открытие папки с результатом"""
        if self.result_path:
            path = Path(self.result_path)
            if path.exists():
                os.startfile(str(path.parent))  # Windows
            else:
                messagebox.showwarning("Предупреждение", "Папка результата не найдена")
        else:
            messagebox.showinfo("Информация", "Результат ещё не получен")


def main():
    root = tk.Tk()
    app = ArchiwatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()