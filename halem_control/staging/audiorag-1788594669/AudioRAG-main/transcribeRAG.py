# ----------------------------------------------------
#  whisper_local_example.py
# ----------------------------------------------------
# Requires:
#pip install torch
#pip install git+https://github.com/openai/whisper.git
#
#If you have a GPU you can speed this up with:
#     pip install torch --extra-index-url https://download.pytorch.org/whl/cu118
#
# ----------------------------------------------------
#  whisper_local_example.py - CORRECTED
# ----------------------------------------------------
import whisper
import torch
import pathlib
import requests
import tempfile
import ssl # <-- IMPORT SSL

# Where the audio lives
audio_path = "harvard.wav"

# --- FIX GOES HERE ---
# This part tells Python to ignore SSL certificate verification errors.
# It's needed for the model download on some networks.
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Python 2.7.9+ adds this, but might not be present in older versions
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
# --- END OF FIX ---


# Load the tiny model (≈ 450 MB on disk, 65 M params)
# This line will now succeed
print("Loading Whisper model...")
model = whisper.load_model("tiny")

# Run inference
print("\nTranscribing… (this may take a few seconds)")
result = model.transcribe(
    audio_path,
    language="en",          # set to "en" or "de" etc. if you know the language
    word_timestamps=True,   # Set to True to get word-level timestamps
)

# Show the text
print("\n=== Transcription ===")
print(result["text"])

# Show word-level timestamps
print("\n=== Word-level timestamps ===")
for segment in result.get("segments", []):
    for word in segment.get("words", []):
        # The structure is slightly different in the open-source version
        print(f"{word['start']:.2f}–{word['end']:.2f}\t{word['word']}")