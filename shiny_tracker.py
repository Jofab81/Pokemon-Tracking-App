import tkinter as tk
from tkinter import ttk, messagebox
import requests
from io import BytesIO
from PIL import Image, ImageTk
import json
import os
import base64

DATA_FILE = "shiny_history.json"
STATE_FILE = "current_hunt.json"

class ShinyTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Shiny Pokémon Tracker")
        self.root.geometry("520x760")
        
        # --- THEME ENGINE: Games, Colors, and Eras ---
        self.THEMES = {
            "gold": ("retro", "#3b3318", "#4f4522", "#ffcc4a"),
            "silver": ("retro", "#2e3236", "#3f454a", "#a9b9c9"),
            "crystal": ("retro", "#18393b", "#224a4f", "#4ae8ff"),
            "ruby": ("retro", "#3b1818", "#4f2222", "#ff4a4a"),
            "sapphire": ("retro", "#18233b", "#22314f", "#4a8dff"),
            "emerald": ("retro", "#183b22", "#224f2f", "#4aff74"),
            "fire red": ("retro", "#4a1c12", "#6e291b", "#ff5938"),
            "leaf green": ("retro", "#1e4a12", "#2d6e1b", "#62ff38"),
            "diamond": ("classic", "#232b38", "#313c4f", "#80b9ff"),
            "pearl": ("classic", "#382330", "#4f3144", "#ff80d5"),
            "platinum": ("classic", "#2b2b2b", "#3b3b3b", "#c4c4c4"),
            "heart gold": ("classic", "#473b18", "#615021", "#ffd700"),
            "soul silver": ("classic", "#1f2730", "#2b3642", "#c0d6e4"),
            "heartgold": ("classic", "#473b18", "#615021", "#ffd700"),
            "soulsilver": ("classic", "#1f2730", "#2b3642", "#c0d6e4"),
            "black": ("classic", "#141414", "#242424", "#666666"),
            "white": ("classic", "#383838", "#4d4d4d", "#cccccc"),
            "black 2": ("classic", "#0a0a0a", "#1a1a1a", "#4287f5"),
            "white 2": ("classic", "#404040", "#545454", "#f56042"),
            "x": ("classic", "#1a243b", "#263557", "#4c7be6"),
            "y": ("classic", "#3b1a1f", "#57262e", "#e64c5e"),
            "omega ruby": ("classic", "#591017", "#7a1620", "#ff2e43"),
            "alpha sapphire": ("classic", "#102959", "#16387a", "#2e6eff"),
            "sun": ("classic", "#3b2612", "#52361a", "#ff9d00"),
            "moon": ("classic", "#1d1436", "#2c1f52", "#9061ff"),
            "ultra sun": ("classic", "#241805", "#382508", "#ffae00"),
            "ultra moon": ("classic", "#110729", "#1d0c42", "#c300ff"),
            "let's go": ("modern", "#383116", "#4a411d", "#ffdd47"), 
            "sword": ("modern", "#122a3b", "#1a3a52", "#00aeff"),
            "shield": ("modern", "#3b1223", "#521a32", "#ff006a"),
            "brilliant diamond": ("modern", "#1a2a3b", "#233952", "#5ca8ff"),
            "shining pearl": ("modern", "#3b1a2f", "#522441", "#ff5ce2"),
            "legends arceus": ("modern", "#153338", "#1c4a52", "#38caff"),
            "scarlet": ("modern", "#421713", "#5c211c", "#ff4838"),
            "violet": ("modern", "#2b1342", "#3d1c5c", "#a238ff"),
            "legends z-a": ("modern", "#142921", "#1d3d31", "#38ff9d"),
            "z-a": ("modern", "#142921", "#1d3d31", "#38ff9d")
        }

        # --- SPRITE ENGINE: Maps games to PokeAPI internal folders ---
        # Gen 8 and 9 fallback automatically to the default modern sprite.
        self.SPRITE_PATHS = {
            "gold": ("generation-ii", "gold"),
            "silver": ("generation-ii", "silver"),
            "crystal": ("generation-ii", "crystal"),
            "ruby": ("generation-iii", "ruby-sapphire"),
            "sapphire": ("generation-iii", "ruby-sapphire"),
            "emerald": ("generation-iii", "emerald"),
            "fire red": ("generation-iii", "firered-leafgreen"),
            "leaf green": ("generation-iii", "firered-leafgreen"),
            "firered": ("generation-iii", "firered-leafgreen"),
            "leafgreen": ("generation-iii", "firered-leafgreen"),
            "diamond": ("generation-iv", "diamond-pearl"),
            "pearl": ("generation-iv", "diamond-pearl"),
            "platinum": ("generation-iv", "platinum"),
            "heart gold": ("generation-iv", "heartgold-soulsilver"),
            "soul silver": ("generation-iv", "heartgold-soulsilver"),
            "heartgold": ("generation-iv", "heartgold-soulsilver"),
            "soulsilver": ("generation-iv", "heartgold-soulsilver"),
            "black 2": ("generation-v", "black-white"),
            "white 2": ("generation-v", "black-white"),
            "black": ("generation-v", "black-white"),
            "white": ("generation-v", "black-white"),
            "omega ruby": ("generation-vi", "omegaruby-alphasapphire"),
            "alpha sapphire": ("generation-vi", "omegaruby-alphasapphire"),
            "x": ("generation-vi", "x-y"),
            "y": ("generation-vi", "x-y"),
            "ultra sun": ("generation-vii", "ultra-sun-ultra-moon"),
            "ultra moon": ("generation-vii", "ultra-sun-ultra-moon"),
            "sun": ("generation-vii", "sun-moon"),
            "moon": ("generation-vii", "sun-moon")
        }

        self.current_era = "modern"
        self.bg_color = "#222831"
        self.frame_bg = "#393E46"
        self.text_color = "#EEEEEE"
        self.accent_color = "#D65A31"
        self.delete_color = "#E94560"

        self.era_settings = {
            "retro": {"font": "Courier", "relief": "raised", "bw": 4, "btn_relief": "raised"},
            "classic": {"font": "Verdana", "relief": "groove", "bw": 2, "btn_relief": "flat"},
            "modern": {"font": "Helvetica", "relief": "flat", "bw": 0, "btn_relief": "flat"}
        }

        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')
        self.root.configure(padx=20, pady=20)

        self.game_var = tk.StringVar()
        self.pokemon_var = tk.StringVar()
        self.encounters_var = tk.IntVar(value=0)
        self.base_odds_var = tk.StringVar(value="1/4096 (Gen 6+)")
        
        self.current_pil_image = None
        self.current_sprite = None
        self.history_images = []
        self.history_widgets = [] 
        
        self.odds_label_var = tk.StringVar(value="Current Odds: 1/4096")
        self.prob_label_var = tk.StringVar(value="Cumulative Probability: 0.00%")
        
        self.charm_var = tk.BooleanVar()
        self.masuda_var = tk.BooleanVar()
        self.sandwich_var = tk.BooleanVar()

        self.apply_theme_styles()

        self.encounters_var.trace_add("write", self.calculate_odds)
        self.base_odds_var.trace_add("write", self.calculate_odds)
        self.charm_var.trace_add("write", self.calculate_odds)
        self.masuda_var.trace_add("write", self.calculate_odds)
        self.sandwich_var.trace_add("write", self.calculate_odds)
        self.game_var.trace_add("write", self.on_game_change)

        self.history = self.load_history()
        self.create_widgets()
        
        self.load_session()
        self.update_history_list()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def apply_theme_styles(self):
        settings = self.era_settings[self.current_era]
        base_font = (settings["font"], 10)
        bold_font = (settings["font"], 10, "bold")
        title_font = (settings["font"], 11, "bold")
        giant_font = ("Courier" if self.current_era == "retro" else settings["font"], 42, "bold")
        
        self.root.configure(bg=self.bg_color)
        
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("Panel.TFrame", background=self.frame_bg, relief=settings["relief"], borderwidth=settings["bw"])
        
        self.style.configure("TLabelframe", background=self.bg_color, foreground=self.text_color, font=title_font, relief=settings["relief"], borderwidth=settings["bw"])
        self.style.configure("TLabelframe.Label", background=self.bg_color, foreground=self.accent_color, font=title_font)
        
        self.style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=base_font)
        self.style.configure("Panel.TLabel", background=self.frame_bg, foreground=self.text_color, font=base_font)
        self.style.configure("Giant.Panel.TLabel", background=self.frame_bg, foreground=self.text_color, font=giant_font)
        self.style.configure("Accent.Panel.TLabel", background=self.frame_bg, foreground=self.accent_color, font=(settings["font"], 12, "bold"))
        
        self.style.configure("TCheckbutton", background=self.frame_bg, foreground=self.text_color, font=base_font)
        
        self.style.configure("TButton", background=self.frame_bg, foreground=self.text_color, font=bold_font, relief=settings["btn_relief"], borderwidth=settings["bw"] if self.current_era == "retro" else 0)
        self.style.map("TButton", background=[("active", self.accent_color)])
        
        self.style.configure("Accent.TButton", background=self.accent_color, foreground="white", font=(settings["font"], 14, "bold"), relief=settings["btn_relief"])
        self.style.map("Accent.TButton", background=[("active", self.accent_color)])
        
        self.style.configure("Delete.TButton", background=self.delete_color, foreground="white", font=bold_font, relief=settings["btn_relief"])
        self.style.map("Delete.TButton", background=[("active", "#c73049")])

        if hasattr(self, 'canvas'):
            self.canvas.configure(bg=self.frame_bg)
            self.scrollable_inner.configure(bg=self.frame_bg)
            self.counter_label.configure(style="Giant.Panel.TLabel")
            for widget in self.history_widgets:
                widget.configure(bg=self.bg_color, fg=self.text_color, font=base_font)

    def on_game_change(self, *args):
        game_str = self.game_var.get().lower()
        new_era, new_bg, new_frame, new_accent = "modern", "#222831", "#393E46", "#D65A31"
        
        sorted_keys = sorted(self.THEMES.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in game_str:
                new_era, new_bg, new_frame, new_accent = self.THEMES[key]
                break
                
        if self.bg_color != new_bg or self.current_era != new_era:
            self.current_era = new_era
            self.bg_color = new_bg
            self.frame_bg = new_frame
            self.accent_color = new_accent
            
            self.apply_theme_styles()
            if hasattr(self, 'scrollable_inner'):
                self.update_history_list()

    def create_widgets(self):
        setup_frame = ttk.LabelFrame(self.root, text="Hunt Setup", padding=15)
        setup_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(setup_frame, text="Game:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(setup_frame, textvariable=self.game_var, width=18).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(setup_frame, text="Pokémon:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(setup_frame, textvariable=self.pokemon_var, width=18).grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(setup_frame, text="Load Sprite", command=self.load_pokemon).grid(row=1, column=2, padx=10)
        
        ttk.Label(setup_frame, text="Base Odds:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(setup_frame, textvariable=self.base_odds_var, values=["1/4096 (Gen 6+)", "1/8192 (Gen 1-5)"], state="readonly", width=15).grid(row=2, column=1, padx=5, pady=5)

        display_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=15)
        display_frame.pack(fill="x", pady=5)

        self.image_label = ttk.Label(display_frame, text="Sprite will appear here", style="Panel.TLabel")
        self.image_label.pack(pady=5)

        self.counter_label = ttk.Label(display_frame, textvariable=self.encounters_var, style="Giant.Panel.TLabel")
        self.counter_label.pack(pady=5)

        btn_frame = ttk.Frame(display_frame, style="Panel.TFrame")
        btn_frame.pack()
        
        ttk.Button(btn_frame, text="-1", width=5, command=self.decrement).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="+1 (Encounter)", width=20, command=self.increment).grid(row=0, column=1, padx=5)

        odds_frame = ttk.Frame(display_frame, style="Panel.TFrame")
        odds_frame.pack(pady=10)
        
        ttk.Label(odds_frame, textvariable=self.odds_label_var, style="Accent.Panel.TLabel").pack()
        ttk.Label(odds_frame, textvariable=self.prob_label_var, style="Panel.TLabel").pack(pady=2)

        boosts_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=10)
        boosts_frame.pack(fill="x", pady=10)

        ttk.Checkbutton(boosts_frame, text="Shiny Charm", variable=self.charm_var, style="TCheckbutton").grid(row=0, column=0, padx=5)
        ttk.Checkbutton(boosts_frame, text="Masuda", variable=self.masuda_var, style="TCheckbutton").grid(row=0, column=1, padx=5)
        ttk.Checkbutton(boosts_frame, text="Sandwich/Lure", variable=self.sandwich_var, style="TCheckbutton").grid(row=0, column=2, padx=5)

        ttk.Button(self.root, text="✨ I CAUGHT IT! ✨", command=self.catch_shiny, style="Accent.TButton").pack(side="bottom", fill="x", pady=(10, 0), ipady=10)

        history_frame = ttk.LabelFrame(self.root, text="Caught Shinies", padding=5)
        history_frame.pack(side="top", fill="both", expand=True, pady=10)

        self.canvas = tk.Canvas(history_frame, bg=self.frame_bg, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_inner = tk.Frame(self.canvas, bg=self.frame_bg)
        self.scrollable_inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas.create_window((0, 0), window=self.scrollable_inner, anchor="nw", width=440)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.root.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.root.bind("<=>", lambda event: self.increment())

    def calculate_odds(self, *args):
        base_val = self.base_odds_var.get()
        base = 8192 if "8192" in base_val else 4096
        rolls = 1 
        
        if self.charm_var.get(): rolls += 2
        if self.masuda_var.get(): rolls += 5 if base == 4096 else 4
        if self.sandwich_var.get(): rolls += 3

        final_odds_denominator = max(1, base / rolls)
        self.odds_label_var.set(f"Current Odds: {rolls}/{base} (1/{final_odds_denominator:.0f})")

        encounters = self.encounters_var.get()
        if encounters > 0:
            chance_per_encounter = rolls / base
            probability = (1 - ((1 - chance_per_encounter) ** encounters)) * 100
            self.prob_label_var.set(f"Cumulative Probability: {probability:.2f}%")
        else:
            self.prob_label_var.set("Cumulative Probability: 0.00%")

    def load_pokemon(self):
        pokemon_name = self.pokemon_var.get().strip().lower()
        game_name = self.game_var.get().strip().lower()

        if not pokemon_name:
            messagebox.showwarning("Input Error", "Please enter a Pokémon name.")
            return False

        try:
            response = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_name}")
            if response.status_code == 200:
                data = response.json()
                sprite_url = None
                
                # 1. Search for Era-Specific Sprite
                sorted_sprite_keys = sorted(self.SPRITE_PATHS.keys(), key=len, reverse=True)
                for key in sorted_sprite_keys:
                    if key in game_name:
                        gen_str, game_str = self.SPRITE_PATHS[key]
                        try:
                            sprite_url = data['sprites']['versions'][gen_str][game_str].get('front_shiny')
                        except (KeyError, AttributeError):
                            pass
                        break
                
                # 2. Fallback to Modern/Default Sprite if Era Sprite is null/doesn't exist
                if not sprite_url:
                    sprite_url = data['sprites'].get('front_shiny')
                
                if sprite_url:
                    img_response = requests.get(sprite_url)
                    self.current_pil_image = Image.open(BytesIO(img_response.content))
                    
                    # Nearest-Neighbor resampling scales pixel art perfectly crisp!
                    display_img = self.current_pil_image.resize((160, 160), Image.Resampling.NEAREST)
                    self.current_sprite = ImageTk.PhotoImage(display_img)
                    self.image_label.config(image=self.current_sprite, text="")
                    return True
                else:
                    self.image_label.config(image="", text="No shiny sprite found.")
                    self.current_pil_image = None
                    return False
            else:
                messagebox.showerror("Error", "Pokémon not found. Check the spelling.")
                return False
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch data: {e}")
            return False

    def increment(self):
        self.encounters_var.set(self.encounters_var.get() + 1)

    def decrement(self):
        if self.encounters_var.get() > 0:
            self.encounters_var.set(self.encounters_var.get() - 1)

    def catch_shiny(self):
        pokemon = self.pokemon_var.get().strip()
        game = self.game_var.get().strip()
        encounters = self.encounters_var.get()

        if not pokemon or not game:
            messagebox.showwarning("Missing Info", "Please enter both the Game and Pokémon name!")
            return

        if not self.current_pil_image:
            success = self.load_pokemon()
            if not success: return

        if encounters == 0:
            if not messagebox.askyesno("Wait", "Counter is at 0. Did you get it on the first try?"):
                return

        thumb = self.current_pil_image.resize((64, 64), Image.Resampling.NEAREST)
        buffered = BytesIO()
        thumb.save(buffered, format="PNG")
        b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        boosts = []
        if self.charm_var.get(): boosts.append("Charm")
        if self.masuda_var.get(): boosts.append("Masuda")
        if self.sandwich_var.get(): boosts.append("Sandwich")
        boost_str = ", ".join(boosts) if boosts else "None"

        record = {
            "pokemon": pokemon.capitalize(),
            "game": game,
            "encounters": encounters,
            "boosts": boost_str,
            "probability": self.prob_label_var.get().split(": ")[1],
            "sprite_b64": b64_str
        }

        self.history.append(record)
        self.save_history()
        self.update_history_list()
        
        messagebox.showinfo("Congratulations!", f"Added Shiny {pokemon.capitalize()} to your collection!")
        self.encounters_var.set(0)

    def delete_record(self, index):
        if messagebox.askyesno("Delete", "Are you sure you want to delete this Shiny from your history?"):
            del self.history[index]
            self.save_history()
            self.update_history_list()

    def update_history_list(self):
        for widget in self.scrollable_inner.winfo_children():
            widget.destroy()
        self.history_images.clear()
        self.history_widgets.clear()

        era_relief = self.era_settings[self.current_era]["relief"]
        era_bw = self.era_settings[self.current_era]["bw"]
        era_font = (self.era_settings[self.current_era]["font"], 10)

        for i, item in enumerate(reversed(self.history)):
            actual_index = len(self.history) - 1 - i
            
            row_frame = tk.Frame(self.scrollable_inner, bg=self.bg_color, relief=era_relief if era_relief != "flat" else "solid", bd=era_bw if era_bw > 0 else 1)
            row_frame.pack(fill="x", pady=4, padx=5)
            
            if "sprite_b64" in item:
                img_data = base64.b64decode(item["sprite_b64"])
                img = Image.open(BytesIO(img_data))
                photo = ImageTk.PhotoImage(img)
                self.history_images.append(photo) 
                lbl_img = tk.Label(row_frame, image=photo, bg=self.bg_color)
                lbl_img.pack(side="left", padx=10, pady=5)
                
            info_text = f"✨ {item['pokemon']} | {item['game']}\n{item['encounters']} enc. ({item.get('probability', 'N/A')})\nBoosts: {item['boosts']}"
            lbl_text = tk.Label(row_frame, text=info_text, bg=self.bg_color, fg=self.text_color, justify="left", font=era_font)
            lbl_text.pack(side="left", fill="x", expand=True, pady=5)
            self.history_widgets.append(lbl_text)
            
            btn_del = ttk.Button(row_frame, text="X", width=3, style="Delete.TButton", command=lambda idx=actual_index: self.delete_record(idx))
            btn_del.pack(side="right", padx=10)

    def on_closing(self):
        state = {
            "game": self.game_var.get(),
            "pokemon": self.pokemon_var.get(),
            "encounters": self.encounters_var.get(),
            "base_odds": self.base_odds_var.get(),
            "charm": self.charm_var.get(),
            "masuda": self.masuda_var.get(),
            "sandwich": self.sandwich_var.get()
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
            
        self.root.destroy()

    def load_session(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    self.game_var.set(state.get("game", ""))
                    self.pokemon_var.set(state.get("pokemon", ""))
                    self.encounters_var.set(state.get("encounters", 0))
                    self.base_odds_var.set(state.get("base_odds", "1/4096 (Gen 6+)"))
                    self.charm_var.set(state.get("charm", False))
                    self.masuda_var.set(state.get("masuda", False))
                    self.sandwich_var.set(state.get("sandwich", False))
                    
                    if self.pokemon_var.get():
                        self.load_pokemon()
            except:
                pass 

    def load_history(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_history(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.history, f, indent=4)

if __name__ == "__main__":
    root = tk.Tk()
    app = ShinyTrackerApp(root)
    root.mainloop()