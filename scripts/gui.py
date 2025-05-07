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
        self.tts_popup_rate_slider = None # TTS rate slider
        self.tts_popup_rate_label = None # TTS rate label

        # TTS Popup state
        self._tts_popup_rate = 160 # TTS rate

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
        self._create_volume_frame()
        self._create_play_pause_controls_frame()
        self._create_media_selection_frame()

        self.sync_binds()

    # --------------   Toolbar   ------------

    def _create_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Reset Settings", command=self.reset_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        self.bind_menu = tk.Menu(menubar, tearoff=False)
        # Binds 0 -> 9
        for i in range(10):
            self.bind_menu.add_command(label=f"{i} - None", command=lambda i=i: self.set_bind(i))
        menubar.add_cascade(label="Binds", menu=self.bind_menu)
        self.config(menu=menubar)

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

        # Select the current input device in the combobox
        for idx, val in enumerate(self.input_devs):
            if val.startswith(f"{self.controller.input_device}:"):
                self.input_device_cb.current(idx)  # Set combobox selection
                break

        # ------ SPEAK (LISTEN) OUT ------
        p = self.controller.p
        devs = [(i, p.get_device_info_by_index(i)) for i in range(p.get_device_count())
                if p.get_device_info_by_index(i)['maxOutputChannels'] > 0]

        # Format list of devices as "index: name"
        self.output_devs = [f"{i}: {d['name']}" for i, d in devs]

        ttk.Label(top, text="Speaker Out (Listen):").pack(side=tk.LEFT)
        self.output_device_cb = ttk.Combobox(top, values=self.output_devs, state="readonly", width=40)
        self.output_device_cb.pack(side=tk.LEFT, padx=5)
        self.output_device_cb.bind('<<ComboboxSelected>>', self._on_output_device_change)

        # Select the current listen device in the combobox
        for idx, val in enumerate(self.output_devs):
            if val.startswith(f"{self.controller.listen_device}:"):
                self.output_device_cb.current(idx)  # Set combobox selection
                break


        # ----- LISTEN MODES -----

        self.listen_mic = tk.BooleanVar(value=self.controller.listen_enabled_mic)
        self.listen_music = tk.BooleanVar(value=self.controller.listen_enabled_music)
        self.listen_tts = tk.BooleanVar(value=self.controller.listen_enabled_tts)

        ttk.Button(top, text="None", command=lambda: self._set_all_listen_modes(False)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top, text="All", command=lambda: self._set_all_listen_modes(True)).pack(side=tk.RIGHT, padx=2)

        ttk.Checkbutton(top, text="TTS", variable=self.listen_tts, command=self._on_listen_mode_change).pack(side=tk.RIGHT, padx=2)
        ttk.Checkbutton(top, text="Music", variable=self.listen_music, command=self._on_listen_mode_change).pack(side=tk.RIGHT, padx=2)
        ttk.Checkbutton(top, text="Mic", variable=self.listen_mic, command=self._on_listen_mode_change).pack(side=tk.RIGHT, padx=2)

        ttk.Label(top, text="Listen Mode: ").pack(side=tk.RIGHT, padx=5)

    def _create_volume_frame(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        # create a volume slider for each volume type (music_volume, mic_volume, tts_volume)
        ttk.Label(top, text="Music Volume:").pack(side=tk.LEFT)
        self.music_volume_slider = ttk.Scale(top, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_music_volume_change)
        self.music_volume_slider.pack(side=tk.LEFT, padx=5)
        self.music_volume_slider.set(self.controller.music_volume)

        ttk.Label(top, text="Mic Volume:").pack(side=tk.LEFT)
        self.mic_volume_slider = ttk.Scale(top, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_mic_volume_change)
        self.mic_volume_slider.pack(side=tk.LEFT, padx=5)
        self.mic_volume_slider.set(self.controller.mic_volume)

        ttk.Label(top, text="TTS Volume:").pack(side=tk.LEFT)
        self.tts_volume_slider = ttk.Scale(top, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_tts_volume_change)
        self.tts_volume_slider.pack(side=tk.LEFT, padx=5)
        self.tts_volume_slider.set(self.controller._tts.tts_volume)

        ttk.Label(top, text="Mic Mode:").pack(side=tk.LEFT)
        self.mic_mode = tk.StringVar(value="Push to Talk")
        self.mic_mode_cb = ttk.Combobox(top, values=["Off", "On", "Push to Talk"], state="readonly", width=20)
        self.mic_mode_cb.current(2)
        self.mic_mode_cb.pack(side=tk.LEFT, padx=5)
        self.mic_mode_cb.bind('<<ComboboxSelected>>', lambda e: self.controller.set_mic_mode(self.mic_mode_cb.get()))

        # Select current mic mode in the combobox
        for idx, val in enumerate(["Off", "On", "Push to Talk"]):
            if val == self.controller.mic_mode:
                self.mic_mode_cb.current(idx)
                break

    
    def _create_media_selection_frame(self):
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        musicFrame = ttk.Labelframe(paned, text="Music Library", width=200)
        paned.add(musicFrame, weight=1)
        self.music_list = tk.Listbox(musicFrame)
        self.music_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(musicFrame, text="Refresh", command=self._refresh_music).pack(pady=5)
        self._refresh_music() # Load music list on startup
        self.music_list.bind('<Double-Button-1>', lambda e: self.play_selected_song(False))

        ttsFrame = ttk.Labelframe(paned, text="TTS", width=200)
        paned.add(ttsFrame, weight=1)
        # add textbox textarea
        self.tts_text = tk.Text(ttsFrame, height=5)
        self.tts_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(ttsFrame, text="Play TTS", command=self._play_tts).pack(side=tk.LEFT, padx=10)
        ttk.Button(ttsFrame, text="Clear TTS", command=self._clear_tts).pack(side=tk.LEFT, padx=10)
        ttk.Button(ttsFrame, text="Save TTS", command=self._save_tts).pack(side=tk.LEFT, padx=10)

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


    def open_popup(self):
        # If tts window is already open, bring it to the front and focus
        if self.tts_popup and self.tts_popup.winfo_exists():
            self._set_focus()
            return

        self.tts_popup = tk.Toplevel()
        self.tts_popup.title("TTS")
        self.tts_popup.geometry("300x150")

        label = ttk.Label(self.tts_popup, text="Enter something:")
        label.pack(pady=(10, 0))

        self.tts_popup_entry = ttk.Entry(self.tts_popup, width=40)
        self.tts_popup_entry.pack(pady=5)
        self.tts_popup_entry.bind("<Return>", lambda event: [self._play_tts_popup(), self._cancel_tts_popup()])

        button_frame = ttk.Frame(self.tts_popup)
        button_frame.pack(pady=10)

        ok_button = ttk.Button(button_frame, text="Play", command=self._play_tts_popup)
        ok_button.pack(side="left", padx=5)

        ok_ai_button = ttk.Button(button_frame, text="Query AI", command=self._play_ai_tts_popup)
        ok_ai_button.pack(side="left", padx=5)

        cancel_button = ttk.Button(button_frame, text="Cancel", command=self._cancel_tts_popup)
        cancel_button.pack(side="left", padx=5)

        rate_frame = ttk.Frame(self.tts_popup)
        rate_frame.pack(pady=10)

        self.tts_popup_rate_slider = ttk.Scale(rate_frame, from_=0, to=300, orient=tk.HORIZONTAL, command=self._tts_popup_rate_change, length=250)
        self.tts_popup_rate_slider.pack(side=tk.LEFT, padx=5)
        self.tts_popup_rate_slider.set(self._tts_popup_rate)

        # Add label showing the rate number
        self.tts_popup_rate_label = ttk.Label(rate_frame, text=str(self._tts_popup_rate))
        self.tts_popup_rate_label.pack(side=tk.LEFT, padx=5)

        self.tts_popup.lift()
        self.tts_popup.attributes("-topmost", True)
        
        # Use after_idle to delay focus setting
        self.tts_popup.after_idle(self._set_focus)

        self.tts_popup.grab_set()  # Make the popup modal
                
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

    # TODO implement generalized TTS input method 
    # def _play_tts_from_input(self,input)

    def _play_tts(self):
        text = self.tts_text.get("1.0", tk.END).strip()
        if not text:
            return
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts)

    # TTS POPUP -----
    
    def _play_tts_popup(self):
        text = self.tts_popup_entry.get().strip()
        if not text:
            return
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts, self._tts_popup_rate)

    def _play_ai_tts_popup(self):
        text = self.controller.ai(self.tts_popup_entry.get().strip())
        if not text:
            return
        self.controller._tts.play_tts(text, self.controller.p, self.controller.output_device, self.controller.listen_device, self.controller.listen_enabled_tts, self._tts_popup_rate)

    def _cancel_tts_popup(self):
        self.tts_popup.destroy()
        self.tts_popup = None  # Reset the popup reference

    def _set_focus(self):
        # Ensure the window is fully initialized before setting focus
        self.tts_popup.focus_force()
        self.tts_popup_entry.focus_set()

    def _tts_popup_rate_change(self, value):
        self._tts_popup_rate = int(float(value))
        if self.tts_popup_rate_label and self.tts_popup_rate_label.winfo_exists():
            # Update the label to show the current rate
            self.tts_popup_rate_label.config(text=str(self._tts_popup_rate))

    # -------

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

    def play_youtube_url(self):
        url = self.youtube_url.get().strip()
        self.controller.play_youtube_url(url)


    def _on_music_volume_change(self, value):
        self.controller.music_volume = int(float(value))
        self.controller.push_settings()  # Save current settings to db
    
    def _on_mic_volume_change(self, value):
        self.controller.mic_volume = int(float(value))
        self.controller.push_settings()  # Save current settings to db
    
    def _on_tts_volume_change(self, value):
        self.controller._tts.tts_volume = int(float(value))    
        self.controller.push_settings()  # Save current settings to db

    # --------------   Main Loop   ------------

    def reset_settings(self):
        # Confirm reset
        if not messagebox.askyesno("Reset Settings", "Are you sure you want to reset settings to default?"):
            return

        # Reset settings to default values and restart program
        self.controller.reset()

    def run(self):
        self.mainloop()