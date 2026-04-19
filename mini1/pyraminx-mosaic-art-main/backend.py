from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import cv2
import numpy as np
import math
import os
from werkzeug.utils import secure_filename
import uuid
import base64
from io import BytesIO
from PIL import Image
from PIL import ImageOps

app = Flask(__name__, static_folder='.')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_and_preprocess_image(file_path):
    """Helper to load image with robust fallback and basic normalization."""
    image = cv2.imread(file_path)
    if image is None:
        with Image.open(file_path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img).convert('RGB')
            image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    
    # Downscale very large images
    max_dim = 2000
    h0, w0 = image.shape[:2]
    if max(h0, w0) > max_dim:
        scale = max_dim / float(max(h0, w0))
        image = cv2.resize(image, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
    
    # Ensure 3-channel BGR
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif len(image.shape) == 3 and image.shape[2] == 4:
        # Handle Alpha channel
        bgr = image[:, :, :3]
        alpha = image[:, :, 3] / 255.0
        white_bg = np.ones_like(bgr) * 255
        image = (bgr.astype(np.float32) * alpha[..., None] + 
                 white_bg.astype(np.float32) * (1 - alpha[..., None])).astype(np.uint8)
    
    return image

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _ciede2000_delta_e(lab1, lab2):
    """Compute CIEDE2000 color difference between two Lab colors.
    lab1, lab2: arrays like [L, a, b] in OpenCV Lab ranges.
    Returns scalar Delta E 2000.
    """
    # Convert to float
    L1, a1, b1 = lab1.astype(np.float64)
    L2, a2, b2 = lab2.astype(np.float64)

    # Compensate for OpenCV Lab ranges: L [0,255] -> [0,100], a/b [0,255] -> [-128,127]
    L1 *= 100.0 / 255.0
    L2 *= 100.0 / 255.0
    a1 -= 128.0
    a2 -= 128.0
    b1 -= 128.0
    b2 -= 128.0

    kL = kC = kH = 1.0

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    C_bar = (C1 + C2) / 2.0

    G = 0.5 * (1 - math.sqrt((C_bar ** 7) / (C_bar ** 7 + 25 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)

    def atan2_deg(y, x):
        ang = math.degrees(math.atan2(y, x))
        return ang + 360 if ang < 0 else ang

    h1p = 0 if C1p == 0 else atan2_deg(b1, a1p)
    h2p = 0 if C2p == 0 else atan2_deg(b2, a2p)

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0
    else:
        dh = h2p - h1p
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
        dhp = dh
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2.0)

    Lp_bar = (L1 + L2) / 2.0
    Cp_bar = (C1p + C2p) / 2.0

    if C1p * C2p == 0:
        hp_bar = h1p + h2p
    else:
        hsum = h1p + h2p
        if abs(h1p - h2p) > 180:
            hp_bar = (hsum + 360) / 2.0 if hsum < 360 else (hsum - 360) / 2.0
        else:
            hp_bar = hsum / 2.0

    T = 1 - 0.17 * math.cos(math.radians(hp_bar - 30)) \
        + 0.24 * math.cos(math.radians(2 * hp_bar)) \
        + 0.32 * math.cos(math.radians(3 * hp_bar + 6)) \
        - 0.20 * math.cos(math.radians(4 * hp_bar - 63))

    d_ro = 30 * math.exp(-((hp_bar - 275) / 25) ** 2)
    RC = 2 * math.sqrt((Cp_bar ** 7) / (Cp_bar ** 7 + 25 ** 7))
    SL = 1 + (0.015 * ((Lp_bar - 50) ** 2)) / math.sqrt(20 + (Lp_bar - 50) ** 2)
    SC = 1 + 0.045 * Cp_bar
    SH = 1 + 0.015 * Cp_bar * T
    RT = -math.sin(math.radians(2 * d_ro)) * RC

    dE = math.sqrt(
        (dLp / (kL * SL)) ** 2 +
        (dCp / (kC * SC)) ** 2 +
        (dHp / (kH * SH)) ** 2 +
        RT * (dCp / (kC * SC)) * (dHp / (kH * SH))
    )
    return dE

def quantize_color(color, palette):
    """Quantize a single BGR color to the nearest palette entry using perceptually accurate color matching.
    
    Uses CIEDE2000 for small palettes (<=16 colors) for maximum accuracy,
    falls back to weighted Lab distance for larger palettes or on errors.
    """
    try:
        color = np.clip(color, 0, 255).astype(np.uint8)
        num_colors = len(palette)
        
        # Convert color to Lab space
        color_lab = cv2.cvtColor(np.uint8([[color]]), cv2.COLOR_BGR2LAB)[0][0].astype(np.float64)
        
        # Convert palette to Lab space (optimized)
        palette_bgr = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
        palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)
        
        # Use CIEDE2000 for small palettes (Pyraminx has 4 colors, so this is always used)
        if num_colors <= 16:
            distances = np.array([_ciede2000_delta_e(color_lab, p_lab) for p_lab in palette_lab])
        else:
            # For larger palettes, use weighted Lab distance (faster)
            weights = np.array([2.0, 1.0, 1.0])  # L is more perceptually important
            diff = color_lab - palette_lab
            weighted_diff = diff * weights
            distances = np.sqrt(np.sum(weighted_diff ** 2, axis=1))
        
        nearest_index = int(np.argmin(distances))
        return palette[nearest_index]
    except Exception:
        # Fallback: Weighted Euclidean in BGR (less accurate but always works)
        color_bgr = np.array(color, dtype=np.float32)
        palette_bgr = np.array(palette, dtype=np.float32)
        # Use weights for BGR: Blue and Green are weighted slightly less than Red
        weights_bgr = np.array([0.8, 1.0, 1.2])  # [B, G, R]
        diff = (palette_bgr - color_bgr) * weights_bgr
        distances = np.linalg.norm(diff, axis=1)
        nearest_index = int(np.argmin(distances))
        return palette[nearest_index]

def apply_clahe_bgr(image_bgr):
    """Apply CLAHE on L channel in Lab space for better contrast/robustness; return BGR."""
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)
    lab_eq = cv2.merge((l_eq, a, b))
    return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

def get_pyraminx_palette():
    """Return the fixed Pyraminx cube colors: Blue, Yellow, Red, Green (in BGR format)."""
    # Standard Pyraminx colors in BGR format (OpenCV uses BGR, not RGB)
    # These are bright, saturated colors matching actual Pyraminx cubes
    return [
        (255, 0, 0),      # Blue (B=255, G=0, R=0) - Bright blue
        (0, 255, 255),    # Yellow (B=0, G=255, R=255) - Bright yellow
        (0, 0, 255),      # Red (B=0, G=0, R=255) - Bright red
        (0, 255, 0),      # Green (B=0, G=255, R=0) - Bright green
    ]

def quantize_image(image, palette, dither=False):
    """Quantize the entire image to the palette colors using optimized vectorized operations.
    
    Uses Lab color space for perceptually accurate color matching.
    For small palettes (<=16 colors), uses CIEDE2000 for maximum accuracy.
    For larger palettes or images, uses weighted Lab distance for speed.
    """
    if dither:
        # Apply Floyd-Steinberg dithering in Lab domain for better perceptual quality
        return apply_floyd_steinberg_dithering_lab(image, palette)
    
    h, w = image.shape[:2]
    num_pixels = h * w
    num_colors = len(palette)
    
    # Convert image to Lab for perceptually uniform color matching
    image_lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float64)
    
    # Convert palette to Lab space once (reshape to column vector format for broadcasting)
    palette_bgr = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
    palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)
    
    # Reshape image for vectorized processing: (h*w, 3)
    pixels_lab = image_lab.reshape(-1, 3)
    
    # Choose quantization method based on image size and palette size
    # For small palettes (Pyraminx has 4 colors), CIEDE2000 is feasible and more accurate
    # For larger images, use weighted Lab distance which is much faster
    
    use_ciede2000 = (num_colors <= 16 and num_pixels < 1000000)  # Use CIEDE2000 for small palettes/images
    
    if use_ciede2000:
        # Use CIEDE2000 for maximum perceptual accuracy (vectorized where possible)
        quantized_indices = np.zeros(num_pixels, dtype=np.int32)
        
        # Vectorized CIEDE2000 computation
        # For each palette color, compute distance to all pixels
        for i in range(num_colors):
            palette_color = palette_lab[i]
            # Compute CIEDE2000 distance for all pixels at once
            # This is still a loop but processes all pixels for one palette color at a time
            distances = np.array([_ciede2000_delta_e(pixel_lab, palette_color) 
                                 for pixel_lab in pixels_lab])
            if i == 0:
                min_distances = distances.copy()
            else:
                # Update indices where this color is closer
                closer_mask = distances < min_distances
                quantized_indices[closer_mask] = i
                min_distances[closer_mask] = distances[closer_mask]
    else:
        # Use weighted Lab distance for speed (perceptually better than Euclidean)
        # Weight factors: L* is more important for perceptual difference
        weights = np.array([2.0, 1.0, 1.0])  # [L, a, b] weights
        
        # Reshape for broadcasting: (num_pixels, 1, 3) vs (1, num_colors, 3)
        pixels_expanded = pixels_lab[:, np.newaxis, :]  # (num_pixels, 1, 3)
        palette_expanded = palette_lab[np.newaxis, :, :]  # (1, num_colors, 3)
        
        # Compute weighted Lab distance (perceptually better than simple Euclidean)
        diff = pixels_expanded - palette_expanded  # (num_pixels, num_colors, 3)
        weighted_diff = diff * weights  # Apply weights
        distances = np.sqrt(np.sum(weighted_diff ** 2, axis=2))  # (num_pixels, num_colors)
        
        # Find nearest palette color for each pixel
        quantized_indices = np.argmin(distances, axis=1)
    
    # Map indices to palette colors (vectorized)
    quantized_flat = np.array(palette)[quantized_indices]
    quantized = quantized_flat.reshape(h, w, 3)
    
    # Ensure output is uint8 and clipped to valid range
    quantized = np.clip(quantized, 0, 255).astype(np.uint8)
    
    return quantized

def apply_floyd_steinberg_dithering(image, palette):
    """Apply Floyd-Steinberg dithering for smoother color transitions.
    
    Uses Lab color space for perceptually accurate error diffusion.
    Optimized for performance while maintaining quality.
    """
    h, w = image.shape[:2]
    num_colors = len(palette)
    
    # Convert to float for error accumulation
    quantized = image.copy().astype(np.float32)
    
    # Convert palette to Lab space once
    palette_bgr = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
    palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)
    
    # Pre-compute weights for Lab distance (L is more perceptually important)
    weights = np.array([2.0, 1.0, 1.0])
    
    # Process image row by row (Floyd-Steinberg requires sequential processing)
    for y in range(h):
        for x in range(w):
            # Get current pixel in Lab space
            current_bgr = np.clip(quantized[y, x], 0, 255).astype(np.uint8)
            current_lab = cv2.cvtColor(np.uint8([[current_bgr]]), cv2.COLOR_BGR2LAB)[0][0].astype(np.float64)
            
            # Find nearest palette color using weighted Lab distance
            if num_colors <= 16:
                # For small palettes, use CIEDE2000 for better accuracy
                distances = np.array([_ciede2000_delta_e(current_lab, p_lab) for p_lab in palette_lab])
            else:
                # For larger palettes, use weighted Lab distance for speed
                diff = current_lab - palette_lab  # (num_colors, 3)
                weighted_diff = diff * weights
                distances = np.sqrt(np.sum(weighted_diff ** 2, axis=1))
            
            nearest_idx = np.argmin(distances)
            new_pixel = np.array(palette[nearest_idx], dtype=np.float32)
            
            # Set quantized pixel
            quantized[y, x] = new_pixel
            
            # Calculate quantization error in BGR space (for error diffusion)
            error = quantized[y, x] - new_pixel
            
            # Distribute error to neighboring pixels (Floyd-Steinberg kernel)
            # Kernel:      [   *   7/16 ]
            #              [3/16  5/16 1/16]
            if x + 1 < w:
                quantized[y, x + 1] += error * (7.0 / 16.0)
            if y + 1 < h:
                if x > 0:
                    quantized[y + 1, x - 1] += error * (3.0 / 16.0)
                quantized[y + 1, x] += error * (5.0 / 16.0)
                if x + 1 < w:
                    quantized[y + 1, x + 1] += error * (1.0 / 16.0)
    
    return np.clip(quantized, 0, 255).astype(np.uint8)

def apply_floyd_steinberg_dithering_lab(image_bgr, palette):
    """Floyd–Steinberg dithering performed in Lab space for perceptual accuracy.
    - image_bgr: uint8 BGR image
    - palette: list of BGR tuples
    Returns uint8 BGR image where all pixels are snapped to palette colors with Lab-domain error diffusion.
    """
    h, w = image_bgr.shape[:2]
    num_colors = len(palette)

    # Working buffer in Lab (float)
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

    # Precompute palette in Lab (float64 for CIEDE2000)
    palette_bgr_np = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
    palette_lab = cv2.cvtColor(palette_bgr_np, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)

    # Error diffusion in Lab domain
    for y in range(h):
        for x in range(w):
            current_lab = lab[y, x].astype(np.float64)
            # Choose nearest by CIEDE2000 (palette is tiny)
            distances = np.array([_ciede2000_delta_e(current_lab, p_lab) for p_lab in palette_lab])
            idx = int(np.argmin(distances))
            new_lab = palette_lab[idx]

            # Set quantized value and compute error (Lab domain)
            old_lab = current_lab
            lab[y, x] = new_lab
            err = old_lab - new_lab

            # Diffuse error (Floyd–Steinberg kernel) in Lab domain
            if x + 1 < w:
                lab[y, x + 1] = np.clip(lab[y, x + 1] + err * (7.0 / 16.0), 0, 255)
            if y + 1 < h:
                if x > 0:
                    lab[y + 1, x - 1] = np.clip(lab[y + 1, x - 1] + err * (3.0 / 16.0), 0, 255)
                lab[y + 1, x] = np.clip(lab[y + 1, x] + err * (5.0 / 16.0), 0, 255)
                if x + 1 < w:
                    lab[y + 1, x + 1] = np.clip(lab[y + 1, x + 1] + err * (1.0 / 16.0), 0, 255)

    # Convert back to BGR
    out_bgr = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    return out_bgr

def sample_triangle_color(quantized_image, mask, method='mode', palette=None, original_image=None, precomputed_edges=None):
    """Sample the representative color from a triangle region, with edge-awareness."""
    # ULTIMATE DIMENSION SYNC: 
    # We force every input array to match the mask's shape (e.g., 1275) 
    # to prevent "1280 vs 1275" boolean indexing crashes.
    h_m, w_m = mask.shape[:2]
    
    if original_image is not None:
        original_image = original_image[:h_m, :w_m]
    if quantized_image is not None:
        quantized_image = quantized_image[:h_m, :w_m]
    if precomputed_edges is not None:
        precomputed_edges = precomputed_edges[:h_m, :w_m]

    sample_img = original_image if original_image is not None else quantized_image

    pixels = sample_img[mask > 0]
    if len(pixels) == 0:
        return (255, 255, 255)  # White fallback

    if method == 'edge_aware' and original_image is not None and precomputed_edges is not None and palette is not None:
        try:
            num_colors = len(palette)
            palette_bgr = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
            palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)

            # Sampling from the guaranteed-aligned edge map
            region_edges = precomputed_edges[:h_mask, :w_mask][mask > 0]
            
            # Separate edge pixels from center (non-edge) pixels
            edge_pixels = pixels[region_edges > 0]
            center_pixels = pixels[region_edges == 0]

            # If not enough edge pixels, fall back to a simple mode of all pixels
            if len(edge_pixels) < 1:
                all_pixels_lab = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
                distances = np.array([[_ciede2000_delta_e(p, p_lab) for p_lab in palette_lab] for p in all_pixels_lab])
                indices = np.argmin(distances, axis=1)
                counts = np.bincount(indices, minlength=num_colors)
                return palette[np.argmax(counts)]

            # --- Edge-aware logic: Weight edge colors more heavily ---
            # 1. Quantize edge pixels to palette and get a distribution of colors
            edge_lab = cv2.cvtColor(edge_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
            edge_distances = np.array([[_ciede2000_delta_e(p, p_lab) for p_lab in palette_lab] for p in edge_lab])
            edge_indices = np.argmin(edge_distances, axis=1)
            counts_edge = np.bincount(edge_indices, minlength=num_colors).astype(np.float64)
            
            if np.sum(counts_edge) > 0:
                counts_edge /= np.sum(counts_edge) # Normalize to get a distribution

            # 2. Do the same for center pixels
            if len(center_pixels) > 0:
                center_lab = cv2.cvtColor(center_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
                center_distances = np.array([[_ciede2000_delta_e(p, p_lab) for p_lab in palette_lab] for p in center_lab])
                center_indices = np.argmin(center_distances, axis=1)
                counts_center = np.bincount(center_indices, minlength=num_colors).astype(np.float64)
                
                if np.sum(counts_center) > 0:
                    counts_center /= np.sum(counts_center)
                
                # 3. Combine distributions with 70/30 weighting (balanced structural priority)
                combined_scores = 0.70 * counts_edge + 0.30 * counts_center
            else:
                combined_scores = counts_edge

            # Choose the palette color with the highest combined score
            chosen_idx = int(np.argmax(combined_scores))
            return palette[chosen_idx]
        except Exception:
             # Fallback on error to simple mean
            mean_color = np.mean(pixels, axis=0)
            return quantize_color(mean_color, palette)

    # Fallback to original methods if not 'edge_aware', but sample from original image
    if palette is None:
        palette = get_pyraminx_palette()

    if method == 'mode':
        # Find mode of nearest colors in the original pixels
        pixels_lab = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
        palette_bgr = np.array(palette, dtype=np.uint8).reshape(len(palette), 1, 3)
        palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(len(palette), 3).astype(np.float64)
        
        distances = np.array([[_ciede2000_delta_e(p, p_lab) for p_lab in palette_lab] for p in pixels_lab])
        indices = np.argmin(distances, axis=1)
        counts = np.bincount(indices, minlength=len(palette))
        return palette[np.argmax(counts)]

    elif method == 'mean':
        mean_color = np.mean(pixels, axis=0)
        return quantize_color(mean_color, palette)

    else:  # center
        center_y, center_x = np.where(mask > 0)
        center_idx = len(center_y) // 2
        center_color = tuple(map(int, sample_img[center_y[center_idx], center_x[center_idx]]))
        return quantize_color(center_color, palette)

def white_balance_gray_world(image_bgr):
    """Simple gray-world white balance to correct color cast."""
    eps = 1e-6
    b, g, r = cv2.split(image_bgr.astype(np.float32))
    mean_b, mean_g, mean_r = b.mean() + eps, g.mean() + eps, r.mean() + eps
    mean_gray = (mean_b + mean_g + mean_r) / 3.0
    b *= mean_gray / mean_b
    g *= mean_gray / mean_g
    r *= mean_gray / mean_r
    balanced = cv2.merge((b, g, r))
    return np.clip(balanced, 0, 255).astype(np.uint8)

def apply_gamma_correction(image_bgr, gamma=None):
    """Apply gamma correction. If gamma is None, estimate from luminance to target mid-tone."""
    if gamma is None:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        mean_l = max(1.0, float(gray.mean()))
        target = 128.0
        # Prevent extreme gamma
        gamma = np.clip(np.log(target / 255.0 + 1e-6) / np.log(mean_l / 255.0 + 1e-6), 0.5, 2.0)
    inv_gamma = 1.0 / float(gamma)
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype('uint8')
    return cv2.LUT(image_bgr, table)

def detect_edges_with_bilateral(image, d=9, sigma_color=75, sigma_space=75):
    """Uses bilateral filtering before Canny to reduce noise while preserving edges."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Bilateral filter is very effective at noise reduction while keeping edges sharp
    blurred = cv2.bilateralFilter(gray, d, sigma_color, sigma_space)
    
    # Use adaptive thresholds based on median intensity for better generalization
    v = np.median(blurred)
    sigma = 0.33
    lower = int(max(15, (1.0 - sigma) * v))
    upper = int(min(240, (1.0 + sigma) * v))
    edges = cv2.Canny(blurred, lower, upper)
    
    # Tighter dilation kernel for more precise edge sampling masks
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_edges = cv2.dilate(edges, kernel, iterations=1)
    return dilated_edges

def create_triangle_mosaic(image, side_length):
    """Create a triangular mosaic with Pyraminx colors (Blue, Yellow, Red, Green) or adaptive palette.
    """
    # Quality Enhancement - enabled by default
    image = white_balance_gray_world(image)
    image = apply_gamma_correction(image, None)
    image = apply_clahe_bgr(image)

    height, width, _ = image.shape
    tri_height = max(4, int(side_length * math.sqrt(3) / 2))
    half_side = max(4, side_length // 2)

    num_cols = max(1, (width // half_side) - 1)
    num_rows = max(1, height // tri_height)
    if num_rows >= 3:
        num_rows = (num_rows // 3) * 3

    # --- STRICT GRID ALIGNMENT ---
    grid_h = num_rows * tri_height
    grid_w = (num_cols + 1) * half_side

    # Force a hard crop and a fresh memory copy (prevents dimension ghosting)
    cropped_source = image[:grid_h, :grid_w].copy()
    h, w = cropped_source.shape[:2]
    
    output = np.ones((h, w, 3), dtype=np.uint8) * 255

    # 1. Generate all derived maps using ONLY the cropped source
    palette = get_pyraminx_palette()
    precomputed_edges = detect_edges_with_bilateral(cropped_source)
    source_quantized = quantize_image(cropped_source, palette, dither=True)

    for row in range(num_rows):
        for col in range(num_cols):
            x = col * half_side
            y = row * tri_height
            
            # Define triangle coordinates
            if (row + col) % 2 == 0: # Upward
                pts = np.array([[x, y + tri_height], [x + half_side, y], [x + side_length, y + tri_height]], np.int32)
            else: # Downward
                pts = np.array([[x, y], [x + side_length, y], [x + half_side, y + tri_height]], np.int32)
            
            # Create mask using the guaranteed synced 'h' and 'w'
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)
            
            # Select color based on edge-weighted sampling
            # This ensures object boundaries (the 'shape') are preserved.
            triangle_color = sample_triangle_color(
                source_quantized,
                mask,
                method='edge_aware',
                palette=palette,
                original_image=cropped_source,
                precomputed_edges=precomputed_edges
            )

            # Render triangle
            cv2.fillPoly(output, [pts], triangle_color)
            # Outline pieces to simulate the physical gaps in a Pyraminx mosaic
            cv2.polylines(output, [pts], isClosed=True, color=(0, 0, 0), thickness=1)

    return output


@app.route('/api/generate-mosaic', methods=['POST'])
def generate_mosaic():
    """Generate triangular mosaic from uploaded image"""
    try:
        # Check if image file is present
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Get parameters with defaults
        side_length = int(request.form.get('triangleSize', 20))

        # Save uploaded file
        unique_filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)

        try:
            image = load_and_preprocess_image(file_path)
        except Exception:
            os.remove(file_path)
            return jsonify({'error': 'Error loading the image.'}), 400
        
        # Adjust triangle size for very small images (guarantee at least some triangles)
        min_dim = min(image.shape[:2])
        max_allowed_side = max(8, min_dim // 2)
        if side_length > max_allowed_side:
            side_length = max(8, min_dim // 4)

        # Create mosaic
        mosaic = create_triangle_mosaic(image, side_length)

        # Calculate physical piece counts
        h, w = mosaic.shape[:2]
        tri_height = int(side_length * math.sqrt(3) / 2)
        total_triangles = ((w // (side_length // 2)) - 1) * (h // tri_height)

        # Encode mosaic to PNG in-memory to ensure consistent data URL format
        success, buffer = cv2.imencode('.png', mosaic)
        if not success:
            os.remove(file_path)
            return jsonify({'error': 'Failed to encode the mosaic image.'}), 500

        mosaic_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')

        # Clean up uploaded file
        os.remove(file_path)

        return jsonify({
            'success': True,
            'mosaicImage': f"data:image/png;base64,{mosaic_base64}",
            'message': f'Mosaic generated successfully with triangle size {side_length}',
            'total_triangles': int(total_triangles),
            'total_units': int(math.ceil(total_triangles / 9))
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'message': 'Pyraminx Mosaic API is running'})

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

if __name__ == '__main__':
    print("Starting Pyraminx Mosaic Art Backend...")
    print("Server will be available at: http://localhost:5000")
    print("API Health Check: http://localhost:5000/api/health")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print("If you get an error, make sure you're running: python backend.py")
    print("=" * 60)
    try:
        app.run(debug=False, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Error starting server: {e}")
        print("Make sure you have all dependencies installed:")
        print("   pip install -r requirements.txt")