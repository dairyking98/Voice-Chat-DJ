#!/usr/bin/env python3
"""
Generate a proper multi-resolution Windows ICO file from a PNG source.
Uses struct to write raw ICO format with all required sizes.
"""
import struct
import zlib
import io
from PIL import Image

src = "/home/ubuntu/vcdj/icon_new.png"
dst = "/home/ubuntu/vcdj/icon.ico"

img = Image.open(src).convert("RGBA")

sizes = [16, 24, 32, 48, 64, 128, 256]

# Build PNG-compressed image data for each size
images_data = []
for s in sizes:
    resized = img.resize((s, s), Image.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="PNG")
    images_data.append((s, buf.getvalue()))

# ICO header
num_images = len(images_data)
header_size = 6 + num_images * 16
data_offset = header_size

# Calculate offsets
offsets = []
offset = header_size
for s, data in images_data:
    offsets.append(offset)
    offset += len(data)

# Write ICO
with open(dst, "wb") as f:
    # ICONDIR header
    f.write(struct.pack("<HHH", 0, 1, num_images))  # reserved, type=1 (icon), count
    
    # ICONDIRENTRY for each image
    for i, (s, data) in enumerate(images_data):
        w = s if s < 256 else 0   # 0 means 256
        h = s if s < 256 else 0
        f.write(struct.pack("<BBBBHHII",
            w,          # width
            h,          # height
            0,          # color count (0 = more than 256)
            0,          # reserved
            1,          # planes
            32,         # bit count
            len(data),  # size of image data
            offsets[i]  # offset of image data
        ))
    
    # Image data
    for s, data in images_data:
        f.write(data)

import os
print(f"ICO saved to {dst}")
print(f"File size: {os.path.getsize(dst):,} bytes")
print(f"Sizes included: {[s for s, _ in images_data]}")

# Verify
img2 = Image.open(dst)
print(f"Verified: format={img2.format}, size={img2.size}")
