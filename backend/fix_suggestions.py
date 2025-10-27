"""
Standalone fix suggestions generator that doesn't require pikepdf.
Generates fix suggestions based on detected issues without actually modifying PDFs.
"""

def generate_fix_suggestions(issues):
    """
    Generate fix suggestions based on detected accessibility issues.
    
    Args:
        issues: Dictionary of detected issues by category
        
    Returns:
        Dictionary with automated, semiAutomated, manual fixes and estimated time
    """
    automated = []
    semi_automated = []
    manual = []
    estimated_time = 0
    
    if issues.get("wcagIssues") and len(issues["wcagIssues"]) > 0:
        for issue in issues["wcagIssues"]:
            severity = issue.get("severity", "high")
            description = issue.get("description", "")
            
            # Determine if fix can be automated based on issue description
            if "metadata" in description.lower() or "title" in description.lower():
                automated.append({
                    "id": f"wcag-metadata-{issue.get('criterion', 'unknown')}",
                    "title": "Fix WCAG metadata issue",
                    "description": description,
                    "action": "Add document metadata and title",
                    "severity": severity,
                    "estimatedTime": 1,
                    "category": "wcagIssues",
                    "criterion": issue.get("criterion", ""),
                    "location": {"criterion": issue.get("criterion", "")}
                })
                estimated_time += 1
            elif "reading order" in description.lower():
                manual.append({
                    "id": f"wcag-reading-order-{issue.get('criterion', 'unknown')}",
                    "title": "Fix reading order",
                    "description": description,
                    "action": "Define proper reading order",
                    "severity": severity,
                    "estimatedTime": 20,
                    "category": "wcagIssues",
                    "criterion": issue.get("criterion", ""),
                    "location": {"criterion": issue.get("criterion", "")},
                    "instructions": "Use PDF editor to create structure tree and define reading order"
                })
                estimated_time += 20
            else:
                # Default to semi-automated for other WCAG issues
                semi_automated.append({
                    "id": f"wcag-{issue.get('criterion', 'unknown')}",
                    "title": f"Fix WCAG {issue.get('criterion', '')} issue",
                    "description": description,
                    "action": issue.get("remediation", "Review and fix WCAG compliance issue"),
                    "severity": severity,
                    "estimatedTime": 10,
                    "category": "wcagIssues",
                    "criterion": issue.get("criterion", ""),
                    "location": {"clause": issue.get("clause", "")}
                })
                estimated_time += 10
    
    if issues.get("pdfuaIssues") and len(issues["pdfuaIssues"]) > 0:
        for issue in issues["pdfuaIssues"]:
            severity = issue.get("severity", "high")
            description = issue.get("description", "")
            
            # Determine if fix can be automated based on issue description
            if any(keyword in description.lower() for keyword in ["metadata stream", "viewerpreferences", "dc:title", "suspects"]):
                automated.append({
                    "id": f"pdfua-{issue.get('clause', 'unknown')}",
                    "title": "Fix PDF/UA structure issue",
                    "description": description,
                    "action": "Add required PDF/UA metadata and structure",
                    "severity": severity,
                    "estimatedTime": 1,
                    "category": "pdfuaIssues",
                    "clause": issue.get("clause", ""),
                    "location": {"clause": issue.get("clause", "")}
                })
                estimated_time += 1
            elif "structure tree" in description.lower() and "no children" in description.lower():
                automated.append({
                    "id": f"pdfua-structure-tree-{issue.get('clause', 'unknown')}",
                    "title": "Create structure tree",
                    "description": description,
                    "action": "Create structure tree with Document element",
                    "severity": severity,
                    "estimatedTime": 1,
                    "category": "pdfuaIssues",
                    "clause": issue.get("clause", ""),
                    "location": {"clause": issue.get("clause", "")}
                })
                estimated_time += 1
            else:
                # Default to semi-automated for other PDF/UA issues
                semi_automated.append({
                    "id": f"pdfua-{issue.get('clause', 'unknown')}",
                    "title": f"Fix PDF/UA {issue.get('clause', '')} issue",
                    "description": description,
                    "action": issue.get("remediation", "Review and fix PDF/UA compliance issue"),
                    "severity": severity,
                    "estimatedTime": 10,
                    "category": "pdfuaIssues",
                    "clause": issue.get("clause", ""),
                    "location": {"clause": issue.get("clause", "")}
                })
                estimated_time += 10
    
    # Automated fixes (can be applied programmatically)
    if issues.get("missingMetadata") and len(issues["missingMetadata"]) > 0:
        for issue in issues["missingMetadata"]:
            automated.append({
                "id": f"add-metadata-{issue.get('page', 1)}",
                "title": "Add default metadata",
                "description": issue.get("description", "Automatically add document title and basic metadata"),
                "action": f"Add {issue.get('description', 'metadata')}",
                "severity": issue.get("severity", "high"),
                "estimatedTime": 1,
                "category": "metadata",
                "page": issue.get("page", 1),
                "location": {"page": issue.get("page", 1)}
            })
        estimated_time += len(issues["missingMetadata"])
    
    if issues.get("missingLanguage") and len(issues["missingLanguage"]) > 0:
        for issue in issues["missingLanguage"]:
            automated.append({
                "id": "set-language",
                "title": "Set document language",
                "description": issue.get("description", "Automatically set document language to English (en-US)"),
                "action": "Set document language to English",
                "severity": issue.get("severity", "medium"),
                "estimatedTime": 1,
                "category": "language",
                "page": issue.get("page", 1),
                "location": {"page": issue.get("page", 1)}
            })
        estimated_time += 1
    
    # Semi-automated fixes (require some user input)
    if issues.get("missingAltText") and len(issues["missingAltText"]) > 0:
        for issue in issues["missingAltText"]:
            pages = issue.get("pages", [1])
            semi_automated.append({
                "id": "add-alt-text",
                "title": "Add alternative text to images",
                "description": issue.get("description", f"Add descriptive alt text to {issue.get('count', 1)} image(s)"),
                "action": f"Add alt text to {issue.get('count', 1)} image(s)",
                "severity": issue.get("severity", "high"),
                "estimatedTime": issue.get("count", 1) * 2,
                "category": "images",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages, "count": issue.get("count", 1)}
            })
        estimated_time += sum(issue.get("count", 1) * 2 for issue in issues["missingAltText"])
    
    if issues.get("formIssues") and len(issues["formIssues"]) > 0:
        for issue in issues["formIssues"]:
            pages = issue.get("pages", [1])
            semi_automated.append({
                "id": "fix-forms",
                "title": "Add form field labels",
                "description": issue.get("description", f"Add labels and descriptions to {issue.get('count', 1)} form field(s)"),
                "action": f"Add labels to {issue.get('count', 1)} form field(s)",
                "severity": issue.get("severity", "high"),
                "estimatedTime": issue.get("count", 1) * 3,
                "category": "forms",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages, "count": issue.get("count", 1)}
            })
        estimated_time += sum(issue.get("count", 1) * 3 for issue in issues["formIssues"])
    
    # Manual fixes (require manual intervention)
    if issues.get("untaggedContent") and len(issues["untaggedContent"]) > 0:
        for issue in issues["untaggedContent"]:
            pages = issue.get("pages", [1])
            manual.append({
                "id": "tag-content",
                "title": "Tag content structure",
                "description": issue.get("description", "Manually tag content with semantic structure using PDF editor"),
                "action": "Tag document structure",
                "severity": issue.get("severity", "high"),
                "estimatedTime": 30,
                "category": "structure",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages},
                "instructions": "Use Adobe Acrobat or similar tool to add proper heading tags, paragraph tags, and list structures"
            })
        estimated_time += 30
    
    if issues.get("tableIssues") and len(issues["tableIssues"]) > 0:
        for issue in issues["tableIssues"]:
            pages = issue.get("pages", [1])
            manual.append({
                "id": "fix-tables",
                "title": "Fix table structure",
                "description": issue.get("description", f"Add proper table headers and markup for {issue.get('count', 1)} table(s)"),
                "action": f"Fix {issue.get('count', 1)} table(s) structure",
                "severity": issue.get("severity", "high"),
                "estimatedTime": issue.get("count", 1) * 20,
                "category": "tables",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages, "count": issue.get("count", 1)},
                "instructions": "Use PDF editor to define table headers, data cells, and proper table structure"
            })
        estimated_time += sum(issue.get("count", 1) * 20 for issue in issues["tableIssues"])
    
    if issues.get("poorContrast") and len(issues["poorContrast"]) > 0:
        for issue in issues["poorContrast"]:
            pages = issue.get("pages", [1])
            manual.append({
                "id": "fix-contrast",
                "title": "Improve color contrast",
                "description": issue.get("description", f"Adjust colors to meet WCAG contrast requirements for {issue.get('count', 1)} element(s)"),
                "action": f"Fix contrast for {issue.get('count', 1)} element(s)",
                "severity": issue.get("severity", "medium"),
                "estimatedTime": issue.get("count", 1) * 5,
                "category": "color",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages, "count": issue.get("count", 1)},
                "instructions": "Modify text and background colors to achieve at least 4.5:1 contrast ratio"
            })
        estimated_time += sum(issue.get("count", 1) * 5 for issue in issues["poorContrast"])
    
    if issues.get("structureIssues") and len(issues["structureIssues"]) > 0:
        for issue in issues["structureIssues"]:
            pages = issue.get("pages", [1])
            manual.append({
                "id": "fix-structure",
                "title": "Fix document structure",
                "description": issue.get("description", "Add proper heading hierarchy and document structure"),
                "action": "Fix document structure",
                "severity": issue.get("severity", "high"),
                "estimatedTime": 40,
                "category": "structure",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages},
                "instructions": "Ensure proper heading levels (H1, H2, H3) and logical document structure"
            })
        estimated_time += 40
    
    if issues.get("readingOrderIssues") and len(issues["readingOrderIssues"]) > 0:
        for issue in issues["readingOrderIssues"]:
            pages = issue.get("pages", [1])
            manual.append({
                "id": "fix-reading-order",
                "title": "Correct reading order",
                "description": issue.get("description", "Adjust content reading order for screen readers"),
                "action": "Fix reading order",
                "severity": issue.get("severity", "medium"),
                "estimatedTime": 20,
                "category": "structure",
                "page": pages[0] if pages else 1,
                "pages": pages,
                "location": {"pages": pages},
                "instructions": "Use PDF editor to reorder content elements for logical reading flow"
            })
        estimated_time += 20
    
    return {
        "automated": automated,
        "semiAutomated": semi_automated,
        "manual": manual,
        "estimatedTime": estimated_time
    }
