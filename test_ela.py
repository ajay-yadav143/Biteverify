# test_ela.py
# Run this to test if ELA is working correctly
# We'll test it on any image you have on your computer

from modules.ela import run_ela, interpret_ela

# ── Put any image path here to test ──────────────────────
# Example: use any food photo you have
# On Windows, use double backslash \\ or forward slash /
IMAGE_PATH = "uploads/test_food.jpg"   # We'll create this below

# Run ELA
print("Running ELA analysis...")
ela_image, score = run_ela(IMAGE_PATH)

# Show result
print(f"ELA Score: {score}/100")

message, color = interpret_ela(score)
print(f"Result: {message}")

# Save the ELA output image so you can see it
ela_image.save("uploads/ela_result.jpg")
print("ELA result image saved to: uploads/ela_result.jpg")
print("Open this file to see which parts of the image were edited!")