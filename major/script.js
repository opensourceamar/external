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
    const showGrid = document.getElementById('showGrid');
    const compareMode = document.getElementById('compareMode');
    const downloadBtn = document.getElementById('downloadBtn');
    const pdfBtn = document.getElementById('pdfBtn');
    const segmentsRows = document.getElementById('segmentsRows');
    const segmentsCols = document.getElementById('segmentsCols');
    const chooseBtn = document.getElementById('chooseBtn');

    let selectedFile = null;
    let lastGenerationResult = null;

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
            formData.append('usePyraminxColors', usePyraminxColors.checked);
            formData.append('paletteSize', paletteSize.value);

            const response = await fetch('/api/generate-mosaic', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                lastGenerationResult = result;
                mosaicImage.src = result.mosaicImage;
                displayResults(result);
                resultsSection.style.display = 'block';
                updateViewMode();
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
            const matchColor = result.coverage > 85 ? '#10b981' : (result.coverage > 70 ? '#f59e0b' : '#ef4444');
            const edgeColor = result.edge_similarity > 30 ? '#10b981' : (result.edge_similarity > 15 ? '#f59e0b' : '#ef4444');
            
            analysisStats.innerHTML = `
                <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
                    <div class="stat-card" style="border-left: 4px solid #3b82f6;">
                        <h5>Physical Pieces</h5>
                        <p><strong>${result.total_triangles}</strong> Triangles</p>
                        <p style="font-size: 0.85em; color: #666;">(${result.total_units} Units)</p>
                    </div>
                    <div class="stat-card" style="border-left: 4px solid ${matchColor};">
                        <h5>Color Fidelity</h5>
                        <p><strong>${result.coverage}%</strong> Match</p>
                        <div style="width: 100%; height: 6px; background: #eee; border-radius: 3px; margin-top: 5px; overflow: hidden;">
                            <div style="width: ${result.coverage}%; height: 100%; background: ${matchColor};"></div>
                        </div>
                    </div>
                    <div class="stat-card" style="border-left: 4px solid ${edgeColor};">
                        <h5>Edge Similarity</h5>
                        <p><strong>${result.edge_similarity}%</strong></p>
                        <div style="width: 100%; height: 6px; background: #eee; border-radius: 3px; margin-top: 5px; overflow: hidden;">
                            <div style="width: ${result.edge_similarity}%; height: 100%; background: ${edgeColor};"></div>
                        </div>
                    </div>
                    <div class="stat-card" style="border-left: 4px solid #6366f1;">
                        <h5>MSE</h5>
                        <p><strong>${result.mse.toFixed(1)}</strong></p>
                        <small style="color: #666;">Lower is better</small>
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
            formData.append('usePyraminxColors', usePyraminxColors.checked);
            formData.append('paletteSize', paletteSize.value);

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

    // Restoration of Preview Grid and Comparison logic
    function updateViewMode() {
        const mode = compareMode.value;
        const grid = document.querySelector('.results-grid');
        const cards = document.querySelectorAll('.result-card');
        const mosaicContainer = mosaicImage.parentElement;
        
        if (mode === 'side-by-side') {
            grid.style.display = 'grid';
            grid.style.gridTemplateColumns = '1fr 1fr';
            cards[0].style.display = 'block';
            mosaicImage.style.opacity = '1';
            mosaicContainer.style.background = 'none';
        } else if (mode === 'mosaic-only') {
            grid.style.display = 'block';
            cards[0].style.display = 'none';
            mosaicImage.style.opacity = '1';
            mosaicContainer.style.background = 'none';
        } else if (mode === 'overlay') {
            grid.style.display = 'block';
            cards[0].style.display = 'none';
            mosaicContainer.style.backgroundImage = `url(${originalImage.src})`;
            mosaicContainer.style.backgroundSize = 'contain';
            mosaicContainer.style.backgroundRepeat = 'no-repeat';
            mosaicImage.style.opacity = '0.5';
        }
        drawGridOverlay();
    }

    compareMode.addEventListener('change', updateViewMode);
    showGrid.addEventListener('change', drawGridOverlay);

    function drawGridOverlay() {
        const existingGrid = document.getElementById('previewGridCanvas');
        if (existingGrid) existingGrid.remove();
        if (!showGrid.checked || !lastGenerationResult) return;

        const canvas = document.createElement('canvas');
        canvas.id = 'previewGridCanvas';
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none';
        mosaicImage.parentElement.appendChild(canvas);

        canvas.width = mosaicImage.naturalWidth;
        canvas.height = mosaicImage.naturalHeight;
        const ctx = canvas.getContext('2d');
        const rows = parseInt(segmentsRows.value);
        const cols = parseInt(segmentsCols.value);
        
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.lineWidth = 2;
        const cellW = canvas.width / cols;
        const cellH = canvas.height / rows;

        for(let i=1; i<cols; i++) {
            ctx.beginPath(); ctx.moveTo(i * cellW, 0); ctx.lineTo(i * cellW, canvas.height); ctx.stroke();
        }
        for(let i=1; i<rows; i++) {
            ctx.beginPath(); ctx.moveTo(0, i * cellH); ctx.lineTo(canvas.width, i * cellH); ctx.stroke();
        }
    }

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
