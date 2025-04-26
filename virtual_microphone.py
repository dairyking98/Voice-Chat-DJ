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
import keyboard      # pip install keyboard
import mouse         # pip install mouse

# ——— CONFIG ———
MIC_RATE      = 48000    # 48 kHz for mic passthrough
MIC_CHANNELS  = 1        # capture mic as mono
MIC_CHUNK     = 1024
MUSIC_CHUNK   = 1024
FORMAT        = pyaudio.paInt16
DEBUG         = True
# ——————————

p = pyaudio.PyAudio()

# State
music_entries       = []    # list of (display_name, full_path)
playback_thread     = None
mic_thread          = None
current_ffmpeg_proc = None

stop_music_flag     = threading.Event()
pause_music_flag    = threading.Event()
stop_mic_flag       = threading.Event()

sel_out_dev = None
sel_in_dev  = None

music_volume = 100
mic_volume   = 50        # default microphone volume
loop_enabled = False

# Hotkey modes
type_mode           = 'toggle'    # 'toggle' or 'hold'
action_mode         = 'playpause' # 'playpause' or 'mute'
original_play_state = False

script_dir  = os.path.dirname(os.path.abspath(__file__))
music_dir   = os.path.join(script_dir, 'music')
youtube_dir = os.path.join(script_dir, 'youtube')

# Create required directories if they do not exist
os.makedirs(music_dir,   exist_ok=True)
os.makedirs(youtube_dir, exist_ok=True)


def debug(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# —— channel conversions & volume —— #
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
        avg = (l + r)//2
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

# —— helper states —— #
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

# —— hotkey callbacks —— #
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

# —— mic PTT (push-to-talk) —— #
def ptt_down():
    debug("PTT down → switch_to_mic()")
    switch_to_mic()

def ptt_up():
    debug("PTT up → stop_mic()")
    stop_mic()

def setup_ptt():
    mouse.on_button(ptt_down, buttons=['x'], types=['down'])
    mouse.on_button(ptt_up,   buttons=['x'], types=['up'])

# —— device selection —— #
def list_audio_devices():
    print("Audio devices:")
    devs = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        devs.append(info)
        print(f" {i}: {info['name']}  OutCh={info['maxOutputChannels']}  InCh={info['maxInputChannels']}")
    return devs

def select_output_device(devs):
    global sel_out_dev
    print("\nSelect OUTPUT device (virtual mic):")
    while True:
        try:
            i = int(input("OUTPUT # → "))
            if 0 <= i < len(devs) and devs[i]['maxOutputChannels'] > 0:
                sel_out_dev = i
                print("→ Using output:", devs[i]['name'])
                return
        except:
            pass
        print("Invalid selection.")

def select_input_device(devs):
    global sel_in_dev
    print("\nSelect INPUT device (your mic):")
    for i, info in enumerate(devs):
        if info['maxInputChannels'] > 0:
            print(f" {i}: {info['name']}  InCh={info['maxInputChannels']}")
    while True:
        try:
            i = int(input("INPUT # → "))
            if 0 <= i < len(devs) and devs[i]['maxInputChannels'] > 0:
                sel_in_dev = i
                print("→ Using input:", devs[i]['name'])
                return
        except:
            pass
        print("Invalid selection.")

# —— music library —— #
def list_music_files():
    global music_entries
    music_entries = []
    for folder in (music_dir, youtube_dir):
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(('.wav', '.mp3')):
                music_entries.append((name, os.path.join(folder, name)))
    print("\nMusic files:")
    if not music_entries:
        print("  (no .wav/.mp3 files)")
    else:
        for i, (name, _) in enumerate(music_entries, 1):
            print(f" {i:2d}. {name}")

# —— playback control —— #
def _stop_music_internal():
    global current_ffmpeg_proc, playback_thread
    stop_music_flag.set()
    if current_ffmpeg_proc:
        try:
            current_ffmpeg_proc.kill()
        except:
            pass
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

def _playback(path):
    global current_ffmpeg_proc
    out_info = p.get_device_info_by_index(sel_out_dev)
    out_ch   = out_info['maxOutputChannels']
    ext      = os.path.splitext(path)[1].lower()

    if ext == '.wav':
        wf = wave.open(path, 'rb')
        in_ch   = wf.getnchannels()
        native_rate = wf.getframerate()
        reader  = lambda n: wf.readframes(n)
        cleanup = wf.close
    else:
        native_rate = int(out_info['defaultSampleRate'])
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', path,
            '-f', 's16le', '-acodec', 'pcm_s16le',
            '-ac', str(out_ch), '-ar', str(native_rate), 'pipe:1'
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        current_ffmpeg_proc = proc
        in_ch   = out_ch
        reader  = lambda n: proc.stdout.read(n * out_ch * 2)
        cleanup = lambda: (proc.stdout.close(), proc.wait())

    rate = native_rate
    try:
        stream = p.open(
            format=FORMAT,
            channels=out_ch,
            rate=rate,
            output=True,
            output_device_index=sel_out_dev,
            frames_per_buffer=MUSIC_CHUNK
        )
    except OSError:
        debug(f"Rate {rate} Hz unsupported; retrying at 48000 Hz")
        rate = 48000
        stream = p.open(
            format=FORMAT,
            channels=out_ch,
            rate=rate,
            output=True,
            output_device_index=sel_out_dev,
            frames_per_buffer=MUSIC_CHUNK
        )

    stop_music_flag.clear()
    pause_music_flag.clear()
    data = reader(MUSIC_CHUNK)
    while data and not stop_music_flag.is_set():
        if pause_music_flag.is_set():
            time.sleep(0.1)
            data = reader(MUSIC_CHUNK)
            continue
        chunk = convert_channels(data, in_ch, out_ch)
        chunk = adjust_volume(chunk, music_volume)
        stream.write(chunk)
        data = reader(MUSIC_CHUNK)

    stream.stop_stream()
    stream.close()
    cleanup()
    current_ffmpeg_proc = None

# —— utility functions —— #
def get_duration(path):
    try:
        if path.lower().endswith('.wav'):
            with wave.open(path,'rb') as wf:
                return wf.getnframes() / wf.getframerate()
        out = subprocess.check_output([
            'ffprobe','-v','error','-show_entries','format=duration',
            '-of','default=noprint_wrappers=1:nokey=1', path
        ], stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except:
        return None

def play_music_from_file(idx):
    global playback_thread
    if idx < 0 or idx >= len(music_entries):
        print("Invalid track.")
        return
    name, path = music_entries[idx]
    debug(f"Selected track {idx+1}: {name} ({path})")
    dur = get_duration(path)
    if dur is not None:
        debug(f"Track duration: {dur:.2f}s")
    _stop_music_internal()
    playback_thread = threading.Thread(target=lambda: _playback(path), daemon=True)
    playback_thread.start()
    debug("Playback thread started")

def play_youtube_url(url):
    debug(f"play_youtube_url: {url}")
    def _dl_play():
        _stop_music_internal()
        opts = {
            'format':'bestaudio/best',
            'outtmpl':os.path.join(youtube_dir,'%(title)s.%(ext)s'),
            'quiet':True,
            'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'wav','preferredquality':'192'}]
        }
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        name = info.get('title') + '.wav'
        list_music_files()
        for i, (n, _) in enumerate(music_entries):
            if n == name:
                play_music_from_file(i)
                return
        print("Downloaded not found.")
    threading.Thread(target=_dl_play, daemon=True).start()

# —— mic passthrough —— #
def switch_to_mic():
    global mic_thread
    if mic_thread and mic_thread.is_alive():
        return
    def _mic_loop():
        stop_mic_flag.clear()
        out_ch = p.get_device_info_by_index(sel_out_dev)['maxOutputChannels']
        in_s  = p.open(format=FORMAT, channels=MIC_CHANNELS, rate=MIC_RATE,
                       input=True, input_device_index=sel_in_dev, frames_per_buffer=MIC_CHUNK)
        out_s = p.open(format=FORMAT, channels=out_ch, rate=MIC_RATE,
                       output=True, output_device_index=sel_out_dev, frames_per_buffer=MIC_CHUNK)
        while not stop_mic_flag.is_set():
            data = in_s.read(MIC_CHUNK, exception_on_overflow=False)
            data = convert_channels(data, MIC_CHANNELS, out_ch)
            data = adjust_volume(data, mic_volume)
            out_s.write(data)
        in_s.stop_stream(); in_s.close()
        out_s.stop_stream(); out_s.close()
    mic_thread = threading.Thread(target=_mic_loop, daemon=True)
    mic_thread.start()

def stop_mic():
    if mic_thread and mic_thread.is_alive():
        stop_mic_flag.set()
        mic_thread.join(timeout=1)

# —— CLI helpers —— #
def show_menu():
    print(f"\nMusic vol={music_volume}%  Mic vol={mic_volume}%  Loop={'On' if loop_enabled else 'Off'}  Mode={type_mode}+{action_mode}")
    print("""
Commands:
  DIR             – list library
  PLAY            – play random
  PLAY <N>        – play entry N
  PLAY <URL>      – play YouTube URL
  PAUSE           – pause music
  RESUME          – resume music
  STOP            – stop music
  MUSIC VOL <n>   – set music vol
  MIC VOL <n>     – set mic vol (1–100)
  MIC ON          – mic passthrough on
  MIC OFF         – mic passthrough off
  MIC PTT         – hold Mouse4 for mic passthrough
  LOOP ON         – enable loop
  LOOP OFF        – disable loop
  MODE TOGGLE     – hotkey toggle mode
  MODE HOLD       – hotkey hold mode
  MODE PLAYPAUSE  – hotkey play/pause
  MODE MUTE       – hotkey mute
  MENU            – show this menu
  QUIT            – exit
""")

def interactive_mode():
    setup_hotkeys()
    setup_ptt()
    list_music_files()
    show_menu()
    global music_volume, mic_volume, loop_enabled, type_mode, action_mode

    while True:
        cmd = input("> ").strip()
        debug(f"User command: {cmd}")
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
        elif low == "pause":
            pause_music()
        elif low == "resume":
            resume_music()
        elif low == "stop":
            stop_music()
        elif low.startswith("music vol "):
            try:
                v = int(low.split()[2])
                if 1 <= v <= 100:
                    music_volume = v
                    print(f"Music vol={v}%")
                    debug(f"Set music_volume to {v}")
                else:
                    raise ValueError
            except:
                print("Usage: MUSIC VOL <1–100>")
        elif low.startswith("mic vol "):
            try:
                v = int(low.split()[2])
                if 1 <= v <= 100:
                    mic_volume = v
                    print(f"Mic vol={v}%")
                    debug(f"Set mic_volume to {v}")
                else:
                    raise ValueError
            except:
                print("Usage: MIC VOL <1–100>")
        elif low == "mic on":
            switch_to_mic()
        elif low == "mic off":
            stop_mic()
        elif low == "mic ptt":
            print("Hold Mouse4 to speak")
        elif low == "loop on":
            loop_enabled = True; print("Loop enabled"); debug("Loop enabled")
        elif low == "loop off":
            loop_enabled = False; print("Loop disabled"); debug("Loop disabled")
        elif low.startswith("mode "):
            m = low.split()[1]
            if m in ['toggle','hold']:
                type_mode = m; print(f"Hotkey mode: {m}"); debug(f"type_mode={m}")
            elif m in ['playpause','mute']:
                action_mode = m; print(f"Hotkey action: {m}"); debug(f"action_mode={m}")
            else:
                print("Usage: MODE TOGGLE|HOLD|PLAYPAUSE|MUTE")
        elif low == "menu":
            show_menu()
        elif low == "quit":
            stop_music()
            stop_mic()
            break
        else:
            print("Unknown command.")

# —— entry point —— #
def main():
    devs = list_audio_devices()
    # auto-select VB-Cable Input if present
    for i, info in enumerate(devs):
        if (info['name'] == 'CABLE Input (VB-Audio Virtual Cable)' and info['maxOutputChannels'] == 2):
            sel_out_dev = i
            print(f"Automatically selected OUTPUT: {info['name']}")
            break
    else:
        select_output_device(devs)
    select_input_device(devs)
    interactive_mode()
    p.terminate()

if __name__ == "__main__":
    main()