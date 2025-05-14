# playback.py
import threading
import subprocess
import wave
import time
import array
import pyaudio
import io
import os
import wave
import numpy as np
import librosa
import numpy as np
from scipy.signal import butter, lfilter, hilbert

from config import FORMAT, MUSIC_CHUNK, DEBUG, MIC_CHANNELS, MIC_RATE, MIC_CHUNK

from .utils import convert_channels, adjust_volume, resample_wav

class Playback():

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._current_proc     = None
        self._playback_thread  = None
        self._pause_flag       = threading.Event()
        self._stop_flag        = threading.Event()
        self._kill_flag        = threading.Event()
        self.stop_mic_flag     = threading.Event()
        self.mic_thread        = None

    def _playback(self, path, pyaudio_instance, sel_out_dev, sel_listen_dev, listen_enabled, music_volume):
        # device info
        out_info = pyaudio_instance.get_device_info_by_index(sel_out_dev)
        out_ch = out_info['maxOutputChannels']

        listen_info = pyaudio_instance.get_device_info_by_index(sel_listen_dev) if sel_listen_dev is not None else None
        listen_ch = listen_info['maxOutputChannels'] if listen_info else 0

        # set up reader/cleanup for wav vs other formats
        if path.lower().endswith('.wav'):
            wf = wave.open(path, 'rb')
            in_ch = wf.getnchannels()
            native_rate = wf.getframerate()
            reader = lambda n: wf.readframes(n)
            cleanup = wf.close
        else:
            # For non-WAV, use ffmpeg to convert to 48kHz for consistency
            native_rate = 48000  # Standard rate instead of device default
            cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', path,
                '-f', 's16le', '-acodec', 'pcm_s16le',
                '-ac', str(out_ch), '-ar', str(native_rate),
                'pipe:1'
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            self._current_proc = proc
            in_ch = out_ch
            reader = lambda n: proc.stdout.read(n * out_ch * 2)
            cleanup = lambda: (proc.stdout.close(), proc.wait())

        # Try opening stream with native rate, fall back to 48kHz if unsupported
        rate = native_rate
        stream = None
        try:
            stream = pyaudio_instance.open(
                format=FORMAT,
                channels=out_ch,
                rate=rate,
                output=True,
                output_device_index=sel_out_dev,
                frames_per_buffer=MUSIC_CHUNK
            )
        except OSError as e:
            if DEBUG: print(f"[playback] Native rate {rate}Hz unsupported; falling back to 48000Hz")
            rate = 48000
            stream = pyaudio_instance.open(
                format=FORMAT,
                channels=out_ch,
                rate=rate,
                output=True,
                output_device_index=sel_out_dev,
                frames_per_buffer=MUSIC_CHUNK
            )

        # Open listen stream (if enabled) with the same rate
        listen_stream = None
        if listen_enabled and sel_listen_dev is not None:
            try:
                listen_stream = pyaudio_instance.open(
                    format=FORMAT,
                    channels=listen_ch,
                    rate=rate,
                    output=True,
                    output_device_index=sel_listen_dev,
                    frames_per_buffer=MUSIC_CHUNK
                )
            except Exception as e:
                if DEBUG: print(f"[playback] Failed to open listen stream: {e}")

        self._stop_flag.clear()
        self._pause_flag.clear()

        # pump data
        data = reader(MUSIC_CHUNK)
        while data and not self._stop_flag.is_set():
            if self._pause_flag.is_set():
                time.sleep(0.1)
                data = reader(MUSIC_CHUNK)
                continue
            
            if self.controller.music_transform_enabled:
                # Audio transformations
                if self.controller.pitch_transform_enabled:
                    # Pitch shift up by 2 semitones
                    data = self.transformAudio(data, "pitch", self.controller.pitch_transform_semitones, "music", rate)  
                if self.controller.reverb_transform_enabled:
                    data = self.transformAudio(data, "reverb", None, "music", rate)
                if self.controller.robot_transform_enabled:
                    data = self.transformAudio(data, "robot", None, "music", rate)

            chunk = convert_channels(data, 1, 1)
            stream.write(adjust_volume(chunk, self.controller.music_volume))
            
            audio_np = np.frombuffer(chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(np.square(audio_np)))
            if rms and not np.isnan(rms):
                level = min(100, int((rms / 200) * 100))
                self.controller.app.vu_meter["value"] = level
            else:
                self.controller.app.vu_meter["value"] = 0

            if listen_stream:
                listen_stream.write(adjust_volume(chunk, self.controller.music_volume))
            data = reader(MUSIC_CHUNK)

        # cleanup
        stream.stop_stream()
        stream.close()
        if listen_stream:
            listen_stream.stop_stream()
            listen_stream.close()
        cleanup()
        self._current_proc = None

    def play_music(self, path, pyaudio_instance, output_device, listen_device, listen_enabled, music_volume, multithreaded=True):
        if not multithreaded:
            self.stop_music()
        self._playback_thread = threading.Thread(
            target=self._playback,
            args=(
                path, pyaudio_instance, output_device,
                listen_device, listen_enabled, music_volume
            ),
            daemon=True
        )
        self._playback_thread.start()

    # ------------- Audio Transformation Variables -------------

    # Robot
    CARRIER_FREQ = 100
    NUM_BANDS = 16
    BAND_EDGES = np.geomspace(80, 5000, NUM_BANDS + 1)

    # Reverb
    DELAY_MS = 100      # Delay time in milliseconds
    FEEDBACK = 0.4      # How much delayed signal is fed back
    MIX = 0.5           # 0 = dry, 1 = fully wet
    delay_samples = int(MIC_RATE * DELAY_MS / 1000)
    echo_buffer = np.zeros(delay_samples, dtype=np.float32)
    echo_pos = 0

    # ------------- Audio Transformation Helpers ------------- 
    def vocode(self, modulator, fs):
        t = np.arange(len(modulator)) / fs
        carrier = 2 * (t * self.CARRIER_FREQ % 1) - 1  # Saw wave
        output = np.zeros_like(modulator)

        for i in range(self.NUM_BANDS):
            low, high = self.BAND_EDGES[i], self.BAND_EDGES[i+1]

            mod_band = self.bandpass(modulator, low, high, fs)
            env = np.abs(hilbert(mod_band))
            env = np.clip(env * 2.0, 0, 1)  # Boost envelope

            car_band = self.bandpass(carrier, low, high, fs)
            output += env * car_band

        # Optional: blend in 10–20% dry voice to help intelligibility
        output = 0.9 * output + 0.1 * modulator

        return output
    
    def bandpass(self, data, lowcut, highcut, fs, order=3):
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return lfilter(b, a, data)

    # ------------- Audio Transformation -------------
    def transformAudio(self, data, transform_type, semitones=0, type='mic', rate=MIC_RATE):
        if transform_type == "pitch":
            try:
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                audio = librosa.util.fix_length(audio, size=MIC_CHUNK if type == 'mic' else MUSIC_CHUNK*2)
                pitched = librosa.effects.pitch_shift(audio, sr=rate, n_steps=semitones)
                pitched = np.clip(pitched * 32768.0, -32768, 32767).astype(np.int16)
                data = pitched.tobytes()
                return data
            except Exception as e:
                print(f"pitch shift audio transformation error: {e}")
                return data
        elif transform_type == "robot":
            try:
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                vocoded = self.vocode(audio, rate)
                vocoded = np.clip(vocoded * 32768.0, -32768, 32767).astype(np.int16)
                data = vocoded.tobytes()
                return data
            except Exception as e:
                print(f"robot audio transformation error: {e}")
                return data
        elif transform_type == "reverb":
            try:
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                out = np.zeros_like(audio)
                for i in range(len(audio)):
                    delayed = self.echo_buffer[self.echo_pos]
                    new_sample = audio[i] + delayed * self.FEEDBACK
                    self.echo_buffer[self.echo_pos] = new_sample
                    self.echo_pos = (self.echo_pos + 1) % self.delay_samples

                    out[i] = (1 - self.MIX) * audio[i] + self.MIX * delayed

                out = np.clip(out * 32768.0, -32768, 32767).astype(np.int16)
                data = out.tobytes()
                return data
            except Exception as e:
                print(f"reverb audio transformation error: {e}")
                return data
        else:
            print(f"invalid transform type: {transform_type}")
            return data

    ### MIC PASSTHROUGH ###
    def switch_to_mic(self, p, sel_in_dev, sel_out_dev, sel_listen_dev, listen_mic_enabled, mic_volume):
        self.stop_mic_flag.clear()
        self._kill_flag.clear()
        if self.mic_thread and self.mic_thread.is_alive(): return

        def _mic_loop():
            self.stop_mic_flag.clear()
            out_ch=p.get_device_info_by_index(self.controller.output_device)['maxOutputChannels']
            in_s=p.open(format=FORMAT,channels=MIC_CHANNELS,rate=MIC_RATE,
                        input=True,input_device_index=self.controller.input_device,
                        frames_per_buffer=MIC_CHUNK)
            out_s1=p.open(format=FORMAT,channels=out_ch,rate=MIC_RATE,
                        output=True,output_device_index=self.controller.output_device,
                        frames_per_buffer=MIC_CHUNK)
            out_s2=None
            if self.controller.listen_enabled_mic and self.controller.listen_device is not None:
                try:
                    out_s2=p.open(format=FORMAT,channels=out_ch,rate=MIC_RATE,
                                output=True,output_device_index=self.controller.listen_device,
                                frames_per_buffer=MIC_CHUNK)
                except:
                    print("mic-listen fail")

            while not self._kill_flag.is_set():
                data = in_s.read(MIC_CHUNK, exception_on_overflow=False)

                if self.controller.mic_transform_enabled:
                    # Audio transformations
                    if self.controller.pitch_transform_enabled:
                        # Pitch shift up by 2 semitones
                        data = self.transformAudio(data, "pitch", self.controller.pitch_transform_semitones, "mic", MIC_RATE)  
                    if self.controller.reverb_transform_enabled:
                        data = self.transformAudio(data, "reverb", None, "mic", MIC_RATE)
                    if self.controller.robot_transform_enabled:
                        data = self.transformAudio(data, "robot", None, "mic", MIC_RATE)

                data = convert_channels(data, MIC_CHANNELS, out_ch)
                data = adjust_volume(data, 0 if self.stop_mic_flag.is_set() else self.controller.mic_volume)
                out_s1.write(data)
                if out_s2:
                    out_s2.write(data)

            in_s.stop_stream();in_s.close()
            out_s1.stop_stream();out_s1.close()
            if out_s2: out_s2.stop_stream();out_s2.close()

        self.mic_thread=threading.Thread(target=_mic_loop,daemon=True)
        self.mic_thread.start()

    def stop_mic(self):
        if self.mic_thread and self.mic_thread.is_alive():
            self.stop_mic_flag.set()

    def kill_mic(self):
        if not self.mic_thread: return
        if not self.mic_thread.is_alive():
            self.mic_thread = None
            return
        self._kill_flag.set()
        self.mic_thread.join(timeout=1)
        self.mic_thread = None


    def pause_music(self):
        """Pause playback if it’s running."""
        self._pause_flag.set()


    def resume_music(self):
        """Resume playback if it’s paused."""
        self._pause_flag.clear()


    def stop_music(self):
        """Stop playback and kill any ffmpeg process."""
        self._stop_flag.set()
        if self._current_proc:
            try: self._current_proc.kill()
            except: pass
            self._current_proc = None
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1)
        self._playback_thread = None

    def run(self):
        self.mainloop()
