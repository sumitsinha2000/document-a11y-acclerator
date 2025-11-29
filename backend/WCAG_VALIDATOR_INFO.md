# Built-in WCAG 2.1 and PDF/UA-1 Validator

## Overview

The Document A11y Accelerator includes a comprehensive built-in validator for WCAG 2.1 and PDF/UA-1 compliance. This validator is based on the algorithms from the veraPDF WCAG algorithms project (https://github.com/veraPDF/veraPDF-wcag-algs) and implements validation rules without requiring external dependencies.

## Features

### WCAG 2.1 Compliance Validation

The validator checks for compliance with WCAG 2.1 success criteria across all three levels:

- **Level A** (minimum accessibility)
- **Level AA** (recommended accessibility)
- **Level AAA** (enhanced accessibility)

Each issue includes:
- WCAG criterion reference (e.g., 1.1.1, 1.3.1, 2.4.2)
- Conformance level (A, AA, or AAA)
- Severity rating (high, medium, low)
- Detailed description
- Remediation recommendations

### PDF/UA-1 (ISO 14289-1) Validation

The validator checks for compliance with PDF/UA-1 technical requirements:

- Document structure and tagging
- Metadata requirements
- Reading order
- Alternative text
- Table structure
- Form field labels
- Annotation descriptions

Each issue includes:
- ISO 14289-1 clause reference
- Severity rating
- Detailed description
- Remediation recommendations

## Validation Checks

### 1. Document Structure (PDF/UA-1:7.1)

**What it checks:**
- Document is marked as tagged (MarkInfo.Marked = true)
- Structure tree root exists
- Structure elements use valid types

**Why it matters:**
- Tagged PDFs enable screen readers to understand document structure
- Structure tree defines the logical reading order
- Valid structure types ensure proper semantic meaning

**Common issues:**
- Document not marked as tagged
- Missing structure tree root
- Invalid or non-standard structure element types

### 2. Document Language (WCAG 3.1.1 - Level A)

**What it checks:**
- Lang entry exists in document catalog
- Language code is valid (ISO 639)

**Why it matters:**
- Screen readers need language information for proper pronunciation
- Required for WCAG Level A compliance

**Common issues:**
- Missing Lang entry
- Invalid language code
- Empty language string

### 3. Document Title (WCAG 2.4.2 - Level A)

**What it checks:**
- Title entry exists in document information dictionary
- Title is not empty

**Why it matters:**
- Helps users identify document content
- Required for WCAG Level A compliance
- Improves document organization

**Common issues:**
- Missing Title entry
- Empty title string

### 4. Link Purpose (WCAG 2.4.4 - Level AA)

**What it checks:**
- Each link annotation exposes descriptive text via the tagged content, `/Contents`, or `/Alt` attributes.
- Icon-only links also carry alternative descriptions so the destination is understandable.

**Why it matters:**
- Screen reader users rely on link names to identify destinations.
- Generic labels like "click here", "here", or "link" force users to guess the target.
- WCAG Level AA requires link purpose to be discernible in context.

**Common issues:**
- Link annotations without any visible text, `/Contents`, or `/Alt` descriptions.
- Links labeled "click here", "here", or "link" without surrounding context.
- Icon-only links that omit alternative or tooltip text.

### 5. Alternative Text (WCAG 1.1.1 - Level A)

**What it checks:**
- Images have Alt or ActualText attributes
- Figures have alternative descriptions

**Why it matters:**
- Screen reader users cannot see images
- Alt text provides equivalent information
- Required for WCAG Level A compliance

**Common issues:**
- Images without Alt text
- Empty Alt text strings
- Missing ActualText for complex content

### 6. Reading Order (WCAG 1.3.2 - Level A)

**What it checks:**
- Structure tree defines logical reading order
- Content sequence is meaningful

**Why it matters:**
- Screen readers follow structure tree order
- Logical sequence ensures comprehension
- Required for WCAG Level A compliance

**Common issues:**
- Missing structure tree
- Illogical content sequence

### 7. Table Structure (WCAG 1.3.1 - Level A)

**What it checks:**
- Tables have Table structure elements
- Table headers (TH elements) are present
- Table structure is properly marked up

**Why it matters:**
- Screen readers need table structure to navigate
- Headers define relationships between cells
- Required for WCAG Level A compliance

**Common issues:**
- Tables without TH elements
- Missing table structure markup
- Improper table hierarchy

### 8. Heading Hierarchy (WCAG 1.3.1 - Level A)

**What it checks:**
- Headings use H1-H6 structure elements
- Heading levels are sequential (no skipping)
- Heading hierarchy is logical

**Why it matters:**
- Screen readers use headings for navigation
- Logical hierarchy improves comprehension
- Required for WCAG Level A compliance

**Common issues:**
- Skipped heading levels (H1 to H3)
- Missing heading markup
- Illogical heading structure

### 9. List Structure (WCAG 1.3.1 - Level A)

**What it checks:**
- Lists have L structure elements
- List items (LI elements) are present
- List structure is properly marked up

**Why it matters:**
- Screen readers announce list structure
- Helps users understand content organization
- Required for WCAG Level A compliance

**Common issues:**
- Lists without LI elements
- Missing list structure markup

### 10. Form Fields (WCAG 3.3.2 - Level A)

**What it checks:**
- Form fields have labels (T entry)
- Field descriptions are present

**Why it matters:**
- Screen reader users need field labels
- Labels help users understand input requirements
- Required for WCAG Level A compliance

**Common issues:**
- Form fields without labels
- Empty label strings

### 11. Annotations (PDF/UA-1:7.18.1)

**What it checks:**
- Annotations have Contents entry (description)
- Tooltip text is present

**Why it matters:**
- Screen readers need annotation descriptions
- Tooltips provide context for interactive elements
- Required for PDF/UA-1 compliance

**Common issues:**
- Annotations without Contents
- Missing tooltip text

## Compliance Scoring

### WCAG Compliance Score (0-100%)

The validator calculates a WCAG compliance score based on:
- Total number of checks performed (15)
- Number of failed checks
- Score = (passed checks / total checks) × 100

### PDF/UA Compliance Score (0-100%)

The validator calculates a PDF/UA compliance score based on:
- Total number of checks performed (10)
- Number of failed checks
- Score = (passed checks / total checks) × 100

### Conformance Levels

**WCAG 2.1 Levels:**
- **Level A**: Minimum accessibility (must pass all Level A criteria)
- **Level AA**: Recommended accessibility (must pass all Level A and AA criteria)
- **Level AAA**: Enhanced accessibility (must pass all Level A, AA, and AAA criteria)

**PDF/UA-1:**
- Binary compliance (pass/fail)
- Must pass all required checks for compliance

## Integration

The validator is automatically used when analyzing PDFs if veraPDF is not available. It provides:

1. **Automatic Detection**: No configuration required
2. **Seamless Integration**: Works with existing analysis pipeline
3. **Comprehensive Results**: Detailed issue reports with remediation guidance
4. **Performance**: Fast validation without external process calls

## Comparison with veraPDF

| Feature | Built-in Validator | veraPDF CLI |
|---------|-------------------|-------------|
| **Setup** | No setup required | Requires Java + veraPDF installation |
| **Dependencies** | Python only (pikepdf) | Java Runtime + veraPDF |
| **Performance** | Fast (in-process) | Slower (subprocess calls) |
| **Accuracy** | Good (based on veraPDF algorithms) | Excellent (official validator) |
| **Customization** | Fully customizable | Limited |
| **Maintenance** | Easy | Requires external tool updates |

## Recommendations

1. **For most users**: Use the built-in validator (default)
   - No setup required
   - Fast and reliable
   - Covers all major WCAG 2.1 and PDF/UA-1 requirements

2. **For maximum accuracy**: Install veraPDF CLI (optional)
   - Official PDF Association validator
   - Most comprehensive validation
   - Industry standard

3. **For custom requirements**: Extend the built-in validator
   - Python source code is fully accessible
   - Add custom validation rules
   - Integrate with existing workflows

## Resources

- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [PDF/UA Standard (ISO 14289)](https://www.iso.org/standard/64599.html)
- [veraPDF WCAG Algorithms](https://github.com/veraPDF/veraPDF-wcag-algs)
- [Section 508 Standards](https://www.section508.gov/)
