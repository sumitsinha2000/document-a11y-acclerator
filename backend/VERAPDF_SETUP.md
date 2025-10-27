# veraPDF Integration Setup

This document explains how to install and configure veraPDF for WCAG 2.1 and PDF/UA compliance validation.

## What is veraPDF?

veraPDF is an open-source, industry-standard PDF validator that checks PDF documents for compliance with:
- **PDF/UA-1** (ISO 14289-1) - PDF accessibility standard
- **WCAG 2.1** - Web Content Accessibility Guidelines
- **Section 508** - U.S. federal accessibility requirements

## Prerequisites

**Java Required**: veraPDF is a Java application and requires Java Runtime Environment (JRE) 8 or higher.

### Check if Java is installed:
\`\`\`bash
java -version
\`\`\`

### Install Java if needed:
- **Windows**: Download from [java.com](https://www.java.com/) or use `winget install Oracle.JavaRuntimeEnvironment`
- **macOS**: `brew install openjdk` or download from [java.com](https://www.java.com/)
- **Linux**: `sudo apt install default-jre` (Ubuntu/Debian) or `sudo yum install java` (RHEL/CentOS)

## Installation

### Option 1: Download and Extract (Recommended for JAR usage)

1. Visit [https://verapdf.org/software/](https://verapdf.org/software/)
2. Download the **veraPDF Greenfield** installer for your OS
3. Extract/Install to a directory (e.g., `C:\veraPDF` on Windows)
4. The installation will contain:
   - `verapdf.jar` or `verapdf-gui.jar` - Main JAR file
   - `verapdf.bat` (Windows) or `verapdf` (Linux/Mac) - Wrapper scripts
   - Supporting libraries in `lib/` folder

### Option 2: Use Wrapper Scripts

If the installer creates wrapper scripts (`verapdf.bat` on Windows or `verapdf` on Linux/Mac):

1. Add the installation directory to your system PATH
2. The application will automatically detect and use the wrapper script

### Option 3: Direct JAR Usage

If you only have the JAR file:

1. Place `verapdf.jar` in a known location (e.g., `C:\veraPDF\verapdf.jar`)
2. Set the `VERAPDF_JAR` environment variable to point to the JAR file:
   \`\`\`bash
   # Windows (PowerShell)
   $env:VERAPDF_JAR = "C:\veraPDF\verapdf.jar"
   
   # Windows (Command Prompt)
   set VERAPDF_JAR=C:\veraPDF\verapdf.jar
   
   # Linux/Mac
   export VERAPDF_JAR=/path/to/verapdf.jar
   \`\`\`
3. The application will automatically detect and use the JAR file

## Verification

After installation, verify that veraPDF is accessible:

### If using wrapper script:
\`\`\`bash
verapdf --version
\`\`\`

### If using JAR directly:
\`\`\`bash
java -jar C:\path\to\verapdf.jar --version
\`\`\`

You should see output like:
\`\`\`
veraPDF 1.25.x (Greenfield)
\`\`\`

## How the Application Uses veraPDF

The Doc A11y Accelerator automatically detects veraPDF in the following order:

1. **Wrapper Script**: Looks for `verapdf` command in system PATH
2. **JAR File**: Searches common installation locations:
   - `C:\Program Files\veraPDF\verapdf.jar` (Windows)
   - `C:\veraPDF\verapdf.jar` (Windows)
   - `~/veraPDF/verapdf.jar` (Linux/Mac)
   - `/usr/local/verapdf/verapdf.jar` (Linux/Mac)
   - Path specified in `VERAPDF_JAR` environment variable
3. **Auto-discovery**: Searches current directory and subdirectories

When a JAR file is found, the application automatically runs it using:
\`\`\`bash
java -jar /path/to/verapdf.jar --format json --flavour ua1 document.pdf
\`\`\`

## Configuration

### Set Custom veraPDF Location

If veraPDF is installed in a non-standard location, set the environment variable:

\`\`\`bash
# Windows (PowerShell - add to your profile for persistence)
$env:VERAPDF_JAR = "D:\MyTools\veraPDF\verapdf.jar"

# Linux/Mac (add to ~/.bashrc or ~/.zshrc for persistence)
export VERAPDF_JAR="/opt/custom/verapdf/verapdf.jar"
\`\`\`

### Validation Timeout

Default timeout is 60 seconds. To change it, modify `verapdf_validator.py`:
\`\`\`python
timeout=120  # Increase to 120 seconds for large PDFs
\`\`\`

## Usage in Doc A11y Accelerator

Once veraPDF is installed and Java is available, the application will automatically:

1. Detect veraPDF on startup
2. Use it for enhanced accessibility validation
3. Provide detailed WCAG 2.1 and PDF/UA compliance reports
4. Map PDF/UA violations to specific WCAG success criteria

### What veraPDF Adds

1. **WCAG 2.1 Compliance Checking**
   - Validates against all WCAG 2.1 Level A and AA success criteria
   - Maps PDF/UA requirements to WCAG guidelines
   - Provides specific WCAG criterion references (e.g., 1.3.1, 2.4.2)

2. **PDF/UA Validation**
   - Checks document structure and tagging
   - Validates metadata requirements
   - Verifies reading order and semantic structure
   - Checks alternative text for images
   - Validates table structure and headers

3. **Section 508 Compliance**
   - PDF/UA compliance ensures Section 508 compliance
   - Validates technical standards for electronic content

### Validation Results

veraPDF validation results are integrated into the existing issue categories:

- **wcagIssues**: WCAG 2.1-specific violations with criterion references
- **pdfuaIssues**: PDF/UA-specific structural issues
- **structureIssues**: Enhanced structure and tagging problems
- **metadataIssues**: Document metadata requirements

Each issue includes:
- Severity level (high/medium/low)
- Specification reference (ISO 14289, WCAG 2.1)
- Clause number
- Detailed description
- Remediation recommendation
- WCAG criterion mapping (when applicable)

## Troubleshooting

### veraPDF Not Found

If you see `[VeraPDF] veraPDF not found`:

1. **Check Java installation**: Run `java -version`
2. **Verify JAR file location**: Ensure `verapdf.jar` exists in one of the expected locations
3. **Set VERAPDF_JAR**: Point to your JAR file location
4. **Check file permissions**: Ensure the JAR file is readable
5. **Restart application**: After setting environment variables

### Java Not Found

If you see `[VeraPDF] Java not found`:

1. Install Java Runtime Environment (JRE) 8 or higher
2. Verify installation: `java -version`
3. Add Java to system PATH if needed
4. Restart your terminal/command prompt

### Validation Timeout

If validation times out on large PDFs:

1. Increase timeout in `verapdf_validator.py`
2. Or process smaller page ranges
3. Or use a more powerful machine

### Permission Issues (Linux/macOS)

If you encounter permission errors:
\`\`\`bash
chmod +x /path/to/verapdf
# Or for JAR file
chmod +r /path/to/verapdf.jar
\`\`\`

## Benefits of veraPDF Integration

1. **Industry Standard**: veraPDF is the official PDF/A and PDF/UA validator
2. **Comprehensive**: Checks all machine-testable accessibility requirements
3. **Open Source**: Free and actively maintained
4. **Accurate**: Developed by the PDF Association
5. **Detailed Reports**: Provides specific clause references and remediation guidance
6. **WCAG Mapping**: Maps PDF/UA requirements to WCAG 2.1 success criteria

## Resources

- [veraPDF Official Website](https://verapdf.org/)
- [veraPDF Documentation](https://docs.verapdf.org/)
- [veraPDF GitHub](https://github.com/veraPDF)
- [PDF/UA Standard (ISO 14289)](https://www.iso.org/standard/64599.html)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Section 508 Standards](https://www.section508.gov/)

## Support

For issues with veraPDF integration:
1. Check the backend console logs for detailed error messages
2. Verify Java installation with `java -version`
3. Verify veraPDF JAR location
4. Check environment variables
5. Review the veraPDF documentation at https://docs.verapdf.org/
6. Report issues to the project repository
