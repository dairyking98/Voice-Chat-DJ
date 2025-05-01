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
        self.geometry("900x600")

        # Toolbar
        self._create_menu()

        # TK Inputs
        self.input_device_cb = None # Input device combobox
        self.output_device_cb = None # Output device combobox
        self.input_devs = [] # Input devices list
        self.output_devs = [] # Output devices list

        # Audio playback states
        self.music_list = None # Music listbox
        self.default_output_device = None # Default output device

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


    def _create_media_selection_frame(self):
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        musicFrame = ttk.Labelframe(paned, text="Music Library", width=300)
        paned.add(musicFrame, weight=1)
        self.music_list = tk.Listbox(musicFrame)
        self.music_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(musicFrame, text="Refresh", command=self._refresh_music).pack(pady=5)
        self._refresh_music() # Load music list on startup

        ttsFrame = ttk.Labelframe(paned, text="TTS", width=300)
        paned.add(ttsFrame, weight=1)
        # add textbox textarea
        self.tts_text = tk.Text(ttsFrame, height=5)
        self.tts_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(ttsFrame, text="Play TTS", command=self._play_tts).pack(pady=5)
        ttk.Button(ttsFrame, text="Clear TTS", command=self._clear_tts).pack(pady=5)


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
        self.input_device_cb = ttk.Combobox(top, values=self.input_devs, state="readonly")
        self.input_device_cb.pack(side=tk.LEFT, padx=5)
        self.input_device_cb.bind('<<ComboboxSelected>>', self._on_device_change)

        # ------ SPEAKER OUT ------
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxOutputChannels'] > 0]

        # Format list of devices as "index: name"
        self.output_devs = [f"{i}: {d['name']}" for i, d in devs]

        ttk.Label(top, text="Speaker Out:").pack(side=tk.LEFT)
        self.output_device_cb = ttk.Combobox(top, values=self.output_devs, state="readonly")
        self.output_device_cb.pack(side=tk.LEFT, padx=5)
        self.output_device_cb.bind('<<ComboboxSelected>>', self._on_output_device_change)

        # Set default output device
        if self.controller.output_device is not None:
            self.default_output_device = self.controller.output_device
            self._set_output_device_to_default()
                
        ttk.Button(top, text="Set Output to Default", command=self._set_output_device_to_default).pack(side=tk.LEFT, padx=5)

    # --------------   Handlers   ------------

    def _on_device_change(self, event):
        dev_id = self.input_device_cb.get()
        dev_idx = dev_id.split(":")[0]
        self.controller.input_device = int(dev_idx)

    def _on_output_device_change(self, event):
        dev_id = self.output_device_cb.get()
        dev_idx = dev_id.split(":")[0]
        self.controller.output_device = int(dev_idx)

    def _set_output_device_to_default(self):
        if self.default_output_device is not None:
            # Set output device to default
            self.controller.output_device = self.default_output_device

            # Update GUI
            # Find the formatted string that matches the index
            target_value = f"{self.controller.output_device}:"
            for i, item in enumerate(self.output_devs):
                if item.startswith(target_value):
                    self.output_device_cb.current(i)
                    break

    def _on_mic_mode_change(self, event):
        mode = self.mic_mode.get()
        print(f"Mic mode changed to: {mode}")

    def _pause_resume_music(self):
        print("Pause/Resume music")    
        sel = self.music_list.curselection()
        if not sel:
            return
        track_index = sel[0]
        self.controller._playback.play_music(self.controller.music_entries[track_index][1], self.controller.p, self.controller.output_device, self.controller.input_device, False, 0, self.controller.music_volume)

    
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
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.input_device, False)
    
    def _clear_tts(self):
        self.tts_text.delete("1.0", tk.END)

    # --------------   Main Loop   ------------

    def run(self):
        self.mainloop()