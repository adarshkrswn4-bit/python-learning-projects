import os
import re
import wave
import time
import threading
import numpy as np
import sounddevice as sd
import whisper
import keyboard
import pyautogui
import pyperclip
import tkinter as tk

# Disable PyAutoGUI delay for fast auto-pasting
pyautogui.PAUSE = 0.05

# Audio capture constants
SAMPLE_RATE = 16000
CHANNELS = 1
TEMP_AUDIO = "temp_dictation.wav"

# Global state
is_recording = False
audio_frames = []


# ==========================================
# 1. FLOATING WINDOW UI (Windows Win+H Style)
# ==========================================
class FloatingUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Whisper Flow Dictation")
        
        # Frameless, always-on-top window
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)  # Sleek transparency
        self.root.config(bg="#1c1c1c")

        # Set size and position (Top Center of primary screen)
        screen_w = self.root.winfo_screenwidth()
        window_w, window_h = 280, 50
        x_pos = (screen_w // 2) - (window_w // 2)
        y_pos = 40  # Top padding
        self.root.geometry(f"{window_w}x{window_h}+{x_pos}+{y_pos}")

        # Rounded container frame
        self.frame = tk.Frame(self.root, bg="#2d2d2d", highlightthickness=1, highlightbackground="#444444")
        self.frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Status indicator icon (Microphone)
        self.icon_label = tk.Label(self.frame, text="🎙️", font=("Segoe UI Emoji", 14), bg="#2d2d2d", fg="#888888")
        self.icon_label.pack(side=tk.LEFT, padx=(12, 5))

        # Status text label
        self.status_label = tk.Label(self.frame, text="Ready (Press Ctrl+Q)", font=("Segoe UI", 10, "bold"), bg="#2d2d2d", fg="#ffffff")
        self.status_label.pack(side=tk.LEFT, padx=5)

    def update_status(self, text, state="ready"):
        """Thread-safe UI update method."""
        def _update():
            self.status_label.config(text=text)
            if state == "recording":
                self.icon_label.config(text="🔴", fg="#ff4444")
                self.frame.config(highlightbackground="#ff4444")
            elif state == "processing":
                self.icon_label.config(text="⚙️", fg="#ffbb00")
                self.frame.config(highlightbackground="#ffbb00")
            else:  # ready
                self.icon_label.config(text="🎙️", fg="#888888")
                self.frame.config(highlightbackground="#444444")

        self.root.after(0, _update)

    def start(self):
        self.root.mainloop()


# Initialize UI instance globally
ui = FloatingUI()


# ==========================================
# 2. MODEL INITIALIZATION (NO JAVA NEEDED)
# ==========================================
print("[+] Initializing Models...")
whisper_model = whisper.load_model("tiny")  # Lightweight 'tiny' model
print("[+] Ready! Press Ctrl + Q to dictate.")


# ==========================================
# 3. TEXT POLISHING FUNCTION (PURE PYTHON)
# ==========================================
def clean_and_polish_text(raw_text: str) -> str:
    if not raw_text:
        return ""

    # 1. Strip thinking / hesitation words
    fillers = [
        r"\bum+\b", r"\bah+\b", r"\baam+\b", r"\baah+\b", 
        r"\buh+\b", r"\bhmm+\b", r"\ber+\b", r"\blike\b"
    ]
    cleaned = raw_text
    for pattern in fillers:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 2. Fix multiple spaces & double punctuation
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([,.?!])", r"\1", cleaned)

    # 3. Capitalize first letter of sentences
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
        
    return cleaned


# ==========================================
# 4. AUDIO RECORDING & AUTO-TYPING PIPELINE
# ==========================================
def record_audio_loop():
    """Reads audio input from microphone into memory buffer."""
    global audio_frames, is_recording
    
    def callback(indata, frames, time_info, status):
        if is_recording:
            audio_frames.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16', callback=callback):
        while is_recording:
            time.sleep(0.05)


def process_and_type():
    """Processes audio, filters fillers, cleans text, and types into focused window."""
    global audio_frames
    
    if not audio_frames:
        ui.update_status("No audio heard", "ready")
        return

    # Save temporary audio file
    audio_data = np.concatenate(audio_frames, axis=0)
    with wave.open(TEMP_AUDIO, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())

    # 1. Whisper Transcription
    result = whisper_model.transcribe(TEMP_AUDIO)
    raw_text = result.get("text", "").strip()

    if not raw_text:
        ui.update_status("Silence detected", "ready")
        return

    # 2. Pure-Python Filler Removal & Text Cleaning
    final_text = clean_and_polish_text(raw_text)

    # 3. Auto-Paste into active input field
    if final_text:
        previous_clipboard = pyperclip.paste()
        pyperclip.copy(final_text + " ")  # Trailing space for smooth typing
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        pyperclip.copy(previous_clipboard)

    # Cleanup & reset UI
    if os.path.exists(TEMP_AUDIO):
        os.remove(TEMP_AUDIO)

    ui.update_status("Done! (Ctrl+Q)", "ready")


def toggle_dictation():
    """Triggers when Ctrl + Q is pressed."""
    global is_recording, audio_frames

    if not is_recording:
        # Start recording
        is_recording = True
        audio_frames = []
        ui.update_status("Listening...", "recording")
        threading.Thread(target=record_audio_loop, daemon=True).start()
    else:
        # Stop recording & process
        is_recording = False
        ui.update_status("Polishing text...", "processing")
        threading.Thread(target=process_and_type, daemon=True).start()


# ==========================================
# 5. HOTKEY LISTENER & APPLICATION START
# ==========================================
def listen_hotkey():
    keyboard.add_hotkey('ctrl+q', toggle_dictation)
    keyboard.wait()

# Run hotkey listener in background thread
threading.Thread(target=listen_hotkey, daemon=True).start()

# Launch Tkinter UI Loop
if __name__ == "__main__":
    ui.start()