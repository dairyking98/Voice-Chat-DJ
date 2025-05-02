# playback.py
import threading
import subprocess
import wave
import time
import array

from config import FORMAT, MUSIC_CHUNK, DEBUG, MIC_CHANNELS, MIC_RATE, MIC_CHUNK

from .utils import convert_channels, adjust_volume

class Playback():

    def __init__(self):
        super().__init__()
        self._current_proc     = None
        self._playback_thread  = None
        self._pause_flag       = threading.Event()
        self._stop_flag        = threading.Event()
        self.stop_mic_flag     = threading.Event()
        self.mic_thread        = None

    def _playback(self, path, pyaudio_instance, sel_out_dev, sel_listen_dev, listen_enabled, listen_volume, music_volume):
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

            chunk = convert_channels(data, 1, 1)
            stream.write(adjust_volume(chunk, music_volume))
            if listen_stream:
                listen_stream.write(adjust_volume(chunk, listen_volume))
            data = reader(MUSIC_CHUNK)

        # cleanup
        stream.stop_stream()
        stream.close()
        if listen_stream:
            listen_stream.stop_stream()
            listen_stream.close()
        cleanup()
        self._current_proc = None

    def play_music(self, path, pyaudio_instance, output_device, listen_device, listen_enabled, listen_volume, music_volume):
        self.stop_music()
        self._playback_thread = threading.Thread(
            target=self._playback,
            args=(
                path, pyaudio_instance, output_device,
                listen_device, listen_enabled,
                listen_volume, music_volume
            ),
            daemon=True
        )
        self._playback_thread.start()

    ### MIC PASSTHROUGH ###
    def switch_to_mic(self, p, sel_in_dev, sel_out_dev, sel_listen_dev, listen_mic_enabled, mic_volume):
        if self.mic_thread and self.mic_thread.is_alive(): return
        def _mic_loop():
            self.stop_mic_flag.clear()
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

            while not self.stop_mic_flag.is_set():
                data=in_s.read(MIC_CHUNK,exception_on_overflow=False)
                data=convert_channels(data,MIC_CHANNELS,out_ch)
                data=adjust_volume(data,mic_volume)
                out_s1.write(data)
                if out_s2: out_s2.write(data)

            in_s.stop_stream();in_s.close()
            out_s1.stop_stream();out_s1.close()
            if out_s2: out_s2.stop_stream();out_s2.close()

        self.mic_thread=threading.Thread(target=_mic_loop,daemon=True)
        self.mic_thread.start()

    def stop_mic(self):
        if self.mic_thread and self.mic_thread.is_alive():
            self.stop_mic_flag.set()
            self.mic_thread.join(timeout=1)


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
