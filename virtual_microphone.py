#!/usr/bin/env python3
#change added
import os
import wave
import random
import threading
import time
import subprocess
import array

import pyaudio
import yt_dlp as youtube_dl
import keyboard      # pip install keyboard
import mouse         # pip install mouse
import pyttsx3       # pip install pyttsx3
import tkinter as tk
from tkinter import font as tkfont

import ctypes

# Win32 constants
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL      = 0x11
VK_TAB          = 0x09
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_MENU = 0x12   # ALT key


# exhaustive list of ctrl/tab names
FLUSH_KEYS = (
    'ctrl','control',
    'left ctrl','right ctrl',
    'ctrl_l','ctrl_r',
    'lctrl','rctrl',
    'tab'
)


# ——— CONFIG ———
MIC_RATE      = 48000    # 48 kHz for mic passthrough
MIC_CHANNELS  = 1         # capture mic as mono
MIC_CHUNK     = 1024
MUSIC_CHUNK   = 1024
FORMAT        = pyaudio.paInt16
DEBUG         = True
# ——————————

p = pyaudio.PyAudio()

# ——— TTS engine/state ———
tts_engine      = pyttsx3.init()
_voicelist      = tts_engine.getProperty('voices')
tts_voices      = {v.name.lower(): v.id for v in _voicelist}
tts_voice_id    = tts_engine.getProperty('voice')
tts_voice_name  = next((v.name for v in _voicelist if v.id == tts_voice_id), '')
tts_volume      = int(tts_engine.getProperty('volume') * 100)  # 0–100

# ——— Global capture state ———
tts_capture_mode   = False
tts_capture_buffer = ""
tts_hook_id        = None

# ——— Listen-mic passthrough ———
listen_mic_enabled = False

# GUI STATE
# Prevent more than one popup at a time
music_popup_open = False
music_capture_mode   = False
music_capture_buffer = ""
music_hook_id        = None

# ——— Playback & mic state ———
music_entries       = []
playback_thread     = None
mic_thread          = None
current_ffmpeg_proc = None

stop_music_flag     = threading.Event()
pause_music_flag    = threading.Event()
stop_mic_flag       = threading.Event()

sel_out_dev    = None
sel_in_dev     = None
sel_listen_dev = None
listen_enabled = False
listen_mic_enabled = False
listen_volume  = 100

music_volume = 100
mic_volume   = 50
loop_enabled = False

type_mode           = 'toggle'
action_mode         = 'playpause'
original_play_state = False

script_dir  = os.path.dirname(os.path.abspath(__file__))
music_dir   = os.path.join(script_dir, 'music')
youtube_dir = os.path.join(script_dir, 'youtube')
binds_dir = os.path.join(script_dir, 'binds')

os.makedirs(music_dir,   exist_ok=True)
os.makedirs(youtube_dir, exist_ok=True)
os.makedirs(binds_dir, exist_ok=True)

binds_map = {}  

def debug(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")


 # helper to resample a wav file to a target rate
def resample_wav(src_path: str, dst_path: str, target_rate: int = 48000):
    """
    Convert any audio file at src_path into a 48 kHz, 16-bit PCM, STEREO WAV
    suitable for feeding into VB-Audio Cable → CS2 voice chat.
    """
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', src_path,
        '-ac', '2',                # FORCE 2 CHANNELS (stereo)
        '-ar', str(target_rate),   # SET SAMPLE RATE to 48 kHz
        '-sample_fmt', 's16',      # 16-bit signed PCM
        dst_path
    ], check=True)

def flush_ctrl_keys():
    # Release all keys in FLUSH_KEYS via keyboard library
    for k in FLUSH_KEYS:
        try:
            keyboard.release(k)
        except:
            pass

    # Simulate key-up for Ctrl and Tab via Win32 API
    for vk in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL, VK_TAB):
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)  # Small delay to ensure OS processes the event

def play_audio_file(path):
    """
    Play the given audio file (wav or mp3) by stopping any current playback
    and spawning a new playback thread.
    """
    global playback_thread
    # stop whatever’s playing now
    _stop_music_internal()
    # start a fresh thread that calls your existing _playback()
    playback_thread = threading.Thread(
        target=lambda: _playback(path),
        daemon=True
    )
    playback_thread.start()

def play_bind(path):
    """
    Play the given audio file into the mic-output device (sel_out_dev),
    and to the speaker (sel_listen_dev) if listen_enabled is True.
    """
    def _worker():
        # Open the file
        wf = wave.open(path, 'rb')
        in_ch, native_rate = wf.getnchannels(), wf.getframerate()

        # MIC (virtual cable) stream
        mic_info  = p.get_device_info_by_index(sel_out_dev)
        out_ch_m  = mic_info['maxOutputChannels']
        rate_m    = native_rate
        try:
            mic_stream = p.open(
                format=FORMAT, channels=out_ch_m, rate=rate_m,
                output=True, output_device_index=sel_out_dev,
                frames_per_buffer=MUSIC_CHUNK
            )
        except OSError:
            # fallback to 48kHz if needed
            mic_stream = p.open(
                format=FORMAT, channels=out_ch_m, rate=48000,
                output=True, output_device_index=sel_out_dev,
                frames_per_buffer=MUSIC_CHUNK
            )

        # SPEAKER stream (optional)
        listen_stream = None
        if listen_enabled and sel_listen_dev is not None:
            spk_info = p.get_device_info_by_index(sel_listen_dev)
            out_ch_s = spk_info['maxOutputChannels']
            rate_s   = native_rate
            try:
                listen_stream = p.open(
                    format=FORMAT, channels=out_ch_s, rate=rate_s,
                    output=True, output_device_index=sel_listen_dev,
                    frames_per_buffer=MUSIC_CHUNK
                )
            except OSError:
                listen_stream = p.open(
                    format=FORMAT, channels=out_ch_s, rate=48000,
                    output=True, output_device_index=sel_listen_dev,
                    frames_per_buffer=MUSIC_CHUNK
                )

        # Stream the audio
        data = wf.readframes(MUSIC_CHUNK)
        while data:
            # send to mic
            chunk_m = convert_channels(data, in_ch, out_ch_m)
            mic_stream.write(adjust_volume(chunk_m, mic_volume))
            # send to speaker if on
            if listen_stream:
                chunk_s = convert_channels(data, in_ch, out_ch_s)
                listen_stream.write(adjust_volume(chunk_s, listen_volume))
            data = wf.readframes(MUSIC_CHUNK)

        # Cleanup
        mic_stream.stop_stream()
        mic_stream.close()
        if listen_stream:
            listen_stream.stop_stream()
            listen_stream.close()
        wf.close()

    threading.Thread(target=_worker, daemon=True).start()

def play_bind_digit(digit):
    print(f"Hotkey CTRL+{digit} pressed")
    if digit in binds_map:
        name, path = binds_map[digit]
        print(f"Playing bind [{digit}] {name}")
        play_bind(path)
    else:
        print(f"No bind assigned to {digit}")


def load_binds():
    binds_map.clear()
    for f in os.listdir(binds_dir):
        if f[0].isdigit() and f[1]=='_' and f.lower().endswith(('.wav','.mp3')):
            binds_map[f[0]] = (f, os.path.join(binds_dir, f))

### CHANNEL/VOLUME HELPERS ###
def mono_to_stereo(data):
    out = bytearray()
    for i in range(0, len(data), 2):
        s = data[i:i+2]
        out += s + s
    return bytes(out)

def stereo_to_mono(data):
    mono = bytearray()
    for i in range(0, len(data), 4):
        l = int.from_bytes(data[i:i+2], 'little', signed=True)
        r = int.from_bytes(data[i+2:i+4], 'little', signed=True)
        avg = (l + r) // 2
        mono += int(avg).to_bytes(2, 'little', signed=True)
    return bytes(mono)

def convert_channels(data, in_ch, out_ch):
    if in_ch == out_ch:
        return data
    if in_ch == 1 and out_ch == 2:
        return mono_to_stereo(data)
    if in_ch == 2 and out_ch == 1:
        return stereo_to_mono(data)
    return data

def adjust_volume(data, vol_percent):
    if vol_percent == 100:
        return data
    factor = vol_percent / 100.0
    arr = array.array('h', data)
    for i in range(len(arr)):
        v = int(arr[i] * factor)
        arr[i] = max(-32768, min(32767, v))
    return arr.tobytes()


### POPUP FOR VOLUME CHANGES ###
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

CTRL_KEYS = {
    'ctrl','control',
    'left ctrl','right ctrl',
    'ctrl_l','ctrl_r','lctrl','rctrl'
}
### GLOBAL KEY CAPTURE FOR TTS TEXT ###
def on_key_capture(event):
    """
    • Hook installed with suppress=True, so by default nothing reaches Windows.
    • For any Ctrl up/down, we send a genuine Win32 keybd_event so Ctrl still flows.
    • All other keys are buffered (and never forwarded) until Enter.
    """
    global tts_capture_mode, tts_capture_buffer, tts_hook_id

    name  = event.name.lower()
    etype = event.event_type

    # 1) If this is a Ctrl key, emit it at the OS level
    if name in CTRL_KEYS:
        vk = VK_CONTROL
        if etype == 'down':
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        else:  # 'up'
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return  # don’t buffer or forward

    # 2) Only build buffer on key-down once in capture mode
    if etype != 'down' or not tts_capture_mode:
        return

    # 3) Enter/Return ends capture
    if name in ('enter', 'return'):
        tts_capture_mode = False
        keyboard.unhook(tts_hook_id)

        # ensure no modifiers remain stuck
        flush_ctrl_keys()

        txt = tts_capture_buffer.strip()
        if txt:
            print(f"TTS input: {txt}")
            play_tts(txt)
        return

    # 4) Otherwise accumulate into our buffer
    if name == 'backspace':
        tts_capture_buffer = tts_capture_buffer[:-1]
    elif name == 'space':
        tts_capture_buffer += ' '
    elif len(name) == 1:
        tts_capture_buffer += name


def show_tts_capture_popup():
    """
    Pops up a modal, grab‐based entry window that dynamically
    resizes to fit the text as you type.
    """
    global tts_capture_buffer, tts_capture_mode
    tts_capture_buffer = ""
    tts_capture_mode   = True

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

    def resize_window(text):
        # measure new text size
        width  = popup_font.measure(text) + pad_x * 2
        height = popup_font.metrics("linespace") + pad_y * 2
        sw = root.winfo_screenwidth()
        x  = (sw - width) // 2
        root.geometry(f"{width}x{height}+{x}+0")

    def on_key(event):
        global tts_capture_buffer, tts_capture_mode

        key = event.keysym

        # finish on Enter
        if key in ('Return', 'KP_Enter'):
            text = tts_capture_buffer.strip()
            root.grab_release()
            root.destroy()
            tts_capture_mode = False
            if text:
                play_tts(text)
            return

        # editing
        if key == 'BackSpace':
            tts_capture_buffer = tts_capture_buffer[:-1]
        elif key == 'space':
            tts_capture_buffer += ' '
        elif event.char and len(event.char) == 1:
            tts_capture_buffer += event.char

        display = "Type: " + tts_capture_buffer
        label.config(text=display)
        # force layout update, then resize
        root.update_idletasks()
        resize_window(display)

    # initial size
    resize_window("Type: ")

    root.bind("<Key>", on_key)
    root.mainloop()


### MOUSE WHEEL SHORTCUTS ###
def on_scroll(event):
    if not hasattr(event, 'delta'):
        return
    dy = event.delta
    global music_volume, mic_volume
    if keyboard.is_pressed('ctrl'):
        music_volume = max(0, min(300, music_volume + (1 if dy > 0 else -1)))
        show_popup(f"Music: {music_volume}%")
    elif keyboard.is_pressed('alt'):
        mic_volume = max(0, min(100, mic_volume + (1 if dy > 0 else -1)))
        show_popup(f"Mic: {mic_volume}%")


### PLAYBACK CONTROL ###
def _stop_music_internal():
    global current_ffmpeg_proc, playback_thread
    stop_music_flag.set()
    if current_ffmpeg_proc:
        try: current_ffmpeg_proc.kill()
        except: pass
        current_ffmpeg_proc.wait()
        current_ffmpeg_proc = None
    if playback_thread and playback_thread.is_alive():
        playback_thread.join(timeout=1)
    playback_thread = None

def stop_music():
    debug("stop_music()")
    _stop_music_internal()
    print("Music stopped.")

def pause_music():
    debug("pause_music()")
    pause_music_flag.set()
    print("Music paused.")

def resume_music():
    debug("resume_music()")
    pause_music_flag.clear()
    print("Music resumed.")

def is_music_playing():
    return playback_thread and playback_thread.is_alive() and not pause_music_flag.is_set()

def toggle_mute():
    global music_volume, pre_mute_volume
    if music_volume == 0:
        music_volume = pre_mute_volume
    else:
        pre_mute_volume = music_volume
        music_volume = 0
    debug(f"Toggled mute: music_volume={music_volume}")


### HOTKEYS & PTT ###
def hotkey_toggle():
    if type_mode != 'toggle':
        return
    if action_mode == 'playpause':
        if is_music_playing():
            pause_music()
        else:
            resume_music()
    else:
        toggle_mute()

def on_p_press(event):
    global original_play_state
    if type_mode == 'hold' and keyboard.is_pressed('ctrl'):
        original_play_state = is_music_playing()
        if action_mode == 'playpause':
            if original_play_state:
                pause_music()
            else:
                resume_music()
        else:
            toggle_mute()

def on_p_release(event):
    if type_mode == 'hold':
        if action_mode == 'playpause':
            if original_play_state:
                resume_music()
            else:
                pause_music()
        else:
            toggle_mute()

def setup_hotkeys():
    keyboard.add_hotkey('ctrl+p', hotkey_toggle)
    keyboard.on_press_key('p', on_p_press)
    keyboard.on_release_key('p', on_p_release)

def ptt_down():
    debug("PTT down → switch_to_mic()")
    switch_to_mic()

def ptt_up():
    debug("PTT up → stop_mic()")
    stop_mic()

def setup_ptt():
    mouse.on_button(ptt_down, buttons=['x'], types=['down'])
    mouse.on_button(ptt_up,   buttons=['x'], types=['up'])


### DEVICE SELECTION ###
def list_audio_devices():
    print("Audio devices:")
    devs=[]
    for i in range(p.get_device_count()):
        info=p.get_device_info_by_index(i)
        devs.append(info)
        print(f" {i}: {info['name']}  OutCh={info['maxOutputChannels']}  InCh={info['maxInputChannels']}")
    return devs

def select_output_device(devs):
    global sel_out_dev
    valid=[(i,info) for i,info in enumerate(devs) if info['maxOutputChannels']>0 and info['maxInputChannels']==0]
    print("\nSelect OUTPUT device:")
    for i,info in valid:
        print(f" {i}: {info['name']}  OutCh={info['maxOutputChannels']}")
    while True:
        try:
            c=int(input("OUTPUT # → "))
            if any(c==idx for idx,_ in valid):
                sel_out_dev=c
                print("→ Using", devs[c]['name'])
                return
        except: pass
        print("Invalid.")

def select_input_device(devs):
    global sel_in_dev
    print("\nSelect INPUT device:")
    for i,info in enumerate(devs):
        if info['maxInputChannels']>0:
            print(f" {i}: {info['name']}  InCh={info['maxInputChannels']}")
    while True:
        try:
            c=int(input("INPUT # → "))
            if 0<=c<len(devs) and devs[c]['maxInputChannels']>0:
                sel_in_dev=c
                print("→ Using", devs[c]['name'])
                return
        except: pass
        print("Invalid.")

def select_listen_device(devs):
    global sel_listen_dev
    valid=[(i,info) for i,info in enumerate(devs) if info['maxOutputChannels']>0 and info['maxInputChannels']==0]
    print("\nSelect LISTEN device:")
    for i,info in valid:
        print(f" {i}: {info['name']}")
    while True:
        try:
            c=int(input("LISTEN # → "))
            if any(c==idx for idx,_ in valid):
                sel_listen_dev=c
                print("→ Using", devs[c]['name'])
                return
        except: pass
        print("Invalid.")


### MUSIC LIBRARY ###
def list_music_files():
    global music_entries
    music_entries=[]
    for folder in (music_dir,youtube_dir):
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(('.wav','.mp3')):
                music_entries.append((name,os.path.join(folder,name)))
    print("\nMusic files:")
    if not music_entries: print("  (none)")
    else:
        for idx,(n,_) in enumerate(music_entries,1):
            print(f" {idx:2d}. {n}")


### PLAYBACK ###
def _playback(path):
    global current_ffmpeg_proc
    out_info=p.get_device_info_by_index(sel_out_dev)
    out_ch=out_info['maxOutputChannels']
    ext=os.path.splitext(path)[1].lower()

    if ext=='.wav':
        wf=wave.open(path,'rb')
        in_ch,native_rate=wf.getnchannels(),wf.getframerate()
        reader,cleanup=(lambda n: wf.readframes(n)),wf.close
    else:
        native_rate=int(out_info['defaultSampleRate'])
        cmd=[
            'ffmpeg','-hide_banner','-loglevel','error','-i',path,
            '-f','s16le','-acodec','pcm_s16le',
            '-ac',str(out_ch),'-ar',str(native_rate),'pipe:1'
        ]
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE)
        current_ffmpeg_proc=proc
        in_ch,reader=out_ch,lambda n: proc.stdout.read(n*out_ch*2)
        cleanup=lambda:(proc.stdout.close(),proc.wait())

    rate=native_rate
    try:
        stream=p.open(format=FORMAT,channels=out_ch,rate=rate,
                      output=True,output_device_index=sel_out_dev,
                      frames_per_buffer=MUSIC_CHUNK)
    except OSError:
        rate=48000
        stream=p.open(format=FORMAT,channels=out_ch,rate=rate,
                      output=True,output_device_index=sel_out_dev,
                      frames_per_buffer=MUSIC_CHUNK)

    listen_stream=None
    if listen_enabled and sel_listen_dev is not None:
        try:
            listen_stream=p.open(format=FORMAT,channels=out_ch,rate=rate,
                                 output=True,output_device_index=sel_listen_dev,
                                 frames_per_buffer=MUSIC_CHUNK)
        except: debug("listen open fail")

    stop_music_flag.clear(); pause_music_flag.clear()
    data=reader(MUSIC_CHUNK)
    while data and not stop_music_flag.is_set():
        if pause_music_flag.is_set():
            time.sleep(0.1); data=reader(MUSIC_CHUNK); continue
        chunk=convert_channels(data,in_ch,out_ch)
        stream.write(adjust_volume(chunk,music_volume))
        if listen_stream: listen_stream.write(adjust_volume(chunk,listen_volume))
        data=reader(MUSIC_CHUNK)

    stream.stop_stream();stream.close()
    if listen_stream: listen_stream.stop_stream();listen_stream.close()
    cleanup(); current_ffmpeg_proc=None

def play_music_from_file(idx):
    global playback_thread
    if idx<0 or idx>=len(music_entries):
        print("Invalid track."); return
    _,path=music_entries[idx]
    _stop_music_internal()
    playback_thread=threading.Thread(target=lambda:_playback(path),daemon=True)
    playback_thread.start()

def play_youtube_url(url):
    def _dl():
        _stop_music_internal()
        opts={'format':'bestaudio/best',
              'outtmpl':os.path.join(youtube_dir,'%(title)s.%(ext)s'),
              'quiet':True,
              'postprocessors':[{'key':'FFmpegExtractAudio',
                                 'preferredcodec':'wav',
                                 'preferredquality':'192'}]}
        with youtube_dl.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=True)
        name=info.get('title')+'.wav'
        list_music_files()
        for i,(n,_) in enumerate(music_entries):
            if n==name: play_music_from_file(i); return
        print("Downloaded not found.")
    threading.Thread(target=_dl,daemon=True).start()

def get_duration(path):
    try:
        if path.lower().endswith('.wav'):
            with wave.open(path,'rb') as wf:
                return wf.getnframes()/wf.getframerate()
        out=subprocess.check_output([
            'ffprobe','-v','error','-show_entries','format=duration',
            '-of','default=noprint_wrappers=1:nokey=1',path],
            stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except:
        return None


### MIC PASSTHROUGH ###
def switch_to_mic():
    global mic_thread
    if mic_thread and mic_thread.is_alive(): return
    def _mic_loop():
        stop_mic_flag.clear()
        out_ch=p.get_device_info_by_index(sel_out_dev)['maxOutputChannels']
        in_s=p.open(format=FORMAT,channels=MIC_CHANNELS,rate=MIC_RATE,
                    input=True,input_device_index=sel_in_dev,
                    frames_per_buffer=MIC_CHUNK)
        out_s1=p.open(format=FORMAT,channels=out_ch,rate=MIC_RATE,
                      output=True,output_device_index=sel_out_dev,
                      frames_per_buffer=MIC_CHUNK)
        out_s2=None
        if listen_mic_enabled and sel_listen_dev is not None:
            try:
                out_s2=p.open(format=FORMAT,channels=out_ch,rate=MIC_RATE,
                              output=True,output_device_index=sel_listen_dev,
                              frames_per_buffer=MIC_CHUNK)
            except: debug("mic-listen fail")

        while not stop_mic_flag.is_set():
            data=in_s.read(MIC_CHUNK,exception_on_overflow=False)
            data=convert_channels(data,MIC_CHANNELS,out_ch)
            data=adjust_volume(data,mic_volume)
            out_s1.write(data)
            if out_s2: out_s2.write(data)

        in_s.stop_stream();in_s.close()
        out_s1.stop_stream();out_s1.close()
        if out_s2: out_s2.stop_stream();out_s2.close()

    mic_thread=threading.Thread(target=_mic_loop,daemon=True)
    mic_thread.start()

def stop_mic():
    if mic_thread and mic_thread.is_alive():
        stop_mic_flag.set()
        mic_thread.join(timeout=1)


### TTS PLAYBACK INTO LISTEN ###
# ——— TTS PLAYBACK INTO VIRTUAL-MIC + (OPTIONAL) SPEAKER ———
def _play_tts_file(path):
    wf = wave.open(path, 'rb')
    in_ch, orig_rate = wf.getnchannels(), wf.getframerate()

    # 1) open the virtual‐mic stream, with fallback on 48000 Hz
    try:
        mic_stream = p.open(
            format=FORMAT,
            channels=in_ch,
            rate=orig_rate,
            output=True,
            output_device_index=sel_out_dev,
            frames_per_buffer=MUSIC_CHUNK
        )
    except OSError:
        debug(f"TTS mic open rate {orig_rate}Hz unsupported; retrying at 48000Hz")
        mic_stream = p.open(
            format=FORMAT,
            channels=in_ch,
            rate=48000,
            output=True,
            output_device_index=sel_out_dev,
            frames_per_buffer=MUSIC_CHUNK
        )

    # 2) open listen stream if enabled, with same fallback
    listen_stream = None
    if listen_enabled and sel_listen_dev is not None:
        try:
            listen_stream = p.open(
                format=FORMAT,
                channels=in_ch,
                rate=orig_rate,
                output=True,
                output_device_index=sel_listen_dev,
                frames_per_buffer=MUSIC_CHUNK
            )
        except OSError:
            debug(f"TTS listen open rate {orig_rate}Hz unsupported; retrying at 48000Hz")
            listen_stream = p.open(
                format=FORMAT,
                channels=in_ch,
                rate=48000,
                output=True,
                output_device_index=sel_listen_dev,
                frames_per_buffer=MUSIC_CHUNK
            )

    # 3) stream the audio
    data = wf.readframes(MUSIC_CHUNK)
    while data:
        chunk = adjust_volume(convert_channels(data, in_ch, in_ch), tts_volume)
        mic_stream.write(chunk)
        if listen_stream:
            listen_stream.write(chunk)
        data = wf.readframes(MUSIC_CHUNK)

    # 4) cleanup
    mic_stream.stop_stream()
    mic_stream.close()
    if listen_stream:
        listen_stream.stop_stream()
        listen_stream.close()
    wf.close()

def play_tts(text):
    # 1) Raw TTS
    raw = os.path.join(script_dir, 'tts_raw.wav')
    tts_engine.save_to_file(text, raw)
    tts_engine.runAndWait()

    # 2) Resample → stereo 48 kHz
    out = os.path.join(script_dir, 'tts_stereo48k.wav')
    resample_wav(raw, out, 48000)

    # 3) Play into virtual-mic & speaker
    threading.Thread(target=lambda: _play_tts_file(out), daemon=True).start()


def show_tts_capture_popup():
    global tts_capture_buffer, tts_capture_mode
    if tts_capture_mode:  # Prevent multiple popups
        return
    print("SHOW TTS CAPTURE POPUP")
    tts_capture_buffer = ""
    tts_capture_mode = True

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)

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

    def resize_window(text):
        width = popup_font.measure(text) + pad_x * 2
        height = popup_font.metrics("linespace") + pad_y * 2
        sw = root.winfo_screenwidth()
        x = (sw - width) // 2
        root.geometry(f"{width}x{height}+{x}+0")

    def close_popup():
        global tts_capture_buffer, tts_capture_mode
        tts_capture_mode = False
        try:
            root.grab_release()
        except:
            pass
        root.destroy()
        flush_ctrl_keys()  # Ensure no stuck keys

    def on_key(event):
        global tts_capture_buffer, tts_capture_mode
        key = event.keysym

        if key in ('Return', 'KP_Enter'):
            text = tts_capture_buffer.strip()
            close_popup()
            if text:
                play_tts(text)
            return

        if key == 'Escape':  # Allow Esc to cancel
            close_popup()
            return

        if key == 'BackSpace':
            tts_capture_buffer = tts_capture_buffer[:-1]
        elif key == 'space':
            tts_capture_buffer += ' '
        elif event.char and len(event.char) == 1:
            tts_capture_buffer += event.char

        display = "Type: " + tts_capture_buffer
        label.config(text=display)
        root.update_idletasks()
        resize_window(display)

    def check_focus():
        # If the window loses focus (e.g., CS:GO minimized), close the popup
        if not root.winfo_exists() or not root.focus_get():
            close_popup()
        else:
            root.after(100, check_focus)  # Check every 100ms

    # Initial setup
    resize_window("Type: ")
    root.bind("<Key>", on_key)
    root.grab_set()
    root.focus_force()

    # Start focus monitoring
    root.after(100, check_focus)

    # Ensure cleanup on window close
    root.protocol("WM_DELETE_WINDOW", close_popup)
    root.mainloop()


    # threading.Thread(target=_popup, daemon=True).start()


### MENU & CLI ###
def show_menu():
    print(f"\nMusic={music_volume}%  Mic={mic_volume}%  Listen={listen_volume}%  "
          f"TTS={tts_volume}%  Voice={tts_voice_name}  Loop={'On' if loop_enabled else 'Off'}  "
          f"Listen={'On' if listen_enabled else 'Off'}  Listen-Mic={'On' if listen_mic_enabled else 'Off'}")
    print("""
Commands:
  DIR               – list library
  PLAY / PLAY <N> / PLAY <URL>
  PAUSE / RESUME / STOP
  MUSIC VOL <n>
  MIC VOL <n>
  LISTEN VOL <n>
  MIC ON / MIC OFF / MIC PTT
  LISTEN ON / LISTEN OFF
  LISTEN MIC ON / LISTEN MIC OFF
  LOOP ON / LOOP OFF
  MODE TOGGLE|HOLD / MODE PLAYPAUSE|MUTE
  TTS <text> / TTS VOL <n>
  VOICE LIST / VOICE <index or name>
  CTRL+TAB          – start speech capture
  MENU / QUIT
""")

def interactive_mode():
    setup_hotkeys()
    setup_ptt()
    list_music_files()
    show_menu()
    global music_volume, mic_volume, loop_enabled
    global type_mode, action_mode
    global listen_enabled, listen_volume, listen_mic_enabled
    global tts_volume, tts_voice_id, tts_voice_name

    while True:
        cmd = input("> ").strip()
        debug(f"CMD: {cmd}")
        low = cmd.lower()

        if low == "dir":
            list_music_files()

        elif low == "play":
            play_music_from_file(random.randrange(len(music_entries)))

        elif low.startswith("play "):
            arg = cmd[5:].strip()
            if arg.startswith("http"):
                play_youtube_url(arg)
            else:
                try:
                    play_music_from_file(int(arg)-1)
                except:
                    print("Usage: PLAY <N> or PLAY <URL>")

        elif low in ("pause", "resume", "stop"):
            {"pause": pause_music, "resume": resume_music, "stop": stop_music}[low]()

        elif low.startswith("music vol "):
            try:
                v = int(low.split()[2]); assert 1 <= v <= 300
                music_volume = v; print(f"Music={v}%")
            except:
                print("Usage: MUSIC VOL <1–300>")

        elif low.startswith("mic vol "):
            try:
                v = int(low.split()[2]); assert 1 <= v <= 100
                mic_volume = v; print(f"Mic={v}%")
            except:
                print("Usage: MIC VOL <1–100>")

        elif low.startswith("listen vol "):
            try:
                v = int(low.split()[2]); assert 1 <= v <= 100
                listen_volume = v; print(f"Listen={v}%")
            except:
                print("Usage: LISTEN VOL <1–100>")

        elif low == "mic on":
            switch_to_mic()
        elif low == "mic off":
            stop_mic()
        elif low == "mic ptt":
            print("Hold Mouse4 to speak")

        elif low == "listen on":
            devs = list_audio_devices(); select_listen_device(devs)
            listen_enabled = True; print("Listen on")
        elif low == "listen off":
            listen_enabled = False; print("Listen off")

        elif low == "listen mic on":
            listen_mic_enabled = True
            print("Mic→speaker passthrough enabled")
            if mic_thread and mic_thread.is_alive():
                stop_mic(); switch_to_mic()
        elif low == "listen mic off":
            listen_mic_enabled = False
            print("Mic→speaker passthrough disabled")
            if mic_thread and mic_thread.is_alive():
                stop_mic(); switch_to_mic()

        elif low in ("loop on", "loop off"):
            loop_enabled = (low == "loop on")
            print(f"Loop {'enabled' if loop_enabled else 'disabled'}")

        elif low.startswith("mode "):
            m = low.split()[1]
            if m in ('toggle', 'hold'):
                type_mode = m; print(f"Hotkey mode={m}")
            elif m in ('playpause', 'mute'):
                action_mode = m; print(f"Hotkey action={m}")
            else:
                print("Usage: MODE TOGGLE|HOLD|PLAYPAUSE|MUTE")

        elif low.startswith("tts vol "):
            try:
                v = int(low.split()[2]); assert 1 <= v <= 300
                tts_volume = v
                tts_engine.setProperty('volume', min(1.0, tts_volume/100.0))
                print(f"TTS={v}%")
            except:
                print("Usage: TTS VOL <1–300>")

        elif low == "voice list":
            print("Voices:")
            for idx, voice in enumerate(_voicelist, start=1):
                print(f"  {idx}. {voice.name}")

        elif low.startswith("voice "):
            arg = cmd[6:].strip()
            if arg.isdigit():
                idx = int(arg) - 1
                if 0 <= idx < len(_voicelist):
                    voice = _voicelist[idx]
                    tts_engine.setProperty('voice', voice.id)
                    tts_voice_name = voice.name
                    print(f"Voice set to [{idx+1}] {tts_voice_name}")
                else:
                    print("Invalid index; try VOICE LIST")
            else:
                name = arg.lower()
                if name in tts_voices:
                    vid = tts_voices[name]
                    tts_engine.setProperty('voice', vid)
                    tts_voice_name = next(v.name for v in _voicelist if v.id == vid)
                    print(f"Voice={tts_voice_name}")
                else:
                    print("Unknown voice; try VOICE LIST")

        elif low.startswith("tts "):
            text = cmd[4:].strip()
            if text:
                print(f"TTS input: {text}")
                play_tts(text)
            else:
                print("Usage: TTS <text>")

        elif low == "menu":
            show_menu()

        elif low == "quit":
            stop_music(); stop_mic()
            break

        else:
            print("Unknown command.")


def on_tab_press(event):
    if keyboard.is_pressed('ctrl'):
        # Flush any stray Ctrl/Tab state
        flush_ctrl_keys()
        # Only show popup if not already in capture mode
        if not tts_capture_mode:
            show_tts_capture_popup()


def main():
    global sel_out_dev
    devs = list_audio_devices()
    for i, info in enumerate(devs):
        if info['name'] == 'CABLE Input (VB-Audio Virtual Cable)' and info['maxOutputChannels'] == 2:
            sel_out_dev = i
            print(f"Auto OUTPUT: {info['name']}")
            break
    else:
        select_output_device(devs)

    select_input_device(devs)

    mouse.hook(on_scroll)
    keyboard.on_press_key('tab', on_tab_press, suppress=False)
    keyboard.on_press_key('i', lambda e: show_music_list_popup() if keyboard.is_pressed('ctrl') else None, suppress=False)

    load_binds()
    for d in "1234567890":
        keyboard.add_hotkey(f"ctrl+{d}", lambda x=d: play_bind_digit(x), suppress=False)

    try:
        interactive_mode()
    finally:
        # Cleanup on exit
        stop_music()
        stop_mic()
        flush_ctrl_keys()
        try:
            tk.Tk().quit()  # Force Tkinter to clean up any lingering windows
        except:
            pass
        p.terminate()


if __name__ == "__main__":
    main()
