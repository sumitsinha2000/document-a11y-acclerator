"""
PDF Structure Standards and RoleMap Definitions
Based on ISO 32000-1 (PDF 1.7), ISO 14289-1 (PDF/UA-1), and ISO 14289-2 (PDF/UA-2)
Derived from veraPDF corpus analysis and Foxit PDF/UA-2 implementation
"""

# Standard PDF structure types as defined in ISO 32000-1:2008, 14.8.4
STANDARD_STRUCTURE_TYPES = {
    # Grouping elements
    'Document': 'Root element of document tag tree',
    'Part': 'Large division of document',
    'Art': 'Article - self-contained body of text',
    'Sect': 'Generic container, section of document',
    'Div': 'Generic block-level element',
    
    # Paragraph-like elements
    'BlockQuote': 'Block of quoted text',
    'Caption': 'Brief description of table or figure',
    'TOC': 'Table of contents',
    'TOCI': 'Individual TOC item',
    'Index': 'Index section',
    'NonStruct': 'Non-structural grouping',
    'Private': 'Private application data',
    
    # Heading elements
    'H': 'Generic heading',
    'H1': 'Level 1 heading',
    'H2': 'Level 2 heading',
    'H3': 'Level 3 heading',
    'H4': 'Level 4 heading',
    'H5': 'Level 5 heading',
    'H6': 'Level 6 heading',
    
    # Paragraph elements
    'P': 'Paragraph',
    
    # List elements
    'L': 'List',
    'LI': 'List item',
    'Lbl': 'List item label',
    'LBody': 'List item body',
    
    # Table elements
    'Table': 'Table',
    'TR': 'Table row',
    'TH': 'Table header cell',
    'TD': 'Table data cell',
    'THead': 'Table header row group',
    'TBody': 'Table body row group',
    'TFoot': 'Table footer row group',
    
    # Inline elements
    'Span': 'Generic inline element',
    'Quote': 'Inline quoted text',
    'Note': 'Footnote or endnote',
    'Reference': 'Citation reference',
    'BibEntry': 'Bibliography entry',
    'Code': 'Computer code',
    'Link': 'Hyperlink',
    'Annot': 'Annotation',
    
    # Ruby (East Asian typography)
    'Ruby': 'Ruby annotation',
    'RB': 'Ruby base text',
    'RT': 'Ruby annotation text',
    'RP': 'Ruby punctuation',
    
    # Warichu (East Asian typography)
    'Warichu': 'Warichu annotation',
    'WT': 'Warichu text',
    'WP': 'Warichu punctuation',
    
    # Illustration elements
    'Figure': 'Figure or image',
    'Formula': 'Mathematical formula',
    'Form': 'Form widget annotation'
}

# Common non-standard types and their standard mappings
# Based on veraPDF corpus analysis
COMMON_ROLEMAP_MAPPINGS = {
    # Annotation-related
    '/Annotation': '/Span',
    '/Annotations': '/Span',
    '/Comment': '/Note',
    '/Highlight': '/Span',
    '/Underline': '/Span',
    '/StrikeOut': '/Span',
    
    # Artifact-related
    '/Artifact': '/NonStruct',
    '/Artifacts': '/NonStruct',
    '/Background': '/NonStruct',
    '/Decoration': '/NonStruct',
    '/Watermark': '/NonStruct',
    '/PageNumber': '/NonStruct',
    '/Header': '/NonStruct',
    '/Footer': '/NonStruct',
    
    # Chart and diagram related
    '/Chart': '/Figure',
    '/Graph': '/Figure',
    '/Diagram': '/Figure',
    '/Illustration': '/Figure',
    '/Image': '/Figure',
    '/Photo': '/Figure',
    
    # Heading variants
    '/Heading': '/H',
    '/Subheading': '/H',
    '/Title': '/H1',
    '/Subtitle': '/H2',
    
    # Text variants
    '/Text': '/P',
    '/Paragraph': '/P',
    '/Body': '/P',
    '/Content': '/Div',
    
    # Table variants
    '/TableHeader': '/TH',
    '/TableData': '/TD',
    '/TableCell': '/TD',
    '/Row': '/TR',
    
    # List variants
    '/ListItem': '/LI',
    '/BulletList': '/L',
    '/NumberedList': '/L',
    
    # Section variants
    '/Section': '/Sect',
    '/Chapter': '/Part',
    '/Article': '/Art',
    
    # Form variants
    '/FormField': '/Form',
    '/TextField': '/Form',
    '/CheckBox': '/Form',
    '/RadioButton': '/Form',
    '/PushButton': '/Form',
    
    # PDF/UA-2 specific (MathML support)
    '/Math': '/Formula',
    '/Equation': '/Formula',
}

# PDF/UA-1 required attributes for structure elements
PDFUA_REQUIRED_ATTRIBUTES = {
    'Table': ['Summary'],  # Optional but recommended
    'TH': ['Scope'],  # Required for header cells
    'Figure': ['Alt'],  # Required alternative text
    'Formula': ['Alt'],  # Required alternative text
    'Form': ['TU'],  # Tooltip/label required
    'Link': ['Contents'],  # Link text required
    'Annot': ['Contents'],  # Annotation content required
}

# WCAG 2.1 Level A requirements mapping to PDF structure
WCAG_PDF_REQUIREMENTS = {
    '1.1.1': {  # Non-text Content
        'elements': ['Figure', 'Formula', 'Form'],
        'requirement': 'Alternative text required',
        'attribute': 'Alt'
    },
    '1.3.1': {  # Info and Relationships
        'elements': ['Table', 'L', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6'],
        'requirement': 'Proper structure and relationships',
        'attribute': 'Structure'
    },
    '1.3.2': {  # Meaningful Sequence
        'elements': ['Document'],
        'requirement': 'Logical reading order',
        'attribute': 'ReadingOrder'
    },
    '2.4.1': {  # Bypass Blocks
        'elements': ['Document'],
        'requirement': 'Bookmarks or structure for navigation',
        'attribute': 'Outlines'
    },
    '2.4.2': {  # Page Titled
        'elements': ['Document'],
        'requirement': 'Document title in metadata',
        'attribute': 'Title'
    },
    '3.1.1': {  # Language of Page
        'elements': ['Document'],
        'requirement': 'Document language specified',
        'attribute': 'Lang'
    },
    '4.1.2': {  # Name, Role, Value
        'elements': ['Form', 'Link', 'Annot'],
        'requirement': 'Accessible name and role',
        'attribute': 'TU'
    }
}

def get_standard_mapping(custom_type: str) -> str:
    """
    Get the standard structure type mapping for a custom type
    
    Args:
        custom_type: Custom structure type (e.g., '/Annotation')
        
    Returns:
        Standard structure type (e.g., '/Span')
    """
    # Ensure type starts with /
    if not custom_type.startswith('/'):
        custom_type = f'/{custom_type}'
    
    return COMMON_ROLEMAP_MAPPINGS.get(custom_type, '/Div')

def is_standard_type(structure_type: str) -> bool:
    """
    Check if a structure type is a standard PDF type
    
    Args:
        structure_type: Structure type to check
        
    Returns:
        True if standard, False otherwise
    """
    # Remove leading / if present
    clean_type = structure_type.lstrip('/')
    return clean_type in STANDARD_STRUCTURE_TYPES

def get_required_attributes(structure_type: str) -> list:
    """
    Get required attributes for a structure type per PDF/UA
    
    Args:
        structure_type: Structure type
        
    Returns:
        List of required attribute names
    """
    clean_type = structure_type.lstrip('/')
    return PDFUA_REQUIRED_ATTRIBUTES.get(clean_type, [])

def validate_structure_tree(struct_tree_root) -> dict:
    """
    Validate structure tree compliance with PDF/UA
    
    Args:
        struct_tree_root: StructTreeRoot dictionary from PDF
        
    Returns:
        Dictionary with validation results
    """
    issues = []
    warnings = []
    
    # Check if RoleMap exists
    if not hasattr(struct_tree_root, 'RoleMap'):
        warnings.append('No RoleMap found - custom structure types may not be mapped')
    
    # Check if ParentTree exists (required for tagged content)
    if not hasattr(struct_tree_root, 'ParentTree'):
        issues.append('ParentTree missing - required for tagged content')
    
    # Check if structure tree has children
    if not hasattr(struct_tree_root, 'K') or len(struct_tree_root.K) == 0:
        issues.append('Structure tree has no children - document not properly tagged')
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings
    }
