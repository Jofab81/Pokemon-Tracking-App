import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
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

# Fix Windows High-DPI scaling
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    pass

LAYOUT_FILE = "obs_layout.json"

class RegionSelector:
    """Interactive screen-crop tool with arrow-key precision nudging."""
    def __init__(self, root, callback):
        self.callback = callback
        self.top = tk.Toplevel(root)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-alpha", 0.3)
        self.top.config(cursor="cross")

        self.canvas = tk.Canvas(self.top, cursor="cross", bg="grey", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.top.bind("<Left>", lambda e: self.move_box(-2, 0))
        self.top.bind("<Right>", lambda e: self.move_box(2, 0))
        self.top.bind("<Up>", lambda e: self.move_box(0, -2))
        self.top.bind("<Down>", lambda e: self.move_box(0, 2))
        self.top.bind("<Return>", self.confirm_selection)
        self.top.bind("<Escape>", lambda e: self.top.destroy())
        
        self.top.focus_set()

        self.start_x = None
        self.start_y = None
        self.current_x2 = 0
        self.current_y2 = 0
        self.rect = None

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            self.bg_image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            self.bg_photo = ImageTk.PhotoImage(self.bg_image)
            self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")
            
        self.canvas.create_text(
            root.winfo_screenwidth() // 2, 30,
            text="Drag to select region | Use Arrow Keys to fine-tune position | Press ENTER to confirm | ESC to cancel",
            fill="yellow", font=("Helvetica", 14, "bold"), tags="instruction"
        )

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.current_x2 = event.x
        self.current_y2 = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.current_x2, self.current_y2, outline='red', width=2)

    def on_drag(self, event):
        self.current_x2 = event.x
        self.current_y2 = event.y
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, self.current_x2, self.current_y2)

    def on_release(self, event):
        pass

    def move_box(self, dx, dy):
        if not self.rect: return
        self.start_x += dx
        self.start_y += dy
        self.current_x2 += dx
        self.current_y2 += dy
        self.canvas.coords(self.rect, self.start_x, self.start_y, self.current_x2, self.current_y2)

    def confirm_selection(self, event=None):
        if not self.rect:
            self.top.destroy()
            return
            
        x1 = min(self.start_x, self.current_x2)
        y1 = min(self.start_y, self.current_y2)
        x2 = max(self.start_x, self.current_x2)
        y2 = max(self.start_y, self.current_y2)
        width = x2 - x1
        height = y2 - y1
        
        region = {"top": y1, "left": x1, "width": width, "height": height}
        self.top.destroy()
        if width > 10 and height > 10:
            self.callback(region)


class AutoTrackerWorker:
    """Background thread that uses a lockout timer to ignore post-battle fades."""
    def __init__(self, callback_function):
        self.is_running = False
        self.callback = callback_function
        self.thread = None
        self.region = {"top": 200, "left": 200, "width": 400, "height": 300}
        self.brightness_threshold = 15
        self.last_encounter_time = 0
        self.lockout_duration = 45.0 

    def start_loop(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

    def stop_loop(self):
        self.is_running = False

    def set_region(self, region):
        if region:
            self.region = region

    def _capture_loop(self):
        with mss.mss() as sct:
            while self.is_running:
                try:
                    img = np.array(sct.grab(self.region))
                    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                    avg_brightness = np.mean(gray)
                    
                    is_black = avg_brightness < self.brightness_threshold
                    current_time = time.time()
                    
                    if is_black:
                        if (current_time - self.last_encounter_time) > self.lockout_duration:
                            print("-> ENCOUNTER DETECTED! Incrementing counter...")
                            self.callback()
                            self.last_encounter_time = time.time()
                        else:
                            time.sleep(1)

                except Exception as e:
                    print(f"Auto-tracker error: {e}")
                
                time.sleep(0.1)


class OBSShinyTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Shiny Tracker - OBS Overlay")
        self.root.geometry("600x400")
        
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # --- Variables ---
        self.pokemon_var = tk.StringVar()
        self.encounters_var = tk.IntVar(value=0)
        self.odds_var = tk.StringVar(value="Odds: 1/4096")
        
        # Expanded Odds Preset List
        self.base_odds_var = tk.StringVar(value="Gen 6+ (1/4096 Standard)")
        
        # Size Controls
        self.size_sprite = tk.IntVar(value=120)
        self.size_counter = tk.IntVar(value=56)
        self.size_odds = tk.IntVar(value=16)

        # Hotkey Config Variables
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

        # --- Dedicated Full-Screen Transparent Caught Overlay Window ---
        self.caught_window = tk.Toplevel(self.root)
        self.caught_window.attributes("-fullscreen", True)
        self.caught_window.attributes("-topmost", True)
        caught_magic_key = "#000002"
        self.caught_window.config(bg=caught_magic_key)
        self.caught_window.wm_attributes("-transparentcolor", caught_magic_key)
        
        self.caught_canvas = tk.Canvas(self.caught_window, bg=caught_magic_key, highlightthickness=0)
        self.caught_canvas.pack(fill="both", expand=True)

        # --- Auto-Tracker Worker ---
        self.auto_worker = AutoTrackerWorker(callback_function=self.increment)

        # --- Canvas Engine ---
        self.canvas = tk.Canvas(self.root, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # 1. Sprite Group
        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_sprite", "drag_sprite_box", "edit_box"))
        self.canvas.create_image(150, 200, image="", tags=("drag_sprite", "drag_sprite_main"))

        # 2. Counter Group
        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_counter", "drag_counter_box", "edit_box"))
        self.create_outlined_text(350, 180, "0", ("Helvetica", 56, "bold"), self.text_color, "drag_counter")

        # 3. Odds Group
        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_odds", "drag_odds_box", "edit_box"))
        self.create_outlined_text(350, 260, "Odds: 1/4096", ("Helvetica", 16, "bold"), self.text_color, "drag_odds")

        # 4. Menu Button Group
        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_box_menu", "drag_menu_box", "edit_box"))
        self.create_outlined_text(80, 30, "⚙️ Menu (Tab)", ("Helvetica", 12, "bold"), "#ffffff", "drag_menu")

        # --- Drag Variables ---
        self.drag_item = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.dragged = False

        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_release)

        # Caught Canvas Drag Bindings
        self.caught_canvas.bind("<ButtonPress-1>", self.on_caught_drag_start)
        self.caught_canvas.bind("<B1-Motion>", self.on_caught_drag_motion)
        self.caught_canvas.bind("<ButtonRelease-1>", self.on_caught_drag_release)

        # --- Control Panel Window ---
        self.control_panel = tk.Toplevel(self.root)
        self.control_panel.title("Stream Control Panel")
        self.control_panel.geometry("450x980")
        self.control_panel.protocol("WM_DELETE_WINDOW", self.on_closing) 
        
        self.create_control_panel()
        self.load_layout()
        
        # Listeners
        self.encounters_var.trace_add("write", self.calculate_odds)
        self.base_odds_var.trace_add("write", self.calculate_odds)
        self.charm_var.trace_add("write", self.calculate_odds)
        self.masuda_var.trace_add("write", self.calculate_odds)
        self.sandwich_var.trace_add("write", self.calculate_odds)
        self.size_sprite.trace_add("write", lambda *args: self.update_transparency())
        self.size_counter.trace_add("write", lambda *args: self.refresh_text_styles())
        self.size_odds.trace_add("write", lambda *args: self.refresh_text_styles())

        # Global Hotkey Listeners
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
        # EDIT MODE TOGGLE
        self.edit_btn = ttk.Button(self.control_panel, text="🛠️ ENABLE EDIT / LAYOUT MODE", command=self.toggle_edit_mode)
        self.edit_btn.pack(fill="x", padx=10, pady=(10, 5))

        # Setup Frame
        setup_frame = ttk.LabelFrame(self.control_panel, text="Hunt Setup & Caught Pokémon", padding=10)
        setup_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(setup_frame, text="Pokémon:").grid(row=0, column=0, pady=5)
        ttk.Entry(setup_frame, textvariable=self.pokemon_var, width=15).grid(row=0, column=1, pady=5)
        ttk.Button(setup_frame, text="Load", command=self.load_pokemon).grid(row=0, column=2, padx=5)
        
        ttk.Label(setup_frame, text="Game / Method:").grid(row=1, column=0, pady=5)
        
        odds_presets = [
            "Gen 6+ (1/4096 Standard)",
            "Gen 1-5 (1/8192 Standard)",
            "Dynamax Adventures (1/300)",
            "Dynamax Adventures + Charm (1/100)",
            "SV: Outbreak / Sandwich Hunt",
            "Legends Arceus / Z-A: Outbreak/MMO"
        ]
        ttk.Combobox(setup_frame, textvariable=self.base_odds_var, values=odds_presets, state="readonly", width=20).grid(row=1, column=1, columnspan=2, sticky="w")
        
        ttk.Button(setup_frame, text="✨ Register Current as Caught!", command=self.register_caught).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5,5))
        
        # Caught Manager Frame inside Setup
        self.caught_mgr_frame = ttk.LabelFrame(setup_frame, text="Manage Caught Pokémon Visibility & Size", padding=5)
        self.caught_mgr_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=5)
        
        self.caught_checkboxes_container = ttk.Frame(self.caught_mgr_frame)
        self.caught_checkboxes_container.pack(fill="x")

        # Size Controls Frame
        size_frame = ttk.LabelFrame(self.control_panel, text="Element Sizes", padding=10)
        size_frame.pack(fill="x", padx=10, pady=5)
        self.make_slider(size_frame, "Sprite Size:", self.size_sprite, 120, 500, None)
        self.make_slider(size_frame, "Counter Size:", self.size_counter, 20, 150, None)
        self.make_slider(size_frame, "Odds Size:", self.size_odds, 10, 40, None)

        # Controls & Hotkeys Frame
        ctrl_frame = ttk.LabelFrame(self.control_panel, text="Counter Controls & Custom Hotkeys", padding=10)
        ctrl_frame.pack(fill="x", padx=10, pady=5)
        
        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill="x", pady=2)
        ttk.Button(btn_row, text="-1", command=self.decrement, width=5).pack(side="left", padx=2)
        ttk.Button(btn_row, text="+1 Encounter", command=self.increment).pack(side="left", expand=True, fill="x", padx=2)

        # Interactive Keybind Buttons Grid
        hk_grid = ttk.Frame(ctrl_frame)
        hk_grid.pack(fill="x", pady=(8,0))
        
        ttk.Label(hk_grid, text="+1 Key:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.btn_inc_bind = ttk.Button(hk_grid, text=f"Key: {self.key_inc.get()}", command=lambda: self.start_key_capture('inc'))
        self.btn_inc_bind.grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        ttk.Label(hk_grid, text="-1 Key:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.btn_dec_bind = ttk.Button(hk_grid, text=f"Key: {self.key_dec.get()}", command=lambda: self.start_key_capture('dec'))
        self.btn_dec_bind.grid(row=1, column=1, sticky="ew", padx=2, pady=2)

        ttk.Label(hk_grid, text="Caught Key:").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.btn_caught_bind = ttk.Button(hk_grid, text=f"Key: {self.key_caught.get()}", command=lambda: self.start_key_capture('caught'))
        self.btn_caught_bind.grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        
        hk_grid.columnconfigure(1, weight=1)

        # Auto-Tracker Frame
        auto_frame = ttk.LabelFrame(self.control_panel, text="Auto-Tracker (Screen Scraping)", padding=10)
        auto_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(auto_frame, text="🎯 Select Screen Region to Watch", command=self.open_region_selector).pack(fill="x", pady=2)
        self.auto_toggle_btn = ttk.Button(auto_frame, text="Start Auto-Tracker", command=self.toggle_auto_tracker)
        self.auto_toggle_btn.pack(fill="x", pady=2)

        # Boosts Frame
        boosts_frame = ttk.LabelFrame(self.control_panel, text="Active Boosts", padding=5)
        boosts_frame.pack(fill="x", padx=10, pady=5)
        ttk.Checkbutton(boosts_frame, text="Shiny Charm", variable=self.charm_var).pack(side="left", padx=5)
        ttk.Checkbutton(boosts_frame, text="Masuda", variable=self.masuda_var).pack(side="left", padx=5)
        ttk.Checkbutton(boosts_frame, text="Sandwich", variable=self.sandwich_var).pack(side="left", padx=5)

        # Settings Frame
        settings_frame = ttk.LabelFrame(self.control_panel, text="Global Colors & Background", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        btn_frame = ttk.Frame(settings_frame)
        btn_frame.pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Text Color", command=self.change_text_color).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(btn_frame, text="Outline Color", command=self.change_outline_color).pack(side="right", expand=True, fill="x", padx=(2, 0))
        ttk.Button(settings_frame, text="Change Background Color", command=self.change_bg_color).pack(fill="x", pady=2)
        
        self.transparent_bg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Make Background 100% Invisible", variable=self.transparent_bg_var, command=self.update_transparency).pack(anchor="w", pady=(5,0))

        # Alpha Frame
        alpha_frame = ttk.LabelFrame(self.control_panel, text="Visibility Controls", padding=10)
        alpha_frame.pack(fill="x", padx=10, pady=5)

        self.alpha_window = tk.DoubleVar(value=1.0)
        self.alpha_sprite = tk.DoubleVar(value=1.0)
        self.alpha_counter = tk.DoubleVar(value=1.0)
        self.alpha_odds = tk.DoubleVar(value=1.0)
        self.alpha_menu = tk.DoubleVar(value=1.0)

        self.make_slider(alpha_frame, "Overall Window:", self.alpha_window, 0.1, 1.0, self.update_transparency)
        ttk.Separator(alpha_frame, orient="horizontal").pack(fill="x", pady=5)
        self.make_slider(alpha_frame, "Pokemon Sprite:", self.alpha_sprite, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Counter Text:", self.alpha_counter, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "Odds Text:", self.alpha_odds, 0.0, 1.0, self.update_transparency)
        self.make_slider(alpha_frame, "⚙️ Menu Button:", self.alpha_menu, 0.0, 1.0, self.update_transparency)

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
            
            cb = ttk.Checkbutton(
                row,
                text=c["name"].capitalize(),
                variable=c["visible_var"],
                command=lambda item=c: self.toggle_caught_visibility(item)
            )
            cb.pack(side="left", padx=2)
            
            slider = ttk.Scale(
                row,
                from_=120,
                to=500,
                orient="horizontal",
                variable=c["size_var"],
                command=lambda val, item=c: self.update_caught_size(item, float(val))
            )
            slider.pack(side="right", expand=True, fill="x", padx=5)

    def toggle_caught_visibility(self, item):
        state = "normal" if item["visible_var"].get() else "hidden"
        self.caught_canvas.itemconfig(f"{item['tag']}_main", state=state)
        if self.edit_mode:
            self.update_edit_boxes()
        self.save_layout()

    def update_caught_size(self, item, new_size_float):
        new_size = int(new_size_float)
        if item["raw_image"]:
            resized = item["raw_image"].resize((new_size, new_size), Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(resized)
            item["photo"] = photo
            self.caught_canvas.itemconfig(f"{item['tag']}_main", image=photo)
            if self.edit_mode:
                self.update_edit_boxes()
            self.save_layout()

    def start_key_capture(self, action_type):
        self.capturing_action = action_type
        self.root.bind_all("<Key>", self.capture_key_press)
        
        if action_type == 'inc':
            self.btn_inc_bind.config(text="Press any key...")
        elif action_type == 'dec':
            self.btn_dec_bind.config(text="Press any key...")
        elif action_type == 'caught':
            self.btn_caught_bind.config(text="Press any key...")

    def capture_key_press(self, event):
        if event.keysym == "Tab":
            return
            
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
        if isinstance(self.root.focus_get(), ttk.Entry):
            return
            
        key = event.keysym.lower()
        if key == self.key_inc.get().lower():
            self.increment()
        elif key == self.key_dec.get().lower():
            self.decrement()
        elif key == self.key_caught.get().lower():
            self.register_caught()

    # --- Caught Pokémon Registration & Spawning ---
    def register_caught(self):
        pokemon_name = self.pokemon_var.get().strip().lower()
        if not pokemon_name:
            messagebox.showwarning("Warning", "Please enter a Pokémon name to register as caught!")
            return

        try:
            resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_name}")
            if resp.status_code == 200:
                s_url = resp.json()['sprites']['front_shiny']
                if s_url:
                    img_resp = requests.get(s_url)
                    raw_img = Image.open(BytesIO(img_resp.content))
                    default_size = 120
                    pil_img = raw_img.resize((default_size, default_size), Image.Resampling.NEAREST)
                    
                    existing = next((c for c in self.caught_list if c["name"].lower() == pokemon_name), None)
                    if not existing:
                        tag_base = f"caught_{len(self.caught_list)}_{int(time.time())}"
                        photo = ImageTk.PhotoImage(pil_img)
                        
                        self.caught_canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=(tag_base, f"{tag_base}_box", "caught_edit_box"))
                        self.caught_canvas.create_image(400, 300, image=photo, tags=(tag_base, f"{tag_base}_main"))
                        
                        vis_var = tk.BooleanVar(value=True)
                        size_var = tk.IntVar(value=default_size)
                        
                        self.caught_list.append({
                            "name": pokemon_name,
                            "raw_image": raw_img,
                            "photo": photo,
                            "tag": tag_base,
                            "visible_var": vis_var,
                            "size_var": size_var
                        })
                        self.rebuild_caught_manager_ui()
                        self.save_layout()
                        messagebox.showinfo("Success", f"Registered and spawned {pokemon_name} on your full-screen overlay!")
                    else:
                        messagebox.showinfo("Info", f"{pokemon_name} is already registered as caught!")
                else:
                    messagebox.showerror("Error", "No shiny sprite found.")
            else:
                messagebox.showerror("Error", "Pokémon not found.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to register: {e}")

    # --- Auto-Tracker Controls ---
    def open_region_selector(self):
        self.control_panel.withdraw()
        RegionSelector(self.root, self.save_selected_region)

    def save_selected_region(self, region):
        self.control_panel.deiconify()
        self.auto_worker.set_region(region)
        messagebox.showinfo("Success", "Auto-tracker region set successfully!")

    def toggle_auto_tracker(self):
        if not self.auto_worker.is_running:
            self.auto_worker.start_loop()
            self.auto_toggle_btn.config(text="Stop Auto-Tracker (Running...)")
        else:
            self.auto_worker.stop_loop()
            self.auto_toggle_btn.config(text="Start Auto-Tracker")

    # --- Edit Mode & Window / Element Dragging / Resizing ---
    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_btn.config(text="✅ DONE EDITING (SAVE & HIDE BOXES)")
            self.canvas.itemconfig("edit_box", state="normal")
            self.caught_canvas.itemconfig("caught_edit_box", state="normal")
            self.root.overrideredirect(False)
            self.update_transparency()
            self.update_edit_boxes()
        else:
            self.edit_btn.config(text="🛠️ ENABLE EDIT / LAYOUT MODE")
            self.canvas.itemconfig("edit_box", state="hidden")
            self.caught_canvas.itemconfig("caught_edit_box", state="hidden")
            self.root.overrideredirect(True)
            self.update_transparency()
            self.save_layout()

    def update_edit_boxes(self):
        tags_to_check = ["drag_sprite", "drag_counter", "drag_odds", "drag_menu"]
        for tag in tags_to_check:
            bbox = self.canvas.bbox(f"{tag}_main")
            if bbox:
                x1, y1, x2, y2 = bbox
                self.canvas.coords(f"{tag}_box", x1-10, y1-10, x2+10, y2+10)

        for c in self.caught_list:
            if c["visible_var"].get():
                bbox = self.caught_canvas.bbox(f"{c['tag']}_main")
                if bbox:
                    x1, y1, x2, y2 = bbox
                    self.caught_canvas.coords(f"{c['tag']}_box", x1-10, y1-10, x2+10, y2+10)

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
        if not self.edit_mode:
            return
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
            dx = event.x_root - self.drag_start_x
            dy = event.y_root - self.drag_start_y
            x = self.root.winfo_x() + dx
            y = self.root.winfo_y() + dy
            self.root.geometry(f"+{x}+{y}")
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
        else:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.canvas.move(self.drag_item, dx, dy)
            self.drag_start_x = event.x
            self.drag_start_y = event.y

    def on_caught_drag_motion(self, event):
        if hasattr(self, 'caught_drag_item') and self.caught_drag_item:
            dx = event.x - self.caught_drag_start_x
            dy = event.y - self.caught_drag_start_y
            self.caught_canvas.move(self.caught_drag_item, dx, dy)
            self.caught_drag_start_x = event.x
            self.caught_drag_start_y = event.y

    def on_drag_release(self, event):
        if self.drag_item == "drag_menu" and not self.dragged:
            self.toggle_menu()
        if self.edit_mode:
            self.update_edit_boxes()
        self.drag_item = None
        self.save_layout()  # Auto-save immediately upon releasing dragged elements

    def on_caught_drag_release(self, event):
        if hasattr(self, 'caught_drag_item'):
            self.caught_drag_item = None
        if self.edit_mode:
            self.update_edit_boxes()
        self.save_layout()  # Auto-save immediately upon releasing caught elements

    def toggle_menu(self, event=None):
        if self.control_panel.winfo_ismapped():
            self.control_panel.withdraw()
        else:
            self.control_panel.deiconify()

    # --- Advanced Game-Specific Odds Calculation Engine ---
    def calculate_odds(self, *args):
        selection = self.base_odds_var.get()
        
        if "Dynamax Adventures + Charm" in selection:
            final_odds = 100
            display_text = f"Odds: 1/{final_odds} (Dynamax Adv.)"
        elif "Dynamax Adventures" in selection:
            final_odds = 300
            display_text = f"Odds: 1/{final_odds} (Dynamax Adv.)"
        else:
            base = 8192 if "8192" in selection else 4096
            rolls = 1 
            
            if self.charm_var.get(): rolls += 2
            if self.masuda_var.get(): rolls += 5 if base == 4096 else 4
            if self.sandwich_var.get(): rolls += 3

            if "SV: Outbreak" in selection:
                rolls += 2 
            elif "Legends Arceus" in selection:
                rolls += 3 

            final_odds = max(1, base / rolls)
            display_text = f"Odds: {rolls}/{base} (1/{final_odds:.0f})"

        self.odds_var.set(display_text)
        self.canvas.itemconfig("drag_odds_main", text=self.odds_var.get())
        self.canvas.itemconfig("drag_odds_shadow", text=self.odds_var.get())
        if self.edit_mode: self.update_edit_boxes()
        self.save_layout()

    def load_pokemon(self):
        pokemon = self.pokemon_var.get().strip().lower()
        if not pokemon: 
            messagebox.showwarning("Warning", "Please enter a Pokémon name.")
            return

        try:
            response = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon}")
            if response.status_code == 200:
                sprite_url = response.json()['sprites']['front_shiny']
                if sprite_url:
                    img_resp = requests.get(sprite_url)
                    size = self.size_sprite.get()
                    self.base_pil_image = Image.open(BytesIO(img_resp.content)).resize((size, size), Image.Resampling.NEAREST)
                    self.update_transparency() 
                    if self.edit_mode: self.update_edit_boxes()
                    self.save_layout()
                else:
                    messagebox.showerror("Error", "No shiny sprite found for this Pokémon.")
            else:
                messagebox.showerror("Error", "Pokémon not found. Check the spelling.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch data: {e}")

    def increment(self): 
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

    # --- Rendering & Transparency Math ---
    def change_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color", initialcolor=self.text_color)[1]
        if color:
            self.text_color = color
            self.update_transparency()
            self.save_layout()

    def change_outline_color(self):
        color = colorchooser.askcolor(title="Choose Outline Color", initialcolor=self.outline_color)[1]
        if color:
            self.outline_color = color
            self.update_transparency()
            self.save_layout()

    def change_bg_color(self):
        color = colorchooser.askcolor(title="Choose Background Color", initialcolor=self.bg_color)[1]
        if color:
            self.bg_color = color
            self.update_transparency()
            self.save_layout()

    def blend_color(self, hex_fg, hex_bg, alpha):
        if alpha <= 0.01: return hex_bg 
        if alpha >= 0.99: return hex_fg 
        
        r1, g1, b1 = int(hex_fg[1:3], 16), int(hex_fg[3:5], 16), int(hex_fg[5:7], 16)
        r2, g2, b2 = int(hex_bg[1:3], 16), int(hex_bg[3:5], 16), int(hex_bg[5:7], 16)
        
        r = int(r1 * alpha + r2 * (1 - alpha))
        g = int(g1 * alpha + g2 * (1 - alpha))
        b = int(b1 * alpha + b2 * (1 - alpha))
        
        return f"#{r:02x}{g:02x}{b:02x}"

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

        c_alpha = 1.0 if self.edit_mode else self.alpha_counter.get()
        o_alpha = 1.0 if self.edit_mode else self.alpha_odds.get()
        m_alpha = 1.0 if self.edit_mode else self.alpha_menu.get()
        s_alpha = 1.0 if self.edit_mode else self.alpha_sprite.get()

        if c_alpha <= 0.01:
            self.canvas.itemconfig("drag_counter_main", state="hidden")
            self.canvas.itemconfig("drag_counter_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_counter_main", state="normal", fill=self.blend_color(self.text_color, blend_bg, c_alpha))
            self.canvas.itemconfig("drag_counter_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, c_alpha))

        if o_alpha <= 0.01:
            self.canvas.itemconfig("drag_odds_main", state="hidden")
            self.canvas.itemconfig("drag_odds_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_odds_main", state="normal", fill=self.blend_color(self.text_color, blend_bg, o_alpha))
            self.canvas.itemconfig("drag_odds_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, o_alpha))

        if m_alpha <= 0.01:
            self.canvas.itemconfig("drag_menu_main", state="hidden")
            self.canvas.itemconfig("drag_menu_shadow", state="hidden")
        else:
            self.canvas.itemconfig("drag_menu_main", state="normal", fill=self.blend_color("#ffffff", blend_bg, m_alpha))
            self.canvas.itemconfig("drag_menu_shadow", state="normal", fill=self.blend_color(self.outline_color, blend_bg, m_alpha))

        if self.pokemon_var.get().strip():
            try:
                resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{self.pokemon_var.get().strip().lower()}")
                if resp.status_code == 200:
                    s_url = resp.json()['sprites']['front_shiny']
                    if s_url:
                        img_resp = requests.get(s_url)
                        size = self.size_sprite.get()
                        self.base_pil_image = Image.open(BytesIO(img_resp.content)).resize((size, size), Image.Resampling.NEAREST)
            except:
                pass

        if self.base_pil_image:
            if s_alpha <= 0.01:
                self.canvas.itemconfig("drag_sprite_main", image="", state="hidden")
            else:
                img = self.base_pil_image.copy().convert("RGBA")
                if s_alpha < 1.0:
                    r, g, b, a = img.split()
                    a = a.point(lambda p: int(p * s_alpha))
                    img = Image.merge("RGBA", (r, g, b, a))
                self.current_sprite = ImageTk.PhotoImage(img)
                self.canvas.itemconfig("drag_sprite_main", image=self.current_sprite, state="normal")

    def move_group_to(self, main_tag, group_tag, new_x, new_y):
        curr = self.canvas.coords(main_tag)
        if curr and len(curr) >= 2:
            dx = new_x - curr[0]
            dy = new_y - curr[1]
            self.canvas.move(group_tag, dx, dy)

    def save_layout(self):
        caught_data = []
        for c in self.caught_list:
            coords = self.caught_canvas.coords(f"{c['tag']}_main")
            caught_data.append({
                "name": c["name"],
                "coords": coords,
                "visible": c["visible_var"].get(),
                "size": c["size_var"].get()
            })

        layout = {
            "window_geometry": self.root.geometry(),
            "hunt_state": {
                "pokemon": self.pokemon_var.get(),
                "encounters": self.encounters_var.get(),
                "base_odds": self.base_odds_var.get(),
                "charm": self.charm_var.get(),
                "masuda": self.masuda_var.get(),
                "sandwich": self.sandwich_var.get()
            },
            "sizes": {
                "sprite": self.size_sprite.get(),
                "counter": self.size_counter.get(),
                "odds": self.size_odds.get()
            },
            "coords": {
                "sprite": self.canvas.coords("drag_sprite_main"),
                "counter": self.canvas.coords("drag_counter_main"),
                "odds": self.canvas.coords("drag_odds_main"),
                "menu": self.canvas.coords("drag_menu_main")
            },
            "caught_sprites": caught_data,
            "hotkeys": {
                "inc": self.key_inc.get(),
                "dec": self.key_dec.get(),
                "caught": self.key_caught.get()
            },
            "text_color": self.text_color,
            "outline_color": self.outline_color,
            "bg_color": self.bg_color,
            "transparent_bg": self.transparent_bg_var.get(),
            "alphas": {
                "window": self.alpha_window.get(),
                "sprite": self.alpha_sprite.get(),
                "counter": self.alpha_counter.get(),
                "odds": self.alpha_odds.get(),
                "menu": self.alpha_menu.get()
            }
        }
        with open(LAYOUT_FILE, "w") as f:
            json.dump(layout, f)

    def on_closing(self):
        self.auto_worker.stop_loop()
        self.save_layout()
        try:
            self.root.destroy()
        except:
            pass
        try:
            self.caught_window.destroy()
        except:
            pass
        try:
            self.control_panel.destroy()
        except:
            pass

    def load_layout(self):
        if os.path.exists(LAYOUT_FILE):
            try:
                with open(LAYOUT_FILE, "r") as f:
                    data = json.load(f)
                    
                    geom = data.get("window_geometry")
                    if geom:
                        self.root.geometry(geom)

                    # Restore Hunt State
                    hunt_state = data.get("hunt_state", {})
                    self.pokemon_var.set(hunt_state.get("pokemon", ""))
                    self.encounters_var.set(hunt_state.get("encounters", 0))
                    self.base_odds_var.set(hunt_state.get("base_odds", "Gen 6+ (1/4096 Standard)"))
                    self.charm_var.set(hunt_state.get("charm", False))
                    self.masuda_var.set(hunt_state.get("masuda", False))
                    self.sandwich_var.set(hunt_state.get("sandwich", False))

                    self.canvas.itemconfig("drag_counter_main", text=str(self.encounters_var.get()))
                    self.canvas.itemconfig("drag_counter_shadow", text=str(self.encounters_var.get()))

                    if self.pokemon_var.get().strip():
                        self.load_pokemon()

                    sizes = data.get("sizes", {})
                    self.size_sprite.set(sizes.get("sprite", 120))
                    self.size_counter.set(sizes.get("counter", 56))
                    self.size_odds.set(sizes.get("odds", 16))
                    self.refresh_text_styles()

                    coords = data.get("coords", {})
                    if "sprite" in coords and coords["sprite"]: 
                        self.move_group_to("drag_sprite_main", "drag_sprite", *coords["sprite"])
                    if "counter" in coords and coords["counter"]: 
                        self.move_group_to("drag_counter_main", "drag_counter", *coords["counter"])
                    if "odds" in coords and coords["odds"]: 
                        self.move_group_to("drag_odds_main", "drag_odds", *coords["odds"])
                    if "menu" in coords and coords["menu"]: 
                        self.move_group_to("drag_menu_main", "drag_menu", *coords["menu"])
                    
                    hotkeys = data.get("hotkeys", {})
                    self.key_inc.set(hotkeys.get("inc", "space"))
                    self.key_dec.set(hotkeys.get("dec", "Down"))
                    self.key_caught.set(hotkeys.get("caught", "c"))
                    
                    self.btn_inc_bind.config(text=f"Key: {self.key_inc.get()}")
                    self.btn_dec_bind.config(text=f"Key: {self.key_dec.get()}")
                    self.btn_caught_bind.config(text=f"Key: {self.key_caught.get()}")

                    for item in data.get("caught_sprites", []):
                        name = item.get("name", "pokemon")
                        c_coords = item.get("coords")
                        visible = item.get("visible", True)
                        saved_size = item.get("size", 120)
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
                                    state_str = "normal" if visible else "hidden"
                                    self.caught_canvas.create_image(c_coords[0], c_coords[1], image=photo, state=state_str, tags=(tag_base, f"{tag_base}_main"))
                                    
                                    vis_var = tk.BooleanVar(value=visible)
                                    size_var = tk.IntVar(value=saved_size)
                                    
                                    self.caught_list.append({
                                        "name": name,
                                        "raw_image": raw_img,
                                        "photo": photo,
                                        "tag": tag_base,
                                        "visible_var": vis_var,
                                        "size_var": size_var
                                    })
                            except:
                                pass
                    self.rebuild_caught_manager_ui()

                    self.text_color = data.get("text_color", "#ffffff")
                    self.outline_color = data.get("outline_color", "#000000")
                    self.bg_color = data.get("bg_color", "#00ff00")
                    self.canvas.configure(bg=self.bg_color)

                    self.transparent_bg_var.set(data.get("transparent_bg", False))

                    alphas = data.get("alphas", {})
                    self.alpha_window.set(alphas.get("window", 1.0))
                    self.alpha_sprite.set(alphas.get("sprite", 1.0))
                    self.alpha_counter.set(alphas.get("counter", 1.0))
                    self.alpha_odds.set(alphas.get("odds", 1.0))
                    self.alpha_menu.set(alphas.get("menu", 1.0))
                    
                    self.update_transparency()
            except:
                pass

if __name__ == "__main__":
    root = tk.Tk()
    app = OBSShinyTracker(root)
    root.mainloop()