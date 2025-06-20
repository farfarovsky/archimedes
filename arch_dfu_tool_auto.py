import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import subprocess
import threading
import sys
import asyncio
from bleak import BleakScanner
import serial.tools.list_ports
import time

class DFUGUI:
    def __init__(self, master):
        self.master = master
        master.title("Archimedes DFU Tool")
        master.geometry("720x600")

        self.running = False
        self.auto_thread = None
        self.last_device_address = None
        self.com_port = None
        self.dongle_check_interval = 2  # секунд

        # --- UI ---
        tk.Label(master, text="Файл прошивки (.zip):").pack()
        self.zip_path = tk.Entry(master, width=60)
        self.zip_path.pack()
        tk.Button(master, text="Выбрать файл", command=self.browse_zip).pack()

        tk.Label(master, text="Имя устройства (BLE):").pack()
        self.device_name = tk.Entry(master, width=60)
        self.device_name.insert(0, "archimedes bootloader")
        self.device_name.pack()

        tk.Label(master, text="Задержка сканирования (сек):").pack()
        self.delay = tk.Entry(master, width=10)
        self.delay.insert(0, "1")
        self.delay.pack()

        self.dongle_label = tk.Label(master, text="🔌 Поиск nRF Dongle...", fg="gray")
        self.dongle_label.pack(pady=5)

        self.start_btn = tk.Button(master, text="▶ Старт", command=self.toggle)
        self.start_btn.pack(pady=10)

        self.status_label = tk.Label(master, text="⏸ Ожидание запуска", fg="blue")
        self.status_label.pack()

        self.progress = ttk.Progressbar(master, orient="horizontal", length=600, mode="determinate")
        self.progress.pack(pady=5)

        tk.Label(master, text="Лог:").pack()
        self.log_output = scrolledtext.ScrolledText(master, height=20, width=85, wrap=tk.WORD)
        self.log_output.pack(padx=10, pady=5)

        # Старт фоновой проверки наличия Dongle
        self.master.after(1000, self.check_dongle_loop)

    def browse_zip(self):
        file_path = filedialog.askopenfilename(filetypes=[("ZIP files", "*.zip")])
        if file_path:
            self.zip_path.delete(0, tk.END)
            self.zip_path.insert(0, file_path)

    def check_dongle_loop(self):
        new_port = self.auto_find_com_port()
        if new_port != self.com_port:
            self.com_port = new_port
            if self.com_port:
                self.dongle_label.config(text=f"✅ nRF Dongle присоединён: {self.com_port}", fg="green")
            else:
                self.dongle_label.config(text="❌ nRF Dongle не найден", fg="red")

        # Повторим через несколько секунд
        self.master.after(self.dongle_check_interval * 1000, self.check_dongle_loop)

    def auto_find_com_port(self):
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "Nordic" in port.description or "nRF" in port.description:
                return port.device
        return None

    def toggle(self):
        if not self.running:
            if not self.com_port:
                messagebox.showerror("Ошибка", "nRF Dongle не найден. Пожалуйста, подключите устройство.")
                return

            self.running = True
            self.start_btn.config(text="⏹ Остановить")
            self.log_output.insert(tk.END, "\n--- Запуск автоматической прошивки ---\n")
            self.log_output.see(tk.END)
            self.auto_thread = threading.Thread(target=self.auto_scan_and_flash, daemon=True)
            self.auto_thread.start()
        else:
            self.running = False
            self.start_btn.config(text="▶ Старт")
            self.status_label.config(text="⏸ Остановлено", fg="blue")

    def set_progress_by_log_line(self, line):
        if "Successfully opened COM" in line:
            self.progress["value"] = 10
        elif "BLE: Scanning for" in line:
            self.progress["value"] = 20
        elif "BLE: Found target advertiser" in line:
            self.progress["value"] = 30
        elif "BLE: Connected to" in line:
            self.progress["value"] = 40
        elif "ATT MTU exchanged" in line or "Enabling longer Data Length" in line:
            self.progress["value"] = 50
        elif "Sending init packet" in line:
            self.progress["value"] = 60
        elif "Sending firmware file" in line:
            self.progress["value"] = 80
        elif "BLE: Disconnected" in line or "Device programmed" in line:
            self.progress["value"] = 100
        self.master.update_idletasks()

    def run_dfu(self):
        self.status_label.config(text="🚀 Запуск прошивки...", fg="orange")
        self.progress["value"] = 0
        self.log_output.insert(tk.END, "\n--- Прошивка началась ---\n")
        self.log_output.see(tk.END)
        self.master.update()

        cmd = [
            sys.executable,
            "-m", "nordicsemi",
            "-v", "-v",
            "dfu", "ble",
            "-ic", "NRF52",
            "-pkg", self.zip_path.get(),
            "-cd", self.delay.get(),
            "-p", self.com_port,
            "-n", self.device_name.get()
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ''):
                    self.log_output.insert(tk.END, line)
                    self.log_output.see(tk.END)
                    self.set_progress_by_log_line(line)
                pipe.close()

            reader_thread = threading.Thread(target=read_output, args=(process.stdout,))
            reader_thread.start()
            reader_thread.join()
            process.wait()

            if process.returncode == 0:
                self.status_label.config(text="✅ Успешно прошито", fg="green")
                self.log_output.insert(tk.END, "\n--- Устройство успешно прошито ---\n")
            else:
                self.status_label.config(text="❌ Ошибка прошивки", fg="red")
                self.log_output.insert(tk.END, f"\n[Ошибка] Код возврата: {process.returncode}\n")

        except Exception as e:
            self.status_label.config(text="❌ Исключение", fg="red")
            self.log_output.insert(tk.END, f"\n[Исключение] {str(e)}\n")

        self.log_output.see(tk.END)

    def auto_scan_and_flash(self):
        asyncio.run(self._scan_loop())

    async def _scan_loop(self):
        try:
            delay = float(self.delay.get())
        except ValueError:
            delay = 1.0
        target_name = self.device_name.get()

        while self.running:
            if not self.com_port:
                self.status_label.config(text="⏸ Ожидание подключения Dongle...", fg="gray")
                await asyncio.sleep(delay)
                continue

            self.status_label.config(text="🔍 Сканирование BLE...", fg="blue")
            devices = await BleakScanner.discover(timeout=2)
            for device in devices:
                if device.name == target_name:
                    if self.last_device_address and device.address == self.last_device_address:
                        self.status_label.config(text=f"⚠️ Уже прошито ({device.address})", fg="gray")
                        await asyncio.sleep(delay)
                        break

                    self.status_label.config(text=f"📡 Обнаружено: {device.name}", fg="orange")
                    self.run_dfu()
                    self.last_device_address = device.address

                    if not self.running:
                        return
                    self.log_output.insert(tk.END, "--- Ожидание следующего устройства ---\n")
                    self.log_output.see(tk.END)
                    await asyncio.sleep(delay)
                    break
            else:
                await asyncio.sleep(delay)

if __name__ == "__main__":
    root = tk.Tk()
    app = DFUGUI(root)
    root.mainloop()
