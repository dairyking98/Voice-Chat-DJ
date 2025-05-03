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
from tkinter import font as tkfont, ttk, simpledialog, messagebox
import ctypes

class MainWindow(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.title("VCDJ")
        self.geometry("1200x800")

        # TK Inputs
        self.input_device_cb = None # Input device combobox
        self.output_device_cb = None # Output device combobox
        self.tts_voice_cb = None # TTS voice combobox

        self.input_devs = [] # Input devices list
        self.output_devs = [] # Output devices list
        self.tts_voice_list = [] # TTS voices list

        self.youtube_url = None # Youtube URL text entry

        # Listen mode states
        self.listen_mic = None # Listen mic flag
        self.listen_music = None # Listen music flag
        self.listen_tts = None # Listen tts flag

        # Audio playback states
        self.music_list = None # Music listbox

        # Toolbar
        self._create_menu()

        # Frames
        self._create_device_selection_frame()
        self._create_play_pause_controls_frame()
        self._create_media_selection_frame()

    # --------------   Toolbar   ------------

    def _create_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

    # --------------   Frames   ------------

    def _create_device_selection_frame(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        # ------ MIC IN ------
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxInputChannels'] > 0]

        # Format list of devices as "index: name"
        self.input_devs = [f"{i}: {d['name']}" for i, d in devs]

        ttk.Label(top, text="Mic In:").pack(side=tk.LEFT)
        self.input_device_cb = ttk.Combobox(top, values=self.input_devs, state="readonly", width=40)
        self.input_device_cb.pack(side=tk.LEFT, padx=5)
        self.input_device_cb.bind('<<ComboboxSelected>>', self._on_device_change)
        self.input_device_cb.current(0) # Set default mic device

        # ------ SPEAKER OUT ------
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxOutputChannels'] > 0]

        # Format list of devices as "index: name"
        self.output_devs = [f"{i}: {d['name']}" for i, d in devs]

        ttk.Label(top, text="Speaker Out (Listen):").pack(side=tk.LEFT)
        self.output_device_cb = ttk.Combobox(top, values=self.output_devs, state="readonly", width=40)
        self.output_device_cb.pack(side=tk.LEFT, padx=5)
        self.output_device_cb.bind('<<ComboboxSelected>>', self._on_output_device_change)


        # ----- LISTEN MODES -----

        self.listen_mic = tk.BooleanVar(value=False)
        self.listen_music = tk.BooleanVar(value=False)
        self.listen_tts = tk.BooleanVar(value=False)

        ttk.Button(top, text="None", command=lambda: self._set_all_listen_modes(False)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top, text="All", command=lambda: self._set_all_listen_modes(True)).pack(side=tk.RIGHT, padx=2)

        ttk.Checkbutton(top, text="TTS", variable=self.listen_tts, command=self._on_listen_mode_change).pack(side=tk.RIGHT, padx=2)
        ttk.Checkbutton(top, text="Music", variable=self.listen_music, command=self._on_listen_mode_change).pack(side=tk.RIGHT, padx=2)
        ttk.Checkbutton(top, text="Mic", variable=self.listen_mic, command=self._on_listen_mode_change).pack(side=tk.RIGHT, padx=2)

        ttk.Label(top, text="Listen Mode: ").pack(side=tk.RIGHT, padx=5)

    def _create_media_selection_frame(self):
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        musicFrame = ttk.Labelframe(paned, text="Music Library", width=200)
        paned.add(musicFrame, weight=1)
        self.music_list = tk.Listbox(musicFrame)
        self.music_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(musicFrame, text="Refresh", command=self._refresh_music).pack(pady=5)
        self._refresh_music() # Load music list on startup

        ttsFrame = ttk.Labelframe(paned, text="TTS", width=200)
        paned.add(ttsFrame, weight=1)
        # add textbox textarea
        self.tts_text = tk.Text(ttsFrame, height=5)
        self.tts_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(ttsFrame, text="Play TTS", command=self._play_tts).pack(side=tk.LEFT, padx=10)
        ttk.Button(ttsFrame, text="Clear TTS", command=self._clear_tts).pack(side=tk.LEFT, padx=10)

        self.tts_voice_list = [f"{i}: {d.name}" for i, d in enumerate(self.controller._tts.voicelist)]

        # Add TTS voice selection
        ttk.Label(ttsFrame, text="TTS Voice").pack(side=tk.LEFT)
        self.tts_voice_cb = ttk.Combobox(ttsFrame, values=self.tts_voice_list, state="readonly", width=60)
        self.tts_voice_cb.pack(side=tk.LEFT, padx=5)
        self.tts_voice_cb.bind('<<ComboboxSelected>>', self._on_tts_voice_change)

    def _create_play_pause_controls_frame(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Button(
            top, text="Pause/Resume", command=self._pause_resume_music
        ).pack(side=tk.LEFT)

        ttk.Button(
            top, text="Stop", command=self._stop_music
        ).pack(side=tk.LEFT)

        ttk.Label(top, text="[Audio Meter Goes Here]").pack(side=tk.LEFT)

        
        ttk.Label(top, text="").pack(side=tk.LEFT, padx=10) # Horizontal spacer


        # add a textbox (not a textarea) for a youtube URL and then a button that says Download Youtube Video
        ttk.Label(top, text="Youtube URL:").pack(side=tk.LEFT)
        self.youtube_url = tk.Entry(top, width=50)
        self.youtube_url.pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Download", command=self.play_youtube_url).pack(side=tk.LEFT, padx=5)

                
    # --------------   Handlers   ------------

    def _on_device_change(self, event):
        dev_id = self.input_device_cb.get()
        dev_idx = dev_id.split(":")[0]
        self.controller.input_device = int(dev_idx)

    def _on_tts_voice_change(self, event):
        voice_id = self.tts_voice_cb.get()
        voice_idx = voice_id.split(":")[0]

        voice = self.controller._tts.voicelist[int(voice_idx)]

        self.controller._tts.tts_voice_id = voice.id
        self.controller._tts.tts_voice_name = str(voice.name)
        self.controller._tts.update_tts_voice()


    def _on_output_device_change(self, event):
        dev_id = self.output_device_cb.get()
        dev_idx = dev_id.split(":")[0]
        self.controller.listen_device = int(dev_idx)

    def _pause_resume_music(self):
        sel = self.music_list.curselection()
        if not sel:
            return
        track_index = sel[0]
        self.controller._playback.play_music(self.controller.music_entries[track_index][1], self.controller.p,  self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_music, self.controller.music_volume)

    
    def _stop_music(self):
        self.controller._playback.stop_music()

    def _refresh_music(self):
        self.controller.load_music_list() # Read music list from disk and update music_entries
        if self.music_list:
            self.music_list.delete(0, tk.END)
        for name, _ in self.controller.music_entries:
            self.music_list.insert(tk.END, name)

    def _play_tts(self):
        text = self.tts_text.get("1.0", tk.END).strip()
        if not text:
            return
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts)
    
    def _clear_tts(self):
        self.tts_text.delete("1.0", tk.END)

    def _set_all_listen_modes(self, state):
        self.listen_mic.set(state)
        self.listen_music.set(state)
        self.listen_tts.set(state)
        self._on_listen_mode_change()

    def _on_listen_mode_change(self):
        self.controller.listen_enabled_mic = self.listen_mic.get()
        self.controller.listen_enabled_music = self.listen_music.get()
        self.controller.listen_enabled_tts = self.listen_tts.get()

    def play_youtube_url(self):
        url = self.youtube_url.get().strip()
        self.controller.play_youtube_url(url)

    # --------------   Main Loop   ------------

    def run(self):
        self.mainloop()