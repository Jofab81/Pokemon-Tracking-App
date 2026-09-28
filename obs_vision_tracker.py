import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog
import requests
from io import BytesIO
from PIL import Image, ImageTk
import json
import os
import threading
import time
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

LAYOUT_FILE = "camera_layout.json"

# --- Smart Path Resolver ---
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
        if os.path.exists(path):
            return path
            
    return ""

# --- Text & API Helper Functions ---
def format_for_pokeapi(name):
    name = name.strip().lower()
    name = name.replace(":", "")     
    name = name.replace("'", "")     
    name = name.replace(".", "")     
    name = name.replace("♀", "-f")   
    name = name.replace("♂", "-m")   
    name = name.replace(" ", "-")    
    while "--" in name:
        name = name.replace("--", "-")
    return name

def normalize_for_ocr(text):
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())

# --- Camera Vision Worker ---
class CameraVisionTrackerWorker:
    """Reads directly from a hardware webcam or OBS Virtual Camera."""
    def __init__(self, callback_function, get_target_pokemon_function, get_cam_index_function):
        self.is_running = False
        self.callback = callback_function
        self.get_target_pokemon = get_target_pokemon_function  
        self.get_cam_index = get_cam_index_function
        self.thread = None
        self.roi = None  # Region of Interest: (x, y, w, h)
        self.last_encounter_time = 0
        self.lockout_duration = 10.0
        self.cap = None

    def start_loop(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._vision_loop, daemon=True)
            self.thread.start()
            print("-> Camera Hardware OCR Tracker started.")
            return True
        return False

    def stop_loop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()

    def _vision_loop(self):
        cam_idx = self.get_cam_index()
        self.cap = cv2.VideoCapture(cam_idx)
        
        # Give the camera a second to warm up
        time.sleep(1.0)
        
        while self.is_running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.5)
                    continue

                raw_target = self.get_target_pokemon()
                target_clean = normalize_for_ocr(raw_target)
                
                if not target_clean:
                    time.sleep(1.0)
                    continue

                # Crop the camera frame to the selected region
                if self.roi and len(self.roi) == 4 and self.roi[2] > 0 and self.roi[3] > 0:
                    x, y, w, h = self.roi
                    crop_img = frame[y:y+h, x:x+w]
                else:
                    # Fallback to full frame if no region selected (not recommended for performance)
                    crop_img = frame

                # Convert to grayscale and apply Otsu Thresholding
                live_gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
                _, binary_img = cv2.threshold(live_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                # Run Tesseract
                raw_screen_text = pytesseract.image_to_string(binary_img, config='--psm 6')
                screen_clean = normalize_for_ocr(raw_screen_text)

                if target_clean in screen_clean:
                    current_time = time.time()
                    if (current_time - self.last_encounter_time) > self.lockout_duration:
                        print(f"🔥 CAMERA MATCH! Found '{raw_target}' in text: '{raw_screen_text.strip()}'")
                        self.callback()  
                        self.last_encounter_time = current_time
                        time.sleep(3.0) 

            except Exception as e:
                print(f"Camera loop error: {e}")
            
            # Fast scan rate since we aren't pulling from the desktop window manager
            time.sleep(0.2)
            
        if self.cap:
            self.cap.release()


class VisionShinyTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Shiny Tracker - Camera Overlay")
        self.root.geometry("600x400")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # --- Variables ---
        self.tesseract_path = ""
        self.pokemon_var = tk.StringVar()
        self.encounters_var = tk.IntVar(value=0)
        self.odds_var = tk.StringVar(value="Odds: 1/4096")
        self.base_odds_var = tk.StringVar(value="Gen 6+ (1/4096 Standard)")
        self.cam_index_var = tk.IntVar(value=0) # Default to first webcam
        
        # Size Controls
        self.size_sprite = tk.IntVar(value=120)
        self.size_counter = tk.IntVar(value=56)
        self.size_odds = tk.IntVar(value=16)

        # Hotkeys
        self.key_inc = tk.StringVar(value="space")
        self.key_dec = tk.StringVar(value="Down")
        self.key_caught = tk.StringVar(value="c")
        self.capturing_action = None

        self.charm_var = tk.BooleanVar()
        self.masuda_var = tk.BooleanVar()
        self.sandwich_var = tk.BooleanVar()

        self.text_color = "#ffffff"
        self.outline_color = "#000000" 
        self.bg_color = "#00ff00" 
        
        self.base_pil_image = None
        self.current_sprite = None
        self.edit_mode = False
        self.caught_list = []

        self.caught_window = tk.Toplevel(self.root)
        self.caught_window.attributes("-fullscreen", True)
        self.caught_window.attributes("-topmost", True)
        caught_magic_key = "#000002"
        self.caught_window.config(bg=caught_magic_key)
        self.caught_window.wm_attributes("-transparentcolor", caught_magic_key)
        
        self.caught_canvas = tk.Canvas(self.caught_window, bg=caught_magic_key, highlightthickness=0)
        self.caught_canvas.pack(fill="both", expand=True)

        # --- Camera Worker Initialization ---
        self.vision_worker = CameraVisionTrackerWorker(
            callback_function=self.increment,
            get_target_pokemon_function=lambda: self.pokemon_var.get(),
            get_cam_index_function=lambda: self.cam_index_var.get()
        )

        # --- Canvas Engine ---
        self.canvas = tk.Canvas(self.root, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_sprite", "drag_sprite_box", "edit_box"))
        self.canvas.create_image(150, 200, image="", tags=("drag_sprite", "drag_sprite_main"))

        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_counter", "drag_counter_box", "edit_box"))
        self.create_outlined_text(350, 180, "0", ("Helvetica", 56, "bold"), self.text_color, "drag_counter")

        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_odds", "drag_odds_box", "edit_box"))
        self.create_outlined_text(350, 260, "Odds: 1/4096", ("Helvetica", 16, "bold"), self.text_color, "drag_odds")

        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_box_menu", "drag_menu_box", "edit_box"))
        self.create_outlined_text(80, 30, "⚙️ Menu (Tab)", ("Helvetica", 12, "bold"), "#ffffff", "drag_menu")

        self.drag_item = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.dragged = False

        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_release)

        self.caught_canvas.bind("<ButtonPress-1>", self.on_caught_drag_start)
        self.caught_canvas.bind("<B1-Motion>", self.on_caught_drag_motion)
        self.caught_canvas.bind("<ButtonRelease-1>", self.on_caught_drag_release)

        self.control_panel = tk.Toplevel(self.root)
        self.control_panel.title("Camera Stream Control Panel")
        self.control_panel.geometry("450x980")
        self.control_panel.protocol("WM_DELETE_WINDOW", self.on_closing) 
        
        self.create_control_panel()
        self.load_layout()
        
        self.encounters_var.trace_add("write", self.calculate_odds)
        self.base_odds_var.trace_add("write", self.calculate_odds)
        self.charm_var.trace_add("write", self.calculate_odds)
        self.masuda_var.trace_add("write", self.calculate_odds)
        self.sandwich_var.trace_add("write", self.calculate_odds)
        self.size_sprite.trace_add("write", lambda *args: self.update_transparency())
        self.size_counter.trace_add("write", lambda *args: self.refresh_text_styles())
        self.size_odds.trace_add("write", lambda *args: self.refresh_text_styles())

        self.root.bind_all("<Key>", self.handle_global_key)
        self.root.bind_all("<Tab>", self.toggle_menu)
        self.control_panel.deiconify()

    def create_outlined_text(self, x, y, text, font, text_color, tag):
        offsets = [(-2, -2), (0, -2), (2, -2), (-2, 0), (2, 0), (-2, 2), (0, 2), (2, 2)]
        for dx, dy in offsets:
            self.canvas.create_text(x+dx, y+dy, text=text, font=font, fill=self.outline_color, tags=(tag, f"{tag}_shadow"))
        self.canvas.create_text(x, y, text=text, font=font, fill=text_color, tags=(tag, f"{tag}_main"))

    def refresh_text_styles(self):
        c_font = ("Helvetica", self.size_counter.get(), "bold")
        o_font = ("Helvetica", self.size_odds.get(), "bold")
        for t in ["drag_counter_main", "drag_counter_shadow"]:
            self.canvas.itemconfig(t, font=c_font)
        for t in ["drag_odds_main", "drag_odds_shadow"]:
            self.canvas.itemconfig(t, font=o_font)
        if self.edit_mode:
            self.update_edit_boxes()

    def create_control_panel(self):
        self.edit_btn = ttk.Button(self.control_panel, text="🛠️ ENABLE EDIT / LAYOUT MODE", command=self.toggle_edit_mode)
        self.edit_btn.pack(fill="x", padx=10, pady=(10, 5))

        setup_frame = ttk.LabelFrame(self.control_panel, text="Hunt Setup", padding=10)
        setup_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(setup_frame, text="Pokémon:").grid(row=0, column=0, pady=5)
        ttk.Entry(setup_frame, textvariable=self.pokemon_var, width=15).grid(row=0, column=1, pady=5)
        ttk.Button(setup_frame, text="Load", command=self.load_pokemon).grid(row=0, column=2, padx=5)
        
        ttk.Label(setup_frame, text="Game / Method:").grid(row=1, column=0, pady=5)
        odds_presets = [
            "Gen 6+ (1/4096 Standard)", "Gen 1-5 (1/8192 Standard)", 
            "Dynamax Adventures (1/300)", "Dynamax Adventures + Charm (1/100)",
            "SV: Outbreak / Sandwich Hunt", "Legends Arceus / Z-A: Outbreak/MMO"
        ]
        ttk.Combobox(setup_frame, textvariable=self.base_odds_var, values=odds_presets, state="readonly", width=20).grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Button(setup_frame, text="✨ Register Current as Caught!", command=self.register_caught).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5,5))
        
        self.caught_mgr_frame = ttk.LabelFrame(setup_frame, text="Manage Caught Pokémon", padding=5)
        self.caught_mgr_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=5)
        self.caught_checkboxes_container = ttk.Frame(self.caught_mgr_frame)
        self.caught_checkboxes_container.pack(fill="x")

        size_frame = ttk.LabelFrame(self.control_panel, text="Element Sizes", padding=10)
        size_frame.pack(fill="x", padx=10, pady=5)
        self.make_slider(size_frame, "Sprite Size:", self.size_sprite, 120, 500, None)
        self.make_slider(size_frame, "Counter Size:", self.size_counter, 20, 150, None)
        self.make_slider(size_frame, "Odds Size:", self.size_odds, 10, 40, None)

        ctrl_frame = ttk.LabelFrame(self.control_panel, text="Counter Controls", padding=10)
        ctrl_frame.pack(fill="x", padx=10, pady=5)
        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill="x", pady=2)
        ttk.Button(btn_row, text="-1", command=self.decrement, width=5).pack(side="left", padx=2)
        ttk.Button(btn_row, text="+1 Encounter", command=self.increment).pack(side="left", expand=True, fill="x", padx=2)

        # --- Hardware Camera Tracker Frame ---
        vision_frame = ttk.LabelFrame(self.control_panel, text="📷 Hardware / OBS Camera Tracker", padding=10)
        vision_frame.pack(fill="x", padx=10, pady=5)

        cam_row = ttk.Frame(vision_frame)
        cam_row.pack(fill="x", pady=2)
        ttk.Label(cam_row, text="Camera Index:").pack(side="left")
        ttk.Spinbox(cam_row, from_=0, to=10, textvariable=self.cam_index_var, width=5).pack(side="left", padx=5)
        ttk.Label(cam_row, text="(0 = Webcam, 1+ = OBS/Capture Card)").pack(side="left", fill="x", expand=True)

        ttk.Button(vision_frame, text="🎯 Preview Camera & Select Target Area", command=self.open_camera_roi).pack(fill="x", pady=5)
        self.vision_toggle_btn = ttk.Button(vision_frame, text="Start Hardware Auto-Tracker", command=self.toggle_vision_tracker)
        self.vision_toggle_btn.pack(fill="x", pady=2)

        boosts_frame = ttk.LabelFrame(self.control_panel, text="Active Boosts", padding=5)
        boosts_frame.pack(fill="x", padx=10, pady=5)
        ttk.Checkbutton(boosts_frame, text="Shiny Charm", variable=self.charm_var).pack(side="left", padx=5)
        ttk.Checkbutton(boosts_frame, text="Masuda", variable=self.masuda_var).pack(side="left", padx=5)
        ttk.Checkbutton(boosts_frame, text="Sandwich", variable=self.sandwich_var).pack(side="left", padx=5)

        settings_frame = ttk.LabelFrame(self.control_panel, text="Global Colors", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        btn_frame = ttk.Frame(settings_frame)
        btn_frame.pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Text Color", command=self.change_text_color).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(btn_frame, text="Outline Color", command=self.change_outline_color).pack(side="right", expand=True, fill="x", padx=(2, 0))
        ttk.Button(settings_frame, text="Change Background Color", command=self.change_bg_color).pack(fill="x", pady=2)
        self.transparent_bg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Make Background 100% Invisible", variable=self.transparent_bg_var, command=self.update_transparency).pack(anchor="w", pady=(5,0))

        alpha_frame = ttk.LabelFrame(self.control_panel, text="Visibility Controls", padding=10)
        alpha_frame.pack(fill="x", padx=10, pady=5)
        self.alpha_window = tk.DoubleVar(value=1.0)
        self.alpha_sprite = tk.DoubleVar(value=1.0)
        self.alpha_counter = tk.DoubleVar(value=1.0)
        self.alpha_odds = tk.DoubleVar(value=1.0)
        self.alpha_menu = tk.DoubleVar(value=1.0)
        self.make_slider(alpha_frame, "Overall Window:", self.alpha_window, 0.1, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Pokemon Sprite:", self.alpha_sprite, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Counter Text:", self.alpha_counter, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Odds Text:", self.alpha_odds, 0.0, 1.0, self.update_transparency)

    def open_camera_roi(self):
        """Uses OpenCV's native selectROI to draw a box on the live camera feed."""
        if self.vision_worker.is_running:
            messagebox.showwarning("Warning", "Please stop the tracker before selecting a new region.")
            return

        idx = self.cam_index_var.get()
        cap = cv2.VideoCapture(idx)
        
        # Give camera time to init and grab a stable frame
        time.sleep(1.0)
        ret, frame = cap.read()
        
        if not ret:
            messagebox.showerror("Camera Error", f"Could not connect to camera at index {idx}.\nMake sure OBS Virtual Camera is turned ON or your capture card is plugged in.")
            cap.release()
            return

        messagebox.showinfo("Instructions", "A camera window will open.\n\n1. Drag a box over the text area.\n2. Press ENTER to confirm and close the window.")
        
        # Open OpenCV's built-in crop tool
        roi = cv2.selectROI("Draw OCR Region (Press ENTER when done)", frame, fromCenter=False, showCrosshair=True)
        cv2.destroyWindow("Draw OCR Region (Press ENTER when done)")
        cap.release()

        # Check if they actually drew a box (width and height > 0)
        if roi[2] > 0 and roi[3] > 0:
            self.vision_worker.roi = roi
            self.save_layout()
            messagebox.showinfo("Success", f"Camera region saved successfully!\nCrop area: {roi}")
        else:
            messagebox.showinfo("Canceled", "No region selected. It will scan the whole frame (slower).")

    def toggle_vision_tracker(self):
        if self.vision_worker.is_running:
            self.vision_worker.stop_loop()
            self.vision_toggle_btn.config(text="Start Hardware Auto-Tracker")
            return

        if not getattr(self, "tesseract_path", "") or not os.path.exists(self.tesseract_path):
            messagebox.showinfo("Tesseract Required", "Tesseract-OCR was not found in the default Windows folders.\n\nPlease locate your 'tesseract.exe' file to enable the hardware tracker.")
            file_path = filedialog.askopenfilename(title="Select tesseract.exe", filetypes=[("Executable", "*.exe")])
            if file_path:
                self.tesseract_path = file_path
                self.save_layout() 
            else:
                return 

        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
        if self.vision_worker.start_loop():
            self.vision_toggle_btn.config(text="Stop Hardware Auto-Tracker (Running...)")

    def make_slider(self, parent, text, variable, from_val, to_val, command):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=1)
        ttk.Label(frame, text=text, width=18, anchor="w").pack(side="left")
        slider = ttk.Scale(frame, from_=from_val, to=to_val, orient="horizontal", variable=variable, command=command)
        slider.pack(side="right", expand=True, fill="x")

    def rebuild_caught_manager_ui(self):
        for widget in self.caught_checkboxes_container.winfo_children():
            widget.destroy()
        for c in self.caught_list:
            row = ttk.Frame(self.caught_checkboxes_container)
            row.pack(fill="x", padx=2, pady=2)
            cb = ttk.Checkbutton(row, text=c["name"].capitalize(), variable=c["visible_var"], command=lambda item=c: self.toggle_caught_visibility(item))
            cb.pack(side="left", padx=2)
            slider = ttk.Scale(row, from_=120, to=500, orient="horizontal", variable=c["size_var"], command=lambda val, item=c: self.update_caught_size(item, float(val)))
            slider.pack(side="right", expand=True, fill="x", padx=5)

    def toggle_caught_visibility(self, item):
        state = "normal" if item["visible_var"].get() else "hidden"
        self.caught_canvas.itemconfig(f"{item['tag']}_main", state=state)
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def update_caught_size(self, item, new_size_float):
        new_size = int(new_size_float)
        if item["raw_image"]:
            resized = item["raw_image"].resize((new_size, new_size), Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(resized)
            item["photo"] = photo
            self.caught_canvas.itemconfig(f"{item['tag']}_main", image=photo)
            if self.edit_mode: self.update_edit_boxes()
            self.save_layout()

    def start_key_capture(self, action_type):
        self.capturing_action = action_type
        self.root.bind_all("<Key>", self.capture_key_press)
        
        if action_type == 'inc': self.btn_inc_bind.config(text="Press any key...")
        elif action_type == 'dec': self.btn_dec_bind.config(text="Press any key...")
        elif action_type == 'caught': self.btn_caught_bind.config(text="Press any key...")

    def capture_key_press(self, event):
        if event.keysym == "Tab": return
        if self.capturing_action:
            key_sym = event.keysym
            if self.capturing_action == 'inc':
                self.key_inc.set(key_sym)
                self.btn_inc_bind.config(text=f"Key: {key_sym}")
            elif self.capturing_action == 'dec':
                self.key_dec.set(key_sym)
                self.btn_dec_bind.config(text=f"Key: {key_sym}")
            elif self.capturing_action == 'caught':
                self.key_caught.set(key_sym)
                self.btn_caught_bind.config(text=f"Key: {key_sym}")
            self.capturing_action = None
            self.root.bind_all("<Key>", self.handle_global_key)

    def handle_global_key(self, event):
        if isinstance(self.root.focus_get(), ttk.Entry): return
        key = event.keysym.lower()
        if key == self.key_inc.get().lower(): self.increment()
        elif key == self.key_dec.get().lower(): self.decrement()
        elif key == self.key_caught.get().lower(): self.register_caught()

    def register_caught(self):
        raw_pokemon = self.pokemon_var.get().strip()
        if not raw_pokemon: return
        pokemon_slug = format_for_pokeapi(raw_pokemon)
        try:
            resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_slug}")
            if resp.status_code == 200:
                s_url = resp.json()['sprites']['front_shiny']
                if s_url:
                    img_resp = requests.get(s_url)
                    raw_img = Image.open(BytesIO(img_resp.content))
                    default_size = 120
                    pil_img = raw_img.resize((default_size, default_size), Image.Resampling.NEAREST)
                    existing = next((c for c in self.caught_list if c["name"].lower() == pokemon_slug), None)
                    if not existing:
                        tag_base = f"caught_{len(self.caught_list)}_{int(time.time())}"
                        photo = ImageTk.PhotoImage(pil_img)
                        self.caught_canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(tag_base, f"{tag_base}_box", "caught_edit_box"))
                        self.caught_canvas.create_image(400, 300, image=photo, tags=(tag_base, f"{tag_base}_main"))
                        self.caught_list.append({"name": pokemon_slug, "raw_image": raw_img, "photo": photo, "tag": tag_base, "visible_var": tk.BooleanVar(value=True), "size_var": tk.IntVar(value=default_size)})
                        self.rebuild_caught_manager_ui()
                        self.save_layout()
        except:
            pass

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_btn.config(text="✅ DONE EDITING")
            self.canvas.itemconfig("edit_box", state="normal")
            self.caught_canvas.itemconfig("caught_edit_box", state="normal")
            self.root.overrideredirect(False)
            self.update_transparency()
            self.update_edit_boxes()
        else:
            self.edit_btn.config(text="🛠️ ENABLE EDIT MODE")
            self.canvas.itemconfig("edit_box", state="hidden")
            self.caught_canvas.itemconfig("caught_edit_box", state="hidden")
            self.root.overrideredirect(True)
            self.update_transparency()
            self.save_layout()

    def update_edit_boxes(self):
        for tag in ["drag_sprite", "drag_counter", "drag_odds", "drag_menu"]:
            bbox = self.canvas.bbox(f"{tag}_main")
            if bbox: self.canvas.coords(f"{tag}_box", bbox[0]-10, bbox[1]-10, bbox[2]+10, bbox[3]+10)
        for c in self.caught_list:
            if c["visible_var"].get():
                bbox = self.caught_canvas.bbox(f"{c['tag']}_main")
                if bbox: self.caught_canvas.coords(f"{c['tag']}_box", bbox[0]-10, bbox[1]-10, bbox[2]+10, bbox[3]+10)

    def on_drag_start(self, event):
        items = self.canvas.find_withtag("current")
        if not items:
            self.drag_item = "window"
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            return
        tags = self.canvas.gettags(items[0])
        if self.edit_mode:
            if "drag_counter" in tags: self.drag_item = "drag_counter"
            elif "drag_odds" in tags: self.drag_item = "drag_odds"
            elif "drag_menu" in tags: self.drag_item = "drag_menu"
            elif "drag_sprite" in tags: self.drag_item = "drag_sprite"
            else: self.drag_item = None
        else:
            self.drag_item = "window"
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            return
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.dragged = False

    def on_caught_drag_start(self, event):
        if not self.edit_mode: return
        items = self.caught_canvas.find_withtag("current")
        if not items:
            self.caught_drag_item = None
            return
        tags = self.caught_canvas.gettags(items[0])
        for c in self.caught_list:
            if c["tag"] in tags:
                self.caught_drag_item = c["tag"]
                self.caught_drag_start_x = event.x
                self.caught_drag_start_y = event.y
                break

    def on_drag_motion(self, event):
        if not self.drag_item: return
        self.dragged = True
        if self.drag_item == "window":
            dx, dy = event.x_root - self.drag_start_x, event.y_root - self.drag_start_y
            self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")
            self.drag_start_x, self.drag_start_y = event.x_root, event.y_root
        else:
            dx, dy = event.x - self.drag_start_x, event.y - self.drag_start_y
            self.canvas.move(self.drag_item, dx, dy)
            self.drag_start_x, self.drag_start_y = event.x, event.y

    def on_caught_drag_motion(self, event):
        if hasattr(self, 'caught_drag_item') and self.caught_drag_item:
            dx, dy = event.x - self.caught_drag_start_x, event.y - self.caught_drag_start_y
            self.caught_canvas.move(self.caught_drag_item, dx, dy)
            self.caught_drag_start_x, self.caught_drag_start_y = event.x, event.y

    def on_drag_release(self, event):
        if self.drag_item == "drag_menu" and not self.dragged: self.toggle_menu()
        if self.edit_mode: self.update_edit_boxes()
        self.drag_item = None
        self.save_layout()

    def on_caught_drag_release(self, event):
        if hasattr(self, 'caught_drag_item'): self.caught_drag_item = None
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def toggle_menu(self, event=None):
        if self.control_panel.winfo_ismapped(): self.control_panel.withdraw()
        else: self.control_panel.deiconify()

    def calculate_odds(self, *args):
        selection = self.base_odds_var.get()
        if "Dynamax Adventures + Charm" in selection: final_odds = 100; display_text = f"Odds: 1/{final_odds} (Dynamax Adv.)"
        elif "Dynamax Adventures" in selection: final_odds = 300; display_text = f"Odds: 1/{final_odds} (Dynamax Adv.)"
        else:
            base = 8192 if "8192" in selection else 4096
            rolls = 1 
            if self.charm_var.get(): rolls += 2
            if self.masuda_var.get(): rolls += 5 if base == 4096 else 4
            if self.sandwich_var.get(): rolls += 3
            if "SV: Outbreak" in selection: rolls += 2 
            elif "Legends Arceus" in selection: rolls += 3 
            final_odds = max(1, base / rolls)
            display_text = f"Odds: {rolls}/{base} (1/{final_odds:.0f})"
        self.odds_var.set(display_text)
        self.canvas.itemconfig("drag_odds_main", text=self.odds_var.get())
        self.canvas.itemconfig("drag_odds_shadow", text=self.odds_var.get())
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def load_pokemon(self, silent=False):
        raw_pokemon = self.pokemon_var.get()
        if not raw_pokemon.strip(): return
        pokemon = format_for_pokeapi(raw_pokemon)
        try:
            response = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon}")
            if response.status_code == 200:
                sprite_url = response.json()['sprites']['front_shiny']
                if sprite_url:
                    img_resp = requests.get(sprite_url)
                    self.base_pil_image = Image.open(BytesIO(img_resp.content))
                    self.update_transparency() 
                    if self.edit_mode: self.update_edit_boxes()
                    self.save_layout()
        except:
            pass

    def increment(self): self.root.after(0, self._do_increment)
    def _do_increment(self):
        self.encounters_var.set(self.encounters_var.get() + 1)
        self.canvas.itemconfig("drag_counter_main", text=str(self.encounters_var.get()))
        self.canvas.itemconfig("drag_counter_shadow", text=str(self.encounters_var.get()))
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def decrement(self): 
        if self.encounters_var.get() > 0: 
            self.encounters_var.set(self.encounters_var.get() - 1)
            self.canvas.itemconfig("drag_counter_main", text=str(self.encounters_var.get()))
            self.canvas.itemconfig("drag_counter_shadow", text=str(self.encounters_var.get()))
            if self.edit_mode: self.update_edit_boxes()
            self.save_layout()

    def change_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color", initialcolor=self.text_color)[1]
        if color: self.text_color = color; self.update_transparency(); self.save_layout()

    def change_outline_color(self):
        color = colorchooser.askcolor(title="Choose Outline Color", initialcolor=self.outline_color)[1]
        if color: self.outline_color = color; self.update_transparency(); self.save_layout()

    def change_bg_color(self):
        color = colorchooser.askcolor(title="Choose Background Color", initialcolor=self.bg_color)[1]
        if color: self.bg_color = color; self.update_transparency(); self.save_layout()

    def blend_color(self, hex_fg, hex_bg, alpha):
        if alpha <= 0.01: return hex_bg 
        if alpha >= 0.99: return hex_fg 
        r1, g1, b1 = int(hex_fg[1:3], 16), int(hex_fg[3:5], 16), int(hex_fg[5:7], 16)
        r2, g2, b2 = int(hex_bg[1:3], 16), int(hex_bg[3:5], 16), int(hex_bg[5:7], 16)
        return f"#{int(r1 * alpha + r2 * (1 - alpha)):02x}{int(g1 * alpha + g2 * (1 - alpha)):02x}{int(b1 * alpha + b2 * (1 - alpha)):02x}"

    def update_transparency(self, event=None):
        if self.edit_mode:
            self.canvas.configure(bg=self.bg_color)
            self.root.wm_attributes("-transparentcolor", "")
            self.root.attributes("-alpha", 1.0)
            blend_bg = self.bg_color
        else:
            if self.transparent_bg_var.get():
                magic_key = "#000001" 
                self.canvas.configure(bg=magic_key)
                self.root.wm_attributes("-transparentcolor", magic_key)
                blend_bg = magic_key
            else:
                self.canvas.configure(bg=self.bg_color)
                self.root.wm_attributes("-transparentcolor", "")
                blend_bg = self.bg_color
            self.root.attributes("-alpha", self.alpha_window.get())

        c_alpha, o_alpha = (1.0, 1.0) if self.edit_mode else (self.alpha_counter.get(), self.alpha_odds.get())
        m_alpha, s_alpha = (1.0, 1.0) if self.edit_mode else (self.alpha_menu.get(), self.alpha_sprite.get())

        if c_alpha <= 0.01:
            self.canvas.itemconfig("drag_counter_main", state="hidden"); self.canvas.itemconfig("drag_counter_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_counter_main", state="normal", fill=self.blend_color(self.text_color, blend_bg, c_alpha))
            self.canvas.itemconfig("drag_counter_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, c_alpha))

        if o_alpha <= 0.01:
            self.canvas.itemconfig("drag_odds_main", state="hidden"); self.canvas.itemconfig("drag_odds_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_odds_main", state="normal", fill=self.blend_color(self.text_color, blend_bg, o_alpha))
            self.canvas.itemconfig("drag_odds_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, o_alpha))

        if m_alpha <= 0.01:
            self.canvas.itemconfig("drag_menu_main", state="hidden"); self.canvas.itemconfig("drag_menu_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_menu_main", state="normal", fill=self.blend_color("#ffffff", blend_bg, m_alpha))
            self.canvas.itemconfig("drag_menu_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, m_alpha))

        if self.base_pil_image:
            if s_alpha <= 0.01:
                self.canvas.itemconfig("drag_sprite_main", image="", state="hidden")
            else:
                current_size = self.size_sprite.get()
                img = self.base_pil_image.resize((current_size, current_size), Image.Resampling.NEAREST).convert("RGBA")
                if s_alpha < 1.0:
                    r, g, b, a = img.split()
                    a = a.point(lambda p: int(p * s_alpha))
                    img = Image.merge("RGBA", (r, g, b, a))
                self.current_sprite = ImageTk.PhotoImage(img)
                self.canvas.itemconfig("drag_sprite_main", image=self.current_sprite, state="normal")
        if self.edit_mode: self.update_edit_boxes()

    def move_group_to(self, main_tag, group_tag, new_x, new_y):
        curr = self.canvas.coords(main_tag)
        if curr and len(curr) >= 2: self.canvas.move(group_tag, new_x - curr[0], new_y - curr[1])

    def save_layout(self):
        caught_data = []
        for c in self.caught_list:
            caught_data.append({"name": c["name"], "coords": self.caught_canvas.coords(f"{c['tag']}_main"), "visible": c["visible_var"].get(), "size": c["size_var"].get()})
        layout = {
            "tesseract_path": getattr(self, "tesseract_path", ""),
            "cam_index": self.cam_index_var.get(),
            "cam_roi": self.vision_worker.roi,
            "window_geometry": self.root.geometry(),
            "hunt_state": {"pokemon": self.pokemon_var.get(), "encounters": self.encounters_var.get(), "base_odds": self.base_odds_var.get(), "charm": self.charm_var.get(), "masuda": self.masuda_var.get(), "sandwich": self.sandwich_var.get()},
            "sizes": {"sprite": self.size_sprite.get(), "counter": self.size_counter.get(), "odds": self.size_odds.get()},
            "coords": {"sprite": self.canvas.coords("drag_sprite_main"), "counter": self.canvas.coords("drag_counter_main"), "odds": self.canvas.coords("drag_odds_main"), "menu": self.canvas.coords("drag_menu_main")},
            "caught_sprites": caught_data,
            "text_color": self.text_color, "outline_color": self.outline_color, "bg_color": self.bg_color, "transparent_bg": self.transparent_bg_var.get(),
            "alphas": {"window": self.alpha_window.get(), "sprite": self.alpha_sprite.get(), "counter": self.alpha_counter.get(), "odds": self.alpha_odds.get(), "menu": self.alpha_menu.get()}
        }
        with open(LAYOUT_FILE, "w") as f: json.dump(layout, f)

    def on_closing(self):
        self.vision_worker.stop_loop()
        self.save_layout()
        try: self.root.destroy(); self.caught_window.destroy(); self.control_panel.destroy()
        except: pass

    def load_layout(self):
        if os.path.exists(LAYOUT_FILE):
            try:
                with open(LAYOUT_FILE, "r") as f:
                    data = json.load(f)
                    self.tesseract_path = get_tesseract_path(data.get("tesseract_path", ""))
                    self.cam_index_var.set(data.get("cam_index", 0))
                    self.vision_worker.roi = data.get("cam_roi", None)
                    
                    if geom := data.get("window_geometry"): self.root.geometry(geom)
                    hunt = data.get("hunt_state", {})
                    self.pokemon_var.set(hunt.get("pokemon", "")); self.encounters_var.set(hunt.get("encounters", 0)); self.base_odds_var.set(hunt.get("base_odds", "Gen 6+ (1/4096 Standard)"))
                    self.charm_var.set(hunt.get("charm", False)); self.masuda_var.set(hunt.get("masuda", False)); self.sandwich_var.set(hunt.get("sandwich", False))
                    self.canvas.itemconfig("drag_counter_main", text=str(self.encounters_var.get())); self.canvas.itemconfig("drag_counter_shadow", text=str(self.encounters_var.get()))
                    if self.pokemon_var.get().strip(): self.load_pokemon(silent=True)
                    
                    sizes = data.get("sizes", {})
                    self.size_sprite.set(sizes.get("sprite", 120)); self.size_counter.set(sizes.get("counter", 56)); self.size_odds.set(sizes.get("odds", 16))
                    self.refresh_text_styles()
                    
                    coords = data.get("coords", {})
                    for key, tag in [("sprite", "drag_sprite"), ("counter", "drag_counter"), ("odds", "drag_odds"), ("menu", "drag_menu")]:
                        if key in coords and coords[key]: self.move_group_to(f"{tag}_main", tag, *coords[key])
                    
                    self.text_color = data.get("text_color", "#ffffff"); self.outline_color = data.get("outline_color", "#000000"); self.bg_color = data.get("bg_color", "#00ff00")
                    self.transparent_bg_var.set(data.get("transparent_bg", False))
                    
                    alphas = data.get("alphas", {})
                    self.alpha_window.set(alphas.get("window", 1.0)); self.alpha_sprite.set(alphas.get("sprite", 1.0)); self.alpha_counter.set(alphas.get("counter", 1.0)); self.alpha_odds.set(alphas.get("odds", 1.0)); self.alpha_menu.set(alphas.get("menu", 1.0))
                    self.update_transparency()
            except: pass

if __name__ == "__main__":
    root = tk.Tk()
    app = VisionShinyTracker(root)
    root.mainloop()