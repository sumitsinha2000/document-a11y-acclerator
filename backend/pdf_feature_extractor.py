"""
PDF Feature Extraction Module
Inspired by veraPDF's pdfbox-feature-reporting
Extracts detailed PDF features for comprehensive analysis
"""

import logging
from typing import Dict, List, Any
from pikepdf import Pdf, PdfError, Name, Dictionary, Array
from collections import defaultdict

logger = logging.getLogger(__name__)

class PDFFeatureExtractor:
    """Extract detailed features from PDF documents"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.pdf = None
        
    def extract_all_features(self) -> Dict[str, Any]:
        """Extract all PDF features"""
        try:
            with Pdf.open(self.pdf_path) as pdf:
                self.pdf = pdf
                
                features = {
                    'fonts': self._extract_font_features(),
                    'images': self._extract_image_features(),
                    'colorSpaces': self._extract_colorspace_features(),
                    'annotations': self._extract_annotation_features(),
                    'embeddedFiles': self._extract_embedded_files(),
                    'formFields': self._extract_form_features(),
                    'metadata': self._extract_metadata_features(),
                    'structure': self._extract_structure_features(),
                    'pages': self._extract_page_features(),
                }
                
                logger.info(f"Extracted features from {self.pdf_path}")
                return features
                
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            return {}
    
    def _extract_font_features(self) -> List[Dict[str, Any]]:
        """Extract font information from PDF"""
        fonts = []
        
        try:
            for page_num, page in enumerate(self.pdf.pages, 1):
                if '/Resources' in page and '/Font' in page.Resources:
                    font_dict = page.Resources.Font
                    
                    for font_name, font_obj in font_dict.items():
                        font_info = {
                            'name': str(font_name),
                            'page': page_num,
                            'type': str(font_obj.get('/Subtype', 'Unknown')),
                            'baseFont': str(font_obj.get('/BaseFont', 'Unknown')),
                            'embedded': self._is_font_embedded(font_obj),
                            'encoding': str(font_obj.get('/Encoding', 'Unknown')),
                        }
                        
                        # Check for ToUnicode mapping
                        if '/ToUnicode' in font_obj:
                            font_info['hasToUnicode'] = True
                        
                        fonts.append(font_info)
                        
        except Exception as e:
            logger.error(f"Error extracting fonts: {e}")
            
        return fonts
    
    def _is_font_embedded(self, font_obj) -> bool:
        """Check if font is embedded"""
        try:
            # Check for font descriptor
            if '/FontDescriptor' in font_obj:
                descriptor = font_obj.FontDescriptor
                # Check for embedded font streams
                if any(key in descriptor for key in ['/FontFile', '/FontFile2', '/FontFile3']):
                    return True
            return False
        except:
            return False
    
    def _extract_image_features(self) -> List[Dict[str, Any]]:
        """Extract image information from PDF"""
        images = []
        
        try:
            for page_num, page in enumerate(self.pdf.pages, 1):
                if '/Resources' in page and '/XObject' in page.Resources:
                    xobjects = page.Resources.XObject
                    
                    for name, obj in xobjects.items():
                        if obj.get('/Subtype') == '/Image':
                            image_info = {
                                'name': str(name),
                                'page': page_num,
                                'width': int(obj.get('/Width', 0)),
                                'height': int(obj.get('/Height', 0)),
                                'colorSpace': str(obj.get('/ColorSpace', 'Unknown')),
                                'bitsPerComponent': int(obj.get('/BitsPerComponent', 0)),
                                'filter': str(obj.get('/Filter', 'None')),
                            }
                            
                            # Check for alternate text
                            if '/Alt' in obj:
                                image_info['hasAltText'] = True
                                
                            images.append(image_info)
                            
        except Exception as e:
            logger.error(f"Error extracting images: {e}")
            
        return images
    
    def _extract_colorspace_features(self) -> Dict[str, Any]:
        """Extract color space information"""
        colorspaces = {
            'outputIntent': None,
            'usedColorSpaces': set(),
            'iccProfiles': []
        }
        
        try:
            # Check for OutputIntent
            if '/OutputIntents' in self.pdf.Root:
                output_intents = self.pdf.Root.OutputIntents
                if output_intents:
                    intent = output_intents[0]
                    colorspaces['outputIntent'] = {
                        'type': str(intent.get('/S', 'Unknown')),
                        'identifier': str(intent.get('/OutputConditionIdentifier', 'Unknown')),
                        'info': str(intent.get('/Info', '')),
                    }
            
            # Collect used color spaces
            for page in self.pdf.pages:
                if '/Resources' in page and '/ColorSpace' in page.Resources:
                    cs_dict = page.Resources.ColorSpace
                    for cs_name in cs_dict.keys():
                        colorspaces['usedColorSpaces'].add(str(cs_name))
                        
            colorspaces['usedColorSpaces'] = list(colorspaces['usedColorSpaces'])
            
        except Exception as e:
            logger.error(f"Error extracting color spaces: {e}")
            
        return colorspaces
    
    def _extract_annotation_features(self) -> List[Dict[str, Any]]:
        """Extract annotation information"""
        annotations = []
        
        try:
            for page_num, page in enumerate(self.pdf.pages, 1):
                if '/Annots' in page:
                    annots = page.Annots
                    for annot in annots:
                        annot_info = {
                            'page': page_num,
                            'type': str(annot.get('/Subtype', 'Unknown')),
                            'hasContents': '/Contents' in annot,
                            'hasAltText': '/Alt' in annot,
                        }
                        
                        if annot.get('/Subtype') == '/Link':
                            annot_info['isLink'] = True
                            
                        annotations.append(annot_info)
                        
        except Exception as e:
            logger.error(f"Error extracting annotations: {e}")
            
        return annotations
    
    def _extract_embedded_files(self) -> List[Dict[str, Any]]:
        """Extract embedded file information"""
        embedded_files = []
        
        try:
            if '/Names' in self.pdf.Root and '/EmbeddedFiles' in self.pdf.Root.Names:
                ef_tree = self.pdf.Root.Names.EmbeddedFiles
                # Parse name tree to get embedded files
                # This is a simplified version
                embedded_files.append({
                    'hasEmbeddedFiles': True,
                    'count': 'Unknown'  # Would need full name tree parsing
                })
                
        except Exception as e:
            logger.error(f"Error extracting embedded files: {e}")
            
        return embedded_files
    
    def _extract_form_features(self) -> Dict[str, Any]:
        """Extract form field information"""
        form_info = {
            'hasAcroForm': False,
            'fieldCount': 0,
            'fields': []
        }
        
        try:
            if '/AcroForm' in self.pdf.Root:
                form_info['hasAcroForm'] = True
                acroform = self.pdf.Root.AcroForm
                
                if '/Fields' in acroform:
                    fields = acroform.Fields
                    form_info['fieldCount'] = len(fields)
                    
                    for field in fields:
                        field_info = {
                            'type': str(field.get('/FT', 'Unknown')),
                            'name': str(field.get('/T', 'Unnamed')),
                            'hasTooltip': '/TU' in field,
                        }
                        form_info['fields'].append(field_info)
                        
        except Exception as e:
            logger.error(f"Error extracting form features: {e}")
            
        return form_info
    
    def _extract_metadata_features(self) -> Dict[str, Any]:
        """Extract metadata information"""
        metadata = {
            'hasXMP': False,
            'hasDocInfo': False,
            'xmpProperties': {},
            'docInfoProperties': {}
        }
        
        try:
            # Check for XMP metadata
            if '/Metadata' in self.pdf.Root:
                metadata['hasXMP'] = True
                
            # Check for document info
            if self.pdf.docinfo:
                metadata['hasDocInfo'] = True
                for key, value in self.pdf.docinfo.items():
                    metadata['docInfoProperties'][str(key)] = str(value)
                    
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            
        return metadata
    
    def _extract_structure_features(self) -> Dict[str, Any]:
        """Extract structure tree information"""
        structure = {
            'isTagged': False,
            'hasStructTreeRoot': False,
            'elementCount': 0,
            'roleMap': {}
        }
        
        try:
            if '/StructTreeRoot' in self.pdf.Root:
                structure['hasStructTreeRoot'] = True
                struct_root = self.pdf.Root.StructTreeRoot
                
                # Check if document is marked as tagged
                if '/MarkInfo' in self.pdf.Root:
                    mark_info = self.pdf.Root.MarkInfo
                    structure['isTagged'] = bool(mark_info.get('/Marked', False))
                
                # Get RoleMap
                if '/RoleMap' in struct_root:
                    role_map = struct_root.RoleMap
                    for key, value in role_map.items():
                        structure['roleMap'][str(key)] = str(value)
                        
        except Exception as e:
            logger.error(f"Error extracting structure: {e}")
            
        return structure
    
    def _extract_page_features(self) -> Dict[str, Any]:
        """Extract page-level information"""
        page_info = {
            'count': len(self.pdf.pages),
            'sizes': [],
            'rotations': []
        }
        
        try:
            for page in self.pdf.pages:
                # Get page size
                if '/MediaBox' in page:
                    media_box = page.MediaBox
                    width = float(media_box[2]) - float(media_box[0])
                    height = float(media_box[3]) - float(media_box[1])
                    page_info['sizes'].append({'width': width, 'height': height})
                
                # Get rotation
                rotation = int(page.get('/Rotate', 0))
                page_info['rotations'].append(rotation)
                
        except Exception as e:
            logger.error(f"Error extracting page features: {e}")
            
        return page_info
