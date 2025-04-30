#!/usr/bin/env python3
import os
import wave
import random
import threading
import time
import subprocess
import array
import pyaudio
import yt_dlp as youtube_dl
import keyboard
import mouse
import pyttsx3
import tkinter as tk
from tkinter import font as tkfont
import ctypes

# Custom classes
from scripts.playback import Playback
from scripts.gui import MainWindow
from scripts.utils import getTime

from config import (
    VIRTUAL_CABLE_RECORD_NAME,
    MUSIC_DIR, YOUTUBE_DIR, BINDS_DIR, DEBUG
)


class Controller:

    # --------------   Initialization   ------------

    def __init__(self):
        # Ensure library & binds folders exist
        os.makedirs(MUSIC_DIR,   exist_ok=True)
        os.makedirs(YOUTUBE_DIR, exist_ok=True)
        os.makedirs(BINDS_DIR,   exist_ok=True)

        # Initialize PyAudio & enumerate devices
        self.p = pyaudio.PyAudio()
        devs = [self.p.get_device_info_by_index(i)
                for i in range(self.p.get_device_count())]

        self.input_device = None

        print(len(devs), "devices found:")

        # Route all audio into the cable's record endpoint
        self.output_device = next(
            (i for i, info in enumerate(devs)
             if VIRTUAL_CABLE_RECORD_NAME in info['name']
             and info['maxOutputChannels'] == 2),
            None
        )
        
        if self.output_device is None:
            raise RuntimeError(
                f"Could not find '{VIRTUAL_CABLE_RECORD_NAME}' with 2 output channels"
            )
        if DEBUG:
            info = devs[self.output_device]
            print(f"[DEBUG] Routing audio → {info['name']} (index {self.output_device})")

        # Bind hotkeys
        self._start_keyboard_listeners()

        # Audio & mic volume popup state
        self.time_last_volume_popup = 0
        self.music_volume = 100
        self.mic_volume = 100

        # TTS state
        self.tts_capture_mode = False
        self.tts_capture_buffer = ""

        # Audio playback state
        self._playback = None
        self.music_entries = [] # Current music list
        self.load_music_list() # Load music list from disk

    # --------------   Event Handlers   ------------

    def on_scroll(self, event):
        # Ignore non-scroll events
        if not hasattr(event, 'delta'):
            return

        # Limit scroll event handler rate
        timeInterval = 50 # Minimum wait time in ms
        time = getTime()
        if time - self.time_last_volume_popup < timeInterval:
            return
        self.time_last_volume_popup = time

        # Update music or mic volume according to scroll direction
        volumeInterval = 5 # Percent change per scroll
        dy = event.delta
        if keyboard.is_pressed('ctrl'):
            self.music_volume = max(0, min(300, self.music_volume + (volumeInterval if dy > 0 else -volumeInterval)))
            self.show_popup(f"Music: {self.music_volume}%")
        elif keyboard.is_pressed('alt'):
            self.mic_volume = max(0, min(100, self.mic_volume + (volumeInterval if dy > 0 else -volumeInterval)))
            self.show_popup(f"Mic: {self.mic_volume}%")

    def _start_keyboard_listeners(self):
        def listen():
            keyboard.add_hotkey('ctrl+t', self.show_tts_entry_popup)
            keyboard.wait()  # Keep listener alive
        threading.Thread(target=listen, daemon=True).start()

    # --------------   Audio Playback   ------------

    def load_music_list(self):
        self.music_entries.clear()
        for folder in (MUSIC_DIR, YOUTUBE_DIR):
            if not os.path.isdir(folder): continue
            for fn in sorted(os.listdir(folder)):
                if fn.lower().endswith(('.wav', '.mp3')):
                    self.music_entries.append((fn, os.path.join(folder, fn)))

    # --------------   UI Helpers   ------------

    def show_popup(self, text, duration=1000):
        def _popup():
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            lbl = tk.Label(root, text=text,
                        font=("Segoe UI", 16, "bold"),
                        bg="black", fg="white",
                        padx=20, pady=10)
            lbl.pack()
            root.update_idletasks()
            w, h = root.winfo_width(), root.winfo_height()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            x = (sw - w)//2
            y = 0  # top center
            root.geometry(f"{w}x{h}+{x}+{y}")
            root.after(duration, root.destroy)
            root.mainloop()
        threading.Thread(target=_popup, daemon=True).start()

    def show_tts_entry_popup(self):
        self.tts_capture_mode = True

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.grab_set()
        root.focus_force()

        popup_font = tkfont.Font(root=root, family="Segoe UI", size=14, weight="bold")
        pad_x, pad_y = 20, 20

        label = tk.Label(
            root,
            text="Type: ",
            font=popup_font,
            bg="blue", fg="white",
            padx=pad_x, pady=pad_y
        )
        label.pack()

        def cancel():
            root.grab_release()
            root.destroy()
            self.tts_capture_mode = False
            self.tts_capture_buffer = ""

        def resize_window(text):
            # measure new text size
            width  = popup_font.measure(text) + pad_x * 2
            height = popup_font.metrics("linespace") + pad_y * 2
            sw = root.winfo_screenwidth()
            x  = (sw - width) // 2
            root.geometry(f"{width}x{height}+{x}+0")

        def on_key(event):
            key = event.keysym

            # Edit buffer
            if key == 'BackSpace':
                self.tts_capture_buffer = self.tts_capture_buffer[:-1]
            elif key == 'space':
                self.tts_capture_buffer += ' '
            elif event.char and len(event.char) == 1:
                self.tts_capture_buffer += event.char

            # Submit buffer
            if key in ('Return', 'KP_Enter'):
                text = self.tts_capture_buffer.strip()
                cancel() # Cancel out of tts popup; clear buffer
                if text:
                    # play_tts(text) # TODO implement
                    print("Playing TTS:", text)
                return

            # Cancel
            if key == 'Escape':
                cancel() # Cancel out of tts popup; maintain buffer
                return

            # Update UI label
            display = "Type: " + self.tts_capture_buffer
            label.config(text=display)

            # Resize popup to fit new text
            root.update_idletasks()
            resize_window(display)

        # Initialize popup size
        resize_window("Type: ")

        root.bind("<Key>", on_key)
        root.mainloop()


    # --------------   Main Loop   ------------
    
    def run(self):
        # Initialize audio & mic volume scroll
        mouse.hook(self.on_scroll)

        # Initialize single instances
        self._playback = Playback()

        # Initialize main window
        app = MainWindow(self)
        app.run()

        self.p.terminate()
        

# Start main loop
if __name__ == '__main__':
    Controller().run()