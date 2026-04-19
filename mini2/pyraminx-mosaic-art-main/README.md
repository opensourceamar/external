# Pyraminx Mosaic Art Generator

## Abstract

The **Pyraminx Mosaic Art Generator** is an innovative web‑based application that converts digital images into mosaic artwork limited to the four colors of a Pyraminx puzzle cube by subdividing the image into triangles and mapping each region to its nearest perceptually accurate color using weighted distance algorithms in Lab space; it can produce segmented PDFs with labeled A–Z/1–n grids for physical assembly, offers customizable triangle sizes, optional dithering, and preprocessing (white balance, gamma) and is useful for creating physical Pyraminx art instructions, turning photographs into puzzle‑style mosaics, designing tessellation installations, or teaching color quantization and image processing concepts—all within a single cohesive tool.
The **Pyraminx Mosaic Art Generator** is an innovative web‑based application that converts digital images into mosaic artwork limited to the four colors of a Pyraminx puzzle cube by subdividing the image into triangles and mapping each region to its nearest perceptually accurate color using weighted distance algorithms in Lab space; it can produce segmented PDFs with labeled A–Z/1–n grids for physical assembly, offers customizable triangle sizes, optional dithering, and preprocessing (white balance, gamma) and is useful for creating physical Pyraminx art instructions, turning photographs into puzzle‑style mosaics, designing tessellation installations, or teaching color quantization and image processing concepts—all within a single cohesive tool. 

## Key Features

- **Simple Image Upload**: Drag & drop or click to upload images
- **Triangle Size Control**: Adjustable triangle size (10-50 pixels)
- **Pyraminx Color Palette**: Strictly limited to the 4 standard Pyraminx colors for authentic puzzle art.
- **Real-time Preview**: See both original and mosaic images
- **Download**: Save your generated mosaic

## How It Works

The application uses OpenCV to:
1. Divide the image into triangular regions
2. Calculate the average color of each triangle
3. Quantize colors to the nearest Pyraminx color using Lab color space
4. Generate a mosaic with alternating upward/downward triangles

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the backend server:**
   ```bash
   python backend.py
   ```

3. **Open your browser and go to:**
   ```
   http://localhost:5000
   ```

## Usage

1. **Upload an image** by dragging & dropping or clicking the upload area
2. **Adjust triangle size** using the slider (default: 20px). Use smaller sizes for "close-up" subjects.
3. **Click "Generate Mosaic"** to create your triangular mosaic. The system strictly uses the 4 standard Pyraminx colors and mandatory detail enhancement to ensure high-quality, recognizable art.
4. **(Optional)** specify the number of rows/columns for PDF segmentation
5. **Click "Download Segmented PDF"** to receive a multi‑page file. The first page shows the full mosaic with a labeled grid (A‑Z, 1‑n) that divides the artwork into equal sections, similar to a cube‑by‑cube breakdown. Subsequent pages contain each segment on its own sheet.
6. **Download** the mosaic image or PDF when complete

## Technical Contributions and Modifications

### 1. Geometric Coordinate Transformation
Implementation of a non-orthogonal tiling engine that calculates precise vertices for alternating upward/downward equilateral triangles, ensuring a continuous geometric mesh tailored for Pyraminx geometry.

### 2. Perceptual Color Optimization
Transition from RGB Euclidean distance to **weighted distance** in the **CIE Lab** color space. This modification ensures that color quantization accounts for human visual non-linearities by prioritizing luminance, preserving the "soul" of the image within a 4-color limit.

### 3. Edge-Aware Structural Sampling
Implementation of a **70/30 Edge-to-Center weighted sampling strategy**. By utilizing Canny edge detection, the system prioritizes the structural boundaries of the subject, preventing "feature wash" in low-resolution outputs.

### 4. Multi-Stage Signal Conditioning
Development of a preprocessing pipeline including **Gray-World White Balance**, **Gamma Correction**, and **CLAHE**. These stages standardize input lighting and enhance local contrast before the quantization process begins.

### 5. Bilateral Noise Suppression
Integration of bilateral filtering to reduce digital noise in homogeneous regions while maintaining the sharpness of high-frequency edges, providing a cleaner signal for structural analysis.

### 6. Modular Logistical Blueprinting
Creation of an automated workflow that generates segmented, coordinate-labeled (A-Z, 1-n) PDF manuals. This modification facilitates the modular physical assembly of large-scale mosaics.

### 7. Vectorized High-Resolution Processing
Refactoring of image processing primitives into vectorized matrix operations, enabling the efficient handling of high-resolution 4K images with minimal computational latency.

## Technical Details

- **Backend**: Flask API with OpenCV image processing
- **Frontend**: Vanilla JavaScript with drag & drop support
- **Image Processing**: OpenCV for triangle detection and color quantization
- **Color Space**: Lab color space for accurate color matching

## API Endpoints

- `POST /api/generate-mosaic`: Generate mosaic from uploaded image
- `GET /api/health`: Health check endpoint

## File Structure

```
pyraminx-mosaic-art-main/
├── backend.py          # Flask backend server
├── index.html          # Main HTML page
├── script.js           # Frontend JavaScript
├── style.css           # CSS styling
├── requirements.txt    # Python dependencies
├── uploads/           # Temporary file storage
```

## Troubleshooting

- **Image not loading**: Ensure the image format is supported (PNG, JPG, JPEG, GIF, BMP)
- **Mosaic not generating**: Check that the image is large enough for the selected triangle size
- **Server not starting**: Verify all dependencies are installed and port 5000 is available

## Dependencies

- Flask 3.0.0
- OpenCV 4.9.0.80
- NumPy 1.26.2
- Pillow 10.1.0
- Flask-CORS 4.0.0

## Extensions & Future Work

### Puzzle System Expansion

The application can be extended to support a wider variety of puzzle systems beyond the Pyraminx. Future versions could include Rubik's Cube support with 6-color mosaics and multiple size variants (2x2, 3x3, 4x4, etc.), allowing users to create mosaic designs that match the standard and advanced Rubik's cube configurations. Additionally, support for the Megaminx puzzle would introduce 12-color dodecahedral mosaic generation, opening possibilities for more detailed and colorful artwork. A custom puzzle palette feature would allow users to upload or define their own color palettes for different puzzle types, making the tool universally applicable to any colored puzzle system. Finally, implementing real-time 3D cube visualization would give users an interactive preview showing exactly how the generated mosaic would appear when assembled on the actual physical puzzle.

### Processing & Quality Enhancements

Advanced image preprocessing capabilities can significantly improve mosaic quality. An enhanced preprocessing pipeline could incorporate edge-aware filtering to preserve important image features and details, histogram equalization and adaptive contrast enhancement for better tonal distribution, and automatic image orientation detection and correction for consistent results. Integrating machine learning color matching through trained neural networks would enable more sophisticated perceptual color matching beyond traditional distance metrics. Batch processing functionality would allow users to process multiple images with consistent settings, while comprehensive preview modes would provide real-time live feedback as users adjust mosaic parameters.

### Output & Export Features

Expanding output options beyond PDF would make the project more versatile. The system could support multiple export formats including SVG for scalable vector graphics, EPS for professional printing, high-resolution PNG and TIFF formats for detailed work, and 3D model formats like STL and OBJ for 3D printing applications. Automated instruction generation would create step-by-step assembly guides complete with piece counts and color distribution maps, making it easier for users to physically construct their mosaics. Video export functionality could animate the mosaic construction process, and e-commerce integration would enable direct ordering of puzzle sets with customized mosaics from partner retailers.

### User Interface & Experience

The user experience can be substantially improved through several enhancements. A web-based real-time editor would enable drag-and-drop color adjustments, manual tile recoloring, and annotation tools for fine-tuning designs. Developing native iOS and Android mobile applications would bring mosaic generation to mobile devices, allowing on-the-go creation. Building a community platform featuring a gallery to share generated mosaics, discover popular designs, and access a template library would foster user engagement and creativity. Advanced control options would allow per-region color overrides, local area enhancement, and selective dithering for users seeking precise control over their artwork.

### Performance & Scalability

Infrastructure improvements would enable handling of larger workloads and more complex operations. GPU acceleration using CUDA and Metal support would significantly speed up processing on consumer hardware. Implementing Progressive Web App (PWA) technology would provide offline functionality through service workers, allowing users to generate mosaics without a constant internet connection. A cloud-based processing backend with job queues could handle extremely large images and complex computations. API rate limiting and intelligent caching strategies would optimize the server infrastructure for handling increased scale and concurrent users.

### Integration & Accessibility

Making the platform accessible to a broader audience requires focused development efforts. Social media integration would enable one-click sharing to Instagram, Pinterest, and Twitter, facilitating viral growth and community engagement. Comprehensive accessibility features including high contrast modes, screen reader support, and keyboard navigation would ensure the application is usable by people with disabilities. Multi-language support through internationalization would expand the user base globally. Finally, providing a robust RESTful API for third-party developers would enable integration into other applications and platforms, creating an ecosystem around the Pyraminx mosaic technology.
