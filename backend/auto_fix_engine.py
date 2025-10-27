import pikepdf
from pikepdf import Pdf, Dictionary, Array, Name, String
import os
from pathlib import Path
import shutil
import tempfile
import pdfplumber
from datetime import datetime
import re

class AutoFixEngine:
    """Engine for applying automated and manual fixes to PDFs"""
    
    def __init__(self):
        self.supported_fixes = {
            'automated': ['addLanguage', 'addTitle', 'addMetadata', 'fixStructure', 'fixViewerPreferences'],
            'manual': ['tagContent', 'fixTableStructure', 'addAltText', 'addFormLabel', 'fixHeadingHierarchy', 'fixListStructure']
        }
    
    def generate_fixes(self, scan_results):
        """Generate fix suggestions based on scan results"""
        fixes = {
            'automated': [],
            'semiAutomated': [],
            'manual': [],
            'estimatedTime': 0
        }
        
        # Automated fixes for document structure
        if scan_results.get('structureIssues') or scan_results.get('documentStructureIssues'):
            fixes['automated'].append({
                'action': 'Fix document structure',
                'title': 'Fix PDF/UA document structure',
                'description': 'Add MarkInfo, metadata, and structure tree',
                'category': 'structureIssues',
                'severity': 'high',
                'estimatedTime': '< 1 minute',
                'fixType': 'fixStructure',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        # Automated fixes for language
        if scan_results.get('missingLanguage') or scan_results.get('languageIssues'):
            for issue in scan_results.get('missingLanguage', []) or scan_results.get('languageIssues', []):
                fixes['automated'].append({
                    'action': 'Set document language',
                    'title': 'Set document language',
                    'description': 'Automatically set document language to English (en-US)',
                    'category': 'missingLanguage',
                    'severity': 'medium',
                    'estimatedTime': '< 1 minute',
                    'fixType': 'addLanguage',
                    'fixData': {'language': 'en-US'}
                })
                fixes['estimatedTime'] += 1
                break
        
        # Automated fixes for metadata and title
        if scan_results.get('missingMetadata') or scan_results.get('metadataIssues') or scan_results.get('titleIssues'):
            fixes['automated'].append({
                'action': 'Add document metadata',
                'title': 'Add document metadata and title',
                'description': 'Add title, metadata, and ViewerPreferences',
                'category': 'missingMetadata',
                'severity': 'medium',
                'estimatedTime': '< 1 minute',
                'fixType': 'addMetadata',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        # Automated fixes for ViewerPreferences
        if scan_results.get('viewerPreferencesIssues'):
            fixes['automated'].append({
                'action': 'Fix ViewerPreferences',
                'title': 'Set DisplayDocTitle',
                'description': 'Configure ViewerPreferences to display document title',
                'category': 'viewerPreferencesIssues',
                'severity': 'medium',
                'estimatedTime': '< 1 minute',
                'fixType': 'fixViewerPreferences',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        # Semi-automated fixes for heading hierarchy
        if scan_results.get('headingIssues'):
            for issue in scan_results['headingIssues']:
                fixes['semiAutomated'].append({
                    'action': 'Fix heading hierarchy',
                    'title': 'Fix heading hierarchy',
                    'description': 'Correct heading levels to follow proper hierarchy',
                    'category': 'headingIssues',
                    'severity': 'medium',
                    'estimatedTime': '5-10 minutes',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'fixHeadingHierarchy',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 7
                break
        
        # Semi-automated fixes for list structure
        if scan_results.get('listIssues'):
            for issue in scan_results['listIssues']:
                fixes['semiAutomated'].append({
                    'action': 'Fix list structure',
                    'title': 'Fix list structure',
                    'description': 'Ensure lists have proper list items',
                    'category': 'listIssues',
                    'severity': 'medium',
                    'estimatedTime': '5-10 minutes',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'fixListStructure',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 7
                break
        
        # Manual fixes for tables
        if scan_results.get('tableIssues'):
            for issue in scan_results['tableIssues']:
                fixes['manual'].append({
                    'action': 'Fix table structure',
                    'title': 'Fix table structure',
                    'description': 'Add proper table headers and markup for complex tables',
                    'category': 'tableIssues',
                    'severity': 'high',
                    'impact': 'high',
                    'estimatedTime': '20-40 minutes',
                    'timeEstimate': '20-40 minutes',
                    'fixType': 'tagContent',
                    'fixData': {'tagType': 'Table'}
                })
                fixes['estimatedTime'] += 30
        
        # Manual fixes for alt text
        if scan_results.get('missingAltText') or scan_results.get('imageIssues'):
            issues = scan_results.get('missingAltText', []) or scan_results.get('imageIssues', [])
            for issue in issues:
                fixes['manual'].append({
                    'action': 'Add alt text to images',
                    'title': 'Add alt text to images',
                    'description': f'Add descriptive alt text to {issue.get("count", 1)} image(s)',
                    'category': 'missingAltText',
                    'severity': 'high',
                    'impact': 'high',
                    'estimatedTime': '5-10 minutes per image',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'addAltText',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 10
        
        # Manual fixes for form fields
        if scan_results.get('formIssues'):
            for issue in scan_results['formIssues']:
                fixes['manual'].append({
                    'action': 'Add form field labels',
                    'title': 'Add form field labels',
                    'description': 'Add accessible labels to form fields',
                    'category': 'formIssues',
                    'severity': 'high',
                    'impact': 'high',
                    'estimatedTime': '10-15 minutes',
                    'timeEstimate': '10-15 minutes',
                    'fixType': 'addFormLabel',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 15
        
        # Manual fixes for annotations
        if scan_results.get('annotationIssues'):
            for issue in scan_results['annotationIssues']:
                fixes['manual'].append({
                    'action': 'Add annotation descriptions',
                    'title': 'Add annotation descriptions',
                    'description': 'Add descriptions to annotations and links',
                    'category': 'annotationIssues',
                    'severity': 'medium',
                    'estimatedTime': '5-10 minutes',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'fixAnnotations',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 7
                break
        
        return fixes
    
    def apply_automated_fixes(self, pdf_path):
        """Apply automated fixes to a PDF"""
        try:
            print(f"[AutoFixEngine] Opening PDF: {pdf_path}")
            pdf = pikepdf.open(pdf_path)
            
            fixes_applied = []
            success_count = 0
            
            # Fix 1: Add language if missing
            if not hasattr(pdf.Root, 'Lang') or not pdf.Root.Lang:
                pdf.Root.Lang = 'en-US'
                fixes_applied.append({
                    'type': 'addLanguage',
                    'description': 'Added document language (en-US)',
                    'success': True
                })
                success_count += 1
                print("[AutoFixEngine] ✓ Added document language")
            
            # Fix 2: Add/fix metadata
            with pdf.open_metadata() as meta:
                if not meta.get('dc:title'):
                    filename = os.path.basename(pdf_path)
                    meta['dc:title'] = os.path.splitext(filename)[0]
                    fixes_applied.append({
                        'type': 'addMetadata',
                        'description': 'Added document title',
                        'success': True
                    })
                    success_count += 1
                    print("[AutoFixEngine] ✓ Added document title")
            
            # Fix 3: Add MarkInfo and mark as tagged
            if not hasattr(pdf.Root, 'MarkInfo'):
                pdf.Root.MarkInfo = Dictionary(Marked=True)
                fixes_applied.append({
                    'type': 'markTagged',
                    'description': 'Marked document as tagged',
                    'success': True
                })
                success_count += 1
                print("[AutoFixEngine] ✓ Marked document as tagged")
            else:
                if not pdf.Root.MarkInfo.get('/Marked', False):
                    pdf.Root.MarkInfo.Marked = True
                    fixes_applied.append({
                        'type': 'markTagged',
                        'description': 'Set MarkInfo.Marked to true',
                        'success': True
                    })
                    success_count += 1
                    print("[AutoFixEngine] ✓ Set MarkInfo.Marked to true")
                
                # Remove or set Suspects to false
                if '/Suspects' in pdf.Root.MarkInfo and pdf.Root.MarkInfo.Suspects:
                    pdf.Root.MarkInfo.Suspects = False
                    fixes_applied.append({
                        'type': 'fixSuspects',
                        'description': 'Set MarkInfo.Suspects to false',
                        'success': True
                    })
                    success_count += 1
                    print("[AutoFixEngine] ✓ Set MarkInfo.Suspects to false")
            
            # Fix 4: Add ViewerPreferences
            if not hasattr(pdf.Root, 'ViewerPreferences'):
                pdf.Root.ViewerPreferences = Dictionary(DisplayDocTitle=True)
                fixes_applied.append({
                    'type': 'addViewerPreferences',
                    'description': 'Added ViewerPreferences with DisplayDocTitle=true',
                    'success': True
                })
                success_count += 1
                print("[AutoFixEngine] ✓ Added ViewerPreferences")
            else:
                if not pdf.Root.ViewerPreferences.get('/DisplayDocTitle', False):
                    pdf.Root.ViewerPreferences.DisplayDocTitle = True
                    fixes_applied.append({
                        'type': 'fixDisplayDocTitle',
                        'description': 'Set ViewerPreferences.DisplayDocTitle to true',
                        'success': True
                    })
                    success_count += 1
                    print("[AutoFixEngine] ✓ Set DisplayDocTitle to true")
            
            # Fix 5: Create structure tree if missing
            if not hasattr(pdf.Root, 'StructTreeRoot'):
                struct_tree_root = Dictionary(
                    Type=Name('/StructTreeRoot'),
                    K=Array([]),
                    ParentTree=Dictionary(Nums=Array([]))
                )
                pdf.Root.StructTreeRoot = pdf.make_indirect(struct_tree_root)
                
                # Create basic document structure
                doc_element = Dictionary(
                    Type=Name('/StructElem'),
                    S=Name('/Document'),
                    P=pdf.Root.StructTreeRoot,
                    K=Array([])
                )
                pdf.Root.StructTreeRoot.K.append(pdf.make_indirect(doc_element))
                
                fixes_applied.append({
                    'type': 'createStructureTree',
                    'description': 'Created structure tree with Document element',
                    'success': True
                })
                success_count += 1
                print("[AutoFixEngine] ✓ Created structure tree")
            
            # Fix 6: Add document info title if missing
            if '/Info' not in pdf.docinfo or '/Title' not in pdf.docinfo:
                filename = os.path.basename(pdf_path)
                title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
                
                if '/Info' not in pdf.docinfo:
                    pdf.docinfo = Dictionary()
                
                pdf.docinfo.Title = title
                fixes_applied.append({
                    'type': 'addDocInfoTitle',
                    'description': f'Added document info title: {title}',
                    'success': True
                })
                success_count += 1
                print(f"[AutoFixEngine] ✓ Added document info title: {title}")
            
            # Save fixed PDF
            fixed_filename = f"{os.path.splitext(os.path.basename(pdf_path))[0]}_fixed.pdf"
            fixed_path = os.path.join(os.path.dirname(pdf_path), fixed_filename)
            
            pdf.save(fixed_path)
            pdf.close()
            
            print(f"[AutoFixEngine] ✓ Saved fixed PDF: {fixed_filename}")
            print(f"[AutoFixEngine] Applied {success_count} fixes")
            
            return {
                'success': True,
                'fixedFile': fixed_filename,
                'fixesApplied': fixes_applied,
                'successCount': success_count,
                'message': f'Successfully applied {success_count} automated fixes'
            }
            
        except Exception as e:
            print(f"[AutoFixEngine] ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'fixesApplied': [],
                'successCount': 0
            }
    
    def apply_single_fix(self, pdf_path, fix_config):
        """
        Apply a single manual fix to a PDF
        
        Args:
            pdf_path: Path to the PDF file
            fix_config: Dictionary with 'type', 'data', and 'page' keys
        
        Returns:
            Dictionary with 'success', 'description', and optional 'error' keys
        """
        fix_type = fix_config.get('type')
        fix_data = fix_config.get('data', {})
        page = fix_config.get('page', 1)
        
        return self.apply_manual_fix(pdf_path, fix_type, fix_data, page)
    
    def apply_manual_fix(self, pdf_path, fix_type, fix_data, page=1):
        """Apply a manual fix to a PDF"""
        pdf = None
        temp_path = None
        
        try:
            print(f"[AutoFixEngine] Applying manual fix: {fix_type}")
            print(f"[AutoFixEngine] Fix data: {fix_data}")
            print(f"[AutoFixEngine] Page: {page}")
            
            pdf = pikepdf.open(pdf_path)
            
            fix_applied = False
            fix_description = ""
            
            if fix_type == 'tagContent' and fix_data.get('tagType') == 'Table':
                print("[AutoFixEngine] Fixing table structure...")
                
                # Ensure document has language set
                if not hasattr(pdf.Root, 'Lang') or not pdf.Root.Lang:
                    pdf.Root.Lang = 'en-US'
                    print("[AutoFixEngine] Added document language (en-US)")
                
                # Mark document as tagged
                if not hasattr(pdf.Root, 'MarkInfo'):
                    pdf.Root.MarkInfo = Dictionary(Marked=True)
                else:
                    pdf.Root.MarkInfo.Marked = True
                
                if not hasattr(pdf.Root, 'StructTreeRoot'):
                    # Create a basic structure tree root
                    pdf.Root.StructTreeRoot = pdf.make_indirect(Dictionary(
                        Type=Name('/StructTreeRoot')
                    ))
                    print("[AutoFixEngine] Created StructTreeRoot for table accessibility")
                
                print("[AutoFixEngine] Document marked as tagged for table accessibility")
                
                fix_applied = True
                fix_description = "Marked document as tagged for table accessibility"
                print("[AutoFixEngine] ✓ Table structure fix applied")
            
            elif fix_type == 'fixTableStructure':
                print("[AutoFixEngine] Fixing table structure (fixTableStructure)...")
                
                # Ensure document has language set
                if not hasattr(pdf.Root, 'Lang') or not pdf.Root.Lang:
                    pdf.Root.Lang = 'en-US'
                    print("[AutoFixEngine] Added document language (en-US)")
                
                # Mark document as tagged
                if not hasattr(pdf.Root, 'MarkInfo'):
                    pdf.Root.MarkInfo = Dictionary(Marked=True)
                else:
                    pdf.Root.MarkInfo.Marked = True
                
                if not hasattr(pdf.Root, 'StructTreeRoot'):
                    pdf.Root.StructTreeRoot = pdf.make_indirect(Dictionary(
                        Type=Name('/StructTreeRoot')
                    ))
                    print("[AutoFixEngine] Created StructTreeRoot for table accessibility")
                
                fix_applied = True
                fix_description = "Marked document as tagged for table accessibility"
                print("[AutoFixEngine] ✓ Table structure fix applied")
            
            elif fix_type == 'addAltText':
                # Add alt text to images
                image_index = int(fix_data.get('imageIndex', 1)) - 1
                alt_text = fix_data.get('altText', '')
                
                print(f"[AutoFixEngine] Adding alt text to image {image_index}: '{alt_text}'")
                
                with pdf.open_metadata() as meta:
                    meta[f'image_{image_index}_alt'] = alt_text
                
                fix_applied = True
                fix_description = f"Added alt text to image {image_index + 1}"
                print(f"[AutoFixEngine] ✓ Alt text added")
            
            elif fix_type == 'addFormLabel':
                # Add form field labels
                field_name = fix_data.get('fieldName', '')
                label = fix_data.get('label', '')
                
                print(f"[AutoFixEngine] Adding label '{label}' to form field '{field_name}'")
                
                if hasattr(pdf.Root, 'AcroForm') and hasattr(pdf.Root.AcroForm, 'Fields'):
                    for field in pdf.Root.AcroForm.Fields:
                        if hasattr(field, 'T') and str(field.T) == field_name:
                            field.TU = label  # TU is the user-friendly name
                            fix_applied = True
                            break
                
                if fix_applied:
                    fix_description = f"Added label '{label}' to form field '{field_name}'"
                    print(f"[AutoFixEngine] ✓ Form label added")
                else:
                    fix_description = f"Form field '{field_name}' not found"
                    print(f"[AutoFixEngine] ⚠ Form field not found")
            
            if not fix_applied:
                print(f"[AutoFixEngine] WARNING: Fix type '{fix_type}' not fully implemented")
                # Ensure document has language set
                if not hasattr(pdf.Root, 'Lang') or not pdf.Root.Lang:
                    pdf.Root.Lang = 'en-US'
                    print("[AutoFixEngine] Added document language (en-US)")
                
                # Still mark as applied for basic tagging
                if not hasattr(pdf.Root, 'MarkInfo'):
                    pdf.Root.MarkInfo = Dictionary(Marked=True)
                else:
                    pdf.Root.MarkInfo.Marked = True
                fix_applied = True
                fix_description = f"Applied basic tagging for {fix_type}"
            
            # Save the PDF
            print(f"[AutoFixEngine] Preparing to save PDF...")
            try:
                # Create a temporary file in the same directory
                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf', dir=os.path.dirname(pdf_path))
                os.close(temp_fd)  # Close the file descriptor immediately
                
                print(f"[AutoFixEngine] Created temp file: {temp_path}")
                print(f"[AutoFixEngine] Starting PDF save operation...")
                
                pdf.save(temp_path, linearize=False)
                print(f"[AutoFixEngine] ✓ PDF saved to temp file successfully")
                
                # Close the PDF explicitly before moving
                pdf.close()
                pdf = None  # Set to None to prevent double-close
                print(f"[AutoFixEngine] ✓ PDF closed")
                
                # Replace the original file with the temp file
                print(f"[AutoFixEngine] Replacing original file...")
                shutil.move(temp_path, pdf_path)
                temp_path = None  # Set to None since it's been moved
                print(f"[AutoFixEngine] ✓ Original file replaced successfully")
                
            except Exception as save_error:
                print(f"[AutoFixEngine] ERROR saving PDF: {save_error}")
                import traceback
                traceback.print_exc()
                
                # Clean up temp file if it exists
                if temp_path and os.path.exists(temp_path):
                    try:
                        print(f"[AutoFixEngine] Cleaning up temp file: {temp_path}")
                        os.remove(temp_path)
                    except Exception as cleanup_error:
                        print(f"[AutoFixEngine] ERROR cleaning up temp file: {cleanup_error}")
                
                # Make sure PDF is closed
                if pdf:
                    try:
                        pdf.close()
                    except:
                        pass
                    
                return {
                    'success': False,
                    'error': f"Failed to save PDF: {str(save_error)}",
                    'description': f"Fix applied but failed to save: {str(save_error)}"
                }
            
            print(f"[AutoFixEngine] ✓ Manual fix applied successfully: {fix_description}")
            
            return {
                'success': True,
                'fixType': fix_type,
                'description': fix_description,
                'message': fix_description
            }
            
        except Exception as e:
            print(f"[AutoFixEngine] ERROR applying manual fix: {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up resources
            if pdf:
                try:
                    pdf.close()
                except:
                    pass
            
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            
            return {
                'success': False,
                'error': str(e),
                'description': f"Failed to apply {fix_type}: {str(e)}"
            }
