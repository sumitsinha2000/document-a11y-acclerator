# veraPDF Integration Setup

This document explains how to install and configure veraPDF for WCAG 2.1 and PDF/UA compliance validation.

## What is veraPDF?

veraPDF is an open-source, industry-standard PDF validator that checks PDF documents for compliance with:
- **PDF/UA-1** (ISO 14289-1) - PDF accessibility standard
- **WCAG 2.1** - Web Content Accessibility Guidelines
- **Section 508** - U.S. federal accessibility requirements

## Installation

### Option 1: Download Installer (Recommended)

1. Visit [https://verapdf.org/software/](https://verapdf.org/software/)
2. Download the installer for your operating system:
   - **Windows**: `verapdf-installer.exe`
   - **macOS**: `verapdf-installer.dmg`
   - **Linux**: `verapdf-installer.sh`
3. Run the installer and follow the prompts
4. Add veraPDF to your system PATH

### Option 2: Command Line Installation

#### Windows (using Chocolatey)
```powershell
choco install verapdf
