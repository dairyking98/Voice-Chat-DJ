# VoiceDJ for CS

A real-time voice processing and audio playback tool designed for use alongside games like Counter-Strike. Routes your microphone through a virtual audio device with effects, plays music/sound clips via hotkeys, and includes a text-to-speech system.

---

## Features

### Microphone (Mic Effects chain)
- **Push-to-Talk** (Mouse4 side button), **Always On**, or **Off** modes
- PTT only gates the virtual microphone output — monitor voice is always-on regardless of mode
- **Pitch Shift** — semitone-based pitch shifting via SoundTouch
- **Reverb** — Schroeder reverb with decay and mix controls
- **Echo** — delay-based echo with feedback and mix controls
- **Robot Voice** — ring modulator effect
- **3-Band EQ** — low shelf, mid peak, high shelf
- **Noise Gate** — threshold-based gate to cut background noise

### Music & Clips (Music Effects chain)
- **Playlist** — load a folder of audio files (MP3, WAV, FLAC, OGG, M4A, OPUS, WEBM)
- **Hotkey binds** — bind Ctrl+0 through Ctrl+9 to any track for instant playback
- **Stackable Audio** — toggle between single-clip mode (new clip replaces current) and stackable mode (all clips play simultaneously)
- **Effects on Hotkey Sounds** — route hotkey clips through the Music Effects chain
- **Effects on Music** — route playlist music through the Music Effects chain
- **Music Effects chain** — independent Pitch Shift, Speed, Reverb, Echo, Robot Voice, 3-Band EQ

### Text-to-Speech
- Uses Windows built-in `System.Speech.Synthesis` (no internet required)
- Press **Ctrl+Tab** from any application to open the TTS popup
- Three actions: **Speak** (play through virtual mic), **Save to Library** (save as WAV), **Play & Save** (both)
- Saved files are named after the typed text (sanitized)

### Monitor
- **Monitor Voice** — hear your own mic (with effects applied) in your headphones, always-on
- **Monitor Music** — hear music/clips output in your headphones (effected version)
- Both monitors have independent device selectors

### YouTube / URL Download
- Paste a YouTube URL to download audio directly into the music library
- Requires `yt-dlp.exe` and `ffmpeg.exe` in the same folder as `VoiceDJ.exe`

### UI
- Resizable left/right panel splitter (drag the vertical divider)
- Resizable Mic Effects and Music Effects sub-panels (drag horizontal dividers)
- Real-time spectrum analyzer
- Notification overlay for hotkey/TTS feedback
- Settings auto-saved to `voicedj_settings.json` next to the executable

---

## Requirements

### Runtime
- Windows 10 or later (64-bit)
- A virtual audio cable driver, e.g. [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — set this as the output device in VoiceDJ and as the microphone input in your game

### Optional (for YouTube downloads)
- `yt-dlp.exe` — place in the same folder as `VoiceDJ.exe`
- `ffmpeg.exe` — place in the same folder as `VoiceDJ.exe` (required for MP3 conversion)

Both can be downloaded from:
- yt-dlp: https://github.com/yt-dlp/yt-dlp/releases
- ffmpeg: https://ffmpeg.org/download.html (get the Windows build, copy `ffmpeg.exe` from the `bin` folder)

---

## Setup

1. Install a virtual audio cable (e.g. VB-Audio Virtual Cable)
2. Place `VoiceDJ.exe` (and optionally `yt-dlp.exe` + `ffmpeg.exe`) in a folder
3. Run `VoiceDJ.exe`
4. Under **Input Device**, select your real microphone
5. Under **Output Device**, select the virtual cable (e.g. `CABLE Input`)
6. Under **Monitor Voice**, select your real headphones/speakers
7. Click **START AUDIO**
8. In your game, set the microphone to the virtual cable output (e.g. `CABLE Output`)

---

## Building from Source

### Prerequisites
- CMake 3.16+
- MinGW-w64 cross-compiler (on Linux) or MSVC (on Windows)
- The following libraries are bundled as single-header or fetched by CMake:
  - [miniaudio](https://miniaud.io/) (bundled, single-header)
  - [dr_libs](https://github.com/mackron/dr_libs) (bundled, single-header: dr_wav.h, dr_mp3.h)
  - [SoundTouch](https://www.surina.net/soundtouch/) (fetched by CMake)
  - [Dear ImGui](https://github.com/ocornut/imgui) (fetched by CMake)
  - [DirectX 11](https://learn.microsoft.com/en-us/windows/win32/direct3d11/atoc-dx-graphics-direct3d-11) (Windows SDK)

### Build on Linux (cross-compile for Windows)

```bash
sudo apt-get install -y mingw-w64 cmake
cd vcdj
mkdir build && cd build
cmake .. -DCMAKE_TOOLCHAIN_FILE=../toolchain-mingw64.cmake -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

The output is `build/VoiceDJ.exe` — a fully static Windows executable (no DLLs required).

### Build on Windows (MSVC)

```bat
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

---

## File Structure

```
vcdj/
├── src/
│   ├── main.cpp          # All application code (single-file)
│   └── resources.rc      # Windows resource file (icon embedding)
├── CMakeLists.txt        # Build configuration
├── toolchain-mingw64.cmake  # Linux cross-compile toolchain
├── icon_new.png          # Application icon source (PNG)
├── make_ico.py           # Script to convert PNG → multi-resolution ICO
└── README.md             # This file
```

---

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Tab` | Open / close TTS popup |
| `Ctrl+0` – `Ctrl+9` | Play bound audio clip |
| `Mouse4` (side button) | Push-to-talk (in PTT mode) |

---

## Settings File

Settings are saved automatically to `voicedj_settings.json` in the same directory as the executable. Delete this file to reset all settings to defaults.

---

## Version History

| Version | Notes |
|---------|-------|
| 2.12.0 | Fixed SoundTouch interlacing artifact; speed range 50–150% |
| 2.11.0 | Fixed Ctrl+Tab foreground; echo drain; SoundTouch flush on load |
| 2.10.0 | Fixed hotkey effects routing; TTS text cleared on open |
| 2.9.0 | Resizable panels; music speed slider; stackable audio; monitor voice effects |
| 2.8.0 | Music Effects chain; Mic/Music split; Ctrl+Tab toggle |
| 2.7.0 | Monitor routing fix; echo tail drain; TTS filename from text |
| 2.6.0 | Initial public build: TTS, pitch shift, reverb, echo, EQ, hotkeys |

---

## License

Source code provided for personal use. Third-party libraries retain their own licenses (MIT/LGPL — see each library's repository).
