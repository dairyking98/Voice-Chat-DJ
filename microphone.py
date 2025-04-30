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


P = pyaudio.PyAudio()

output_device = None # Output device index
input_device = None # Input device index

music_volume = 100 # Music volume percentage
mic_volume = 100 # Mic volume percentage

time_last_volume_popup = 0

# ------------   DEVICE SELECTION FUNCTIONS   ------------

def list_audio_devices():
    devices = []
    for i in range(P.get_device_count()):
        device = P.get_device_info_by_index(i)
        devices.append(device)
    return devices

def select_output_device(devices):
    global output_device
    valid=[(i,info) for i,info in enumerate(devices) if info['maxOutputChannels']>0 and info['maxInputChannels']==0]
    print("\nSelect OUTPUT device:")
    for i,info in valid:
        print(f" {i}: {info['name']}  OutCh={info['maxOutputChannels']}")
    while True:
        try:
            c=int(input("OUTPUT # → "))
            if any(c==idx for idx,_ in valid):
                output_device=c
                print("→ Using", devices[c]['name'])
                return True
        except: pass
        print("Invalid output device.")
    return False

def select_input_device(devices):
    global input_device
    print("\nSelect INPUT device:")
    for i,info in enumerate(devices):
        if info['maxInputChannels']>0:
            print(f" {i}: {info['name']}  InCh={info['maxInputChannels']}")
    while True:
        try:
            c=int(input("INPUT # → "))
            if 0<=c<len(devices) and devices[c]['maxInputChannels']>0:
                input_device=c
                print("→ Using", devices[c]['name'])
                return True
        except: pass
        print("Invalid.")
    return False


# ------------   UI FUNCTIONS   ------------


def show_popup(text, duration=1000):
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

# ------------   EVENT LISTENERS   ------------

# Handle music and microphone volume changes with mouse scroll + ctrl/alt key
def on_scroll(event):
    # Ignore non-scroll events
    if not hasattr(event, 'delta'):
        return

    # Limit event handler rate to interval of 50ms
    global time_last_volume_popup
    limit = 50 # Interval in ms
    time = getTime()
    if time - time_last_volume_popup < 50:
        return
    time_last_volume_popup = time

    global music_volume, mic_volume
    dy = event.delta
    if keyboard.is_pressed('ctrl'):
        music_volume = max(0, min(300, music_volume + (5 if dy > 0 else -5)))
        show_popup(f"Music: {music_volume}%")
    elif keyboard.is_pressed('alt'):
        mic_volume = max(0, min(100, mic_volume + (5 if dy > 0 else -5)))
        show_popup(f"Mic: {mic_volume}%")

# --------------   HELPER FUNCTIONS   ------------

def getTime():
    return int(time.time()*1000)

# ------------   MAIN   ------------

def main():
    # -------- INITIALIZE AUDIO DEVICES ------

    # List audio devices and allow user to select one
    global output_device
    devices = list_audio_devices()
    for i, device in enumerate(devices):
        # Found valid output device
        if device['name'] == 'CABLE Input (VB-Audio Virtual Cable)' and device['maxOutputChannels'] == 2:
            output_device = i
            break
    else:
        # Virtual cable not found
        print("Virtual cable not found. Please select an output device.") 

        found_valid_output_device = select_output_device(devices)
        if not found_valid_output_device:
            print("No valid output device selected. Exiting.")
            return

    # If no input device is found, user will be able to stream audio and TTS only
    found_valid_input_device = select_input_device(devices)

    # --------- INITIALIZE EVENT LISTENERS -------
    
    mouse.hook(on_scroll) # Mouse event listener

    # --------- CLEANUP -------

    P.terminate() # Terminate pyaudio instance before exiting
    input("Exiting...") # Pause before exiting program


if __name__ == "__main__":
    main()