import asyncio
import threading
import time
from time import sleep
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import font, messagebox
from bleak import BleakScanner

baudrate = 115200
BYTES = [
    [0x47, 0x14, 0xAA, 0xFB, 0x67, 0x24, 0x10, 0x65, 0x57, 0x16, 0x10, 0x83],
    [0x47, 0x14, 0xE0],
]
number = 0  # Переменная для режимов increment и decrement

# Хранение обработанных устройств
processed_devices = set()

# Функции для работы с серийными номерами
def add_control_sum(list_num):
    sum_num = sum(list_num) & 0xFF
    control_sum = (~sum_num + 1) & 0xFF
    list_num.append(control_sum)

def crc8(data):
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            crc &= 0xFF
    return crc

def add_crc8(list_num):
    checksum = crc8(list_num)
    list_num.append(checksum)

def get_ports_list():
    return serial.tools.list_ports.comports()

def int_to_list_bytes(num):
    return [num >> 8, num & 0xFF]

def write_serial_num(port, num=None):
    ser = None
    try:
        sleep(0.5)
        ser = serial.Serial(port, baudrate=baudrate, timeout=0.5)
        if num is None:
            num = int(input("Enter serial number: "))
        number_serial = int_to_list_bytes(num)
        bytes = [b.copy() for b in BYTES]
        bytes[-1].extend(number_serial)
        add_control_sum(bytes[-1])
        for byte_set in bytes:
            ser.write(serial.to_bytes(byte_set))
            response = ser.readline()
            print(f"response: {response}")
    except Exception as e:
        print(e)
    finally:
        if ser:
            ser.close()

def filter_silicon_labs_ports(ports):
    return [port for port in ports if "Silicon Labs" in port.description]

# Интерфейс Tkinter для серийных номеров и Bluetooth
class BluetoothScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Присвоение серийных номеров и Bluetooth сканер")
        self.root.geometry("600x650")

        # Выбор режима присвоения серийного номера
        self.var = tk.StringVar(value='manual')
        radio_manual = tk.Radiobutton(root, text="Ручной режим", variable=self.var, value='manual')
        radio_increment = tk.Radiobutton(root, text="Автоматический режим (увеличение)", variable=self.var, value='increment')
        radio_decrement = tk.Radiobutton(root, text="Автоматический режим (уменьшение)", variable=self.var, value='decrement')
        radio_manual.pack(anchor=tk.W)
        radio_increment.pack(anchor=tk.W)
        radio_decrement.pack(anchor=tk.W)

        # Ввод начального числа для режимов increment/decrement
        label_number = tk.Label(root, text="Начальное число для автоматических режимов:")
        self.entry_number = tk.Entry(root)
        label_number.pack(anchor=tk.W)
        self.entry_number.pack(anchor=tk.W)

        # Ввод серийного номера для ручного режима
        label_serial_manual = tk.Label(root, text="Введите серийный номер для ручного режима:")
        self.serial_entry_manual = tk.Entry(root)
        label_serial_manual.pack(anchor=tk.W)
        self.serial_entry_manual.pack(anchor=tk.W)

        # Кнопка Start
        start_button = tk.Button(root, text="Старт", command=self.on_start_serial)
        start_button.pack(pady=10)

        # Область вывода для серийных номеров
        self.serial_output_text = tk.Text(root, height=10, width=50)
        self.serial_output_text.pack()

        # Текстовое поле для найденных Bluetooth-устройств
        self.bt_text = tk.Text(root, wrap='word', height=10, width=50)
        self.bt_text.pack(pady=10)

        # Определяем шрифт для увеличенного имени
        self.bold_font = font.Font(family="Comic Sans MS", size=14)
        self.bt_text.tag_configure("bold", font=self.bold_font)

        self.scanning = True  # Флаг для остановки сканирования
        self.start_bt_scanning()

        # Кнопка для выхода
        quit_button = tk.Button(root, text="Выход", command=self.quit_app)
        quit_button.pack(pady=10)

    def on_start_serial(self):
        mode = self.var.get()
        if mode == 'manual':
            serial_number = self.serial_entry_manual.get()
            if serial_number.isdigit():
                self.manual_mode_update()
            else:
                messagebox.showerror("Некорректный ввод", "Пожалуйста, введите корректный серийный номер")
        elif mode in ['increment', 'decrement']:
            if self.entry_number.get().isdigit():
                global number
                number = int(self.entry_number.get())
                threading.Thread(target=self.auto_mode_update, args=(mode,), daemon=True).start()
            else:
                messagebox.showerror("Некорректный ввод", "Пожалуйста, введите корректное начальное число для автоматических режимов")

    def manual_mode_update(self):
        ports = get_ports_list()
        silicon_labs_ports = filter_silicon_labs_ports(ports)
        serial_number = self.serial_entry_manual.get()
        for port in silicon_labs_ports:
            write_serial_num(port.device, int(serial_number))
            self.serial_output_text.insert(tk.END, f"Серийный номер {serial_number} присвоен устройству: {port.device}\n")

    def auto_mode_update(self, mode):
        global number, processed_devices
        while True:
            ports = get_ports_list()
            silicon_labs_ports = filter_silicon_labs_ports(ports)
            if not silicon_labs_ports:
                sleep(1)
                continue

            for port in silicon_labs_ports:
                if port.device not in processed_devices:
                    write_serial_num(port.device, number)
                    self.serial_output_text.insert(tk.END, f"Серийный номер {number} присвоен устройству: {port.device}\n")
                    processed_devices.add(port.device)
                    if mode == 'increment':
                        number += 1
                    elif mode == 'decrement':
                        number -= 1
                    sleep(0.5)

            processed_devices = {device.device for device in silicon_labs_ports}
            sleep(1)

    # Запуск сканирования Bluetooth
    def start_bt_scanning(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.run_bt_scanner, args=(self.loop,), daemon=True).start()

    def run_bt_scanner(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.scan_bt())

    async def scan_bt(self):
        scanner = BleakScanner()
        while self.scanning:
            devices = await scanner.discover(timeout=2)
            self.bt_text.delete(1.0, tk.END)
            for device in devices:
                if device.name and device.name.startswith("Archimedes_") and device.name != "Archimedes_1234":
                    self.bt_text.insert(tk.END, f"Имя: ", ("bold",))
                    self.bt_text.insert(tk.END, f"{device.name}\n", ("bold",))
            await asyncio.sleep(1)

    def quit_app(self):
        self.scanning = False
        self.root.after(100, self.root.destroy)

# Функция для запуска Tkinter GUI
def run_app():
    root = tk.Tk()
    app = BluetoothScannerApp(root)
    root.mainloop()

# Запуск приложения
if __name__ == "__main__":
    run_app()
