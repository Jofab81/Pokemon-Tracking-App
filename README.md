# 🌟 Pokémon Shiny Tracker Suite

A collection of lightweight, customizable, and automated overlay tools designed to make your shiny hunting streams cleaner and easier. Whether you want to hunt manually, listen for sparkles, or have the app automatically read your game screen, there is a tracker here for your specific hunting style.

All trackers feature a fully customizable transparent overlay. You can drag, drop, resize, and change the opacity of your Pokémon sprites, counters, and odds text directly on your screen!

---

## 📥 How to Download and Install

You do **not** need to download the Python source code to use these tools unless you want to edit them yourself.

1. Go to the [Releases page](../../releases) on the right side of this GitHub repository.
2. Click on the latest release.
3. Under the **Assets** section, download the `.exe` files for the trackers you want to use.
4. Put the downloaded `.exe` files into a dedicated folder on your computer (they will generate a save file in whichever folder they are placed to remember your layout settings).
5. Double-click the `.exe` to run it! 
   * *Note: Windows might show a blue "Windows protected your PC" popup since these are unknown indie apps. Just click **More Info -> Run Anyway**.*

---

## 🛠️ The Trackers & How to Use Them

### 👁️ 1. Vision Tracker (`vision_tracker.exe`)
An automated, pure-OCR (Optical Character Recognition) tracker that watches your game screen and counts encounters by reading text.

* **Prerequisite:** You MUST have [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed on your computer for this to work. The app will automatically try to find it, or ask you to locate `tesseract.exe` the first time you run it.
* **How to use:**
  1. Type your target Pokémon's name into the setup menu and click **Load** (it will automatically fetch the shiny sprite).
  2. Click **Select Screen Region to Watch**.
  3. A transparent gray window will appear. Click and drag a box directly over the area of your game where the Pokémon's name appears in text (e.g., "A wild Pikachu appeared!"). Press **ENTER** to lock it in.
  4. Click **Start Vision Auto-Tracker**. The app will now quietly read that box and add +1 to your counter whenever your target Pokémon's name appears!

### 🎧 2. Audio Tracker (`obs_tracker.exe`)
An automated tracker that runs in the background and listens to your system audio for the specific "shiny sparkle" sound effect.

* **How to use:**
  1. Launch the app and load your target Pokémon.
  2. Start the audio listener in the control panel.
  3. Play your game normally. When the app hears the shiny sparkle sound effect through your desktop audio, it will automatically register the encounter.
* ⚠️ **Important Limitation:** This tracker relies purely on wild encounter sound effects. It has **not** been configured to work with Egg hatches or Gift Pokémon!

### 🖱️ 3. Manual Tracker (`manual_tracker.exe`)
The classic, reliable shiny tracker. Perfect for dual-hunting, soft resetting, or hunts where audio/video automation isn't ideal.

* **How to use:**
  1. Launch the app and load your target Pokémon.
  2. Go into the Control Panel and click the buttons to bind your custom **+1**, **-1**, and **Caught** hotkeys (e.g., bind +1 to your Spacebar).
  3. Press your hotkey to manually increase your counter as you hunt.

---

## ⚙️ Shared Overlay Features

No matter which tracker you use, you have access to a powerful layout engine:
* **Edit Mode:** Click "Enable Edit Mode" in the control panel to reveal the hitboxes of your UI elements.
* **Drag & Drop:** Click and drag the sprite, counter, or odds text anywhere on your screen.
* **Live Resizing:** Use the sliders in the control panel to make your sprite or text as big or small as you need.
* **Full Transparency:** Check the "Make Background 100% Invisible" box to turn the green background completely transparent, leaving just your floating tracker elements on screen. Perfect for capturing via OBS "Window Capture".
* **Caught Screen:** Register a Pokémon as "Caught!" to permanently spawn its sprite on your screen. You can resize and toggle visibility for your entire shiny team!

---

## ⚠️ Known Issues & Disclaimers

**This is a solo passion project!** Because it interacts with live video feeds, OCR text reading, and system audio, you might encounter occasional bugs or quirks.
* **Missed Vision Counts:** If the Vision Tracker misses an encounter, double-check that your selected screen region is tight around the text box and the text has good contrast.
* **App Freezes:** If an app freezes, simply close it and restart it. Your layout, hotkeys, and counter numbers are automatically saved to a `.json` file every time you make a change, so you won't lose your progress!
