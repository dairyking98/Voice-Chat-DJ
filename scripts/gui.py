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
import re
import win32gui
import win32con
import win32com.client
import ctypes
from tkinter import ttk
import tkinter as tk
from tkinter import font as tkfont, ttk, simpledialog, messagebox

class MainWindow(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.title("VCDJ")
        self.geometry("1300x790")

        # TK Inputs
        self.bind_menu = None # Bind menu

        self.input_device_cb = None # Input device combobox
        self.output_device_cb = None # Output device combobox
        self.tts_voice_cb = None # TTS voice combobox

        self.input_devs = [] # Input devices list
        self.output_devs = [] # Output devices list
        self.tts_voice_list = [] # TTS voices list

        self.youtube_url = None # Youtube URL text entry

        self.mic_mode_cb = None # Mic mode combobox

        self.tts_popup = None # TTS popup window
        self.tts_popup_entry = None # TTS popup entry
        self.tts_popup_rate_slider = None # TTS rate slider for popup
        self.tts_popup_rate_label = None # TTS rate label for popup

        self.tts_rate_slider = None # TTS rate slider for main window
        self.tts_rate_label = None # TTS rate label for main window

        self.tts_mode_cb = None # TTS mode combobox
        self.tts_voice_cb = None # TTS voice combobox

        self.music_volume_label = None # Music volume label
        self.mic_volume_label = None # Mic volume label
        self.tts_volume_label = None # TTS volume label

        self.gpt_popup = None # GPT popup window
        self.gpt_popup_name_entry = None # GPT profile name entry
        self.gpt_popup_system_entry = None # GPT system prompt entry
        self.gpt_popup_assistant_entry = None # GPT assistant prompt entry
        self.gpt_popup_temperature_slider = None # GPT temperature slider
        self.gpt_popup_temperature_label = None # GPT temperature label
        self.gpt_popup_maxtoken_slider = None # GPT max token slider
        self.gpt_popup_maxtoken_label = None # GPT max token label
        self.gpt_popup_top_p_slider = None # GPT top p slider
        self.gpt_popup_top_p_label = None # GPT top p label
        self.gpt_popup_frequency_penalty_slider = None # GPT frequency penalty slider
        self.gpt_popup_frequency_penalty_label = None # GPT frequency penalty label
        self.gpt_popup_presence_penalty_slider = None # GPT presence penalty slider
        self.gpt_popup_presence_penalty_label = None # GPT presence penalty label

        self.vu_meter = None # VU meter for sound output        

        # TTS Popup state
        self._tts_popup_rate = 160 # TTS rate for popup window
        self.tts_mode = "TTS" # TTS mode
        self._tts_voice_mode = "OpenAI" # TTS voice mode
        self._tts_voice_modes = ["SAPI5", "OpenAI"] # TTS voice modes list
        self._tts_voice = "sage"
        self._tts_voices = ["nova", "shimmer", "echo", "onyx", "fable", "alloy", "ash", "sage", "coral"]

        # Listen mode states
        self.listen_mic = None # Listen mic flag
        self.listen_music = None # Listen music flag
        self.listen_tts = None # Listen tts flag

        # Audio playback states
        self.music_list = None # Music listbox

        # Toolbar
        self._create_menu()

        self.topFrame = ttk.Frame(self, padding=10)
        self.topFrame.pack(side=tk.TOP, fill=tk.X)

        self.bottomFrame = ttk.Frame(self, padding=10)
        self.bottomFrame.pack(side=tk.TOP, fill=tk.X)


        # Frames
        self._create_device_selection_frame()
        self._create_volume_frame()
        self._create_tts_frame()
        self._create_media_playback_frame()

        self.sync_binds()

    # --------------   Toolbar   ------------

    def _create_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Reset Settings", command=self.reset_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        gpt_menu = tk.Menu(menubar, tearoff=False)
        gpt_menu.add_command(label="Set OpenAI API key", command=self.open_set_api_key_popup)
        gpt_menu.add_separator()

        # Add a profile for every profile in self.controller.gpt_profiles
        for idx, profile in enumerate(self.controller.gpt_profiles):
            label = f"{idx} - {profile['name']}"
            if idx == self.controller.gpt_profile:
                label = "* " + label
            submenu = tk.Menu(gpt_menu, tearoff=False)
            submenu.add_command(label="Set", command=lambda i=idx: self.set_gpt_profile(i))
            submenu.add_command(label="Edit", command=lambda i=idx: self.create_gpt_profile("edit", i))
            submenu.add_command(label="Delete", command=lambda i=idx: self.delete_gpt_profile(i))
            gpt_menu.add_cascade(label=label, menu=submenu)

        gpt_menu.add_command(label="Create GPT Profile", command=lambda: self.create_gpt_profile("create"))
        
        self.bind_menu = tk.Menu(menubar, tearoff=False)
        # Binds 0 -> 9
        for i in range(10):
            self.bind_menu.add_command(label=f"{i} - None", command=lambda i=i: self.set_bind(i))
        menubar.add_cascade(label="Binds", menu=self.bind_menu)
        menubar.add_cascade(label="GPT", menu=gpt_menu)
        self.config(menu=menubar)

    def set_gpt_profile(self, profile_id):
        # Set the current profile to the selected one
        self.controller.gpt_profile = profile_id
        self._create_menu()
        self.controller.push_settings()

    def delete_gpt_profile(self, profile_id):
        # Delete the selected profile from the list, and unset the current profile
        del self.controller.gpt_profiles[profile_id]
        if self.controller.gpt_profile == profile_id:
            self.controller.gpt_profile = None
        elif self.controller.gpt_profile > profile_id:
            self.controller.gpt_profile -= 1
        self._create_menu()
        self.controller.push_settings()
    
    def edit_gpt_profile(self, profile_id):
        print("Editing GPT profile:", profile_id)

    def set_bind(self, bindNumber):
        if self.controller.binds.get(bindNumber) is not None:
            self.controller.binds[bindNumber] = None
            self.bind_menu.delete(bindNumber)
            self.bind_menu.insert_command(bindNumber, label=f"{bindNumber} - None", command=lambda: self.set_bind(bindNumber))
            keyboard.remove_hotkey(f'ctrl+{bindNumber}') # Unbind hotkey
            return

        # get music list selction song name
        sel = self.music_list.curselection()
        if not sel:
            return
        track_index = sel[0]
        song_name = self.controller.music_entries[track_index][0]
        self.controller.binds[bindNumber] = song_name
        # bind hotkey
        keyboard.add_hotkey(f'ctrl+{bindNumber}', lambda i=bindNumber: self.controller.play_bind(bindNumber))
        # remove command from menu and add new one
        self.bind_menu.delete(bindNumber)
        self.bind_menu.insert_command(bindNumber, label=f"{bindNumber} - {song_name}", command=lambda: self.set_bind(bindNumber))

        self.sync_binds()

        # Save current settings to db
        self.controller.push_settings()

    def sync_binds(self):
        # Update GUI for binds to reflect current state
        for i in range(10):
            if self.controller.binds.get(str(i)) is not None:
                self.bind_menu.delete(i)
                self.bind_menu.insert_command(i, label=f"{i} - {self.controller.binds.get(str(i))}", command=lambda i=i: self.set_bind(i))
                keyboard.add_hotkey(f'ctrl+{str(i)}', lambda i=str(i): self.controller.play_bind(str(i)))

    def open_set_api_key_popup(self):
        api_key = simpledialog.askstring("Set OpenAI API Key", "Enter API Key:")
        if api_key is None:
            return
        self.controller.ai_api_key = api_key.strip()
        self.controller.push_settings()
        self.controller.initializeGPTClient()

    def create_gpt_profile(self, mode, selected_profile=None):
        if self.gpt_popup and self.gpt_popup.winfo_exists():
            self._gpt_popup_set_focus()
            return

        profile_values = self.controller.default_gpt_profile.copy() if mode == "create" else self.controller.gpt_profiles[selected_profile].copy()

        self.gpt_popup = tk.Toplevel()
        self.gpt_popup.title("Edit GPT Profile" if mode == "edit" else "Create GPT Profile")
        self.gpt_popup.geometry("500x600")

        # Name entry
        subframe = ttk.Frame(self.gpt_popup, height=50)
        subframe.pack(fill=tk.X, pady=(10,10), padx=20, anchor="w")
        label = ttk.Label(subframe, text="Name:", width=8)
        label.pack(side=tk.LEFT)
        self.gpt_popup_name_entry = tk.Entry(subframe)
        self.gpt_popup_name_entry.pack(fill="both", expand=True)
        self.gpt_popup_name_entry.insert(0, profile_values["name"])

        # System prompt
        label = ttk.Label(self.gpt_popup, text="System prompt:")
        label.pack(pady=(10, 10), padx=20, anchor="w")
        self.gpt_popup_system_entry = tk.Text(self.gpt_popup, wrap=tk.WORD, height=5)
        self.gpt_popup_system_entry.pack(fill="both", expand=True, padx = 20)
        self.gpt_popup_system_entry.insert("1.0", profile_values["system_prompt"])

        # Assistant few-shot prompt
        label = ttk.Label(self.gpt_popup, text="Few-Shot prompt:", anchor="w")
        label.pack(pady=(10, 10), padx=20, anchor="w")
        self.gpt_popup_assistant_entry = tk.Text(self.gpt_popup, wrap=tk.WORD, height=5)
        self.gpt_popup_assistant_entry.pack(fill="both", expand=True, padx = 20)
        self.gpt_popup_assistant_entry.insert("1.0", profile_values["assistant_prompt"])

        # Temperature slider
        subframe = ttk.Frame(self.gpt_popup, height=50)
        subframe.pack(fill=tk.X, pady=(10,10), padx=20, anchor="w")
        label = ttk.Label(subframe, text="Temperature:", width=20)
        label.pack(side=tk.LEFT)
        self.gpt_popup_temperature_slider = ttk.Scale(subframe, from_=0, to=1, orient=tk.HORIZONTAL, command=self._gpt_popup_temperature_slider_change, length=220)
        self.gpt_popup_temperature_slider.pack(side=tk.LEFT)
        self.gpt_popup_temperature_slider.set(profile_values["temperature"])
        self.gpt_popup_temperature_label = ttk.Label(subframe, width=5)
        self.gpt_popup_temperature_label.pack(side=tk.LEFT, padx=(20, 0))
        self.gpt_popup_temperature_label.config(text=str(profile_values["temperature"]))


        # Max token slider
        subframe = ttk.Frame(self.gpt_popup, height=50)
        subframe.pack(fill=tk.X, pady=(0,20), padx=20, anchor="w")
        label = ttk.Label(subframe, text="Max tokens:", width=20)
        label.pack(side=tk.LEFT)
        self.gpt_popup_maxtoken_slider = ttk.Scale(subframe, from_=10, to=200, orient=tk.HORIZONTAL, command=self._gpt_popup_maxtoken_slider_change, length=220)
        self.gpt_popup_maxtoken_slider.pack(side=tk.LEFT)
        self.gpt_popup_maxtoken_slider.set(profile_values["max_tokens"])
        self.gpt_popup_maxtoken_label = ttk.Label(subframe, width=5)
        self.gpt_popup_maxtoken_label.pack(side=tk.LEFT, padx=(20, 0))
        self.gpt_popup_maxtoken_label.config(text=str(profile_values["max_tokens"]))


        # Top P slider
        subframe = ttk.Frame(self.gpt_popup, height=50)
        subframe.pack(fill=tk.X, pady=(0,20), padx=20, anchor="w")
        label = ttk.Label(subframe, text="Top P:", width=20)
        label.pack(side=tk.LEFT)
        self.gpt_popup_top_p_slider = ttk.Scale(subframe, from_=0, to=1, orient=tk.HORIZONTAL, command=self._gpt_popup_top_p_slider_change, length=220)
        self.gpt_popup_top_p_slider.pack(side=tk.LEFT)
        self.gpt_popup_top_p_slider.set(profile_values["top_p"])
        self.gpt_popup_top_p_label = ttk.Label(subframe, width=5)
        self.gpt_popup_top_p_label.pack(side=tk.LEFT, padx=(20, 0))
        self.gpt_popup_top_p_label.config(text=str(profile_values["top_p"]))


        # Frequency penalty slider
        subframe = ttk.Frame(self.gpt_popup, height=50)
        subframe.pack(fill=tk.X, pady=(0,20), padx=20, anchor="w")
        label = ttk.Label(subframe, text="Frequency Penalty:", width=20)
        label.pack(side=tk.LEFT)
        self.gpt_popup_frequency_penalty_slider = ttk.Scale(subframe, from_=-2, to=2, orient=tk.HORIZONTAL, command=self._gpt_popup_frequency_penalty_slider_change, length=220)
        self.gpt_popup_frequency_penalty_slider.pack(side=tk.LEFT)
        self.gpt_popup_frequency_penalty_slider.set(profile_values["frequency_penalty"])
        self.gpt_popup_frequency_penalty_label = ttk.Label(subframe, width=5)
        self.gpt_popup_frequency_penalty_label.pack(side=tk.LEFT, padx=(20, 0))
        self.gpt_popup_frequency_penalty_label.config(text=str(profile_values["frequency_penalty"]))


        # Presence penalty slider
        subframe = ttk.Frame(self.gpt_popup, height=50)
        subframe.pack(fill=tk.X, pady=(0,20), padx=20, anchor="w")
        label = ttk.Label(subframe, text="Presence Penalty:", width=20)
        label.pack(side=tk.LEFT)
        self.gpt_popup_presence_penalty_slider = ttk.Scale(subframe, from_=-2, to=2, orient=tk.HORIZONTAL, command=self._gpt_popup_presence_penalty_slider_change, length=220)
        self.gpt_popup_presence_penalty_slider.pack(side=tk.LEFT)
        self.gpt_popup_presence_penalty_slider.set(profile_values["presence_penalty"])
        self.gpt_popup_presence_penalty_label = ttk.Label(subframe, width=5)
        self.gpt_popup_presence_penalty_label.pack(side=tk.LEFT, padx=(20, 0))
        self.gpt_popup_presence_penalty_label.config(text=str(profile_values["presence_penalty"]))

        
        # Save button
        button_frame = ttk.Frame(self.gpt_popup, height=50)
        button_frame.pack(fill=tk.X, pady=(0, 20), padx=20, anchor="w")
        save_button = ttk.Button(button_frame, text="Save", command=lambda mode=mode: self._save_gpt_profile(mode, selected_profile))
        save_button.pack(side=tk.LEFT, padx=5)

        self._gpt_popup_set_focus()

    # --------------   Frames   ------------

    def _create_device_selection_frame(self):

        spacing = 7

        # Add labelframe using grid (not pack)
        frame = ttk.Frame(self.topFrame, padding=5)
        frame.pack(side=tk.LEFT, anchor='n') 

        labelframe = ttk.Labelframe(frame, text="Audio Devices", padding=5)
        labelframe.pack(side=tk.LEFT, anchor='n') 

        subframe = ttk.Frame(labelframe, height=250, width=300)
        subframe.pack(fill=tk.X, pady=(0, 5), anchor='n')
        subframe.pack_propagate(False)

        # Content inside labelframe
        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X, pady=(spacing, spacing))
        simpleSubframeDiv.pack_propagate(False)

        # ------ MIC IN ------
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxInputChannels'] > 0]

        # Format list of devices as "index: name"
        self.input_devs = [f"{i}: {d['name']}" for i, d in devs]

        ttk.Label(simpleSubframeDiv, text="Mic In").pack(fill=tk.X)
        self.input_device_cb = ttk.Combobox(simpleSubframeDiv, values=self.input_devs, state="readonly", width=40)
        self.input_device_cb.pack(side=tk.LEFT)
        self.input_device_cb.bind('<<ComboboxSelected>>', self._on_device_change)

        # Select the current input device in the combobox
        for idx, val in enumerate(self.input_devs):
            if val.startswith(f"{self.controller.input_device}:"):
                self.input_device_cb.current(idx)  # Set combobox selection
                break

        # ------ SPEAK (LISTEN) OUT ------
        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X, pady=(spacing, spacing))
        simpleSubframeDiv.pack_propagate(False)  # Prevent frame from resizing to fit contents
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxOutputChannels'] > 0]

        # Format list of devices as "index: name"
        self.output_devs = [f"{i}: {d['name']}" for i, d in devs]

        ttk.Label(simpleSubframeDiv, text="Speaker Out (Listen)").pack(fill=tk.X)
        self.output_device_cb = ttk.Combobox(simpleSubframeDiv, values=self.output_devs, state="readonly", width=40)
        self.output_device_cb.pack(side=tk.LEFT)
        self.output_device_cb.bind('<<ComboboxSelected>>', self._on_output_device_change)

        # Select the current listen device in the combobox
        for idx, val in enumerate(self.output_devs):
            if val.startswith(f"{self.controller.listen_device}:"):
                self.output_device_cb.current(idx)  # Set combobox selection
                break

        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X,pady=(spacing, spacing))
        simpleSubframeDiv.pack_propagate(False)  # Prevent frame from resizing to fit contents

        # ----- LISTEN MODES -----

        self.listen_mic = tk.BooleanVar(value=self.controller.listen_enabled_mic)
        self.listen_music = tk.BooleanVar(value=self.controller.listen_enabled_music)
        self.listen_tts = tk.BooleanVar(value=self.controller.listen_enabled_tts)

        
        ttk.Label(simpleSubframeDiv, text="Listen Mode").pack(fill=tk.X)
        ttk.Checkbutton(simpleSubframeDiv, text="Music", variable=self.listen_music, command=self._on_listen_mode_change).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Checkbutton(simpleSubframeDiv, text="Mic", variable=self.listen_mic, command=self._on_listen_mode_change).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(simpleSubframeDiv, text="TTS", variable=self.listen_tts, command=self._on_listen_mode_change).pack(side=tk.LEFT, padx=2)

        ttk.Button(simpleSubframeDiv, text="All", width=6, command=lambda: self._set_all_listen_modes(True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(simpleSubframeDiv, text="None", width=6, command=lambda: self._set_all_listen_modes(False)).pack(side=tk.LEFT, padx=4)

        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X, pady=(0, 5))
        simpleSubframeDiv.pack_propagate(False)

        ttk.Label(simpleSubframeDiv, text="Mic Mode").pack(fill=tk.X)
        modeToId = {
            "Off": 0,
            "On": 1,
            "Push to Talk": 2
        }
        self.mic_mode_cb = ttk.Combobox(simpleSubframeDiv, values=["Off", "On", "Push to Talk"], state="readonly", width=20)
        self.mic_mode_cb.current(modeToId[self.controller.mic_mode])  # Set combobox selection
        self.mic_mode_cb.pack(side=tk.LEFT)
        self.mic_mode_cb.bind('<<ComboboxSelected>>', lambda e: self.controller.set_mic_mode(self.mic_mode_cb.get()))

        # Set current mic mode
        self.controller.set_mic_mode(self.mic_mode_cb.get())

        # Select current mic mode in the combobox
        for idx, val in enumerate(["Off", "On", "Push to Talk"]):
            if val == self.controller.mic_mode:
                self.mic_mode_cb.current(idx)
                break

    def _create_volume_frame(self):
        frame = ttk.Frame(self.topFrame, padding=5)
        frame.pack(side=tk.LEFT, anchor='n') 

        labelframe = ttk.Labelframe(frame, text="Volume", padding=5)
        labelframe.pack(side=tk.LEFT, anchor='n')

        subframe = ttk.Frame(labelframe, height=250, width=300)
        subframe.pack(fill=tk.X, pady=(0, 5), anchor='n')
        subframe.pack_propagate(False)

        # Content inside labelframe
        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X, pady=(0, 5))
        simpleSubframeDiv.pack_propagate(False)

        # create a volume slider for each volume type (music_volume, mic_volume, tts_volume)
        ttk.Label(simpleSubframeDiv, text="Music", width=8).pack(side=tk.LEFT)
        self.music_volume_slider = ttk.Scale(simpleSubframeDiv, length=200, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_music_volume_change)
        self.music_volume_slider.pack(side=tk.LEFT)
        self.music_volume_slider.set(self.controller.music_volume)

        self.music_volume_label = ttk.Label(simpleSubframeDiv, text=str(self.controller.music_volume))
        self.music_volume_label.pack(side=tk.LEFT, padx=5)

        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X, pady=(0, 5))
        simpleSubframeDiv.pack_propagate(False)

        ttk.Label(simpleSubframeDiv, text="Mic", width=8).pack(side=tk.LEFT)
        self.mic_volume_slider = ttk.Scale(simpleSubframeDiv, length=200, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_mic_volume_change)
        self.mic_volume_slider.pack(side=tk.LEFT)
        self.mic_volume_slider.set(self.controller.mic_volume)

        self.mic_volume_label = ttk.Label(simpleSubframeDiv, text=str(self.controller.mic_volume))
        self.mic_volume_label.pack(side=tk.LEFT, padx=5)

        simpleSubframeDiv = ttk.Frame(subframe, height=50, width=300)
        simpleSubframeDiv.pack(fill=tk.X, pady=(0, 5))
        simpleSubframeDiv.pack_propagate(False)

        ttk.Label(simpleSubframeDiv, text="TTS", width=8).pack(side=tk.LEFT)
        self.tts_volume_slider = ttk.Scale(simpleSubframeDiv, length=200, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_tts_volume_change)
        self.tts_volume_slider.pack(side=tk.LEFT)
        self.tts_volume_slider.set(self.controller._tts.tts_volume)

        self.tts_volume_label = ttk.Label(simpleSubframeDiv, text=str(self.controller._tts.tts_volume))
        self.tts_volume_label.pack(side=tk.LEFT, padx=5)

    
    def _create_tts_frame(self):
        frame = ttk.Frame(self.topFrame, padding=5)
        frame.pack(side=tk.LEFT, anchor='n')

        # Add labelframe using grid (not pack)
        labelframe = ttk.Labelframe(frame, text="Text-To-Speech", padding=5)
        labelframe.pack(side=tk.LEFT, anchor='n')


        # Content inside labelframe
        subframe = ttk.Frame(labelframe, height=250, width=600)
        subframe.pack(fill=tk.X, pady=(0, 5), anchor='n')
        subframe.pack_propagate(False)


        leftSubFrameDiv = ttk.Frame(subframe, height=250, width=300)
        leftSubFrameDiv.pack(side=tk.LEFT, padx=5, pady=5, anchor='n')
        leftSubFrameDiv.pack_propagate(False)

        # add textbox textarea
        self.tts_text = tk.Text(leftSubFrameDiv, width=30, wrap=tk.WORD)
        self.tts_text.pack(side=tk.LEFT, padx=5, pady=5, anchor='n', fill="both", expand=True)

        rightSubFrameDiv = ttk.Frame(subframe, height=250, width=300)
        rightSubFrameDiv.pack(side=tk.RIGHT, padx=5, pady=5, anchor='n')
        rightSubFrameDiv.pack_propagate(False)

        rightTop = ttk.Frame(rightSubFrameDiv, height=40, width=300)
        rightTop.pack(side=tk.TOP, pady=(0, 5), anchor='n')
        rightTop.pack_propagate(False)


        ttk.Button(rightTop, text="Play TTS", command=self._play_tts).pack(side=tk.LEFT, padx=10)
        ttk.Button(rightTop, text="Clear TTS", command=self._clear_tts).pack(side=tk.LEFT, padx=10)
        ttk.Button(rightTop, text="Save TTS", command=self._save_tts).pack(side=tk.LEFT, padx=10)

        rightMiddle = ttk.Frame(rightSubFrameDiv, height=40, width=300)
        rightMiddle.pack(side=tk.TOP, pady=(0, 5), anchor='n')
        rightMiddle.pack_propagate(False)

        self.tts_voice_list = [f"{i}: {d.name}" for i, d in enumerate(self.controller._tts.voicelist)]

        # Add TTS voice selection
        ttk.Label(rightMiddle, text="TTS Voice").pack(side=tk.LEFT)
        self.tts_voice_cb = ttk.Combobox(rightMiddle, values=self.tts_voice_list, state="readonly", width=60)
        self.tts_voice_cb.pack(side=tk.LEFT, padx=5)
        self.tts_voice_cb.bind('<<ComboboxSelected>>', self._on_tts_voice_change)
        self.tts_voice_cb.current(0)

        rightBottom = ttk.Frame(rightSubFrameDiv, height=40, width=300)
        rightBottom.pack(side=tk.TOP, pady=(0, 5), anchor='n')
        rightBottom.pack_propagate(False)

        # Add tts rate slider
        ttk.Label(rightBottom, text="TTS Rate:").pack(side=tk.LEFT)
        self.tts_rate_slider = ttk.Scale(rightBottom, from_=0, to=300, orient=tk.HORIZONTAL, command=self._tts_rate_change, length=180)
        self.tts_rate_slider.pack(side=tk.LEFT, padx=5)
        self.tts_rate_slider.set(self.controller._tts_rate)
        self.tts_rate_label = ttk.Label(rightBottom, text=str(self.controller._tts_rate))
        self.tts_rate_label.pack(side=tk.LEFT, padx=5)


        anotherBottomFrame = ttk.Frame(rightSubFrameDiv, height=40, width=300)
        anotherBottomFrame.pack(side=tk.TOP, pady=(0, 5), anchor='n')
        anotherBottomFrame.pack_propagate(False)

        self.vu_meter = ttk.Progressbar(anotherBottomFrame, orient="horizontal", length=200, mode="determinate", maximum=100)
        self.vu_meter.pack(side=tk.LEFT, padx=5, pady=5, anchor='n')



    def _create_media_playback_frame(self):
        frame = ttk.Frame(self.bottomFrame, padding=5)
        frame.pack(side=tk.LEFT, anchor='n')

        labelframe = ttk.Labelframe(frame, text="Music Library", padding=10, width=200)
        labelframe.pack(side=tk.LEFT, anchor='n')

        subframe = ttk.Frame(labelframe, height=400, width=1237.5)
        subframe.pack(fill=tk.X, pady=(0, 5), anchor='n')
        subframe.pack_propagate(False)

        topFrame = ttk.Frame(subframe, height=50, width=1240)
        topFrame.pack(side=tk.TOP, pady=(0, 5), anchor='n')
        topFrame.pack_propagate(False)

        ttk.Button(
            topFrame, text="Pause/Resume", command=self._pause_resume_music
        ).pack(side=tk.LEFT)

        ttk.Button(
            topFrame, text="Stop", command=self._stop_music
        ).pack(side=tk.LEFT)

        ttk.Label(topFrame, text="Youtube URL:").pack(side=tk.LEFT, padx=20)
        self.youtube_url = tk.Entry(topFrame, width=50)
        self.youtube_url.pack(side=tk.LEFT)
        ttk.Button(topFrame, text="Download", command=self.play_youtube_url).pack(side=tk.LEFT, padx=10)

        bottomFrame = ttk.Frame(subframe, height=300, width=600)
        bottomFrame.pack(fill=tk.BOTH, expand=True, pady=(0, 5), anchor='n')
        bottomFrame.pack_propagate(False)

        self.music_list = tk.Listbox(bottomFrame)
        ttk.Button(bottomFrame, text="Refresh", command=self._refresh_music).pack(side=tk.TOP, pady=5, anchor='w')
        self.music_list.pack(fill=tk.BOTH, expand=True)
        self.music_list.bind('<Double-Button-1>', lambda e: self.play_selected_song(False))

        self._refresh_music() # Load music list on startup
        

    def open_popup(self):
        # If tts window is already open, bring it to the front and focus
        if self.tts_popup and self.tts_popup.winfo_exists():
            self._tts_popup_set_focus()
            return

        self.tts_popup = tk.Toplevel()
        self.tts_popup.title("TTS")
        self.tts_popup.geometry("400x200")
        self.tts_popup.bind("<Escape>", lambda event: self._cancel_tts_popup())

        label = ttk.Label(self.tts_popup, text="Enter something:")
        label.pack(pady=(10, 0))

        self.tts_popup_entry = ttk.Entry(self.tts_popup, width=40)
        # self.tts_popup_entry.pack(pady=5)
        self.tts_popup_entry.pack(fill="x", expand=True, padx = 20)
        self.tts_popup_entry.bind("<Return>", lambda event: [self._play_tts_popup(), self._cancel_tts_popup()])

        button_frame = ttk.Frame(self.tts_popup)
        button_frame.pack(pady=10)

        ok_button = ttk.Button(button_frame, text="Play", command=self._play_tts_popup)
        ok_button.pack(side=tk.LEFT, padx=5)
        

        cancel_button = ttk.Button(button_frame, text="Cancel", command=self._cancel_tts_popup)
        cancel_button.pack(side=tk.LEFT, padx=5)

        # mode_frame = ttk.Frame(self.tts_popup)
        # mode_frame.pack(pady=10)

        # TTS mode dropdown
        self.tts_mode_cb = ttk.Combobox(self.tts_popup, values=["TTS", "AI TTS"], state="readonly", width=20)
        self.tts_mode_cb.current(1 if self.tts_mode == "AI TTS" else 0)
        self.tts_mode_cb.pack(side=tk.LEFT, padx=5)
        self.tts_mode_cb.bind('<<ComboboxSelected>>', self._on_tts_mode_change)

        self.tts_voice_mode_cb = ttk.Combobox(self.tts_popup, values=["SAPI5", "OpenAI"], state="readonly", width=20)
        self.tts_voice_mode_cb.current(self._tts_voice_modes.index(self._tts_voice_mode))
        self.tts_voice_mode_cb.pack(side=tk.RIGHT, padx=5)
        self.tts_voice_mode_cb.bind('<<ComboboxSelected>>', self._on_tts_voice_mode_change)

        self.tts_voice_cb = ttk.Combobox(self.tts_popup, values=self._tts_voices, state="readonly", width=20)
        self.tts_voice_cb.current(self._tts_voices.index(self._tts_voice))
        self.tts_voice_cb.pack(side=tk.RIGHT, padx=5)
        self.tts_voice_cb.bind('<<ComboboxSelected>>', self._on_tts_voice_change)

        rate_frame = ttk.Frame(self.tts_popup)
        rate_frame.pack(pady=10)

        self.tts_popup_rate_slider = ttk.Scale(rate_frame, from_=0, to=300, orient=tk.HORIZONTAL, command=self._tts_popup_rate_change, length=250)
        self.tts_popup_rate_slider.pack(side=tk.LEFT, padx=5)
        self.tts_popup_rate_slider.set(self._tts_popup_rate)

        # Add label showing the rate number
        self.tts_popup_rate_label = ttk.Label(rate_frame, text=str(self._tts_popup_rate))
        self.tts_popup_rate_label.pack(side=tk.LEFT, padx=5)
        
        # Use after_idle to delay focus setting
        self._tts_popup_set_focus()
                
    # --------------   Handlers   ------------

    def _on_device_change(self, event):
        dev_id = self.input_device_cb.get()
        dev_idx = dev_id.split(":")[0]
        self.controller.input_device = int(dev_idx)
        self.controller.push_settings()  # Save current settings to db

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
        self.controller.push_settings()  # Save current settings to db

    def _pause_resume_music(self):
        # Toggle pause flag
        if self.controller._playback._pause_flag.is_set():
            self.controller._playback.resume_music()
        else:
            self.controller._playback.pause_music()

    def play_selected_song(self, multithreaded):
        sel = self.music_list.curselection()
        if not sel:
            return
        track_index = sel[0]
        self.controller._playback.play_music(self.controller.music_entries[track_index][1], self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_music, self.controller.music_volume, multithreaded)
    
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
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts, self.controller._tts_rate)

    # TTS POPUP -----
    
    def _play_tts_popup(self):
        if self.tts_mode_cb.get() == "TTS":
            text = self.tts_popup_entry.get().strip()
        elif self.tts_mode_cb.get() == "AI TTS":
            text = self.controller.ai(self.tts_popup_entry.get().strip())
        else:
            return

        if not text:
            return

        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts, self._tts_popup_rate, self._tts_voice_mode, self._tts_voice)

    def _play_ai_tts_popup(self):
        text = self.controller.ai(self.tts_popup_entry.get().strip())
        if not text:
            return
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts, self._tts_popup_rate)

    def _cancel_tts_popup(self):
        self.tts_popup.destroy()
        self.tts_popup = None  # Reset the popup reference

    def _tts_popup_set_focus(self):
        # Focus on window on OS level
        hwnd = self.tts_popup.winfo_id()
        self.force_focus_hwnd(hwnd)

        # Focus window and system prompt
        self.tts_popup.focus_force()
        self.tts_popup_entry.focus_set()

    def _gpt_popup_set_focus(self):
        # Focus on window on OS level
        hwnd = self.gpt_popup.winfo_id()
        self.force_focus_hwnd(hwnd)

        # Focus window and name entry
        self.gpt_popup.focus_force()
        self.gpt_popup_name_entry.focus_set()

    def _tts_popup_rate_change(self, value):
        self._tts_popup_rate = int(float(value))
        if self.tts_popup_rate_label and self.tts_popup_rate_label.winfo_exists():
            # Update the label to show the current rate
            self.tts_popup_rate_label.config(text=str(self._tts_popup_rate))

    def _tts_rate_change(self, value):
        self.controller._tts_rate = int(float(value))
        if self.tts_rate_label and self.tts_rate_label.winfo_exists():
            # Update the label to show the current rate
            self.tts_rate_label.config(text=str(self.controller._tts_rate))

        self.controller.push_settings()  # Save current settings to db

    def _on_tts_mode_change(self, event):
        self.tts_mode = self.tts_mode_cb.get()

    def _on_tts_voice_mode_change(self, event):
        self._tts_voice_mode = self.tts_voice_mode_cb.get()

    def _on_tts_voice_change(self, event):
        self._tts_voice = self.tts_voice_cb.get()

    # -------



    # GPT POPUP -----

    def _gpt_popup_temperature_slider_change(self, value):
        if not self.gpt_popup_temperature_label or not self.gpt_popup_temperature_label.winfo_exists(): return
        temperature = round(float(value), 2)
        self.gpt_popup_temperature_label.config(text=str(temperature))

    def _gpt_popup_maxtoken_slider_change(self, value):
        if not self.gpt_popup_maxtoken_label or not self.gpt_popup_maxtoken_label.winfo_exists(): return
        maxtokens = int(float(value))
        self.gpt_popup_maxtoken_label.config(text=str(maxtokens))

    def _gpt_popup_top_p_slider_change(self, value):
        if not self.gpt_popup_top_p_label or not self.gpt_popup_top_p_label.winfo_exists(): return
        top_p = round(float(value), 2)
        self.gpt_popup_top_p_label.config(text=str(top_p))

    def _gpt_popup_frequency_penalty_slider_change(self, value):
        if not self.gpt_popup_frequency_penalty_label or not self.gpt_popup_frequency_penalty_label.winfo_exists(): return
        frequency_penalty = round(float(value), 2)
        self.gpt_popup_frequency_penalty_label.config(text=str(frequency_penalty))

    def _gpt_popup_presence_penalty_slider_change(self, value):
        if not self.gpt_popup_presence_penalty_label or not self.gpt_popup_presence_penalty_label.winfo_exists(): return
        presence_penalty = round(float(value), 2)
        self.gpt_popup_presence_penalty_label.config(text=str(presence_penalty))

    def _save_gpt_profile(self, mode, selected_profile=None):
        # Get values from the popup entries and sliders
        name_prompt = self.gpt_popup_name_entry.get().strip()
        system_prompt = self.gpt_popup_system_entry.get("1.0", tk.END).strip()
        assistant_prompt = self.gpt_popup_assistant_entry.get("1.0", tk.END).strip()
        temperature = round(float(self.gpt_popup_temperature_slider.get()), 2)
        max_tokens = int(float(self.gpt_popup_maxtoken_slider.get()))
        top_p = round(float(self.gpt_popup_top_p_slider.get()), 2)
        frequency_penalty = round(float(self.gpt_popup_frequency_penalty_slider.get()), 2)
        presence_penalty = round(float(self.gpt_popup_presence_penalty_slider.get()), 2)

        # Save the profile to the controller
        if mode == "create":
            self.controller.gpt_profiles.append({
                "name": name_prompt,
                "system_prompt": system_prompt,
                "assistant_prompt": assistant_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
            })
        elif mode == "edit":
            self.controller.gpt_profiles[selected_profile] = {
                "name": name_prompt,
                "system_prompt": system_prompt,
                "assistant_prompt": assistant_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
            }

        # Update menu GUI
        self._create_menu()

        # Close the popup
        self.gpt_popup.destroy()
        self.gpt_popup = None

        self.controller.push_settings()  # Save current settings to db

    # ------

    def _clear_tts(self):
        self.tts_text.delete("1.0", tk.END)

    def _save_tts(self):
        text = self.tts_text.get("1.0", tk.END).strip()
        if not text:
            return
        
        # Ask user for filename
        filename = simpledialog.askstring("Save TTS", "Enter filename:")
        if not filename:
            return
        if not filename.endswith(".wav"):
            filename += ".wav"

        filename = "TTS_" + filename  

        # Save TTS to file
        self.controller._tts.save_tts(text, filename)

        # Update music list
        self._refresh_music()

        for idx,(n,path) in enumerate(self.controller.music_entries):
            if re.sub(r"\s+", "", n)==re.sub(r"\s+", "", filename): 
                self.music_list.selection_clear(0, tk.END)
                self.music_list.selection_set(idx)        # Select the audio item in the GUI music list
                self.music_list.see(idx)                  # Scroll to it

    def _set_all_listen_modes(self, state):
        self.listen_mic.set(state)
        self.listen_music.set(state)
        self.listen_tts.set(state)
        self._on_listen_mode_change()

    def _on_listen_mode_change(self):
        self.controller.listen_enabled_mic = self.listen_mic.get()
        self.controller.listen_enabled_music = self.listen_music.get()
        self.controller.listen_enabled_tts = self.listen_tts.get()
        self.controller.push_settings()  # Save current settings to db

        # Restart mic thread to reset settings that only occur before the thread starts
        self.controller._playback.kill_mic()
        self.controller.mic_down()

    def play_youtube_url(self):
        url = self.youtube_url.get().strip()
        self.controller.play_youtube_url(url)


    def _on_music_volume_change(self, value):
        self.controller.music_volume = int(float(value))
        if self.music_volume_label and self.music_volume_label.winfo_exists():
            self.music_volume_label.config(text=str(self.controller.music_volume))
        self.controller.push_settings()  # Save current settings to db
    
    def _on_mic_volume_change(self, value):
        self.controller.mic_volume = int(float(value))
        if self.mic_volume_label and self.mic_volume_label.winfo_exists():
            self.mic_volume_label.config(text=str(self.controller.mic_volume))
        self.controller.push_settings()  # Save current settings to db
    
    def _on_tts_volume_change(self, value):
        self.controller._tts.tts_volume = int(float(value))    
        if self.tts_volume_label and self.tts_volume_label.winfo_exists():
            self.tts_volume_label.config(text=str(self.controller._tts.tts_volume))
        self.controller.push_settings()  # Save current settings to db

    # --------------   Main Loop   ------------

    def force_focus_hwnd(self, hwnd):
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys('%')  # Send ALT key to allow focus steal
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
        win32gui.SetForegroundWindow(hwnd)

    def reset_settings(self):
        # Confirm reset
        if not messagebox.askyesno("Reset Settings", "Are you sure you want to reset settings to default?"):
            return

        # Reset settings to default values and restart program
        self.controller.reset()

    def run(self):
        self.mainloop()