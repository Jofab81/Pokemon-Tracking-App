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
    """Background thread that monitors screen pixel changes with live console testing."""
    def __init__(self, callback_function):
        self.is_running = False
        self.callback = callback_function
        self.thread = None
        self.region = {"top": 200, "left": 200, "width": 400, "height": 300}
        self.threshold = 10 

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
            last_frame = None
            while self.is_running:
                try:
                    img = np.array(sct.grab(self.region))
                    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                    
                    if last_frame is not None:
                        diff = cv2.absdiff(gray, last_frame)
                        changed_pixels = np.count_nonzero(diff > self.threshold)
                        total_pixels = self.region["width"] * self.region["height"]
                        
                        print(f"[Auto-Tracker Test] Pixel Change Score: {changed_pixels} (Target needed: {int(total_pixels * 0.15)})")
                        
                        if changed_pixels > (total_pixels * 0.15):
                            print("-> ENCOUNTER DETECTED! Incrementing counter...")
                            self.callback()
                            time.sleep(3) 
                            
                    last_frame = gray
                except Exception as e:
                    print(f"Auto-tracker error: {e}")
                time.sleep(0.1)


class OBSShinyTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Shiny Tracker - OBS Overlay")
        self.root.geometry("600x400")
        
        # --- LiveSplit Behavior & Borderless Window ---
        self.root.overrideredirect(True)      # Hides native title bar
        self.root.attributes("-topmost", True)  # Forces app to stay on top constantly
        
        # --- Variables ---
        self.pokemon_var = tk.StringVar()
        self.encounters_var = tk.IntVar(value=0)
        self.odds_var = tk.StringVar(value="Odds: 1/4096")
        self.base_odds_var = tk.StringVar(value="1/4096 (Gen 6+)")
        
        self.charm_var = tk.BooleanVar()
        self.masuda_var = tk.BooleanVar()
        self.sandwich_var = tk.BooleanVar()

        self.text_color = "#ffffff"
        self.outline_color = "#000000" 
        self.bg_color = "#00ff00" 
        
        self.base_pil_image = None
        self.current_sprite = None
        self.edit_mode = False

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
        self.canvas.create_rectangle(0, 0, 0, 0, fill="#555555", outline="#ffffff", width=2, state="hidden", tags=("drag_menu", "drag_menu_box", "edit_box"))
        self.create_outlined_text(80, 30, "⚙️ Menu (Tab)", ("Helvetica", 12, "bold"), "#ffffff", "drag_menu")

        # --- Drag Variables ---
        self.drag_item = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.dragged = False

        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_release)

        # --- Control Panel Window ---
        self.control_panel = tk.Toplevel(self.root)
        self.control_panel.title("Stream Control Panel")
        self.control_panel.geometry("450x800")
        self.control_panel.protocol("WM_DELETE_WINDOW", self.on_closing) 
        
        self.create_control_panel()
        self.load_layout()
        
        # Listeners
        self.encounters_var.trace_add("write", self.calculate_odds)
        self.base_odds_var.trace_add("write", self.calculate_odds)
        self.charm_var.trace_add("write", self.calculate_odds)
        self.masuda_var.trace_add("write", self.calculate_odds)
        self.sandwich_var.trace_add("write", self.calculate_odds)

        # Hotkeys
        self.root.bind("<space>", lambda event: self.increment())
        self.root.bind("<Tab>", self.toggle_menu)
        self.control_panel.bind("<Tab>", self.toggle_menu)

        self.control_panel.deiconify()

    def create_outlined_text(self, x, y, text, font, text_color, tag):
        offsets = [(-2, -2), (0, -2), (2, -2), (-2, 0), (2, 0), (-2, 2), (0, 2), (2, 2)]
        for dx, dy in offsets:
            self.canvas.create_text(x+dx, y+dy, text=text, font=font, fill=self.outline_color, tags=(tag, f"{tag}_shadow"))
        self.canvas.create_text(x, y, text=text, font=font, fill=text_color, tags=(tag, f"{tag}_main"))

    def create_control_panel(self):
        # EDIT MODE TOGGLE
        self.edit_btn = ttk.Button(self.control_panel, text="🛠️ ENABLE EDIT / LAYOUT MODE", command=self.toggle_edit_mode)
        self.edit_btn.pack(fill="x", padx=10, pady=(10, 5))

        # Setup Frame
        setup_frame = ttk.LabelFrame(self.control_panel, text="Hunt Setup", padding=10)
        setup_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(setup_frame, text="Pokémon:").grid(row=0, column=0, pady=5)
        ttk.Entry(setup_frame, textvariable=self.pokemon_var, width=15).grid(row=0, column=1, pady=5)
        ttk.Button(setup_frame, text="Load", command=self.load_pokemon).grid(row=0, column=2, padx=5)
        ttk.Label(setup_frame, text="Base Odds:").grid(row=1, column=0, pady=5)
        ttk.Combobox(setup_frame, textvariable=self.base_odds_var, values=["1/4096 (Gen 6+)", "1/8192 (Gen 1-5)"], state="readonly", width=15).grid(row=1, column=1, columnspan=2, sticky="w")

        # Controls Frame
        ctrl_frame = ttk.LabelFrame(self.control_panel, text="Counter Controls", padding=10)
        ctrl_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(ctrl_frame, text="-1", command=self.decrement, width=5).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="+1 Encounter (Spacebar)", command=self.increment).pack(side="left", expand=True, fill="x", padx=5)

        # Auto-Tracker Frame
        auto_frame = ttk.LabelFrame(self.control_panel, text="Auto-Tracker (Screen Scraping Test)", padding=10)
        auto_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(auto_frame, text="🎯 Select Screen Region to Watch", command=self.open_region_selector).pack(fill="x", pady=2)
        self.auto_toggle_btn = ttk.Button(auto_frame, text="Start Auto-Tracker", command=self.toggle_auto_tracker)
        self.auto_toggle_btn.pack(fill="x", pady=2)
        ttk.Label(auto_frame, text="💡 Tip: Watch your Python console terminal to test live pixel scores!", font=("Helvetica", 8, "italic"), foreground="gray").pack(anchor="w", pady=2)

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
        alpha_frame = ttk.LabelFrame(self.control_panel, text="Visibility Controls (Slide to 0 for invisible)", padding=10)
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

    # --- Edit Mode & Window / Element Dragging ---
    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_btn.config(text="✅ DONE EDITING (SAVE & HIDE BOXES)")
            self.canvas.itemconfig("edit_box", state="normal")
            self.update_transparency()
            self.update_edit_boxes()
        else:
            self.edit_btn.config(text="🛠️ ENABLE EDIT / LAYOUT MODE")
            self.canvas.itemconfig("edit_box", state="hidden")
            self.update_transparency()
            self.save_layout()

    def update_edit_boxes(self):
        for tag in ["drag_sprite", "drag_counter", "drag_odds", "drag_menu"]:
            bbox = self.canvas.bbox(f"{tag}_main")
            if bbox:
                x1, y1, x2, y2 = bbox
                self.canvas.coords(f"{tag}_box", x1-10, y1-10, x2+10, y2+10)

    def on_drag_start(self, event):
        items = self.canvas.find_withtag("current")
        if not items:
            # Clicked empty space: Drag the whole window around the screen!
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
            # If not in edit mode, clicking anywhere drags the entire window
            self.drag_item = "window"
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            return

        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.dragged = False

    def on_drag_motion(self, event):
        if not self.drag_item: return
        self.dragged = True
        
        if self.drag_item == "window":
            # Move the entire application window across the screen
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

    def on_drag_release(self, event):
        if self.drag_item == "drag_menu" and not self.dragged:
            self.toggle_menu()
        if self.edit_mode:
            self.update_edit_boxes()
        self.drag_item = None

    def toggle_menu(self, event=None):
        if self.control_panel.winfo_ismapped():
            self.control_panel.withdraw()
        else:
            self.control_panel.deiconify()

    # --- Feature Logic ---
    def calculate_odds(self, *args):
        base = 8192 if "8192" in self.base_odds_var.get() else 4096
        rolls = 1 
        if self.charm_var.get(): rolls += 2
        if self.masuda_var.get(): rolls += 5 if base == 4096 else 4
        if self.sandwich_var.get(): rolls += 3

        final_odds = max(1, base / rolls)
        self.odds_var.set(f"Odds: {rolls}/{base} (1/{final_odds:.0f})")
        
        self.canvas.itemconfig("drag_odds_main", text=self.odds_var.get())
        self.canvas.itemconfig("drag_odds_shadow", text=self.odds_var.get())
        if self.edit_mode: self.update_edit_boxes()

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
                    self.base_pil_image = Image.open(BytesIO(img_resp.content)).resize((160, 160), Image.Resampling.NEAREST)
                    self.update_transparency() 
                    if self.edit_mode: self.update_edit_boxes()
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

    def decrement(self): 
        if self.encounters_var.get() > 0: 
            self.encounters_var.set(self.encounters_var.get() - 1)
            self.canvas.itemconfig("drag_counter_main", text=str(self.encounters_var.get()))
            self.canvas.itemconfig("drag_counter_shadow", text=str(self.encounters_var.get()))
            if self.edit_mode: self.update_edit_boxes()

    # --- Rendering & Transparency Math ---
    def change_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color", initialcolor=self.text_color)[1]
        if color:
            self.text_color = color
            self.update_transparency() 

    def change_outline_color(self):
        color = colorchooser.askcolor(title="Choose Outline Color", initialcolor=self.outline_color)[1]
        if color:
            self.outline_color = color
            self.update_transparency() 

    def change_bg_color(self):
        color = colorchooser.askcolor(title="Choose Background Color", initialcolor=self.bg_color)[1]
        if color:
            self.bg_color = color
            self.update_transparency() 

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
        layout = {
            "coords": {
                "sprite": self.canvas.coords("drag_sprite_main"),
                "counter": self.canvas.coords("drag_counter_main"),
                "odds": self.canvas.coords("drag_odds_main"),
                "menu": self.canvas.coords("drag_menu_main")
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
            self.control_panel.destroy()
        except:
            pass

    def load_layout(self):
        if os.path.exists(LAYOUT_FILE):
            try:
                with open(LAYOUT_FILE, "r") as f:
                    data = json.load(f)
                    
                    coords = data.get("coords", {})
                    if "sprite" in coords and coords["sprite"]: 
                        self.move_group_to("drag_sprite_main", "drag_sprite", *coords["sprite"])
                    if "counter" in coords and coords["counter"]: 
                        self.move_group_to("drag_counter_main", "drag_counter", *coords["counter"])
                    if "odds" in coords and coords["odds"]: 
                        self.move_group_to("drag_odds_main", "drag_odds", *coords["odds"])
                    if "menu" in coords and coords["menu"]: 
                        self.move_group_to("drag_menu_main", "drag_menu", *coords["menu"])
                    
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