import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import os
import sys

from compressor.core import compress_file, decompress_file


class ArchiwatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Archiwator - Компрессор файлов")
        self.root.geometry("700x500")
        self.root.resizable(True, True)

        self.file_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status_var = tk.StringVar(value="Готов к работе")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._setup_ui()

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        title_label = ttk.Label(main_frame, text="🗜️ Archiwator", font=("Helvetica", 20, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        drop_frame = ttk.LabelFrame(main_frame, text="Перетащите файл сюда или выберите вручную", padding="20")
        drop_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        drop_frame.columnconfigure(0, weight=1)

        self.file_entry = ttk.Entry(drop_frame, textvariable=self.file_path, width=60)
        self.file_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))

        browse_btn = ttk.Button(drop_frame, text="Обзор...", command=self._browse_file)
        browse_btn.grid(row=0, column=1)

        self._setup_drag_drop(drop_frame)

        settings_frame = ttk.LabelFrame(main_frame, text="Настройки", padding="10")
        settings_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)

        self.verify_var = tk.BooleanVar(value=True)
        verify_check = ttk.Checkbutton(settings_frame, text="Проверять целостность", variable=self.verify_var)
        verify_check.grid(row=0, column=0, sticky=tk.W, padx=(0, 20))

        self.force_var = tk.BooleanVar(value=False)
        force_check = ttk.Checkbutton(settings_frame, text="Принудительное сжатие", variable=self.force_var)
        force_check.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))

        self.office_var = tk.BooleanVar(value=True)
        office_check = ttk.Checkbutton(settings_frame, text="Оптимизировать Office", variable=self.office_var)
        office_check.grid(row=1, column=0, sticky=tk.W, padx=(0, 20), pady=(5, 0))

        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=3, column=0, columnspan=3, pady=(0, 10))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        compress_btn = ttk.Button(action_frame, text="📦 Сжать", command=self._compress)
        compress_btn.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))

        decompress_btn = ttk.Button(action_frame, text="📂 Распаковать", command=self._decompress)
        decompress_btn.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0))

        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, mode='determinate')
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground="gray")
        status_label.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E))

        result_frame = ttk.LabelFrame(main_frame, text="Результат", padding="10")
        result_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        result_frame.columnconfigure(1, weight=1)
        result_frame.rowconfigure(0, weight=1)

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

        open_folder_btn = ttk.Button(result_frame, text="📁 Открыть папку результата", command=self._open_result_folder)
        open_folder_btn.grid(row=5, column=0, columnspan=2, pady=(10, 0))

        self.result_path = None

    def _setup_drag_drop(self, frame):
        self._setup_native_dnd(frame)
        hint_label = ttk.Label(frame, text="(перетащите файл мышью)", foreground="gray", font=("Helvetica", 9))
        hint_label.grid(row=1, column=0, columnspan=2, pady=(5, 0))

    def _setup_native_dnd(self, frame):
        try:
            frame.tk.eval('''
                package require tkdnd 2.0
                tkdnd::drop_target register %s {text/uri-list}
            ''' % frame)

            frame.bind('<<Drop>>', self._on_drop)
        except (tk.TclError, AttributeError):
            try:
                frame.drop_target_register(tk.DND_FILES)
                frame.bind('<Drop>', self._on_drop)
            except (AttributeError, TypeError, tk.TclError):
                pass

    def _on_drop(self, event):
        try:
            file_path = None

            if hasattr(event, 'data'):
                file_path = event.data
            elif hasattr(event, 'string'):
                file_path = event.string

            if not file_path:
                return

            if file_path.startswith('{') and file_path.endswith('}'):
                file_path = file_path[1:-1]
            elif file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]

            if file_path.startswith('file://'):
                from urllib.parse import unquote
                file_path = unquote(file_path[7:])  
                if file_path.startswith('/') and len(file_path) > 2 and file_path[2] == ':':
                    file_path = file_path[1:]

            file_path = file_path.strip()

            if Path(file_path).exists():
                self.file_path.set(file_path)
                self.status_var.set(f"Файл выбран: {Path(file_path).name}")
            else:
                messagebox.showwarning("Предупреждение", f"Файл не найден: {file_path}")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать перетаскивание: {e}")

    def _browse_file(self):
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
        file_path = self.file_path.get()
        if not file_path or not Path(file_path).exists():
            messagebox.showerror("Ошибка", "Пожалуйста, выберите существующий файл")
            return

        thread = threading.Thread(target=self._run_compress, args=(file_path,))
        thread.daemon = True
        thread.start()

    def _run_compress(self, file_path):
        try:
            self.status_var.set("Сжатие...")
            self.progress_var.set(0.0)

            src = Path(file_path)
            optimize_office = self.office_var.get() and src.suffix.lower() in ('.docx', '.xlsx', '.pptx')

            def update_progress(progress):
                self.root.after(0, lambda: self.progress_var.set(progress * 100))

            result = compress_file(
                src=src,
                dst=None,
                verify=self.verify_var.get(),
                force=self.force_var.get(),
                optimize_office=optimize_office,
                progress_callback=update_progress
            )

            self.root.after(0, self._update_result, result)
            self.root.after(0, lambda: self.status_var.set("Сжатие завершено"))
            self.root.after(0, lambda: self.progress_var.set(0))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка сжатия", str(e)))
            self.root.after(0, lambda: self.status_var.set("Ошибка при сжатии"))
            self.root.after(0, lambda: self.progress_var.set(0.0))

    def _decompress(self):
        file_path = self.file_path.get()
        if not file_path or not Path(file_path).exists():
            messagebox.showerror("Ошибка", "Пожалуйста, выберите существующий файл")
            return

        thread = threading.Thread(target=self._run_decompress, args=(file_path,))
        thread.daemon = True
        thread.start()

    def _run_decompress(self, file_path):
        try:
            self.status_var.set("Распаковка...")
            self.progress_var.set(0.0)

            def update_progress(progress):
                self.root.after(0, lambda: self.progress_var.set(progress * 100))

            result = decompress_file(
                src=Path(file_path),
                dst=None,
                verify=self.verify_var.get(),
                delete_source=True,
                progress_callback=update_progress
            )

            self.root.after(0, self._update_result, result)
            self.root.after(0, lambda: self.status_var.set("Распаковка завершена"))
            self.root.after(0, lambda: self.progress_var.set(1.0))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка распаковки", str(e)))
            self.root.after(0, lambda: self.status_var.set("Ошибка при распаковке"))
            self.root.after(0, lambda: self.progress_var.set(0.0))

    def _update_result(self, result):
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
        if self.result_path:
            path = Path(self.result_path)
            if path.exists():
                os.startfile(str(path.parent))
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