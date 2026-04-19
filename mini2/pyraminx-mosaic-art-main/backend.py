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
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

app = Flask(__name__, static_folder='.')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def quantize_color(color, palette):
    """Quantize a single BGR color to the nearest palette entry using weighted Lab distance."""
    try:
        color = np.clip(color, 0, 255).astype(np.uint8)
        num_colors = len(palette)
        
        # Convert color to Lab space
        color_lab = cv2.cvtColor(np.uint8([[color]]), cv2.COLOR_BGR2LAB)[0][0].astype(np.float64)
        
        # Convert palette to Lab space (optimized)
        palette_bgr = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
        palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)
        
        # Use weighted Lab distance (L is more perceptually important)
        weights = np.array([2.0, 1.0, 1.0])
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

def create_adaptive_palette(image, num_colors=16, method='kmeans'):
    """Create an adaptive color palette from the image using k-means clustering.
    method options: 'kmeans' (BGR), 'kmeans_lab' (Lab space), 'pyraminx'
    """
    # Reshape image to be a list of pixels
    if method == 'pyraminx':
        return get_pyraminx_palette()

    if method == 'kmeans_lab':
        # Cluster in Lab space for perceptual grouping
        lab_img = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        data = lab_img.reshape((-1, 3)).astype(np.float32)
    else:
        # Default to BGR kmeans
        data = image.reshape((-1, 3)).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    flags = cv2.KMEANS_RANDOM_CENTERS

    K = max(2, min(int(num_colors), 64))
    _, labels, centers = cv2.kmeans(data, K, None, criteria, 5, flags)
    if method == 'kmeans_lab':
        # Convert Lab centers back to BGR
        centers_uint8 = np.clip(centers, 0, 255).astype(np.uint8).reshape(K, 1, 3)
        centers_bgr = cv2.cvtColor(centers_uint8, cv2.COLOR_LAB2BGR).reshape(K, 3)
        palette = np.uint8(centers_bgr)
    else:
        palette = np.uint8(centers)
    return [tuple(map(int, color)) for color in palette]

def quantize_image(image, palette, dither=False):
    """Quantize image to palette colors using vectorized weighted Lab distance."""
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
    
    # Use weighted Lab distance for speed and quality
    weights = np.array([2.0, 1.0, 1.0])  # [L, a, b] weights
    
    # Reshape for broadcasting
    pixels_expanded = pixels_lab[:, np.newaxis, :]
    palette_expanded = palette_lab[np.newaxis, :, :]
    
    # Compute weighted Lab distance
    diff = pixels_expanded - palette_expanded
    weighted_diff = diff * weights
    distances = np.sqrt(np.sum(weighted_diff ** 2, axis=2))
    
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
            diff = current_lab - palette_lab
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
    palette_lab = cv2.cvtColor(palette_bgr_np, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float32)

    weights = np.array([2.0, 1.0, 1.0])

    # Error diffusion in Lab domain
    for y in range(h):
        for x in range(w):
            current_lab = lab[y, x].astype(np.float64)
            # Choose nearest by weighted Lab distance
            distances = np.sqrt(np.sum(((current_lab - palette_lab) * weights)**2, axis=1))
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
    # Always sample from the original image if available for better accuracy
    sample_img = original_image if original_image is not None else quantized_image
    pixels = sample_img[mask > 0]

    if len(pixels) == 0:
        return (255, 255, 255)  # White fallback

    # The 'edge_aware' method is the key improvement for structural accuracy
    if method == 'edge_aware' and original_image is not None and precomputed_edges is not None and palette is not None:
        try:
            num_colors = len(palette)
            palette_bgr = np.array(palette, dtype=np.uint8).reshape(num_colors, 1, 3)
            palette_lab = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2LAB).reshape(num_colors, 3).astype(np.float64)
            weights = np.array([2.0, 1.0, 1.0])

            # Extract region from edge map
            region_edges = precomputed_edges[mask > 0]
            
            # Separate edge pixels from center (non-edge) pixels
            edge_pixels = pixels[region_edges > 0]
            center_pixels = pixels[region_edges == 0]

            # If not enough edge pixels, fall back to a simple mode of all pixels
            if len(edge_pixels) < 1:
                all_pixels_lab = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
                diff = all_pixels_lab[:, np.newaxis, :] - palette_lab[np.newaxis, :, :]
                distances = np.sqrt(np.sum((diff * weights)**2, axis=2))
                indices = np.argmin(distances, axis=1)
                counts = np.bincount(indices, minlength=num_colors)
                return palette[np.argmax(counts)]

            # --- Edge-aware logic: Weight edge colors more heavily ---
            # 1. Quantize edge pixels to palette and get a distribution of colors
            edge_lab = cv2.cvtColor(edge_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
            diff_edge = edge_lab[:, np.newaxis, :] - palette_lab[np.newaxis, :, :]
            edge_distances = np.sqrt(np.sum((diff_edge * weights)**2, axis=2))
            edge_indices = np.argmin(edge_distances, axis=1)
            counts_edge = np.bincount(edge_indices, minlength=num_colors).astype(np.float64)
            
            if np.sum(counts_edge) > 0:
                counts_edge /= np.sum(counts_edge) # Normalize to get a distribution

            # 2. Do the same for center pixels
            if len(center_pixels) > 0:
                center_lab = cv2.cvtColor(center_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
                diff_center = center_lab[:, np.newaxis, :] - palette_lab[np.newaxis, :, :]
                center_distances = np.sqrt(np.sum((diff_center * weights)**2, axis=2))
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
        weights = np.array([2.0, 1.0, 1.0])
        
        diff = pixels_lab[:, np.newaxis, :] - palette_lab[np.newaxis, :, :]
        distances = np.sqrt(np.sum((diff * weights)**2, axis=2))
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

def create_triangle_mosaic(image, side_length, palette_size=4, use_dithering=False, sampling_method='mode', use_pyraminx_colors=True, palette_method='kmeans_lab', gamma_value=None, enhanceForDetail=False):
    """Create a triangular mosaic with Pyraminx colors (Blue, Yellow, Red, Green) or adaptive palette.
    
    Args:
        image: Input BGR image
        side_length: Triangle side length in pixels
        sampling_method: 'mode', 'mean', 'center', or 'edge_aware' for sampling triangle colors
        enhanceForDetail: If True, applies a preprocessing pipeline to enhance image before processing.
    """
    # Ensure image is in correct format
    if len(image.shape) != 3 or image.shape[2] != 3:
        raise ValueError("Image must be a 3-channel BGR image.")
    
    # The 'enhanceForDetail' flag now controls the preprocessing pipeline.
    if enhanceForDetail:
        # Preprocess to improve consistency and enhance local contrast.
        image = white_balance_gray_world(image)
        image = apply_gamma_correction(image, gamma_value)
        image = apply_clahe_bgr(image)

    # All subsequent operations will use this (potentially enhanced) image as the source.
    original_input_image = image.copy()

    height, width, _ = image.shape

    # Ensure valid side_length and avoid impossible grid sizes
    side_length = max(8, int(side_length))
    max_side = max(8, min(width, height) // 2)
    if side_length > max_side:
        side_length = max(8, min(width, height) // 4)

    tri_height = max(4, int(side_length * math.sqrt(3) / 2))
    half_side = max(4, side_length // 2)

    # Calculate grid dimensions properly
    # Each horizontal step is half_side. A full triangle width is 2 * half_side.
    num_cols = max(1, (width // half_side) - 1)
    num_rows = max(1, height // tri_height)

    # Maintain the Pyraminx-structured layer approach for larger images,
    # but avoid dropping to zero rows on small inputs.
    if num_rows >= 3:
        num_rows = max(1, (num_rows // 3) * 3)

    num_cols = max(1, num_cols)
    num_rows = max(1, num_rows)

    new_width = (num_cols + 1) * half_side
    new_height = num_rows * tri_height
    
    # Precompute edges only if needed
    precomputed_edges = None
    if sampling_method == 'edge_aware':
        precomputed_edges = detect_edges_with_bilateral(original_input_image)

    # Crop to fit the calculated triangle grid precisely
    original_input_image = original_input_image[:new_height, :new_width]
    output = np.ones((new_height, new_width, 3), dtype=np.uint8) * 255

    # 1. Establish the Palette
    palette = get_pyraminx_palette() if use_pyraminx_colors else create_adaptive_palette(original_input_image, num_colors=palette_size, method=palette_method)

    # 2. Precompute edges for structural alignment (Rubik's "Shape" preservation)
    precomputed_edges = detect_edges_with_bilateral(original_input_image)
    
    # 3. Process each triangle to find the best representative color
    # If dithering is on, we use the source-quantized image for sampling context.
    source_quantized = quantize_image(original_input_image, palette, dither=use_dithering)

    for row in range(num_rows):
        for col in range(num_cols):
            x = col * half_side
            y = row * tri_height
            
            # Define triangle coordinates
            if (row + col) % 2 == 0:  # Upward
                pts = np.array([[x, y + tri_height], [x + half_side, y], [x + side_length, y + tri_height]], np.int32)
            else: # Downward
                pts = np.array([[x, y], [x + side_length, y], [x + half_side, y + tri_height]], np.int32)
            
            # Create a local mask for this specific triangle
            mask = np.zeros((new_height, new_width), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)
            
            # Select color based on edge-weighted sampling
            # This ensures object boundaries (the 'shape') are preserved.
            triangle_color = sample_triangle_color(
                source_quantized,
                mask,
                method=sampling_method,
                palette=palette,
                original_image=original_input_image,
                precomputed_edges=precomputed_edges
            )

            # Render triangle
            cv2.fillPoly(output, [pts], triangle_color)
            # Outline pieces to simulate the physical gaps in a Pyraminx mosaic
            cv2.polylines(output, [pts], isClosed=True, color=(0, 0, 0), thickness=1)

    return output


def segment_image_into_tiles(image_bgr, num_rows, num_cols):
    """Divide an image (BGR numpy array) into equal tiles (rows x cols). Returns list of RGB PIL Images."""
    height, width, _ = image_bgr.shape
    # Ensure divisibility by cropping to nearest divisible area
    tile_width = width // num_cols
    tile_height = height // num_rows
    new_width = tile_width * num_cols
    new_height = tile_height * num_rows
    image_bgr = image_bgr[:new_height, :new_width]

    tiles = []
    # Convert once to RGB for PIL usage
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    for r in range(num_rows):
        for c in range(num_cols):
            x0 = c * tile_width
            y0 = r * tile_height
            tile_np = image_rgb[y0:y0 + tile_height, x0:x0 + tile_width]
            tile_img = Image.fromarray(tile_np)
            tiles.append(tile_img)
    return tiles

def column_label_from_index(index):
    """Return Excel-style column label for zero-based index (0 -> A, 25 -> Z, 26 -> AA)."""
    if index < 0:
        return ""
    label_chars = []
    n = index
    while n >= 0:
        n, rem = divmod(n, 26)
        label_chars.append(chr(ord('A') + rem))
        n -= 1
    return ''.join(reversed(label_chars))

def load_reference_pdf_layout(reference_path):
    """Read first page size and margins from reference PDF if margins are encoded via mediabox/cropbox differences.
    Returns (page_width, page_height, margin_left, margin_top, margin_right, margin_bottom) in points.
    If margins are not derivable, defaults to zero margins and detected page size.
    """
    try:
        reader = PdfReader(reference_path)
        page = reader.pages[0]
        mediabox = page.mediabox
        cropbox = getattr(page, 'cropbox', None) or mediabox
        pw = float(mediabox.width)
        ph = float(mediabox.height)
        # Basic margin inference: margins = mediabox - cropbox
        ml = float(cropbox.left) - float(mediabox.left)
        mb = float(cropbox.bottom) - float(mediabox.bottom)
        mr = float(mediabox.right) - float(cropbox.right)
        mt = float(mediabox.top) - float(cropbox.top)
        # Clamp margins to >= 0
        ml = max(0.0, ml)
        mr = max(0.0, mr)
        mt = max(0.0, mt)
        mb = max(0.0, mb)
        return pw, ph, ml, mt, mr, mb
    except Exception:
        # Fallback to letter with zero margins
        pw, ph = letter
        return pw, ph, 0.0, 0.0, 0.0, 0.0

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
        palette_size = 4  # Strictly limited to 4 colors
        use_dithering = request.form.get('useDithering', 'false').lower() == 'true'
        sampling_method = request.form.get('samplingMethod', 'mode')  # default set to mode for reliability
        use_pyraminx_colors = True  # Strictly limited to Pyraminx colors
        palette_method = request.form.get('paletteMethod', 'kmeans_lab')  # kmeans, kmeans_lab, pyraminx
        gamma_value_raw = request.form.get('gamma', '')
        gamma_value = float(gamma_value_raw) if gamma_value_raw not in (None, '') else None
        enhanceForDetail = True  # Always enhance for detail by default

        if sampling_method not in ['mode', 'mean', 'center', 'edge_aware']:
            sampling_method = 'mode'
        if palette_method not in ['kmeans', 'kmeans_lab', 'pyraminx']:
            palette_method = 'kmeans_lab'

        side_length = max(8, side_length)

        # Save uploaded file
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        
        # Read image with robust fallback (EXIF orientation, uncommon modes)
        image = cv2.imread(file_path)
        if image is None:
            try:
                with Image.open(file_path) as pil_img:
                    pil_img = ImageOps.exif_transpose(pil_img).convert('RGB')
                    image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception:
                os.remove(file_path)
                return jsonify({'error': 'Error loading the image. Please check the file format and ensure it\'s a valid image file.'}), 400
        
        # Downscale very large images for performance, and allow small images by adapting triangle size later
        max_dim = 2000
        h0, w0 = image.shape[:2]
        if max(h0, w0) > max_dim:
            scale = max_dim / float(max(h0, w0))
            image = cv2.resize(image, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
        
        # Convert to BGR if needed (some formats might be RGB)
        if len(image.shape) == 3 and image.shape[2] == 3:
            # Image is already 3-channel, ensure it's BGR
            pass
        elif len(image.shape) == 2:
            # Grayscale image, convert to BGR
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            # Handle images with alpha channel by compositing on white
            if len(image.shape) == 3 and image.shape[2] == 4:
                bgr = image[:, :, :3]
                alpha = image[:, :, 3] / 255.0
                white_bg = np.ones_like(bgr) * 255
                image = (bgr.astype(np.float32) * alpha[..., None] + white_bg.astype(np.float32) * (1 - alpha[..., None])).astype(np.uint8)
            else:
                os.remove(file_path)
                return jsonify({'error': 'Unsupported image format. Please use RGB, BGR, or grayscale images.'}), 400
        
        # Adjust triangle size for very small images (guarantee at least some triangles)
        min_dim = min(image.shape[:2])
        max_allowed_side = max(8, min_dim // 2)
        if side_length > max_allowed_side:
            side_length = max(8, min_dim // 4)

        # Create mosaic
        mosaic = create_triangle_mosaic(
            image,
            side_length,
            palette_size=palette_size,
            use_dithering=use_dithering,
            sampling_method=sampling_method,
            use_pyraminx_colors=use_pyraminx_colors,
            palette_method=palette_method,
            gamma_value=gamma_value,
            enhanceForDetail=enhanceForDetail
        )

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

@app.route('/api/generate-mosaic-pdf', methods=['POST'])
def generate_mosaic_pdf():
    """Generate triangular mosaic and return a segmented PDF with equal tiles."""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400

        side_length = int(request.form.get('triangleSize', 20))
        num_rows = int(request.form.get('segmentsRows', 4))
        num_cols = int(request.form.get('segmentsCols', 4))
        
        # Get improved parameters with defaults
        palette_size = 4  # Strictly limited to 4 colors
        use_dithering = request.form.get('useDithering', 'false').lower() == 'true'
        sampling_method = request.form.get('samplingMethod', 'mode')
        use_pyraminx_colors = True  # Strictly limited to Pyraminx colors
        palette_method = request.form.get('paletteMethod', 'kmeans_lab')
        gamma_value_raw = request.form.get('gamma', '')
        gamma_value = float(gamma_value_raw) if gamma_value_raw not in (None, '') else None
        enhanceForDetail = True  # Always enhance for detail by default

        if num_rows < 1 or num_cols < 1:
            return jsonify({'error': 'segmentsRows and segmentsCols must be >= 1'}), 400
        
        if sampling_method not in ['mode', 'mean', 'center', 'edge_aware']:
            sampling_method = 'mode'
        if palette_method not in ['kmeans', 'kmeans_lab', 'pyraminx']:
            palette_method = 'kmeans_lab'

        side_length = max(8, side_length)

        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)

        # Read and process with enhanced validation and robust fallback
        image = cv2.imread(file_path)
        if image is None:
            try:
                with Image.open(file_path) as pil_img:
                    pil_img = ImageOps.exif_transpose(pil_img).convert('RGB')
                    image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception:
                os.remove(file_path)
                return jsonify({'error': 'Error loading the image. Please check the file format and ensure it\'s a valid image file.'}), 400
        
        # Downscale very large images for performance; small images are handled by adaptive triangle size
        max_dim = 2000
        h0, w0 = image.shape[:2]
        if max(h0, w0) > max_dim:
            scale = max_dim / float(max(h0, w0))
            image = cv2.resize(image, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
        
        # Convert to BGR if needed
        if len(image.shape) == 3 and image.shape[2] == 3:
            # Image is already 3-channel, ensure it's BGR
            pass
        elif len(image.shape) == 2:
            # Grayscale image, convert to BGR
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            # Handle images with alpha channel by compositing on white
            if len(image.shape) == 3 and image.shape[2] == 4:
                bgr = image[:, :, :3]
                alpha = image[:, :, 3] / 255.0
                white_bg = np.ones_like(bgr) * 255
                image = (bgr.astype(np.float32) * alpha[..., None] + white_bg.astype(np.float32) * (1 - alpha[..., None])).astype(np.uint8)
            else:
                os.remove(file_path)
                return jsonify({'error': 'Unsupported image format. Please use RGB, BGR, or grayscale images.'}), 400

        min_dim = min(image.shape[:2])
        max_allowed_side = max(8, min_dim // 2)
        if side_length > max_allowed_side:
            side_length = max(8, min_dim // 4)

        mosaic = create_triangle_mosaic(
            image,
            side_length,
            palette_size=palette_size,
            use_dithering=use_dithering,
            sampling_method=sampling_method,
            use_pyraminx_colors=use_pyraminx_colors,
            palette_method=palette_method,
            gamma_value=gamma_value,
            enhanceForDetail=enhanceForDetail
        )

        # Segment the mosaic
        tiles = segment_image_into_tiles(mosaic, num_rows, num_cols)
        if not tiles:
            os.remove(file_path)
            return jsonify({'error': 'Failed to segment image.'}), 500

        # Read layout from reference.pdf
        reference_path = os.path.join('.', 'reference.pdf')
        page_w, page_h, margin_l, margin_t, margin_r, margin_b = load_reference_pdf_layout(reference_path)

        # Calculate total pyraminx pieces needed
        # Count actual triangles created in the mosaic
        height, width, _ = mosaic.shape
        tri_height = int(side_length * math.sqrt(3) / 2)
        half_side = side_length // 2
        m_cols = int(width / half_side) - 1
        m_rows = height // tri_height
        total_triangles = m_cols * m_rows
        total_pyraminx_units = math.ceil(total_triangles / 9)
        
        pdf_bytes = BytesIO()
        c = canvas.Canvas(pdf_bytes, pagesize=(page_w, page_h))
        
        # PAGE 1: Grid layout with all segments (like reference)
        # Title at top
        c.setFont("Helvetica-Bold", 16)
        title = f"{total_triangles} triangles ({total_pyraminx_units} Pyraminx units)"
        title_width = c.stringWidth(title, "Helvetica-Bold", 16)
        title_x = (page_w - title_width) / 2
        c.drawString(title_x, page_h - 50, title)
        
        # Calculate grid layout
        grid_margin = 60  # Space for labels
        grid_w = page_w - 2 * grid_margin
        grid_h = page_h - 2 * grid_margin - 80  # Extra space for title
        
        # Calculate segment size
        seg_w = grid_w / num_cols
        seg_h = grid_h / num_rows
        
        # Draw column labels (A..Z, AA..ZZ, ...)
        c.setFont("Helvetica-Bold", 12)
        for col in range(num_cols):
            label = column_label_from_index(col)
            x = grid_margin + col * seg_w + seg_w / 2
            # Top labels
            label_width = c.stringWidth(label, "Helvetica-Bold", 12)
            c.drawString(x - label_width/2, page_h - grid_margin - 20, label)
            # Bottom labels
            c.drawString(x - label_width/2, grid_margin - 20, label)
        
        # Draw row labels (1, 2, 3, ...)
        for row in range(num_rows):
            label = str(num_rows - row)  # Count down from top
            y = grid_margin + row * seg_h + seg_h / 2
            # Left labels
            c.drawString(grid_margin - 20, y - 6, label)
            # Right labels
            c.drawString(page_w - grid_margin + 5, y - 6, label)
        
        # Draw segments in grid
        for idx, tile in enumerate(tiles):
            row = idx // num_cols
            col = idx % num_cols
            
            # Calculate position (top-left origin, convert to bottom-left)
            x = grid_margin + col * seg_w
            y = page_h - grid_margin - (row + 1) * seg_h
            
            # Scale tile to fit segment
            tw, th = tile.size
            scale = min(seg_w / tw, seg_h / th)
            draw_w = tw * scale
            draw_h = th * scale
            
            # Center within segment
            offset_x = (seg_w - draw_w) / 2
            offset_y = (seg_h - draw_h) / 2
            
            c.drawImage(ImageReader(tile), x + offset_x, y + offset_y, 
                       width=draw_w, height=draw_h)
            
            # Draw segment border
            c.setLineWidth(2)
            c.setStrokeColorRGB(0, 0, 0)
            c.rect(x, y, seg_w, seg_h, stroke=1, fill=0)
        
        c.showPage()  # End of page 1
        
        # PAGES 2+: Individual segments (original format)
        content_w = max(1.0, page_w - margin_l - margin_r)
        content_h = max(1.0, page_h - margin_t - margin_b)
        
        for tile in tiles:
            # Fit tile into content area with aspect-ratio preserved
            tw, th = tile.size
            scale = min(content_w / tw, content_h / th)
            draw_w = tw * scale
            draw_h = th * scale
            # Center within content area
            x = margin_l + (content_w - draw_w) / 2
            # Y from bottom considering bottom margin
            y = margin_b + (content_h - draw_h) / 2
            c.drawImage(ImageReader(tile), x, y, width=draw_w, height=draw_h)
            # Draw border around content area
            c.setLineWidth(1)
            c.setStrokeColorRGB(0, 0, 0)
            c.rect(margin_l, margin_b, content_w, content_h, stroke=1, fill=0)
            # Add page label (row-col)
            idx = tiles.index(tile)
            row = (idx // num_cols) + 1
            col = (idx % num_cols) + 1
            label = f"Segment {row}-{col}"
            c.setFont("Helvetica", 10)
            # Place label at bottom-left inside margin
            c.drawString(margin_l + 8, margin_b + 8, label)
            c.showPage()
        
        c.save()
        pdf_bytes.seek(0)

        # Cleanup
        os.remove(file_path)

        # Send as attachment
        return send_file(
            pdf_bytes,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='pyraminx-mosaic-segments.pdf'
        )
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