# config.py

import os
import pyaudio

# ——— AUDIO SETTINGS ———
MIC_RATE      = 48000      # 48 kHz for mic passthrough
MIC_CHANNELS  = 1          # capture mic as mono
MIC_CHUNK     = 1024
MUSIC_CHUNK   = 1024
FORMAT        = pyaudio.paInt16

# ——— DEBUG ———
DEBUG = True

# ——— DEVICE IDENTIFIER ———
# We pick the recording side of the cable, which exposes 2 input channels.
VIRTUAL_CABLE_RECORD_NAME = 'VB-Audio Virtual Cable'

# ——— PATHS ———
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR    = os.path.join(SCRIPT_DIR, 'music')
YOUTUBE_DIR  = os.path.join(SCRIPT_DIR, 'youtube')
BINDS_DIR    = os.path.join(SCRIPT_DIR, 'binds')
DB_DIR = os.path.join(SCRIPT_DIR, 'db')
SETTINGS_DB_PATH = os.path.join(DB_DIR, 'settings.json')

# Ensure directories exist
os.makedirs(MUSIC_DIR,   exist_ok=True)
os.makedirs(YOUTUBE_DIR, exist_ok=True)
os.makedirs(BINDS_DIR,   exist_ok=True)

# Temporary test OpenAI API key
TEST_OPENAI_API_KEY = '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'
