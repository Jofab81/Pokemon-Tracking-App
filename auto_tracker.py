import threading
import time
import mss
import numpy as np
import cv2

class AutoTrackerWorker:
    """Background thread that uses a lockout timer to ignore post-battle fades."""
    def __init__(self, callback_function):
        self.is_running = False
        self.callback = callback_function
        self.thread = None
        self.region = {"top": 200, "left": 200, "width": 400, "height": 300}
        self.brightness_threshold = 15
        
        # Lockout timer to prevent double-counting or end-of-battle triggers
        self.last_encounter_time = 0
        self.lockout_duration = 15.0 # Ignore triggers for 15 seconds after an encounter

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
                        # Check if we are currently outside of the lockout window
                        if (current_time - self.last_encounter_time) > self.lockout_duration:
                            print("-> ENCOUNTER DETECTED! Incrementing counter...")
                            self.callback()
                            # Reset the lockout clock
                            self.last_encounter_time = time.time()
                        else:
                            print("-> Black screen ignored (currently inside battle lockout window).")
                            
                            # Sleep a bit longer during the black screen to avoid spamming the console
                            time.sleep(1)

                except Exception as e:
                    print(f"Auto-tracker error: {e}")
                
                time.sleep(0.1)