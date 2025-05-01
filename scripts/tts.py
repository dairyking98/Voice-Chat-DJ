# ttsself.engine.py

import os
import threading
import wave
import pyaudio
import pyttsx3
import tkinter as tk

from config import FORMAT, MUSIC_CHUNK
from .utils import convert_channels, adjust_volume, resample_wav

class TTS():
    def __init__(self):
        super().__init__()
        self.engine = pyttsx3.init()
        self.voicelist = self.engine.getProperty('voices')
        self.tts_voices  = {v.name.lower(): v.id for v in self.voicelist}
        self.tts_voice_id = self.engine.getProperty('voice')
        self.tts_voice_name = next((v.name for v in self.voicelist if v.id == self.tts_voice_id), '')
        self.tts_volume = int(self.engine.getProperty('volume') * 100)

    def play_tts(self, text, pyaudio_instance, sel_out_dev, sel_listen_dev, listen_enabled):
        """
        1) Save raw TTS to WAV
        2) Resample to stereo 48 kHz
        3) Stream into virtual-mic (+ speaker if enabled)
        """
        raw = os.path.join(os.getcwd(), 'tts_raw.wav')
        stereo = os.path.join(os.getcwd(), 'tts_stereo48k.wav')

        self.engine.save_to_file(text, raw)
        self.engine.runAndWait()
        resample_wav(raw, stereo, 48000)

        def _play():
            wf = wave.open(stereo, 'rb')
            in_ch, rate = wf.getnchannels(), wf.getframerate()
            reader = lambda n: wf.readframes(n)
            stream = pyaudio_instance.open(
                format=FORMAT,
                channels=in_ch,
                rate=rate,
                output=True,
                output_device_index=sel_out_dev,
                frames_per_buffer=MUSIC_CHUNK
            )
            spk = None
            if listen_enabled and sel_listen_dev is not None:
                spk = pyaudio_instance.open(
                    format=FORMAT,
                    channels=in_ch,
                    rate=rate,
                    output=True,
                    output_device_index=sel_listen_dev,
                    frames_per_buffer=MUSIC_CHUNK
                )
            data = reader(MUSIC_CHUNK)
            while data:
                chunk = adjust_volume(convert_channels(data, in_ch, in_ch), self.tts_volume)
                stream.write(chunk)
                if spk:
                    spk.write(chunk)
                data = reader(MUSIC_CHUNK)
            stream.stop_stream(); stream.close()
            if spk:
                spk.stop_stream(); spk.close()
            wf.close()

        threading.Thread(target=_play, daemon=True).start()

    def run(self):
        self.mainloop()
