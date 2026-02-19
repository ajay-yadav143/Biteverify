# modules/ela.py
# ─────────────────────────────────────────────────────────
# ELA = Error Level Analysis
# 
# HOW IT WORKS:
# When you save a JPEG image, it gets compressed slightly.
# If someone edited part of an image (pasted insects, etc.)
# the edited area was saved at a DIFFERENT time than the rest.
# So when we re-compress the image and compare,
# edited areas show a DIFFERENT error level = they appear BRIGHTER.
#
# Think of it like: original photo = old paint on wall
#                   edited part = fresh new paint
#                   ELA = shining a UV light to see the new paint
# ─────────────────────────────────────────────────────────

import os                          # For file/folder operations
from PIL import Image              # For opening and editing images
from PIL import ImageChops         # For finding differences between images
from PIL import ImageEnhance       # For making differences more visible
import numpy as np                 # For math calculations on image data


def run_ela(image_path, quality=90):
    """
    This function takes an image and runs ELA on it.
    
    Parameters:
        image_path : the path/location of the image file
        quality    : JPEG compression quality (90 is standard)
    
    Returns:
        ela_image        : the visual ELA result (brighter = more edited)
        ela_score        : a number from 0-100 (higher = more suspicious)
    """

    # ── Step 1: Open the original uploaded image ──────────
    # .convert('RGB') makes sure image is in standard color format
    # (some images are RGBA or grayscale, this normalizes them)
    original = Image.open(image_path).convert('RGB')

    # ── Step 2: Save a compressed copy of the image ───────
    # We save it at quality=90 (slightly lower than original)
    # This simulates normal JPEG compression
    temp_path = "uploads/temp_ela_check.jpg"
    original.save(temp_path, 'JPEG', quality=quality)

    # ── Step 3: Open the compressed copy ──────────────────
    compressed = Image.open(temp_path)

    # ── Step 4: Find the DIFFERENCE between original and compressed ──
    # ImageChops.difference() compares pixel by pixel
    # Where pixels are the same → black (no difference)
    # Where pixels differ → bright color (high difference)
    ela_image = ImageChops.difference(original, compressed)

    # ── Step 5: Make differences more visible ─────────────
    # The differences are usually very small (hard to see)
    # We "stretch" the brightness so differences become visible
    extrema = ela_image.getextrema()   # Get min/max values per channel
    max_diff = max([e[1] for e in extrema])  # Find the biggest difference

    if max_diff == 0:
        scale = 1          # No difference found, no scaling needed
    else:
        scale = 255.0 / max_diff   # Scale so max difference = white (255)

    # Apply the brightness boost
    ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)

    # ── Step 6: Calculate ELA Score ───────────────────────
    # Convert image to a numpy array (grid of numbers)
    # Each pixel = a number 0-255 (0=black, 255=white)
    ela_array = np.array(ela_image)

    # Find the average brightness across all pixels
    # High average brightness = many edited areas = suspicious
    average_brightness = float(np.mean(ela_array))

    # Convert from 0-255 range to 0-100 range (easier to understand)
    ela_score = round((average_brightness / 255) * 100, 2)

    # ── Step 7: Clean up temp file ────────────────────────
    if os.path.exists(temp_path):
        os.remove(temp_path)

    # Return both the visual image and the score
    return ela_image, ela_score


def interpret_ela(score):
    """
    Takes the ELA score (0-100) and returns a human-readable message.
    
    Score ranges:
        0  - 20 : Looks normal, not much editing
        21 - 45 : Some editing detected, be cautious
        46 - 100: Heavy editing, very suspicious
    """
    if score < 20:
        return "Low editing detected — image appears authentic", "green"
    elif score < 45:
        return "Moderate editing detected — review carefully", "orange"
    else:
        return "Heavy editing detected — image is likely manipulated", "red"