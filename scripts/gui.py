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

        self._create_menu()

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
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="[Media Selection Goes Here]").pack(side=tk.LEFT)
        

    def _create_device_selection_frame(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        # Mic In
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxInputChannels'] > 0]

        self.device_name_to_index = {d['name']: i for i, d in devs}

        ttk.Label(top, text="Mic In:").pack(side=tk.LEFT)
        self.input_device_cb = ttk.Combobox(top, values=list(self.device_name_to_index.keys()), state="readonly")
        self.input_device_cb.pack(side=tk.LEFT, padx=5)
        self.input_device_cb.bind('<<ComboboxSelected>>', self._on_device_change)

        # Speaker Out
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxOutputChannels'] > 0]

        self.output_device_name_to_index = {d['name']: i for i, d in devs}

        ttk.Label(top, text="Speaker Out:").pack(side=tk.LEFT)
        self.output_device_cb = ttk.Combobox(top, values=list(self.output_device_name_to_index.keys()), state="readonly")
        self.output_device_cb.pack(side=tk.LEFT, padx=5)
        self.output_device_cb.bind('<<ComboboxSelected>>', self._on_output_device_change)

    # --------------   Handlers   ------------

    def _on_device_change(self, event):
        name = self.input_device_cb.get()
        self.controller.input_device = self.device_name_to_index[name]

    def _on_output_device_change(self, event):
        name = self.output_device_cb.get()
        self.controller.output_device = self.output_device_name_to_index[name]

    def _on_mic_mode_change(self, event):
        mode = self.mic_mode.get()
        print(f"Mic mode changed to: {mode}")

    def _pause_resume_music(self):
        print("Pause/Resume music")    
    
    def _stop_music(self):
        print("Stop music")    

    # --------------   Main Loop   ------------

    def run(self):
        self.mainloop()