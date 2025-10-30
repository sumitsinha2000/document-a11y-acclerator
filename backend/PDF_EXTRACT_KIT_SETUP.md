# PDF-Extract-Kit Integration Guide

PDF-Extract-Kit is not available via pip and requires manual setup. Follow these steps to integrate it:

## Prerequisites

- Python 3.10
- Conda (recommended)

## Installation Steps

1. **Create Conda Environment**

   \`\`\`bash
   conda create -n pdf-extract python=3.10
   conda activate pdf-extract
   \`\`\`

2. **Clone PDF-Extract-Kit Repository**

   \`\`\`bash
   git clone https://github.com/opendatalab/PDF-Extract-Kit.git
   cd PDF-Extract-Kit
   \`\`\`

3. **Install Dependencies**

   For GPU:

   \`\`\`bash
   pip install -r requirements.txt
   \`\`\`

   For CPU only:

   \`\`\`bash
   pip install -r requirements-cpu.txt
   \`\`\`

4. **Download Model Weights**

   From HuggingFace:

   \`\`\`python
   from huggingface_hub import snapshot_download
   snapshot_download(repo_id='opendatalab/pdf-extract-kit-1.0', local_dir='./', max_workers=20)
   \`\`\`

   Or from ModelScope:

   \`\`\`python
   from modelscope import snapshot_download
   snapshot_download('opendatalab/pdf-extract-kit-1.0', local_dir='./')
   \`\`\`

5. **Configure Python Path**

   Add PDF-Extract-Kit to your Python path:

   \`\`\`bash
   export PYTHONPATH="${PYTHONPATH}:/path/to/PDF-Extract-Kit"
   \`\`\`

   Or in your Python code:

   \`\`\`python
   import sys
   sys.path.insert(0, '/path/to/PDF-Extract-Kit')
   \`\`\`

6. **Verify Installation**

   Test the integration:

   \`\`\`python
   from pdf_extract_kit_processor import get_pdf_extract_kit
   
   processor = get_pdf_extract_kit()
   if processor.is_available():
       print("PDF-Extract-Kit is ready!")
   else:
       print("PDF-Extract-Kit not available, using fallback methods")
   \`\`\`

## Integration Status

The backend automatically detects PDF-Extract-Kit availability:

- **When Available**: Uses advanced analysis for better accuracy
  - Enhanced table structure detection
  - Accurate form field and label detection
  - Document structure analysis (headings, reading order)
  - Better image and alt text detection
  - Layout analysis and element positioning

- **When Not Available**: Falls back to PyPDF2 + pdfplumber
  - Basic metadata and structure checks
  - Simple table and image detection
  - Form field detection via annotations
  - Standard accessibility analysis

## Usage in Backend

The analyzer automatically uses PDF-Extract-Kit when available:

\`\`\`python
from pdf_analyzer import PDFAccessibilityAnalyzer

analyzer = PDFAccessibilityAnalyzer()
issues = analyzer.analyze('document.pdf')

# PDF-Extract-Kit is used automatically if available

# No code changes needed!

\`\`\`

## Features Enabled by PDF-Extract-Kit

1. **Advanced Table Analysis**
   - Detects table headers accurately
   - Extracts cell structure and relationships
   - Identifies complex table layouts

2. **Form Field Detection**
   - Accurate label-field associations
   - Detects unlabeled form fields
   - Analyzes form accessibility

3. **Document Structure**
   - Heading hierarchy detection
   - Reading order analysis
   - Paragraph and list identification

4. **Image Analysis**
   - Precise image location and sizing
   - Alt text presence detection
   - Image type classification

5. **Layout Analysis**
   - Multi-column detection
   - Element positioning
   - Visual hierarchy analysis

## Troubleshooting

### Import Errors

If you see "PDF-Extract-Kit not available":

1. Verify conda environment is activated
2. Check PYTHONPATH includes PDF-Extract-Kit directory
3. Ensure all dependencies are installed

### Model Loading Errors

If models fail to load:

1. Verify model weights are downloaded
2. Check available disk space (models are large)
3. Ensure correct model path configuration

### Performance Issues

For better performance:

1. Use GPU if available (much faster)
2. Process PDFs in batches
3. Consider caching results for large documents

## Documentation

- Full documentation: <https://pdf-extract-kit.readthedocs.io/>
- GitHub: <https://github.com/opendatalab/PDF-Extract-Kit>
- Model Hub: <https://huggingface.co/opendatalab/pdf-extract-kit-1.0>

## Current Status

✅ Integration code ready
✅ Automatic fallback implemented
✅ Enhanced analysis features available
⏳ Requires manual PDF-Extract-Kit installation

Once PDF-Extract-Kit is installed in your conda environment, the backend will automatically use it for enhanced PDF analysis!
