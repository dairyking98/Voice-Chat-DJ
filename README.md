# Voice Chat DJ
 A virtual microphone to stream anything (music) and your microphone

# Dependency Installation (Windows 10)
## FFMPEG
1. Download a Windows build from https://ffmpeg.org/download.html
2. Unzip it somewhere (e.g. C:\ffmpeg\)
3. Add its bin\ folder to your PATH in System → Advanced → Environment Variables.

## VB Cable (virtual audio cable)
1. Download “VB-Cable” from https://vb-audio.com/Cable/
2. Run the installer
3. Reboot if prompted.

You’ll then see “CABLE Input (VB-Audio Virtual Cable)” in your audio devices list.

## Python Dependencies
From inside your (activated) venv:

`pip install yt-dlp keyboard mouse pyaudio`

# Run Sctipt
1. Run your script: `python virtual_microphone.py`
2. Enter input microphone device number

# Program Usage
