import ctypes
import json
import math
import bettercam
import time
import win32api
import win32gui
from ultralytics import YOLO
import pygame
import win32con
import os
import threading
from rich.console import Console
from rich.prompt import FloatPrompt, IntPrompt

os.system("cls")

PUL = ctypes.POINTER(ctypes.c_ulong)

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("mi", MouseInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

class SettingsConfigurator:
    def __init__(self, cls, config_file="config.json"):
        self.console = Console()
        self.config_file = config_file
        self.config = self.load_config()
        self.cls = cls

    def load_config(self):
        with open(self.config_file, 'r') as f:
            return json.load(f)

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def clear_console(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def get_config_value(self, prompt_text, min_value, max_value, precision=2):
        while True:
            try:
                value = FloatPrompt.ask(
                    prompt_text,
                    default=min_value,
                    show_default=True
                )
                if value < min_value or value > max_value:
                    raise ValueError(f"Value must be between {min_value} and {max_value}.")
                return round(value, precision)
            except ValueError as e:
                self.console.print(f"[bold red]{e}[/bold red]", style="bold white")

    def get_int_choice(self, prompt_text, min_value, max_value):
        while True:
            try:
                choice = IntPrompt.ask(prompt_text)
                if choice < min_value or choice > max_value:
                    raise ValueError(f"Choice must be between {min_value} and {max_value}.")
                return choice
            except ValueError as e:
                self.console.print(f"[bold red]{e}[/bold red]", style="bold white")

    def show_menu(self):
        self.console.print()
        self.console.print("[bold blue]Settings Menu[/bold blue]", justify="center")
        self.console.print("1. XY Sensitivity", justify="center")
        self.console.print("2. Targeting Sensitivity", justify="center")
        self.console.print("3. FOV Radius", justify="center")
        self.console.print("4. Mouse Delay", justify="center")
        self.console.print("5. Smoothing Factor", justify="center")
        self.console.print("6. Aim Height", justify="center")
        self.console.print("7. Confidence", justify="center")
        self.console.print()
        return self.get_int_choice("Select an option (1-7)", 1, 7)

    def configure_settings(self):
        while True:
            self.clear_console()
            self.console.print(f"\n[bold green]Current Configuration[/bold green]", justify="center")
            for key, value in self.config.items():
                self.console.print(f"{key.replace('_', ' ').title()}: {value}", justify="center")

            choice = self.show_menu()

            if choice == 1:
                self.config["xy_sens"] = self.get_config_value("Enter XY Sensitivity (0-100)", 0, 100)
                self.cls.scale = 1000 / (self.config["xy_sens"] * self.config["targeting_sens"])
            elif choice == 2:
                self.config["targeting_sens"] = self.get_config_value("Enter Targeting Sensitivity (0-100)", 0, 100)
                self.cls.scale = 1000 / (self.config["xy_sens"] * self.config["targeting_sens"])
            elif choice == 3:
                self.config["fov_radius"] = int(self.get_config_value("Enter FOV Radius (10-500)", 10, 500))
                self.cls.fov_radius = int(self.config["fov_radius"])
            elif choice == 4:
                self.config["mouse_delay"] = self.get_config_value("Enter Mouse Delay (0.00001-0.01)", 0.00001, 0.01, 10)
                self.cls.mouse_delay = self.config["mouse_delay"]
            elif choice == 5:
                self.config["smoothing_factor"] = self.get_config_value("Enter Smoothing Factor (0.001-0.99)", 0.001, 0.99)
                self.cls.smoothing_factor = self.config["smoothing_factor"]
            elif choice == 6:
                self.config["aim_height"] = self.get_config_value("Enter Aim Height (2-100)", 2, 100)
                self.cls.aim_height = self.config["aim_height"]
            elif choice == 7:
                self.config["confidence"] = self.get_config_value("Enter Confidence (0.10-0.99)", 0.10, 0.99, precision=2)
                self.cls.conf = self.config["confidence"]
            self.save_config()
        
class Aimbot:
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    screen = bettercam.create()
    
    def __init__(self):
        with open("config.json") as f:
            self.config = json.load(f)
        self.scale = 1000 / (self.config["xy_sens"] * self.config["targeting_sens"])
        self.fov_radius = self.config["fov_radius"]
        self.box_size = self.fov_radius * 2
        self.model = YOLO('best.pt').to("cuda")
        self.conf = self.config["confidence"]
        self.iou = 0.5
        self.aim_height = self.config["aim_height"]
        self.mouse_delay = self.config["mouse_delay"]
        self.smoothing_factor = self.config["smoothing_factor"]
        
        screensize = {'X': ctypes.windll.user32.GetSystemMetrics(0), 'Y': ctypes.windll.user32.GetSystemMetrics(1)}
        self.screen_x = screensize['X'] // 2
        self.screen_y = screensize['Y'] // 2
        self.detection_box = {
            'left': self.screen_x - self.box_size // 2,
            'top': self.screen_y - self.box_size // 2,
            'width': self.box_size,
            'height': self.box_size
        }
        self.last_target = {}
        
    def smooth_target_position(self, target):
        if self.last_target:
            alpha = self.smoothing_factor
            smoothed_x = alpha * target["x"] + (1 - alpha) * self.last_target["x"]
            smoothed_y = alpha * target["y"] + (1 - alpha) * self.last_target["y"]
            self.last_target = {"x": smoothed_x, "y": smoothed_y}
            return {"x": int(smoothed_x), "y": int(smoothed_y)}
        return target

    def sleep(self, duration, get_now=time.perf_counter):
        if duration == 0:
            return
        end = get_now() + duration
        while get_now() < end:
            pass
    
    def is_targeting(self):
        return win32api.GetKeyState(0x02) in (-127, -128)
            
    def move_crosshair(self, x, y):
        response = self.is_targeting()
        if response:
            scale = self.scale
            for rel_x, rel_y in self.interpolate_coordinates(self, (x, y), scale):
                self.ii_.mi = MouseInput(rel_x, rel_y, 0, 0x0001, 0, ctypes.pointer(self.extra))
                input_obj = Input(ctypes.c_ulong(0), self.ii_)
                ctypes.windll.user32.SendInput(1, ctypes.byref(input_obj), ctypes.sizeof(input_obj))
                self.sleep(self.mouse_delay)
                
    def interpolate_coordinates(self, target_coords, scale):
        diff_x = (target_coords[0] - self.screen_x) * scale
        diff_y = (target_coords[1] - self.screen_y) * scale
        length = int(math.hypot(diff_x, diff_y))
        if length == 0:
            return
        unit_x, unit_y = diff_x / length, diff_y / length
        sum_x = sum_y = 0
        for k in range(length):
            dx, dy = int(k * unit_x - sum_x), int(k * unit_y - sum_y)
            sum_x += dx
            sum_y += dy
            yield dx, dy

    def process_frame(self, frame):
        detections = self.model.predict(source=frame, verbose=False, conf=self.conf, iou=self.iou, half=True)
        return detections[0]

    def find_closest_target(self, boxes):
        least_dist = float('inf')
        closest_target = None
        for box in boxes.xyxy:
            x1, y1, x2, y2 = map(int, box)
            height = y2 - y1
            head_x, head_y = (x1 + x2) // 2, (y1 + y2) // 2 - height // self.aim_height
            if x1 < 15 or (x1 < self.box_size / 5 and y2 > self.box_size / 1.2):
                continue
            dist = math.hypot(head_x - self.box_size // 2, head_y - self.box_size // 2)
            if dist < least_dist:
                least_dist = dist
                closest_target = {"x": head_x, "y": head_y}

        if closest_target:
            return self.smooth_target_position(closest_target), box
        return None

    def start(self):
        region = (
            self.detection_box['left'],
            self.detection_box['top'],
            self.detection_box['left'] + self.detection_box['width'],
            self.detection_box['top'] + self.detection_box['height']
        )
        while True:
                frame = self.screen.grab(region=region)
                if frame is None:
                    continue
                result = self.process_frame(frame)
                if result.boxes.xyxy.numel() == 0:
                    continue
                
                target = self.find_closest_target(result.boxes)
                if target:
                    self.move_crosshair(target[0]["x"] + region[0], target[0]["y"] + region[1])
                    x1, y1, x2, y2 = map(int, target[1])
                    x1 += region[0]
                    y1 += region[1]
                    x2 += region[0]
                    y2 += region[1]
                
    def update_pygame(self):
        pygame.init()
        screen_width, screen_height = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
        window = pygame.display.set_mode((screen_width, screen_height), pygame.NOFRAME | pygame.SRCALPHA)
        pygame.display.set_caption("Visual Overlay")
        hwnd = pygame.display.get_wm_info()['window']
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style | win32con.WS_EX_TOPMOST | win32con.WS_EX_LAYERED)
        win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(0, 0, 0), 0, win32con.LWA_COLORKEY)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        pygame.event.clear()
        
        while True:
            pygame.event.pump()
            window.fill((0, 0, 0, 0))
            pygame.draw.circle(window, (255, 255, 255), (self.screen_x, self.screen_y), self.fov_radius, 2)
            pygame.display.update()
            time.sleep(1)
            
        
def pygame_update(aimbot):
    aimbot.update_pygame()
         
def run_aimbot(aimbot):
    aimbot.start()


def run_configurator(aimbot):
    configurator = SettingsConfigurator(aimbot)
    configurator.configure_settings()
 
def main():
    aimbot = Aimbot()
    configurator_thread = threading.Thread(target=run_configurator, args=(aimbot,), daemon=True)
    pygame_thread = threading.Thread(target=pygame_update, args=(aimbot,), daemon=True)
    aimbot_thread = threading.Thread(target=run_aimbot, args=(aimbot,), daemon=True)
    
    configurator_thread.start()
    pygame_thread.start()
    aimbot_thread.start()
    while True:
        time.sleep(5)

if __name__ == "__main__":
    main()
