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
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.engine = pyttsx3.init()
        self.voicelist = self.engine.getProperty('voices')
        self.tts_voices  = {v.name.lower(): v.id for v in self.voicelist}
        self.tts_voice_id = self.engine.getProperty('voice')
        self.tts_voice_name = next((v.name for v in self.voicelist if v.id == self.tts_voice_id), '')
        self.tts_volume = int(self.engine.getProperty('volume') * 100)

    def play_tts(self, text, pyaudio_instance, sel_out_dev, sel_listen_dev, listen_enabled, ttsRate=160, voiceMode="SAPI5", voice="sage"):
        """
        1) Save raw TTS to WAV
        2) Resample to stereo 48 kHz
        3) Stream into virtual-mic (+ speaker if enabled)
        """
        raw = os.path.join(os.getcwd(), 'tts_raw.wav')
        stereo = os.path.join(os.getcwd(), 'tts_stereo48k.wav')

        self.engine.setProperty('rate', ttsRate)
        self.engine.save_to_file(text, raw)
        self.engine.runAndWait()
        resample_wav(raw, stereo, 48000)

        def _play():
            if voiceMode == "OpenAI":
                response = self.controller.client.audio.speech.create(
                    model="tts-1",
                    voice=voice,
                    input=text,
                    response_format="wav",
                )
                audio_data = response.read()  # Read the full response content
                
                # Save to temporary file
                input_path = "input_audio.wav"
                output_path = "resampled_audio.wav"

                # Save audio data to input_path
                with open(input_path, "wb") as f:
                    f.write(audio_data)

                # Resample to 48 kHz
                resample_wav(input_path, output_path, target_rate=48000)

            wf = wave.open(output_path if voiceMode == "OpenAI" else stereo, 'rb')
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
                
                if self.controller.tts_transform_enabled:
                    # Audio transformations
                    if self.controller.pitch_transform_enabled:
                        # Pitch shift up by 2 semitones
                        data = self.controller._playback.transformAudio(data, "pitch", self.controller.pitch_transform_semitones, "music", rate)  
                    if self.controller.reverb_transform_enabled:
                        data = self.controller._playback.transformAudio(data, "reverb", None, "music", rate)
                    if self.controller.robot_transform_enabled:
                        data = self.controller._playback.transformAudio(data, "robot", None, "music", rate)

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

    def update_tts_voice(self):
        self.engine.setProperty('voice', self.tts_voice_id)

    def save_tts(self, text, filename):
        # Create wav
        self.engine.setProperty('rate', 160)
        self.engine.save_to_file(text, f"music/raw_{filename}")
        self.engine.runAndWait()
        resample_wav(f"music/raw_{filename}", f"music/{filename}", 48000)

        # Delete raw wav
        os.remove(f"music/raw_{filename}")

    def run(self):
        self.mainloop()
