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


# ------------   HELPER FUNCTIONS   ------------

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


# ------------   MAIN   ------------

def main():
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


    input("Everything looks good. Type anything to exit...")

    # Terminate pyaudio instance before exiting
    P.terminate()


if __name__ == "__main__":
    main()