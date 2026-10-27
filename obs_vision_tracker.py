import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog
import requests
from io import BytesIO
from PIL import Image, ImageTk
import json
import os
import threading
import time
import mss
import numpy as np
import cv2
import pytesseract
import re

# Fix Windows High-DPI scaling
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    pass

LAYOUT_FILE = "vision_layout.json"

# --- Smart Path & Helpers ---
def get_tesseract_path(saved_path=""):
    if saved_path and os.path.exists(saved_path):
        return saved_path
    user_profile = os.environ.get('USERPROFILE', '')
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(user_profile, r"AppData\Local\Tesseract-OCR\tesseract.exe"),
        os.path.join(user_profile, r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
    ]
    for path in common_paths:
        if os.path.exists(path): return path
    return ""

def format_for_pokeapi(name):
    name = name.strip().lower().replace(":", "").replace("'", "").replace(".", "")
    name = name.replace("♀", "-f").replace("♂", "-m").replace(" ", "-")
    while "--" in name: name = name.replace("--", "-")
    return name

def normalize_for_ocr(text):
    if not text: return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())

# --- Core Classes ---
class CameraScannerApp:
    def __init__(self, root, on_select_callback):
        self.top = tk.Toplevel(root)
        self.top.title("Select a Camera")
        self.top.geometry("800x600")
        self.top.attributes("-topmost", True)
        self.on_select = on_select_callback
        ttk.Label(self.top, text="Scanning for available cameras... Please wait.", font=("Helvetica", 12)).pack(pady=20)
        self.top.update()
        self.grid_frame = ttk.Frame(self.top)
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.photos = [] 
        row, col, found_any = 0, 0, False
        for i in range(6):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) 
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    found_any = True
                    frame_rgb = cv2.cvtColor(cv2.resize(frame, (320, 240)), cv2.COLOR_BGR2RGB)
                    photo = ImageTk.PhotoImage(Image.fromarray(frame_rgb))
                    self.photos.append(photo)
                    btn_frame = ttk.Frame(self.grid_frame)
                    btn_frame.grid(row=row, column=col, padx=10, pady=10)
                    tk.Button(btn_frame, image=photo, command=lambda idx=i: self.choose_camera(idx)).pack()
                    ttk.Label(btn_frame, text=f"Camera Index: {i}", font=("Helvetica", 10, "bold")).pack(pady=5)
                    col += 1
                    if col > 2: col, row = 0, row + 1
            cap.release()
        if not found_any: ttk.Label(self.grid_frame, text="No cameras found!", foreground="red").pack()

    def choose_camera(self, index):
        self.on_select(index)
        self.top.destroy()

class RegionSelector:
    def __init__(self, root, callback):
        self.callback = callback
        self.top = tk.Toplevel(root)
        self.top.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
        self.top.overrideredirect(True)
        self.top.attributes("-alpha", 0.3)
        self.top.config(cursor="cross")
        self.canvas = tk.Canvas(self.top, cursor="cross", bg="grey", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.top.bind("<Left>", lambda e: self.move_box(-2, 0))
        self.top.bind("<Right>", lambda e: self.move_box(2, 0))
        self.top.bind("<Up>", lambda e: self.move_box(0, -2))
        self.top.bind("<Down>", lambda e: self.move_box(0, 2))
        self.top.bind("<Return>", self.confirm_selection)
        self.top.bind("<Escape>", self.cancel_selection)
        self.top.focus_set()
        self.start_x = self.start_y = None
        self.current_x2 = self.current_y2 = 0
        self.rect = None
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            sct_img = sct.grab(monitor)
            self.bg_photo = ImageTk.PhotoImage(Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX"))
            self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")
        self.canvas.create_text(root.winfo_screenwidth() // 2, 30, text="Drag to select region | Arrow Keys to nudge | ENTER to confirm | ESC to cancel", fill="yellow", font=("Helvetica", 14, "bold"))

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.current_x2, self.current_y2 = event.x, event.y
        if self.rect: self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.current_x2, self.current_y2, outline='red', width=2)

    def on_drag(self, event):
        self.current_x2, self.current_y2 = event.x, event.y
        if self.rect: self.canvas.coords(self.rect, self.start_x, self.start_y, self.current_x2, self.current_y2)

    def move_box(self, dx, dy):
        if not self.rect: return
        self.start_x += dx; self.start_y += dy; self.current_x2 += dx; self.current_y2 += dy
        self.canvas.coords(self.rect, self.start_x, self.start_y, self.current_x2, self.current_y2)

    def cancel_selection(self, event=None):
        self.callback(None)
        self.top.destroy()

    def confirm_selection(self, event=None):
        if not self.rect: return self.cancel_selection()
        x1, y1 = min(self.start_x, self.current_x2), min(self.start_y, self.current_y2)
        w, h = max(self.start_x, self.current_x2) - x1, max(self.start_y, self.current_y2) - y1
        if w > 10 and h > 10: self.callback({"top": y1, "left": x1, "width": w, "height": h})
        else: self.cancel_selection()
        self.top.destroy()

class AdvancedVisionTrackerWorker(threading.Thread):
    def __init__(self, app_ref):
        super().__init__(daemon=True)
        self.app = app_ref
        self.is_running = False

    def run(self):
        self.is_running = True
        caps = {}
        with mss.mss() as sct:
            while self.is_running:
                frames_cache = {}
                for hunt in self.app.active_hunts:
                    target_clean = normalize_for_ocr(hunt["pokemon_var"].get())
                    if not target_clean: continue

                    mode = hunt.get("active_mode")
                    if mode == "camera" and hunt.get("camera_index") is not None:
                        c_idx = hunt["camera_index"]
                        if c_idx not in caps: caps[c_idx] = cv2.VideoCapture(c_idx, cv2.CAP_DSHOW)
                        if c_idx not in frames_cache:
                            ret, f = caps[c_idx].read()
                            frames_cache[c_idx] = f if ret else None
                            
                        frame = frames_cache[c_idx]
                        if frame is None: continue

                        for roi_data in hunt["camera_rois"]:
                            x, y, w, h = roi_data["coords"]
                            if w <= 0 or h <= 0: continue
                            
                            gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
                            if roi_data["awaiting_black_screen"]:
                                if np.mean(gray) < 15: roi_data["awaiting_black_screen"] = False
                                continue

                            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                            screen_clean = normalize_for_ocr(pytesseract.image_to_string(binary, config='--psm 6'))

                            if target_clean in screen_clean:
                                if hunt["require_extra_var"].get():
                                    ext = normalize_for_ocr(hunt["extra_word_var"].get())
                                    if ext and ext not in screen_clean: continue
                                self.app.increment_hunt(hunt["id"])
                                roi_data["awaiting_black_screen"] = True

                    elif mode == "screen" and hunt.get("screen_region"):
                        reg = hunt["screen_region"]
                        gray = cv2.cvtColor(np.array(sct.grab(reg)), cv2.COLOR_BGRA2GRAY)
                        if hunt.get("screen_awaiting_black_screen"):
                            if np.mean(gray) < 15: hunt["screen_awaiting_black_screen"] = False
                            continue
                            
                        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        screen_clean = normalize_for_ocr(pytesseract.image_to_string(binary, config='--psm 6'))

                        if target_clean in screen_clean:
                            if hunt["require_extra_var"].get():
                                ext = normalize_for_ocr(hunt["extra_word_var"].get())
                                if ext and ext not in screen_clean: continue
                            self.app.increment_hunt(hunt["id"])
                            hunt["screen_awaiting_black_screen"] = True
                time.sleep(0.5)
        for cap in caps.values(): cap.release()

    def stop_loop(self):
        self.is_running = False

class VisionShinyTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Ultimate Multi-Shiny Tracker")
        self.root.geometry("800x600")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        self.tesseract_path = ""
        self.active_hunts = []
        self.next_hunt_id = 0
        
        # --- UI & Alpha States ---
        self.size_sprite = tk.IntVar(value=120)
        self.size_counter = tk.IntVar(value=56)
        self.size_odds = tk.IntVar(value=16)
        
        self.alpha_window = tk.DoubleVar(value=1.0)
        self.alpha_sprite = tk.DoubleVar(value=1.0)
        self.alpha_counter = tk.DoubleVar(value=1.0)
        self.alpha_odds = tk.DoubleVar(value=1.0)
        self.alpha_menu = tk.DoubleVar(value=1.0)
        self.transparent_bg_var = tk.BooleanVar(value=False)
        
        self.text_color, self.outline_color, self.bg_color = "#ffffff", "#000000", "#00ff00"
        self.edit_mode = False
        
        self.caught_list = []
        self.capturing_action = None

        self.caught_window = tk.Toplevel(self.root)
        self.caught_window.attributes("-fullscreen", True)
        self.caught_window.attributes("-topmost", True)
        self.caught_window.config(bg="#000002")
        self.caught_window.wm_attributes("-transparentcolor", "#000002")
        self.caught_canvas = tk.Canvas(self.caught_window, bg="#000002", highlightthickness=0)
        self.caught_canvas.pack(fill="both", expand=True)

        self.vision_worker = AdvancedVisionTrackerWorker(self)

        self.canvas = tk.Canvas(self.root, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_menu_box", "edit_box"))
        self.create_outlined_text(80, 30, "⚙️ Menu (Tab)", ("Helvetica", 12, "bold"), "#ffffff", "drag_menu")

        self.drag_item = None
        self.drag_start_x = self.drag_start_y = 0
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_release)
        self.caught_canvas.bind("<ButtonPress-1>", self.on_caught_drag_start)
        self.caught_canvas.bind("<B1-Motion>", self.on_caught_drag_motion)
        self.caught_canvas.bind("<ButtonRelease-1>", self.on_caught_drag_release)

        self.control_panel = tk.Toplevel(self.root)
        self.control_panel.title("Vision Stream Control Panel")
        self.control_panel.geometry("560x980")
        self.control_panel.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.build_control_panel()
        
        self.load_layout()
        if not self.active_hunts: self.add_new_hunt_ui()
        
        self.size_sprite.trace_add("write", lambda *a: self.update_transparency())
        self.size_counter.trace_add("write", lambda *a: self.refresh_text_styles())
        self.size_odds.trace_add("write", lambda *a: self.refresh_text_styles())
        
        self.root.bind_all("<KeyPress-Tab>", self.toggle_menu)
        self.root.bind_all("<Key>", self.handle_global_key)

    def blend_color(self, hex_fg, hex_bg, alpha):
        if alpha <= 0.01: return hex_bg
        if alpha >= 0.99: return hex_fg
        r1, g1, b1 = int(hex_fg[1:3], 16), int(hex_fg[3:5], 16), int(hex_fg[5:7], 16)
        r2, g2, b2 = int(hex_bg[1:3], 16), int(hex_bg[3:5], 16), int(hex_bg[5:7], 16)
        return f"#{int(r1 * alpha + r2 * (1 - alpha)):02x}{int(g1 * alpha + g2 * (1 - alpha)):02x}{int(b1 * alpha + b2 * (1 - alpha)):02x}"

    def create_outlined_text(self, x, y, text, font, text_color, tag):
        for dx, dy in [(-2,-2),(0,-2),(2,-2),(-2,0),(2,0),(-2,2),(0,2),(2,2)]:
            self.canvas.create_text(x+dx, y+dy, text=text, font=font, fill=self.outline_color, tags=(tag, f"{tag}_shadow"))
        self.canvas.create_text(x, y, text=text, font=font, fill=text_color, tags=(tag, f"{tag}_main"))

    def build_control_panel(self):
        self.edit_btn = ttk.Button(self.control_panel, text="🛠️ ENABLE EDIT / LAYOUT MODE", command=self.toggle_edit_mode)
        self.edit_btn.pack(fill="x", padx=10, pady=5)
        ttk.Button(self.control_panel, text="➕ Add Another Pokémon Tracker", command=self.add_new_hunt_ui).pack(fill="x", padx=10, pady=5)
        
        self.vision_toggle_btn = ttk.Button(self.control_panel, text="▶ Start Vision Auto-Tracker (All Hunts)", command=self.toggle_vision_tracker)
        self.vision_toggle_btn.pack(fill="x", padx=10, pady=5)

        self.scroll_canvas = tk.Canvas(self.control_panel)
        self.scrollbar = ttk.Scrollbar(self.control_panel, orient="vertical", command=self.scroll_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.scroll_canvas)
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_window_id = self.scroll_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.scroll_canvas.bind("<Configure>", self.on_canvas_configure)
        
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scroll_canvas.pack(side="top", fill="both", expand=True, padx=10, pady=5)
        self.scrollbar.pack(side="right", fill="y")
        
        # Containers
        self.hunts_container = ttk.Frame(self.scrollable_frame)
        self.hunts_container.pack(fill="both", expand=True)
        
        ttk.Separator(self.scrollable_frame, orient="horizontal").pack(fill="x", pady=20)
        ttk.Label(self.scrollable_frame, text="Global Settings", font=("Helvetica", 14, "bold")).pack(pady=5)
        
        self.settings_container = ttk.Frame(self.scrollable_frame)
        self.settings_container.pack(fill="both", expand=True)

        # Sizes
        globals_frame = ttk.LabelFrame(self.settings_container, text="Global Element Sizes", padding=10)
        self.make_slider(globals_frame, "Sprite Size:", self.size_sprite, 50, 300, None)
        self.make_slider(globals_frame, "Counter Size:", self.size_counter, 20, 150, None)
        self.make_slider(globals_frame, "Odds Size:", self.size_odds, 10, 40, None)
        
        # Colors & Background
        colors_frame = ttk.LabelFrame(self.settings_container, text="Global Colors & Background", padding=10)
        btn_frame = ttk.Frame(colors_frame)
        btn_frame.pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Text Color", command=self.change_text_color).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(btn_frame, text="Outline Color", command=self.change_outline_color).pack(side="right", expand=True, fill="x", padx=(2, 0))
        ttk.Button(colors_frame, text="Change Background Color", command=self.change_bg_color).pack(fill="x", pady=2)
        ttk.Checkbutton(colors_frame, text="Make Background 100% Invisible", variable=self.transparent_bg_var, command=self.update_transparency).pack(anchor="w", pady=(5,0))

        # Alpha Controls
        alpha_frame = ttk.LabelFrame(self.settings_container, text="Visibility & Opacity Controls", padding=10)
        self.make_slider(alpha_frame, "Overall Window:", self.alpha_window, 0.1, 1.0, self.update_transparency)
        ttk.Separator(alpha_frame, orient="horizontal").pack(fill="x", pady=5)
        self.make_slider(alpha_frame, "Pokemon Sprite:", self.alpha_sprite, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Counter Text:", self.alpha_counter, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Odds Text:", self.alpha_odds, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "⚙️ Menu Button:", self.alpha_menu, 0.0, 1.0, self.update_transparency)

        # Caught Manager
        self.caught_mgr_frame = ttk.LabelFrame(self.settings_container, text="Manage Caught Pokémon", padding=10)
        self.caught_checkboxes_container = ttk.Frame(self.caught_mgr_frame)
        self.caught_checkboxes_container.pack(fill="x")
        
        self.update_flow_layout()

    # --- DYNAMIC FLOW LAYOUT ENGINE ---
    def on_canvas_configure(self, event):
        self.scroll_canvas.itemconfig(self.scroll_window_id, width=event.width)
        self.update_flow_layout(event.width)
        
    def update_flow_layout(self, canvas_width=None):
        if not hasattr(self, 'scroll_canvas'): return
        if canvas_width is None:
            self.scroll_canvas.update_idletasks()
            canvas_width = self.scroll_canvas.winfo_width()
            
        if canvas_width < 10: return

        col_width = 450
        num_cols = max(1, canvas_width // col_width)
        
        for i in range(10): 
            self.hunts_container.columnconfigure(i, weight=0)
            self.settings_container.columnconfigure(i, weight=0)
            
        for i in range(num_cols): 
            self.hunts_container.columnconfigure(i, weight=1)
            self.settings_container.columnconfigure(i, weight=1)

        for idx, child in enumerate(self.hunts_container.winfo_children()):
            child.grid(row=idx // num_cols, column=idx % num_cols, sticky="nsew", padx=10, pady=10)

        for idx, child in enumerate(self.settings_container.winfo_children()):
            child.grid(row=idx // num_cols, column=idx % num_cols, sticky="nsew", padx=10, pady=10)

    def make_slider(self, parent, text, variable, from_val, to_val, command):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=1)
        ttk.Label(frame, text=text, width=15).pack(side="left")
        ttk.Scale(frame, from_=from_val, to=to_val, orient="horizontal", variable=variable, command=command).pack(side="right", expand=True, fill="x")

    def change_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color", initialcolor=self.text_color)[1]
        if color: self.text_color = color; self.update_transparency(); self.save_layout()

    def change_outline_color(self):
        color = colorchooser.askcolor(title="Choose Outline Color", initialcolor=self.outline_color)[1]
        if color: self.outline_color = color; self.update_transparency(); self.save_layout()

    def change_bg_color(self):
        color = colorchooser.askcolor(title="Choose Background Color", initialcolor=self.bg_color)[1]
        if color: self.bg_color = color; self.update_transparency(); self.save_layout()

    def add_new_hunt_ui(self, saved_data=None):
        if saved_data is None: saved_data = {}

        h_id = saved_data.get("id", self.next_hunt_id)
        self.next_hunt_id = max(self.next_hunt_id, h_id + 1)
        
        hunt = {
            "id": h_id,
            "pokemon_var": tk.StringVar(value=saved_data.get("pokemon", "")),
            "encounters_var": tk.IntVar(value=saved_data.get("encounters", 0)),
            "base_odds_var": tk.StringVar(value=saved_data.get("base_odds", "Gen 6+ (1/4096 Standard)")),
            "require_extra_var": tk.BooleanVar(value=saved_data.get("require_extra", False)),
            "extra_word_var": tk.StringVar(value=saved_data.get("extra_word", "take")),
            "key_inc": tk.StringVar(value=saved_data.get("key_inc", "space")),
            "key_dec": tk.StringVar(value=saved_data.get("key_dec", "Down")),
            "key_caught": tk.StringVar(value=saved_data.get("key_caught", "c")),
            "active_mode": saved_data.get("active_mode", None),
            "screen_region": saved_data.get("screen_region", None),
            "camera_index": saved_data.get("camera_index", None),
            "camera_rois": saved_data.get("camera_rois", []),
            "screen_awaiting_black_screen": False,
            "base_pil": None,
            "photo": None,
            "tag_sprite": f"hunt_{h_id}_sprite",
            "tag_counter": f"hunt_{h_id}_counter",
            "tag_odds": f"hunt_{h_id}_odds",
            "ui_frame": None
        }
        
        hunt["pokemon_var"].trace_add("write", lambda *a, h=hunt: self.sync_and_update(h))
        
        for roi in hunt["camera_rois"]: roi["awaiting_black_screen"] = False

        frame = ttk.LabelFrame(self.hunts_container, text=f"Tracker: Hunt #{h_id + 1}", padding=10)
        hunt["ui_frame"] = frame

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

        ttk.Label(frame, text="Pokemon:").grid(row=0, column=0, sticky="e", padx=(0, 5))
        ttk.Entry(frame, textvariable=hunt["pokemon_var"]).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(frame, text="Load Image", command=lambda: self.load_sprite(hunt)).grid(row=0, column=2, sticky="w", padx=(5, 0))

        ttk.Combobox(frame, textvariable=hunt["base_odds_var"], values=["Gen 6+ (1/4096 Standard)", "Dynamax Adventures (1/300)"], state="readonly").grid(row=1, column=0, columnspan=3, pady=5, sticky="ew")
        
        ttk.Checkbutton(frame, text="Dynamax Extra Word:", variable=hunt["require_extra_var"]).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Entry(frame, textvariable=hunt["extra_word_var"]).grid(row=2, column=2, sticky="ew")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=3, pady=5, sticky="ew")
        ttk.Button(btn_row, text="-1", width=4, command=lambda: self.adjust_hunt(hunt, -1)).pack(side="left")
        ttk.Button(btn_row, text="+1 Encounter", command=lambda: self.increment_hunt(hunt["id"])).pack(side="left", expand=True, fill="x")
        
        vis_row = ttk.Frame(frame)
        vis_row.grid(row=4, column=0, columnspan=3, pady=5, sticky="ew")
        ttk.Button(vis_row, text="Select Screen Region", command=lambda: self.assign_screen_roi(hunt)).pack(side="left", expand=True, fill="x")
        ttk.Button(vis_row, text="Select Camera Regions", command=lambda: self.assign_camera_rois(hunt)).pack(side="left", expand=True, fill="x")

        hk_row = ttk.Frame(frame)
        hk_row.grid(row=5, column=0, columnspan=3, pady=5, sticky="ew")
        
        btn_inc = ttk.Button(hk_row, text=f"+1 Key: {hunt['key_inc'].get()}")
        btn_inc.config(command=lambda b=btn_inc, h=hunt: self.start_key_capture(h, 'inc', b))
        btn_inc.pack(side="left", expand=True, fill="x", padx=1)

        btn_dec = ttk.Button(hk_row, text=f"-1 Key: {hunt['key_dec'].get()}")
        btn_dec.config(command=lambda b=btn_dec, h=hunt: self.start_key_capture(h, 'dec', b))
        btn_dec.pack(side="left", expand=True, fill="x", padx=1)

        btn_caught = ttk.Button(hk_row, text=f"Caught Key: {hunt['key_caught'].get()}")
        btn_caught.config(command=lambda b=btn_caught, h=hunt: self.start_key_capture(h, 'caught', b))
        btn_caught.pack(side="left", expand=True, fill="x", padx=1)

        ttk.Button(frame, text="✨ Register Current as Caught!", command=lambda h=hunt: self.register_caught(h)).grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")
        ttk.Button(frame, text="🗑️ Delete Tracker", command=lambda h=hunt: self.delete_hunt(h)).grid(row=7, column=0, columnspan=3, pady=5, sticky="ew")

        self.spawn_overlay_elements(hunt, saved_data)
        self.active_hunts.append(hunt)
        if saved_data and hunt["pokemon_var"].get(): self.load_sprite(hunt, silent=True)
        
        self.update_flow_layout()
        self.save_layout()

    # --- Duplicate Tracker Logic ---
    def sync_and_update(self, hunt):
        poke = format_for_pokeapi(hunt["pokemon_var"].get())
        if poke:
            for h in self.active_hunts:
                if h != hunt and format_for_pokeapi(h["pokemon_var"].get()) == poke:
                    hunt["encounters_var"].set(h["encounters_var"].get())
                    break
        self.update_transparency()

    def delete_hunt(self, hunt):
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete Hunt #{hunt['id'] + 1}?"):
            return
            
        if hunt["ui_frame"] and hunt["ui_frame"].winfo_exists():
            hunt["ui_frame"].destroy()
            
        self.canvas.delete(hunt["tag_sprite"], hunt["tag_counter"], hunt["tag_odds"], f"{hunt['tag_sprite']}_box", f"{hunt['tag_counter']}_box", f"{hunt['tag_odds']}_box")
        
        if hunt in self.active_hunts:
            self.active_hunts.remove(hunt)
            
        self.update_flow_layout()
        self.update_transparency()
        self.save_layout()

    # --- Hotkey & Counter Management ---
    def start_key_capture(self, hunt, action_type, btn_widget):
        self.capturing_action = (hunt, action_type, btn_widget)
        self.root.bind_all("<Key>", self.capture_key_press)
        btn_widget.config(text="Press any key...")

    def capture_key_press(self, event):
        if event.keysym == "Tab": return
        if self.capturing_action:
            hunt, action_type, btn_widget = self.capturing_action
            key_sym = event.keysym
            if action_type == 'inc':
                hunt["key_inc"].set(key_sym)
                btn_widget.config(text=f"+1 Key: {key_sym}")
            elif action_type == 'dec':
                hunt["key_dec"].set(key_sym)
                btn_widget.config(text=f"-1 Key: {key_sym}")
            elif action_type == 'caught':
                hunt["key_caught"].set(key_sym)
                btn_widget.config(text=f"Caught Key: {key_sym}")
            self.capturing_action = None
            self.save_layout()
            self.root.bind_all("<Key>", self.handle_global_key)

    def handle_global_key(self, event):
        if isinstance(self.root.focus_get(), ttk.Entry): return
        key = event.keysym.lower()
        for hunt in self.active_hunts:
            if key == hunt["key_inc"].get().lower():
                self.increment_hunt(hunt["id"])
            elif key == hunt["key_dec"].get().lower():
                self.adjust_hunt(hunt, -1)
            elif key == hunt["key_caught"].get().lower():
                self.register_caught(hunt)

    def increment_hunt(self, h_id):
        hunt = next((h for h in self.active_hunts if h["id"] == h_id), None)
        if hunt:
            self.adjust_hunt(hunt, 1)

    def adjust_hunt(self, hunt, val):
        poke = format_for_pokeapi(hunt["pokemon_var"].get())
        targets = [hunt]
        if poke:
            targets = [h for h in self.active_hunts if format_for_pokeapi(h["pokemon_var"].get()) == poke]
        
        for h in targets:
            h["encounters_var"].set(max(0, h["encounters_var"].get() + val))
            self.canvas.itemconfig(f"{h['tag_counter']}_main", text=str(h["encounters_var"].get()))
            self.canvas.itemconfig(f"{h['tag_counter']}_shadow", text=str(h["encounters_var"].get()))
        self.save_layout()

    # --- Caught Pokemon Logic ---
    def register_caught(self, hunt):
        raw_pokemon = hunt["pokemon_var"].get().strip()
        if not raw_pokemon: return messagebox.showwarning("Warning", "Please enter a Pokémon name to register as caught!")
        pokemon_slug = format_for_pokeapi(raw_pokemon)
        try:
            resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_slug}")
            if resp.status_code == 200 and resp.json()['sprites']['front_shiny']:
                img_resp = requests.get(resp.json()['sprites']['front_shiny'])
                raw_img = Image.open(BytesIO(img_resp.content))
                default_size = 120
                pil_img = raw_img.resize((default_size, default_size), Image.Resampling.NEAREST)
                
                existing = next((c for c in self.caught_list if c["name"].lower() == pokemon_slug), None)
                if not existing:
                    tag_base = f"caught_{len(self.caught_list)}_{int(time.time())}"
                    photo = ImageTk.PhotoImage(pil_img)
                    self.caught_canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(tag_base, f"{tag_base}_box", "caught_edit_box"))
                    self.caught_canvas.create_image(400, 300, image=photo, tags=(tag_base, f"{tag_base}_main"))
                    
                    self.caught_list.append({
                        "name": pokemon_slug, "raw_image": raw_img, "photo": photo,
                        "tag": tag_base, "visible_var": tk.BooleanVar(value=True), "size_var": tk.IntVar(value=default_size)
                    })
                    self.rebuild_caught_manager_ui()
                    self.save_layout()
                    messagebox.showinfo("Success", f"Spawned {raw_pokemon} on your full-screen overlay!")
                else: messagebox.showinfo("Info", f"{raw_pokemon} is already registered!")
            else: messagebox.showerror("Error", "No shiny sprite found.")
        except Exception as e: messagebox.showerror("Error", f"Failed to register: {e}")

    def rebuild_caught_manager_ui(self):
        for widget in self.caught_checkboxes_container.winfo_children(): widget.destroy()
        for c in self.caught_list:
            row = ttk.Frame(self.caught_checkboxes_container)
            row.pack(fill="x", padx=2, pady=2)
            cb = ttk.Checkbutton(row, text=c["name"].capitalize(), variable=c["visible_var"], command=lambda item=c: self.toggle_caught_visibility(item))
            cb.pack(side="left", padx=2)
            ttk.Scale(row, from_=120, to=500, orient="horizontal", variable=c["size_var"], command=lambda val, item=c: self.update_caught_size(item, float(val))).pack(side="right", expand=True, fill="x", padx=5)

    def toggle_caught_visibility(self, item):
        self.caught_canvas.itemconfig(f"{item['tag']}_main", state="normal" if item["visible_var"].get() else "hidden")
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def update_caught_size(self, item, new_size_float):
        new_size = int(new_size_float)
        if item["raw_image"]:
            photo = ImageTk.PhotoImage(item["raw_image"].resize((new_size, new_size), Image.Resampling.NEAREST))
            item["photo"] = photo
            self.caught_canvas.itemconfig(f"{item['tag']}_main", image=photo)
            if self.edit_mode: self.update_edit_boxes()
            self.save_layout()

    # --- Vision Trackers ---
    def assign_screen_roi(self, hunt):
        self.control_panel.withdraw()
        RegionSelector(self.root, lambda r: self._save_screen(hunt, r))
    def _save_screen(self, hunt, region):
        self.control_panel.deiconify()
        if region:
            hunt["screen_region"] = region
            hunt["active_mode"] = "screen"
            self.save_layout()
            messagebox.showinfo("Success", f"Screen region locked for Hunt #{hunt['id']+1}")

    def assign_camera_rois(self, hunt):
        self.control_panel.withdraw()
        CameraScannerApp(self.root, lambda idx: self._save_cam(hunt, idx))
    def _save_cam(self, hunt, index):
        self.control_panel.deiconify()
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        time.sleep(1.0)
        ret, frame = cap.read()
        if not ret: return messagebox.showerror("Error", "Could not connect to camera.")
        messagebox.showinfo("Draw", "Draw boxes, press ENTER after each, ESC when done.")
        rois = cv2.selectROIs("Draw Regions", frame, fromCenter=False, showCrosshair=True)
        cv2.destroyWindow("Draw Regions")
        cap.release()
        if len(rois) > 0:
            hunt["camera_index"] = index
            hunt["camera_rois"] = [{"coords": [int(c) for c in r], "awaiting_black_screen": False} for r in rois]
            hunt["active_mode"] = "camera"
            self.save_layout()

    def load_sprite(self, hunt, silent=False):
        name = format_for_pokeapi(hunt["pokemon_var"].get())
        if not name: return
        try:
            resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{name}")
            if resp.status_code == 200 and resp.json()['sprites']['front_shiny']:
                hunt["base_pil"] = Image.open(BytesIO(requests.get(resp.json()['sprites']['front_shiny']).content))
                self.update_transparency()
            elif not silent: messagebox.showerror("Error", "No sprite found.")
        except: pass

    # FIX: Added a visual stagger cascade so new trackers don't spawn completely glued on top of each other
    def spawn_overlay_elements(self, hunt, saved_data=None):
        offset = len(self.active_hunts) * 40
        sx, sy = (150 + offset, 200 + offset)
        cx, cy = (350 + offset, 180 + offset)
        ox, oy = (350 + offset, 260 + offset)
        
        if saved_data and "coords" in saved_data:
            c = saved_data["coords"]
            sx, sy = c.get("sprite", [sx, sy])
            cx, cy = c.get("counter", [cx, cy])
            ox, oy = c.get("odds", [ox, oy])

        ts, tc, to = hunt["tag_sprite"], hunt["tag_counter"], hunt["tag_odds"]
        self.canvas.create_rectangle(0,0,0,0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(ts, f"{ts}_box", "edit_box", "drag_sprite"))
        self.canvas.create_image(sx, sy, image="", tags=(ts, f"{ts}_main", "drag_sprite"))
        
        self.canvas.create_rectangle(0,0,0,0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(tc, f"{tc}_box", "edit_box", "drag_counter"))
        self.create_outlined_text(cx, cy, str(hunt["encounters_var"].get()), ("Helvetica", self.size_counter.get(), "bold"), self.text_color, tc)
        
        self.canvas.create_rectangle(0,0,0,0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(to, f"{to}_box", "edit_box", "drag_odds"))
        self.create_outlined_text(ox, oy, hunt["base_odds_var"].get(), ("Helvetica", self.size_odds.get(), "bold"), self.text_color, to)

    def toggle_vision_tracker(self):
        if self.vision_worker.is_running:
            self.vision_worker.stop_loop()
            self.vision_toggle_btn.config(text="▶ Start Vision Auto-Tracker (All Hunts)")
        else:
            if not self.tesseract_path or not os.path.exists(self.tesseract_path):
                self.tesseract_path = filedialog.askopenfilename(title="Select tesseract.exe")
            if self.tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
                self.vision_worker.start()
                self.vision_toggle_btn.config(text="⏹ Stop Vision Auto-Tracker")

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.edit_btn.config(text="✅ DONE EDITING (SAVE & HIDE BOXES)" if self.edit_mode else "🛠️ ENABLE EDIT / LAYOUT MODE")
        self.canvas.itemconfig("edit_box", state="normal" if self.edit_mode else "hidden")
        self.caught_canvas.itemconfig("caught_edit_box", state="normal" if self.edit_mode else "hidden")
        self.root.overrideredirect(not self.edit_mode)
        self.update_transparency()
        self.update_edit_boxes()
        if not self.edit_mode: self.save_layout()

    def update_edit_boxes(self):
        t = "drag_menu"
        bbox = self.canvas.bbox(f"{t}_main")
        if bbox: self.canvas.coords(f"{t}_box", bbox[0]-10, bbox[1]-10, bbox[2]+10, bbox[3]+10)

        seen_pokemon = set()
        for h in self.active_hunts:
            poke = format_for_pokeapi(h["pokemon_var"].get())
            is_dup = False
            if poke:
                if poke in seen_pokemon: is_dup = True
                else: seen_pokemon.add(poke)
            
            for tag in (h["tag_sprite"], h["tag_counter"], h["tag_odds"]):
                if is_dup:
                    self.canvas.itemconfig(f"{tag}_box", state="hidden") 
                else:
                    if self.edit_mode: self.canvas.itemconfig(f"{tag}_box", state="normal")
                    bbox = self.canvas.bbox(f"{tag}_main")
                    if bbox: self.canvas.coords(f"{tag}_box", bbox[0]-10, bbox[1]-10, bbox[2]+10, bbox[3]+10)
        
        for c in self.caught_list:
            if c["visible_var"].get():
                bbox = self.caught_canvas.bbox(f"{c['tag']}_main")
                if bbox: self.caught_canvas.coords(f"{c['tag']}_box", bbox[0]-10, bbox[1]-10, bbox[2]+10, bbox[3]+10)

    # FIX: Precise Dragging logic. Instead of moving the generic "drag_sprite" tag, it targets individual elements like "hunt_4_sprite" 
    def on_drag_start(self, event):
        items = self.canvas.find_withtag("current")
        self.drag_item = None
        if items and self.edit_mode:
            tags = self.canvas.gettags(items[0])
            for t in tags:
                if t.startswith("hunt_") and (t.endswith("_sprite") or t.endswith("_counter") or t.endswith("_odds")):
                    self.drag_item = t
                    break
                elif t == "drag_menu":
                    self.drag_item = t
                    break
        if not self.drag_item: self.drag_item = "window"
        self.drag_start_x, self.drag_start_y = (event.x_root, event.y_root) if self.drag_item == "window" else (event.x, event.y)

    def on_caught_drag_start(self, event):
        if not self.edit_mode: return
        items = self.caught_canvas.find_withtag("current")
        self.caught_drag_item = None
        if items:
            tags = self.caught_canvas.gettags(items[0])
            for c in self.caught_list:
                if c["tag"] in tags:
                    self.caught_drag_item = c["tag"]
                    self.caught_drag_start_x, self.caught_drag_start_y = event.x, event.y
                    break

    def on_drag_motion(self, event):
        if not self.drag_item: return
        if self.drag_item == "window":
            new_x = self.root.winfo_x() + event.x_root - self.drag_start_x
            new_y = self.root.winfo_y() + event.y_root - self.drag_start_y
            self.root.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height()}+{new_x}+{new_y}")
            self.drag_start_x, self.drag_start_y = event.x_root, event.y_root
        else:
            self.canvas.move(self.drag_item, event.x - self.drag_start_x, event.y - self.drag_start_y)
            self.drag_start_x, self.drag_start_y = event.x, event.y

    def on_caught_drag_motion(self, event):
        if getattr(self, 'caught_drag_item', None):
            self.caught_canvas.move(self.caught_drag_item, event.x - self.caught_drag_start_x, event.y - self.caught_drag_start_y)
            self.caught_drag_start_x, self.caught_drag_start_y = event.x, event.y

    def on_drag_release(self, event):
        if self.edit_mode: self.update_edit_boxes()
        self.drag_item = None
    
    def on_caught_drag_release(self, event):
        if getattr(self, 'caught_drag_item', None): self.caught_drag_item = None
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def toggle_menu(self, event=None):
        if event and isinstance(self.root.focus_get(), ttk.Entry): return
        if self.control_panel.winfo_ismapped(): self.control_panel.withdraw()
        else: self.control_panel.deiconify()
        return "break" 

    def update_transparency(self, event=None):
        magic_key = "#000001"
        if self.edit_mode:
            self.canvas.configure(bg=self.bg_color)
            self.root.wm_attributes("-transparentcolor", "")
            self.root.attributes("-alpha", 1.0)
            blend_bg = self.bg_color
        else:
            if self.transparent_bg_var.get():
                self.canvas.configure(bg=magic_key)
                self.root.wm_attributes("-transparentcolor", magic_key)
                blend_bg = magic_key
            else:
                self.canvas.configure(bg=self.bg_color)
                self.root.wm_attributes("-transparentcolor", "")
                blend_bg = self.bg_color
            self.root.attributes("-alpha", self.alpha_window.get())

        c_alpha = 1.0 if self.edit_mode else self.alpha_counter.get()
        o_alpha = 1.0 if self.edit_mode else self.alpha_odds.get()
        m_alpha = 1.0 if self.edit_mode else self.alpha_menu.get()
        s_alpha = 1.0 if self.edit_mode else self.alpha_sprite.get()

        if m_alpha <= 0.01:
            self.canvas.itemconfig("drag_menu_main", state="hidden")
            self.canvas.itemconfig("drag_menu_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_menu_main", state="normal", fill=self.blend_color("#ffffff", blend_bg, m_alpha))
            self.canvas.itemconfig("drag_menu_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, m_alpha))

        seen_pokemon = set()

        for hunt in self.active_hunts:
            tc, to, ts = hunt["tag_counter"], hunt["tag_odds"], hunt["tag_sprite"]
            
            poke = format_for_pokeapi(hunt["pokemon_var"].get())
            is_duplicate = False
            if poke:
                if poke in seen_pokemon:
                    is_duplicate = True
                else:
                    seen_pokemon.add(poke)

            if is_duplicate:
                self.canvas.itemconfig(f"{tc}_main", state="hidden")
                self.canvas.itemconfig(f"{tc}_shadow", state="hidden")
                self.canvas.itemconfig(f"{to}_main", state="hidden")
                self.canvas.itemconfig(f"{to}_shadow", state="hidden")
                self.canvas.itemconfig(f"{ts}_main", state="hidden")
                self.canvas.itemconfig(f"{ts}_box", state="hidden")
                self.canvas.itemconfig(f"{tc}_box", state="hidden")
                self.canvas.itemconfig(f"{to}_box", state="hidden")
                continue

            if c_alpha <= 0.01:
                self.canvas.itemconfig(f"{tc}_main", state="hidden")
                self.canvas.itemconfig(f"{tc}_shadow", state="hidden")
            else:
                self.canvas.itemconfig(f"{tc}_main", state="normal", fill=self.blend_color(self.text_color, blend_bg, c_alpha))
                self.canvas.itemconfig(f"{tc}_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, c_alpha))

            if o_alpha <= 0.01:
                self.canvas.itemconfig(f"{to}_main", state="hidden")
                self.canvas.itemconfig(f"{to}_shadow", state="hidden")
            else:
                self.canvas.itemconfig(f"{to}_main", state="normal", fill=self.blend_color(self.text_color, blend_bg, o_alpha))
                self.canvas.itemconfig(f"{to}_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, o_alpha))

            if hunt["base_pil"]:
                if s_alpha <= 0.01:
                    self.canvas.itemconfig(f"{ts}_main", image="", state="hidden")
                else:
                    sz = self.size_sprite.get()
                    img = hunt["base_pil"].resize((sz, sz), Image.Resampling.NEAREST).convert("RGBA")
                    if s_alpha < 1.0:
                        r, g, b, a = img.split()
                        a = a.point(lambda p: int(p * s_alpha))
                        img = Image.merge("RGBA", (r, g, b, a))
                    hunt["photo"] = ImageTk.PhotoImage(img)
                    self.canvas.itemconfig(f"{ts}_main", image=hunt["photo"], state="normal")
                    
        if self.edit_mode: self.update_edit_boxes()

    def refresh_text_styles(self):
        cf, of = ("Helvetica", self.size_counter.get(), "bold"), ("Helvetica", self.size_odds.get(), "bold")
        for hunt in self.active_hunts:
            self.canvas.itemconfig(f"{hunt['tag_counter']}_main", font=cf)
            self.canvas.itemconfig(f"{hunt['tag_counter']}_shadow", font=cf)
            self.canvas.itemconfig(f"{hunt['tag_odds']}_main", font=of)
            self.canvas.itemconfig(f"{hunt['tag_odds']}_shadow", font=of)
        if self.edit_mode: self.update_edit_boxes()

    def save_layout(self):
        caught_data = []
        for c in self.caught_list:
            caught_data.append({"name": c["name"], "coords": self.caught_canvas.coords(f"{c['tag']}_main"), "visible": c["visible_var"].get(), "size": c["size_var"].get()})
        
        layout = {
            "tesseract": self.tesseract_path, "geom": self.root.geometry(),
            "sizes": {"sprite": self.size_sprite.get(), "counter": self.size_counter.get(), "odds": self.size_odds.get()},
            "text_color": self.text_color, "outline_color": self.outline_color, "bg_color": self.bg_color,
            "transparent_bg": self.transparent_bg_var.get(),
            "alphas": {
                "window": self.alpha_window.get(), "sprite": self.alpha_sprite.get(),
                "counter": self.alpha_counter.get(), "odds": self.alpha_odds.get(),
                "menu": self.alpha_menu.get()
            },
            "caught_sprites": caught_data,
            "hunts": []
        }
        for h in self.active_hunts:
            layout["hunts"].append({
                "id": h["id"], "pokemon": h["pokemon_var"].get(), "encounters": h["encounters_var"].get(),
                "base_odds": h["base_odds_var"].get(), "require_extra": h["require_extra_var"].get(), "extra_word": h["extra_word_var"].get(),
                "key_inc": h["key_inc"].get(), "key_dec": h["key_dec"].get(), "key_caught": h["key_caught"].get(),
                "active_mode": h.get("active_mode"), "screen_region": h.get("screen_region"), "camera_index": h.get("camera_index"), "camera_rois": h.get("camera_rois", []),
                "coords": {
                    "sprite": self.canvas.coords(f"{h['tag_sprite']}_main"),
                    "counter": self.canvas.coords(f"{h['tag_counter']}_main"),
                    "odds": self.canvas.coords(f"{h['tag_odds']}_main")
                }
            })
        with open(LAYOUT_FILE, "w") as f: json.dump(layout, f)

    def load_layout(self):
        if not os.path.exists(LAYOUT_FILE): return
        try:
            with open(LAYOUT_FILE, "r") as f: data = json.load(f)
            self.tesseract_path = get_tesseract_path(data.get("tesseract", ""))
            
            if data.get("geom"):
                geom = data["geom"]
                try:
                    w = int(geom.split('x')[0])
                    h = int(geom.split('x')[1].split('+')[0])
                    if w < 100 or h < 100:
                        geom = f"800x600+{geom.split('+')[1]}+{geom.split('+')[2]}"
                except:
                    pass
                self.root.geometry(geom)

            sz = data.get("sizes", {})
            self.size_sprite.set(sz.get("sprite", 120)); self.size_counter.set(sz.get("counter", 56)); self.size_odds.set(sz.get("odds", 16))
            
            self.text_color = data.get("text_color", "#ffffff")
            self.outline_color = data.get("outline_color", "#000000")
            self.bg_color = data.get("bg_color", "#00ff00")
            self.transparent_bg_var.set(data.get("transparent_bg", False))
            
            alphas = data.get("alphas", {})
            self.alpha_window.set(alphas.get("window", 1.0))
            self.alpha_sprite.set(alphas.get("sprite", 1.0))
            self.alpha_counter.set(alphas.get("counter", 1.0))
            self.alpha_odds.set(alphas.get("odds", 1.0))
            self.alpha_menu.set(alphas.get("menu", 1.0))
            
            for hd in data.get("hunts", []): self.add_new_hunt_ui(hd)
            
            for item in data.get("caught_sprites", []):
                name, c_coords, visible, saved_size = item.get("name", "pokemon"), item.get("coords"), item.get("visible", True), item.get("size", 120)
                if c_coords and len(c_coords) >= 2:
                    try:
                        resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{name.lower()}")
                        if resp.status_code == 200:
                            s_url = resp.json()['sprites']['front_shiny']
                            img_resp = requests.get(s_url)
                            raw_img = Image.open(BytesIO(img_resp.content))
                            pil_img = raw_img.resize((saved_size, saved_size), Image.Resampling.NEAREST)
                            tag_base = f"caught_{len(self.caught_list)}_{int(time.time())}"
                            self.caught_canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(tag_base, f"{tag_base}_box", "caught_edit_box"))
                            photo = ImageTk.PhotoImage(pil_img)
                            self.caught_canvas.create_image(c_coords[0], c_coords[1], image=photo, state="normal" if visible else "hidden", tags=(tag_base, f"{tag_base}_main"))
                            self.caught_list.append({"name": name, "raw_image": raw_img, "photo": photo, "tag": tag_base, "visible_var": tk.BooleanVar(value=visible), "size_var": tk.IntVar(value=saved_size)})
                    except: pass
            self.rebuild_caught_manager_ui()
            
            self.refresh_text_styles()
            self.update_transparency()
        except Exception as e: print("Load error:", e)

    def on_closing(self):
        self.vision_worker.stop_loop()
        self.save_layout()
        try:
            self.control_panel.destroy()
            self.caught_window.destroy()
            self.root.destroy()
        except: pass
        os._exit(0)

if __name__ == "__main__":
    app = VisionShinyTracker(tk.Tk())
    app.root.mainloop()