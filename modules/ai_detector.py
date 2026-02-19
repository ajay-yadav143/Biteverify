# modules/ai_detector.py
# AI-Generated Image Detection
# Detects: GAN fingerprints, diffusion model artifacts,
#          Gemini/DALL-E edits, frequency anomalies, noise patterns

import numpy as np
from PIL import Image
import os

# ── Try importing heavy libs, fallback gracefully ────────────
try:
    from scipy import fftpack
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False

try:
    from skimage import filters, measure, morphology, color as sk_color
    SKIMAGE_OK = True
except ImportError:
    SKIMAGE_OK = False

try:
    import torch
    import torchvision.transforms as T
    TORCH_OK = True
except ImportError:
    TORCH_OK = False


# ═══════════════════════════════════════════════════════
#  1. FREQUENCY DOMAIN ANALYSIS (FFT)
#  AI-generated images have unnatural frequency patterns
# ═══════════════════════════════════════════════════════
def analyze_frequency(image_path):
    """
    Real photos have natural 1/f frequency distribution.
    AI/GAN images show grid artifacts and spectral spikes.
    Returns score 0-100 (higher = more suspicious)
    """
    if not SCIPY_OK:
        return 0, "scipy not installed", []

    img = Image.open(image_path).convert("L")  # grayscale
    img = img.resize((512, 512))
    arr = np.array(img, dtype=float)

    # 2D FFT
    fft    = fftpack.fft2(arr)
    fft_sh = fftpack.fftshift(fft)
    mag    = np.log(np.abs(fft_sh) + 1)

    # Check for grid artifacts (GAN signature)
    center  = mag.shape[0] // 2
    cross_h = mag[center, :]
    cross_v = mag[:, center]

    # Detect unnatural spikes in frequency domain
    h_std = np.std(cross_h)
    v_std = np.std(cross_v)
    h_mean = np.mean(cross_h)
    v_mean = np.mean(cross_v)

    h_spikes = np.sum(cross_h > h_mean + 2.5 * h_std)
    v_spikes = np.sum(cross_v > v_mean + 2.5 * v_std)

    # Check high-frequency energy ratio (AI images over-smooth)
    h, w     = mag.shape
    center_r = 50
    mask     = np.zeros((h, w), dtype=bool)
    cy, cx   = h // 2, w // 2
    Y, X     = np.ogrid[:h, :w]
    mask[(Y - cy)**2 + (X - cx)**2 <= center_r**2] = True
    low_freq  = np.mean(mag[mask])
    high_freq = np.mean(mag[~mask])

    # Natural photos: high_freq/low_freq ratio ~0.3-0.5
    # AI images: ratio is either too low (over-smoothed) or too high (artifacts)
    ratio = high_freq / (low_freq + 1e-6)
    ratio_suspicion = 0
    if ratio < 0.25:   ratio_suspicion = 60   # over-smoothed = AI
    elif ratio < 0.30: ratio_suspicion = 30
    elif ratio > 0.65: ratio_suspicion = 50   # excessive HF artifacts
    elif ratio > 0.55: ratio_suspicion = 25

    # Spike score
    spike_score = min(100, (h_spikes + v_spikes) * 3)

    total = round((spike_score * 0.4 + ratio_suspicion * 0.6), 2)

    flags = []
    if spike_score > 30:   flags.append(f"Grid artifacts in frequency domain ({h_spikes+v_spikes} spikes)")
    if ratio < 0.28:       flags.append("Image over-smoothed — possible AI generation")
    if ratio > 0.60:       flags.append("Excessive high-frequency artifacts detected")

    return min(total, 100), f"Freq ratio: {round(ratio,3)} | Spikes: {h_spikes+v_spikes}", flags


# ═══════════════════════════════════════════════════════
#  2. NOISE PATTERN ANALYSIS
#  Real cameras have sensor noise; AI images don't
# ═══════════════════════════════════════════════════════
def analyze_noise_pattern(image_path):
    """
    Real photos have natural Gaussian sensor noise.
    AI images either have zero noise or artificial noise.
    Returns score 0-100 (higher = more suspicious)
    """
    if not SKIMAGE_OK:
        return 0, "scikit-image not installed", []

    img = Image.open(image_path).convert("L").resize((512, 512))
    arr = np.array(img, dtype=float)

    # High-pass filter to isolate noise
    from scipy.ndimage import gaussian_filter
    smoothed = gaussian_filter(arr, sigma=1.5)
    noise    = arr - smoothed

    noise_std  = np.std(noise)
    noise_mean = np.mean(np.abs(noise))

    # Check local noise variance across regions
    regions    = []
    block_size = 64
    for y in range(0, 512 - block_size, block_size):
        for x in range(0, 512 - block_size, block_size):
            block = noise[y:y+block_size, x:x+block_size]
            regions.append(np.std(block))

    region_std = np.std(regions)
    region_mean = np.mean(regions)

    flags = []
    score = 0

    # Very low noise → likely AI generated (too perfect)
    if noise_std < 2.0:
        score += 55
        flags.append(f"Extremely low sensor noise ({round(noise_std,2)}) — possible AI generation")
    elif noise_std < 3.5:
        score += 25
        flags.append(f"Below-normal noise level ({round(noise_std,2)})")

    # Very uniform noise across regions = AI
    # Real cameras: noise varies by region (shadows vs highlights)
    if region_mean > 0 and region_std / region_mean < 0.15:
        score += 35
        flags.append("Noise is unnaturally uniform across image regions")
    elif region_mean > 0 and region_std / region_mean < 0.25:
        score += 15

    # Very high noise in patches but zero elsewhere = spliced
    if region_mean > 0 and region_std / region_mean > 1.5:
        score += 40
        flags.append("Highly inconsistent noise — possible image splicing/editing")

    return min(round(score, 2), 100), f"Noise σ={round(noise_std,2)}, Region variation={round(region_std,3)}", flags


# ═══════════════════════════════════════════════════════
#  3. REGION-LEVEL EDIT LOCALIZATION HEATMAP
#  Shows EXACTLY where edits were made in the image
# ═══════════════════════════════════════════════════════
def generate_edit_heatmap(image_path, output_path="uploads/heatmap_out.jpg"):
    """
    Generates a heatmap showing suspicious edited regions.
    Red = highly suspicious, Blue = clean.
    Returns the heatmap PIL image and list of suspicious regions.
    """
    from PIL import ImageFilter, ImageChops, ImageEnhance
    import io

    img = Image.open(image_path).convert("RGB")
    orig_size = img.size
    img_resized = img.resize((512, 512))

    # --- Method 1: ELA-based region detection ---
    buffer = io.BytesIO()
    img_resized.save(buffer, "JPEG", quality=75)
    buffer.seek(0)
    ela_img = Image.open(buffer).resize((512, 512))
    ela_diff = ImageChops.difference(img_resized, ela_img)
    ela_arr  = np.array(ela_diff, dtype=float)
    ela_mag  = np.mean(ela_arr, axis=2)

    # --- Method 2: Local variance map ---
    gray_arr = np.array(img_resized.convert("L"), dtype=float)
    from scipy.ndimage import uniform_filter
    local_mean = uniform_filter(gray_arr, size=15)
    local_sq   = uniform_filter(gray_arr**2, size=15)
    local_var  = np.sqrt(np.maximum(local_sq - local_mean**2, 0))

    # --- Method 3: Color inconsistency ---
    rgb_arr  = np.array(img_resized, dtype=float)
    r, g, b  = rgb_arr[:,:,0], rgb_arr[:,:,1], rgb_arr[:,:,2]
    # Detect unnatural color ratios (AI often gets these wrong)
    rg_ratio = np.abs(r - g) / (r + g + 1)
    rb_ratio = np.abs(r - b) / (r + b + 1)
    color_anomaly = (rg_ratio + rb_ratio) * 50

    # --- Combine all signals ---
    ela_norm   = (ela_mag / (ela_mag.max() + 1e-6)) * 100
    var_norm   = (local_var / (local_var.max() + 1e-6)) * 100
    color_norm = np.clip(color_anomaly, 0, 100)

    combined = ela_norm * 0.45 + var_norm * 0.25 + color_norm * 0.30

    # --- Create colormap (blue=clean, green=medium, red=suspicious) ---
    heatmap = np.zeros((512, 512, 3), dtype=np.uint8)
    norm    = combined / (combined.max() + 1e-6)

    for y in range(512):
        for x in range(0, 512, 4):  # skip pixels for speed
            v = norm[y, x]
            if v < 0.33:
                r2, g2, b2 = int(0), int(50 * v * 3), int(200 * (1 - v * 3))
            elif v < 0.66:
                t = (v - 0.33) / 0.33
                r2, g2, b2 = int(200 * t), int(180), int(0)
            else:
                t = (v - 0.66) / 0.34
                r2, g2, b2 = int(200 + 55 * t), int(180 - 180 * t), int(0)
            heatmap[y, x:x+4] = [r2, g2, b2]

    heatmap_img = Image.fromarray(heatmap, "RGB")

    # Blend with original for overlay effect
    heatmap_resized = heatmap_img.resize(orig_size)
    orig_rgba   = img.convert("RGBA")
    heat_rgba   = heatmap_resized.convert("RGBA")
    blended     = Image.blend(orig_rgba, heat_rgba, alpha=0.45).convert("RGB")
    blended.save(output_path, "JPEG", quality=90)

    # Find suspicious regions
    suspicious_regions = []
    block = 64
    for y in range(0, 512 - block, block):
        for x in range(0, 512 - block, block):
            region_score = np.mean(combined[y:y+block, x:x+block])
            if region_score > 45:
                suspicious_regions.append({
                    "region": f"({x//64},{y//64})",
                    "score":  round(region_score, 1)
                })

    return blended, suspicious_regions


# ═══════════════════════════════════════════════════════
#  4. GAN / DIFFUSION FINGERPRINT DETECTOR
#  Checks for known AI model artifacts
# ═══════════════════════════════════════════════════════
def detect_ai_fingerprint(image_path):
    """
    Detects GAN and diffusion model fingerprints:
    - Checkerboard artifacts (DCGAN, StyleGAN)
    - Over-smooth textures (Midjourney, Gemini)
    - Perfect symmetry (common in AI)
    - Texture inconsistency between regions
    """
    img  = Image.open(image_path).convert("RGB").resize((512, 512))
    arr  = np.array(img, dtype=float)
    gray = np.mean(arr, axis=2)

    score = 0
    flags = []

    # --- Test 1: Checkerboard pattern (transposed conv artifact) ---
    if SCIPY_OK:
        fft    = fftpack.fft2(gray)
        fft_sh = np.abs(fftpack.fftshift(fft))
        h, w   = fft_sh.shape
        corner_energy = (
            np.mean(fft_sh[:30, :30]) +
            np.mean(fft_sh[:30, -30:]) +
            np.mean(fft_sh[-30:, :30]) +
            np.mean(fft_sh[-30:, -30:])
        ) / 4
        center_energy = np.mean(fft_sh[h//2-30:h//2+30, w//2-30:w//2+30])
        checker_ratio = corner_energy / (center_energy + 1e-6)
        if checker_ratio > 0.08:
            score += 40
            flags.append(f"Checkerboard artifact detected (GAN fingerprint, ratio={round(checker_ratio,3)})")
        elif checker_ratio > 0.05:
            score += 20
            flags.append(f"Mild checkerboard pattern (ratio={round(checker_ratio,3)})")

    # --- Test 2: Over-smooth texture (Gemini/DALL-E) ---
    # Real photos: local standard deviation > 8 in most regions
    local_vars = []
    block = 32
    for y in range(0, 512 - block, block):
        for x in range(0, 512 - block, block):
            block_arr = gray[y:y+block, x:x+block]
            local_vars.append(np.std(block_arr))

    mean_local_var = np.mean(local_vars)
    smooth_blocks  = sum(1 for v in local_vars if v < 6)
    total_blocks   = len(local_vars)

    if mean_local_var < 8:
        score += 35
        flags.append(f"Over-smooth texture ({round(mean_local_var,2)} σ) — characteristic of AI generation")
    elif mean_local_var < 12:
        score += 15

    if smooth_blocks / total_blocks > 0.4:
        score += 25
        flags.append(f"{round(smooth_blocks/total_blocks*100)}% of regions are abnormally smooth")

    # --- Test 3: Texture inconsistency (spliced image) ---
    # High variance BETWEEN block variances = spliced (real vs AI)
    between_var = np.std(local_vars)
    if between_var > 18:
        score += 30
        flags.append(f"High texture inconsistency between regions ({round(between_var,1)}) — possible splicing")
    elif between_var > 12:
        score += 10

    # --- Test 4: Perfect edge symmetry (AI often oversmooths edges) ---
    edges_h = np.abs(np.diff(gray, axis=0))
    edges_v = np.abs(np.diff(gray, axis=1))
    edge_ratio = np.mean(edges_h) / (np.mean(edges_v) + 1e-6)
    if 0.98 < edge_ratio < 1.02:
        score += 15
        flags.append("Suspiciously symmetric edge distribution — possible AI")

    return min(round(score, 2), 100), flags


# ═══════════════════════════════════════════════════════
#  5. HUGGINGFACE AI IMAGE CLASSIFIER (Optional)
#  Uses pre-trained AI detector if transformers installed
# ═══════════════════════════════════════════════════════
def run_hf_classifier(image_path):
    """
    Uses Hugging Face AI image detector model.
    Model: umm-maybe/AI-image-detector
    Downloads ~100MB on first run.
    Returns score 0-100 and label.
    """
    try:
        from transformers import pipeline
        classifier = pipeline(
            "image-classification",
            model="umm-maybe/AI-image-detector",
            device=-1  # CPU
        )
        result = classifier(image_path)
        # Result: [{'label': 'artificial', 'score': 0.87}, {'label': 'human', 'score': 0.13}]
        for r in result:
            if r["label"].lower() in ["artificial", "fake", "ai"]:
                return round(r["score"] * 100, 2), f"HF Model: {round(r['score']*100,1)}% AI probability"
        return 0, "HF Model: Classified as real"
    except Exception as e:
        return -1, f"HF model unavailable ({str(e)[:40]})"


# ═══════════════════════════════════════════════════════
#  MASTER AI DETECTION FUNCTION
# ═══════════════════════════════════════════════════════
def run_ai_detection(image_path, use_hf=False):
    """
    Runs all AI detection methods and returns combined result.
    """
    results = {}

    # 1. Frequency analysis
    freq_score, freq_detail, freq_flags = analyze_frequency(image_path)
    results["frequency"] = {"score": freq_score, "detail": freq_detail, "flags": freq_flags}

    # 2. Noise pattern
    noise_score, noise_detail, noise_flags = analyze_noise_pattern(image_path)
    results["noise"] = {"score": noise_score, "detail": noise_detail, "flags": noise_flags}

    # 3. GAN fingerprint
    gan_score, gan_flags = detect_ai_fingerprint(image_path)
    results["gan"] = {"score": gan_score, "flags": gan_flags}

    # 4. Optional HF classifier
    if use_hf:
        hf_score, hf_detail = run_hf_classifier(image_path)
        results["hf"] = {"score": max(hf_score, 0), "detail": hf_detail}
    else:
        results["hf"] = {"score": -1, "detail": "HF model disabled"}

    # 5. Heatmap
    try:
        heatmap_img, suspicious_regions = generate_edit_heatmap(image_path)
        results["heatmap"] = {"regions": suspicious_regions, "generated": True}
    except Exception as e:
        results["heatmap"] = {"regions": [], "generated": False, "error": str(e)}

    # Combined score
    weights  = {"frequency": 0.25, "noise": 0.25, "gan": 0.50}
    combined = (
        freq_score  * weights["frequency"] +
        noise_score * weights["noise"] +
        gan_score   * weights["gan"]
    )

    if use_hf and results["hf"]["score"] >= 0:
        combined = combined * 0.5 + results["hf"]["score"] * 0.5

    all_flags = freq_flags + noise_flags + gan_flags
    label = "AI-GENERATED / EDITED" if combined > 55 else "POSSIBLY EDITED" if combined > 30 else "LIKELY GENUINE"
    color = "red" if combined > 55 else "orange" if combined > 30 else "green"

    results["combined"] = {
        "score":  round(combined, 2),
        "label":  label,
        "color":  color,
        "flags":  all_flags
    }

    return results


def interpret_ai_score(score):
    if score > 60:
        return "Strong AI/editing indicators detected", "red"
    elif score > 35:
        return "Some AI/editing patterns present", "orange"
    else:
        return "No significant AI indicators", "green"