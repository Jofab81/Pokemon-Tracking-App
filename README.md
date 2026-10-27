# 🌟 Pokémon Shiny Tracker Suite

A collection of lightweight, customizable, and automated overlay tools designed to make your shiny hunting streams cleaner and easier. Whether you are hunting a single target manually, listening for sparkles, or running multiple games simultaneously with screen-reading OCR, there is a tracker here tailored to your specific hunting style.

All trackers feature a fully customizable transparent overlay. You can drag, drop, resize, and change the opacity of your Pokémon sprites, counters, and odds text directly on your screen!

---

## 📥 How to Download and Install

You do **not** need to download the Python source code to use these tools unless you want to edit them yourself.

1. Go to the **Releases** page on the right side of this GitHub repository.
2. Click on the latest release (`v2.0`).
3. Under the **Assets** section, download the `.exe` files for the trackers you want to use.
4. Put the downloaded `.exe` files into a dedicated folder on your computer (they will generate a `vision_layout.json` save file in whichever folder they are placed to remember your layout settings).
5. Double-click the `.exe` to run it!

> **Note:** Windows might show a blue "Windows protected your PC" popup since these are unknown indie apps. Just click **More Info -> Run Anyway**.

---

## 🛠️ The Trackers & How to Use Them

### 👁️ 1. Ultimate Multi-Hunt Vision Tracker (`vision_tracker.exe`)
An advanced, automated OCR (Optical Character Recognition) tracker that watches your game screens or camera feeds and counts encounters by reading text. Now updated to support multiple simultaneous hunts across different games!

* **Prerequisite:** You MUST have [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed on your computer for this to work. The app will automatically try to find it, or ask you to locate `tesseract.exe` the first time you run it.
* **How to use:**
  1. Click **+ Add Another Pokémon Tracker** to spawn a new hunt card. Type your target Pokémon's name and click **Load Image**.
  2. Choose your input method: **Select Screen Region** (for emulators/capture cards on your monitor) or **Select Camera Regions** (for physical webcams pointed at your screens).
  3. Draw a box over the area of your game where the Pokémon's name appears in text (e.g., `"A wild Pikachu appeared!"`). Press **ENTER** to lock it in.
  4. Repeat steps 1–3 for as many games/hunts as you are running.
  5. Click **Start Vision Auto-Tracker**. The app will quietly monitor all regions and independently increment your counters whenever a target Pokémon's name appears!

### 🎧 2. Audio Tracker (`Shiny_Tracker_Audio.zip`)
An automated tracker that runs in the background and listens to your system audio for the specific "shiny sparkle" sound effect.

* **How to use:**
  1. Launch the app and load your target Pokémon.
  2. Start the audio listener in the control panel.
  3. Play your game normally. When the app hears the shiny sparkle sound effect through your desktop audio, it will automatically register the encounter.
* ⚠️ **Important Limitation:** This tracker relies purely on wild encounter sound effects. It has not been configured to work with Egg hatches or Gift Pokémon! This is not a recommended version to use, as it's very buggy and not fully finished. This one is a discontinued project on here, but I'm leaving it up just in case anyone wants to use it.

### 🖱️ 3. Manual Tracker (`shiny_tracker.exe`)
The classic, reliable shiny tracker. Perfect for single hunts, soft resetting, or setups where audio/video automation isn't ideal.

* **How to use:**
  1. Launch the app and load your target Pokémon.
  2. Go into the Control Panel and click the buttons to bind your custom **+1**, **-1**, and **Caught** hotkeys (e.g., bind +1 to your Spacebar).
  3. Press your hotkey to manually increase your counter as you hunt.

---

## ⚙️ Shared Overlay & v2.0 Features

No matter which tracker you use, you have access to a powerful, fully transparent layout engine. The v2.0 update introduces massive quality-of-life improvements for multi-hunters:

* **Duplicate Tracker Syncing:** Hunting the exact same Pokémon on multiple consoles? Adding a duplicate tracker card automatically links its encounters to your primary visual counter and hides the duplicate sprites/text to keep your stream overlay completely clutter-free.
* **Responsive Masonry Grid:** The Control Panel is now fully responsive. Stretch your window wider, and your hunt settings and global options will dynamically snap into a fluid multi-column grid, reducing the need to scroll.
* **Precision Drag & Drop:** Click `"Enable Edit Mode"` to reveal the hitboxes of your UI elements. You can independently drag specific sprites, counters, or odds text anywhere on your screen. New trackers spawn with a staggered offset so they never get stuck glued together.
* **Live Resizing & Full Transparency:** Use the global sliders to make your sprites or text exactly the size you need. Check `"Make Background 100% Invisible"` to drop the background entirely, leaving just your floating tracker elements for OBS `"Window Capture"`.
* **Caught Team Manager:** Register a Pokémon as `"Caught!"` to permanently spawn its sprite on your screen. You can resize, drag, and toggle visibility for your entire shiny team!
* **Tracker Deletion:** Easily remove old or completed hunts from your overlay and save file with a single click.

---

## ⚠️ Known Issues & Disclaimers

**This is a solo passion project!** Because it interacts with live video feeds, OCR text reading, and system audio, you might encounter occasional bugs or quirks.

* **Missed Vision Counts:** If the Vision Tracker misses an encounter, double-check that your selected screen region is tight around the text box and the text has high contrast.
* **Corrupted Saves:** If your overlay window ever vanishes or shrinks to a single pixel due to an OS dragging glitch, simply restart the app. A new failsafe will automatically rescue corrupted window dimensions. Your layout, hotkeys, and counter numbers are safely auto-saved to a `.json` file every time you make a change, so you will never lose your progress!
