import time

import threading
import subprocess
import wave
import time
import array

from config import FORMAT, MUSIC_CHUNK, DEBUG

def getTime():
    return int(time.time()*1000)


# Weird audio stuff that chatgpt wrote

def convert_channels(data: bytes, in_ch: int, out_ch: int) -> bytes:
    """Convert between mono↔stereo PCM."""
    if in_ch == out_ch:
        return data
    if in_ch == 1 and out_ch == 2:
        # duplicate each sample
        out = bytearray()
        for i in range(0, len(data), 2):
            sample = data[i:i+2]
            out += sample + sample
        return bytes(out)
    if in_ch == 2 and out_ch == 1:
        # average left/right
        mono = bytearray()
        for i in range(0, len(data), 4):
            l = int.from_bytes(data[i:i+2], 'little', signed=True)
            r = int.from_bytes(data[i+2:i+4], 'little', signed=True)
            avg = (l + r) // 2
            mono += int(avg).to_bytes(2, 'little', signed=True)
        return bytes(mono)
    # fallback
    return data

def adjust_volume(data: bytes, vol_percent: int) -> bytes:
    """Scale 16-bit PCM by vol_percent (0–100)."""
    if vol_percent == 100:
        return data
    factor = vol_percent / 100.0
    arr = array.array('h', data)
    for i in range(len(arr)):
        v = int(arr[i] * factor)
        arr[i] = max(-32768, min(32767, v))
    return arr.tobytes()

def resample_wav(src_path: str, dst_path: str, target_rate: int = 48000):
    """
    Use ffmpeg to convert any audio file into a 48 kHz, 16-bit PCM WAV.
    """
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', src_path,
        '-ac', '2',
        '-ar', str(target_rate),
        '-sample_fmt', 's16',
        dst_path
    ], check=True)
