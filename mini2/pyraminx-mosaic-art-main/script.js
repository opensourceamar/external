// Pyraminx Mosaic Art - Frontend JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    const uploadArea = document.getElementById('uploadArea');
    const imageInput = document.getElementById('imageInput');
    const generateBtn = document.getElementById('generateBtn');
    const resultsSection = document.getElementById('resultsSection');
    const loading = document.getElementById('loading');
    const originalImage = document.getElementById('originalImage');
    const mosaicImage = document.getElementById('mosaicImage');
    const triangleSize = document.getElementById('triangleSize');
    const triangleSizeValue = document.getElementById('triangleSizeValue');
    // Advanced settings for animal images
    const enhanceForDetail = document.getElementById('enhanceForDetail');
    const samplingMethod = document.getElementById('samplingMethod');
    const paletteMethod = document.getElementById('paletteMethod');
    const useDithering = document.getElementById('useDithering');
    // new controls
    const usePyraminxColors = document.getElementById('usePyraminxColors');
    const paletteSize = document.getElementById('paletteSize');
    const paletteSizeValue = document.getElementById('paletteSizeValue');
    // Coverage preview removed — no DOM elements for stats anymore
    const downloadBtn = document.getElementById('downloadBtn');
    const pdfBtn = document.getElementById('pdfBtn');
    const segmentsRows = document.getElementById('segmentsRows');
    const segmentsCols = document.getElementById('segmentsCols');
    // Removed on-screen grid overlay; grid will only appear in exported PDF
    const chooseBtn = document.getElementById('chooseBtn');
    // comparison UI removed; preview shows coverage and piece count only

    let selectedFile = null;

    // Update triangle size display
    triangleSize.addEventListener('input', function() {
        triangleSizeValue.textContent = this.value;
    });
    // Update palette size display
    if (paletteSize) {
        paletteSize.value = 4;
        paletteSizeValue.textContent = "4";
        paletteSize.addEventListener('input', function() {
            paletteSizeValue.textContent = this.value;
        });
    }

    // Default "Enhance for Detail" to ON as requested
    if (enhanceForDetail) enhanceForDetail.checked = true;
    
    // Default to strict Pyraminx colors
    if (usePyraminxColors) usePyraminxColors.checked = true;
    if (useDithering) useDithering.checked = true; // Better for close-ups

    // File upload handling - simplified
    function triggerFileInput() {
        imageInput.value = ''; // Reset to allow selecting same file again
        imageInput.click();
    }
    
    // Click handlers
    uploadArea.addEventListener('click', triggerFileInput);
    if (chooseBtn) {
        chooseBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            triggerFileInput();
        });
    }
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    imageInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });


    function handleFileSelect(file) {
        console.log('File selected:', file.name, file.type, file.size);
        
        if (!file) {
            console.log('No file selected');
            return;
        }
        
        if (!file.type.startsWith('image/')) {
            alert('Please select an image file (PNG, JPG, JPEG, GIF, BMP).');
            return;
        }

        // Check file size (limit to 10MB)
        if (file.size > 10 * 1024 * 1024) {
            alert('File is too large. Please select an image smaller than 10MB.');
            return;
        }

        selectedFile = file;
        displayOriginalImage(file);
        generateBtn.disabled = false;
        pdfBtn.disabled = false;
        resultsSection.style.display = 'none';
        
        // Update upload area to show file is selected
        const uploadContent = document.querySelector('.upload-content');
        uploadContent.innerHTML = `
            <div class="upload-icon">✅</div>
            <h3>File Selected: ${file.name}</h3>
            <p>Click "Generate Mosaic" to create your triangular mosaic art</p>
            <button class="upload-btn" id="chooseBtn" type="button">
                Choose Different File
            </button>
        `;
        
        // Re-attach event listener for the new button
        const newChooseBtn = document.getElementById('chooseBtn');
        if (newChooseBtn) {
            newChooseBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                triggerFileInput();
            });
        }
        
        console.log('File successfully loaded:', file.name);
    }

    function displayOriginalImage(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            originalImage.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }

    // Generate mosaic
    generateBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        loading.style.display = 'block';
        generateBtn.disabled = true;

        try {
            const formData = new FormData();
            formData.append('image', selectedFile);
            formData.append('triangleSize', triangleSize.value);
            
            // Add advanced settings
            formData.append('enhanceForDetail', enhanceForDetail.checked);
            formData.append('samplingMethod', samplingMethod.value);
            formData.append('paletteMethod', paletteMethod.value);
            formData.append('useDithering', useDithering.checked);
            // pyraminx options
            formData.append('usePyraminxColors', 'true');
            formData.append('paletteSize', '4');

            const response = await fetch('/api/generate-mosaic', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                mosaicImage.src = result.mosaicImage;
                displayResults(result);
                resultsSection.style.display = 'block';
            } else {
                alert('Error: ' + result.error);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to generate mosaic. Please try again.');
        } finally {
            loading.style.display = 'none';
            generateBtn.disabled = false;
        }
    });

    function displayResults(result) {
        const analysisStats = document.getElementById('analysisStats');
        if (analysisStats) {
            analysisStats.innerHTML = `
                <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 1rem;">
                    <div class="stat-card" style="border-left: 4px solid #3b82f6;">
                        <h5>Physical Pieces</h5>
                        <p><strong>${result.total_triangles}</strong> Triangles</p>
                        <p style="font-size: 0.85em; color: #666;">(${result.total_units} Pyraminx Units)</p>
                    </div>
                </div>
            `;
        }
    }

    // Download functionality
    downloadBtn.addEventListener('click', () => {
        if (mosaicImage.src) {
            const link = document.createElement('a');
            link.download = 'pyraminx-mosaic.png';
            link.href = mosaicImage.src;
            link.click();
        }
    });

    // PDF generation (segmented)
    pdfBtn.addEventListener('click', async () => {
        if (!selectedFile) return;
        loading.style.display = 'block';
        pdfBtn.disabled = true;
        try {
            const formData = new FormData();
            formData.append('image', selectedFile);
            formData.append('triangleSize', triangleSize.value);
            formData.append('segmentsRows', segmentsRows.value);
            formData.append('segmentsCols', segmentsCols.value);
            
            // Add advanced settings
            formData.append('enhanceForDetail', enhanceForDetail.checked);
            formData.append('samplingMethod', samplingMethod.value);
            formData.append('paletteMethod', paletteMethod.value);
            formData.append('useDithering', useDithering.checked);
            // pyraminx options
            formData.append('usePyraminxColors', 'true');
            formData.append('paletteSize', '4');

            const response = await fetch('/api/generate-mosaic-pdf', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || 'Failed to generate PDF');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'pyraminx-mosaic-segments.pdf';
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('PDF error:', error);
            alert('Failed to generate PDF: ' + error.message);
        } finally {
            loading.style.display = 'none';
            pdfBtn.disabled = false;
        }
    });

    // Removed grid overlay drawing and listeners

    // Health check on page load
    async function checkBackendHealth() {
        try {
            const response = await fetch('/api/health');
            const result = await response.json();
            console.log('Backend status:', result);
        } catch (error) {
            console.error('Backend not responding:', error);
            alert('Warning: Backend server is not responding. Please make sure the Python server is running.');
        }
    }

    // Comparison toggle removed

    // Check backend health when page loads
    checkBackendHealth();
});
