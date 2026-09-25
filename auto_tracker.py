import threading
import time
import mss
import numpy as np
import cv2

class AutoTrackerWorker:
    def __init__(self, callback_function):
        self.is_running = False
        self.callback = callback_function # This will trigger your +1 counter
        self.thread = None

    def start_loop(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

    def stop_loop(self):
        self.is_running = False

    def _capture_loop(self):
        # Define the screen region to watch (Left, Top, Width, Height pixels)
        monitor_region = {"top": 200, "left": 200, "width": 400, "height": 300}
        
        with mss.mss() as sct:
            last_frame = None
            
            while self.is_running:
                # 1. Grab the specific screen region
                img = np.array(sct.grab(monitor_region))
                
                # 2. Convert to grayscale to simplify pixel comparison
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                
                if last_frame is not None:
                    # 3. Compare the current frame to the previous frame
                    # Calculate absolute difference between pixels
                    diff = cv2.absdiff(gray, last_frame)
                    non_zero_count = np.count_nonzero(diff > 25) # Threshold for change
                    
                    # 4. If a massive pixel shift happens (e.g., battle transition flash)
                    if non_zero_count > 5000: # Adjust threshold based on your game
                        self.callback() # Trigger your app's increment function!
                        time.sleep(3)   # Cooldown so it doesn't count the same encounter 50 times
                
                last_frame = gray
                time.sleep(0.1) # Check roughly 10 times a second