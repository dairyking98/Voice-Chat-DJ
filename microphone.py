#!/usr/bin/env python3
import os
import wave
import random
import threading
import time
import subprocess
import array
import pyaudio
import keyboard
import mouse
import pyttsx3
import ctypes
import re
import json
import os
import sys
import tkinter as tk
import yt_dlp as youtube_dl
from tkinter import font as tkfont
from pynput import mouse as pymouse
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

# Custom classes
from scripts.playback import Playback
from scripts.tts import TTS
from scripts.gui import MainWindow
from scripts.utils import getTime

from config import (
    VIRTUAL_CABLE_RECORD_NAME,
    MUSIC_DIR, YOUTUBE_DIR, BINDS_DIR, DEBUG,
    DB_DIR, SETTINGS_DB_PATH,
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
        self.app = None # Main window
        devs = [self.p.get_device_info_by_index(i)
                for i in range(self.p.get_device_count())]

        self.input_device = 0 # Default input device

        # Route all audio into the cable's record endpoint
        self.output_device = next(
            (i for i, info in enumerate(devs)
             if VIRTUAL_CABLE_RECORD_NAME in info['name']
             and info['maxOutputChannels'] == 2),
            None
        )

        self.listen_device = None # Default listen device
        
        if self.output_device is None:
            raise RuntimeError(
                f"Could not find '{VIRTUAL_CABLE_RECORD_NAME}' with 2 output channels"
            )
        if DEBUG:
            info = devs[self.output_device]
            print(f"[DEBUG] Routing audio → {info['name']} (index {self.output_device})")

        # Audio & mic volume popup state
        self.time_last_volume_popup = 0
        self.music_volume = 100
        self.mic_volume = 100

        # TTS state
        self.tts_capture_mode = False
        self.tts_capture_buffer = ""
        self._tts_rate = 160 # Default TTS rate

        # Audio playback state
        self._playback = None
        self.music_entries = [] # Current music list
        self.load_music_list() # Load music list from disk

        self.listen_enabled_mic = False # Listen mode for micrphone passthrough
        self.listen_enabled_music = False # Listen mode for music playback
        self.listen_enabled_tts = False # Listen mode for TTS playback

        # Mic passthrough state
        self.mic_modes = ["Off", "On", "Push to Talk"] # Mic modes
        self.mic_mode = "Push to Talk" # Mic mode

        # Audio transform state for mic
        self.pitch_transform_enabled = False
        self.pitch_transform_semitones = 0
        self.reverb_transform_enabled = False
        self.robot_transform_enabled = False

        # Binds config
        self.binds = {}

        # GPT profiles
        self.client = None
        self.ai_api_key = ""

        # Current profile
        self.gpt_profile = None

        # All profiles
        self.default_gpt_profile = {
            "name": "",
            "system_prompt": "",
            "temperature": 0.7,
            "max_tokens": 80,
            "top_p": 0.9,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.5,
            "fewshots": []
        }

        self.gpt_profiles = []

    def get_current_gpt_profile(self):
        if self.gpt_profile is None:
            return self.default_gpt_profile
        return self.gpt_profiles[self.gpt_profile]


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
        volumeInterval = 10 # Percent change per scroll
        dy = event.delta
        if keyboard.is_pressed('ctrl'):
            self.music_volume = max(0, min(600, self.music_volume + (volumeInterval if dy > 0 else -volumeInterval)))
            self.show_popup(f"Music: {self.music_volume}%")
        elif keyboard.is_pressed('alt'):
            self.mic_volume = max(0, min(100, self.mic_volume + (volumeInterval if dy > 0 else -volumeInterval)))
            self.show_popup(f"Mic: {self.mic_volume}%")

    def _start_keyboard_listeners(self):
        def listen():
            keyboard.add_hotkey('ctrl+tab', self.show_tts_entry_popup)

            # go through 0 to 9 and make a ctrl + the number and alambda funciotn that apsses that param
            for i in range(10):
                keyboard.add_hotkey(f'ctrl+{i}', lambda i=i: self.play_bind(i))


            keyboard.wait()  # Keep listener alive
        threading.Thread(target=listen, daemon=True).start()

    # --------------   Audio Related Functions   ------------

    def load_music_list(self):
        self.music_entries.clear()
        for folder in (MUSIC_DIR, YOUTUBE_DIR):
            if not os.path.isdir(folder): continue
            for fn in sorted(os.listdir(folder)):
                if fn.lower().endswith(('.wav', '.mp3')):
                    self.music_entries.append((fn, os.path.join(folder, fn)))

    def play_youtube_url(self, url):
        def _dl():
            self._playback.stop_music()
            opts={'format':'bestaudio/best',
                'outtmpl':os.path.join(YOUTUBE_DIR,'%(title)s.%(ext)s'),
                'quiet':True,
                'postprocessors':[{'key':'FFmpegExtractAudio',
                                    'preferredcodec':'wav',
                                    'preferredquality':'192'}]}
            with youtube_dl.YoutubeDL(opts) as ydl:
                info=ydl.extract_info(url,download=True)

            self.app._refresh_music()

            name=info.get('title')+'.wav'
            for idx,(n,path) in enumerate(self.music_entries):
                if re.sub(r"\s+", "", n)==re.sub(r"\s+", "", name): 
                    self.app.music_list.selection_clear(0, tk.END)
                    self.app.music_list.selection_set(idx)        # Select the audio item in the GUI music list
                    self.app.music_list.see(idx)                  # Scroll to it
                    self.app.play_selected_song(False)                 # Play the audio
                    return
            print("Downloaded not found.")
        threading.Thread(target=_dl,daemon=True).start()

    def play_bind(self, bindNumber):
        if bindNumber not in self.binds:
            return
        bind = self.binds[bindNumber]
        # find music entry with name
        for idx,(n,path) in enumerate(self.music_entries):
            if re.sub(r"\s+", "", n)==re.sub(r"\s+", "", bind): 
                self.app.music_list.selection_clear(0, tk.END)
                self.app.music_list.selection_set(idx)        # Select the audio item in the GUI music list
                self.app.music_list.see(idx)                  # Scroll to it
                self.app.play_selected_song(True)                 # Play the audio
                return


    def mic_down(self):
        self._playback.switch_to_mic(self.p, self.input_device, self.output_device, self.listen_device, self.listen_enabled_mic, self.mic_volume)

    def mic_up(self):
        self._playback.stop_mic()

    def mic_listen(self):
        def on_click(x, y, button, pressed):
            if button == pymouse.Button.x1 and self.mic_mode == "Push to Talk":  # Mouse4 button
                if pressed:
                    self.mic_down()
                else:
                    self.mic_up()

        # Start the listener in a separate thread
        listener = pymouse.Listener(on_click=on_click)
        listener.start()

    

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
        self.app.open_popup()

    # --------------   DB Actions   ------------
    
    def _initialize_db(self):
        # Create db directory if it doesn't exist
        if not os.path.exists(DB_DIR):
            os.makedirs(DB_DIR)

        # Create db if it doesn't exist
        if not os.path.exists(SETTINGS_DB_PATH):
            with open(SETTINGS_DB_PATH, 'w') as f:
                json.dump({}, f)
            self.push_settings()  # Save current settings to db

    def _load_db(self):
        # Load db
        if not os.path.exists(SETTINGS_DB_PATH):
            return {}
        with open(SETTINGS_DB_PATH, 'r') as f:
            return json.load(f)

    def update_db(self, updates: dict):
        # Update db given a dictionary of updates
        data = self._load_db()
        data.update(updates)
        with open(SETTINGS_DB_PATH, 'w') as f:
            json.dump(data, f, indent=2)

    def pull_settings(self):
        # Load settings from db
        db = self._load_db()
        self.mic_mode = db.get("mic_mode", "Push to Talk")
        self.music_volume = db.get("music_volume", 100)
        self.mic_volume = db.get("mic_volume", 100)
        self.input_device = db.get("input_device", 0)
        self.listen_device = db.get("listen_device", None)
        self.listen_enabled_mic = db.get("listen_enabled_mic", False)
        self.listen_enabled_music = db.get("listen_enabled_music", False)
        self.listen_enabled_tts = db.get("listen_enabled_tts", False)
        self._tts_rate = db.get("tts_rate", 160)
        self.binds = db.get("binds", {})
        self.gpt_profile = db.get("gpt_profile", None)
        self.gpt_profiles = db.get("gpt_profiles", [])

        self.ai_api_key = db.get("ai_api_key", "")

        # Non-controller settings
        self._tts.tts_volume = db.get("tts_volume", 100)
    
    def push_settings(self):
        # Save current settings to db
        updates = {
            "mic_mode": self.mic_mode,
            "music_volume": self.music_volume,
            "mic_volume": self.mic_volume,
            "input_device": self.input_device,
            "listen_device": self.listen_device,
            "listen_enabled_mic": self.listen_enabled_mic,
            "listen_enabled_music": self.listen_enabled_music,
            "listen_enabled_tts": self.listen_enabled_tts,
            "binds": self.binds,
            "tts_rate": self._tts_rate,
            "ai_api_key": self.ai_api_key,
            "gpt_profile": self.gpt_profile,
            "gpt_profiles": self.gpt_profiles,

            # Non-controller settings
            "tts_volume": self._tts.tts_volume,
        }
        
        self.update_db(updates)
            

    # --------------   Main Loop   ------------

    def reset(self):
        # Delete db file
        if SETTINGS_DB_PATH and os.path.exists(SETTINGS_DB_PATH):
            os.remove(SETTINGS_DB_PATH)

        # Restart program to reload settings
        # TODO: Currently I only have a way to update all the GUI on init in gui.py so i resort to restarting the program.
        # Need to create a method to update GUI dynamically
        subprocess.Popen([sys.executable, __file__])
        os._exit(0)


    def initializeGPTClient(self):
        self.client = OpenAI(api_key=self.ai_api_key)
    
    def ai(self, user_text):
        fewshots = self.get_current_gpt_profile()["fewshots"]
        messages = [
            {"role": "system",    "content": self.get_current_gpt_profile()["system_prompt"]},
            {"role": "user",      "content": user_text},
        ]

        # Insert fewshot prompts
        for fewshot in reversed(fewshots):
            messages.insert(1, {"role": "user", "content": fewshot["input"]})
            messages.insert(2, {"role": "assistant", "content": fewshot["output"]})

        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            # Decoding & Sampling Parameters:
            temperature=self.get_current_gpt_profile()["temperature"],
            max_tokens=self.get_current_gpt_profile()["max_tokens"],
            top_p=self.get_current_gpt_profile()["top_p"],
            frequency_penalty=self.get_current_gpt_profile()["frequency_penalty"],
            presence_penalty=self.get_current_gpt_profile()["presence_penalty"],
        )
        return resp.choices[0].message.content.strip()
    
    def run(self):
        # Initialize audio & mic volume scroll
        mouse.hook(self.on_scroll)

        # Mic passthrough binds
        self.mic_listen()

        # Initialize single instances
        self._playback = Playback(self)
        self._tts = TTS(self)

        # Bind hotkeys
        self._start_keyboard_listeners()
        
        # Initialize db if it doesn't exist
        self._initialize_db()

        # Load settings from db
        self.pull_settings()  

        self.initializeGPTClient()

        # Initialize main window
        self.app = MainWindow(self)
        self.app.run()

        # Cleanup
        self.p.terminate()

# Start main loop
if __name__ == '__main__':
    Controller().run()