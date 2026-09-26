import pyaudiowpatch as pyaudio
import numpy as np
from scipy import signal
import wave
import time

# --- CONFIGURATION ---
TEMPLATE_FILE = "sounds/pokemon_sv/encounter.wav"
MATCH_THRESHOLD = 0.75  # 75% confidence needed to trigger

def load_template(filename):
    """Loads a .wav file and converts it to a numpy array."""
    with wave.open(filename, 'rb') as wf:
        # Read the raw audio data
        raw_data = wf.readframes(wf.getnframes())
        # Convert to numpy array (assuming 16-bit audio)
        audio_data = np.frombuffer(raw_data, dtype=np.int16)
        
        # If stereo, average the two channels into mono for easier matching
        if wf.getnchannels() == 2:
            audio_data = audio_data.reshape(-1, 2).mean(axis=1)
            
        # Normalize the template so loud/quiet volume doesn't break the math
        if np.max(np.abs(audio_data)) > 0:
            audio_data = audio_data / np.max(np.abs(audio_data))
            
        return audio_data, wf.getframerate()

def main():
    print(f"Loading template: {TEMPLATE_FILE}")
    try:
        template, template_rate = load_template(TEMPLATE_FILE)
    except Exception as e:
        print(f"Failed to load WAV file: {e}")
        return

    # Initialize PyAudio
    p = pyaudio.PyAudio()

    # Find the Default WASAPI Loopback Device (Your Speakers/Headphones)
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break

    print(f"Listening to: {default_speakers['name']} at {int(default_speakers['defaultSampleRate'])} Hz")

    # Audio stream settings
    chunk_size = 4096 * 4  # Read a good chunk of audio at a time
    rate = int(default_speakers["defaultSampleRate"])

    # Open the live audio stream
    stream = p.open(format=pyaudio.paInt16,
                    channels=default_speakers["maxInputChannels"],
                    rate=rate,
                    input=True,
                    input_device_index=default_speakers["index"],
                    frames_per_buffer=chunk_size)

    print("\n🎧 Listening for encounter sound... (Press Ctrl+C to stop)")
    last_trigger_time = 0

    try:
        while True:
            # Grab live audio data
            data = stream.read(chunk_size, exception_on_overflow=False)
            live_audio = np.frombuffer(data, dtype=np.int16)
            
            # Convert live audio to mono if it's stereo
            if default_speakers["maxInputChannels"] == 2:
                live_audio = live_audio.reshape(-1, 2).mean(axis=1)

            # Normalize live audio
            max_val = np.max(np.abs(live_audio))
            if max_val > 0:
                live_audio_norm = live_audio / max_val
            else:
                live_audio_norm = live_audio

            # Do a fast cross-correlation to find the template in the live audio
            # (We only do this if there's actual sound playing to save CPU)
            if max_val > 500: 
                correlation = signal.correlate(live_audio_norm, template, mode='valid')
                max_corr = np.max(correlation) / len(template)  # Rough confidence score
                
                if max_corr > MATCH_THRESHOLD:
                    current_time = time.time()
                    if current_time - last_trigger_time > 10.0:  # 10 second lockout
                        print(f"🔥 MATCH FOUND! (Confidence: {max_corr:.2f}) -> INCREMENT COUNTER")
                        last_trigger_time = current_time

    except KeyboardInterrupt:
        print("\nStopping listener...")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    main()