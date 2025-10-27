from fpdf import FPDF
from PIL import Image, ImageDraw
import io
import os
from datetime import datetime

class PDFGenerator:
    """
    Generates both accessible and inaccessible PDFs for testing purposes.
    """
    
    def __init__(self):
        self.output_dir = "generated_pdfs"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def create_accessible_pdf(self, company_name="BrightPath Consulting", services=None):
        """
        Create an accessible PDF following WCAG guidelines
        """
        if services is None:
            services = [
                "Strategic Planning",
                "Market Research",
                "Digital Transformation",
                "Change Management",
                "Leadership Coaching"
            ]
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Set document metadata
        pdf.set_title(f"{company_name} - Services Overview")
        pdf.set_author(company_name)
        pdf.set_subject("Company Services and Information")
        
        # Page 1: About Us
        pdf.add_page()
        
        # Header with proper contrast (black on white)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", 'B', 20)
        pdf.cell(0, 10, company_name, ln=True, align="C")
        pdf.ln(5)
        
        # Body text with good contrast
        pdf.set_font("Helvetica", '', 12)
        pdf.set_text_color(0, 0, 0)
        about_text = (
            f"{company_name} is a forward-thinking advisory firm helping businesses "
            "navigate complex strategic challenges. Our multidisciplinary team brings deep "
            "industry expertise, data-driven insights, and innovative solutions to every project.\n\n"
            "We partner with organizations to transform operations, optimize performance, "
            "and unlock sustainable growth. Our mission is to empower clients to thrive "
            "in a rapidly changing world."
        )
        pdf.multi_cell(0, 8, about_text)
        
        # Page 2: Our Services
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 18)
        pdf.cell(0, 10, "Our Services", ln=True)
        pdf.ln(3)
        
        # Services list with proper structure
        pdf.set_font("Helvetica", '', 12)
        for service in services:
            pdf.cell(10, 8, chr(149), ln=0)  # Bullet point
            pdf.cell(0, 8, service, ln=True)
        
        # Page 3: Contact Information
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 18)
        pdf.cell(0, 10, "Contact Us", ln=True)
        pdf.ln(5)
        
        pdf.set_font("Helvetica", '', 12)
        contact_text = f"Email: contact@{company_name.lower().replace(' ', '')}.com\n"
        contact_text += "Phone: +1 (555) 123-4567\n"
        contact_text += "Address: 123 Business Ave, Suite 100, City, State 12345"
        pdf.multi_cell(0, 8, contact_text)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"accessible_{company_name.lower().replace(' ', '_')}_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, filename)
        
        pdf.output(output_path)
        return output_path
    
    def create_inaccessible_pdf(self, company_name="BrightPath Consulting", services=None, options=None):
        """
        Create an inaccessible PDF with selected accessibility issues
        
        Args:
            company_name: Name of the company
            services: List of services
            options: Dict of accessibility issues to include
        """
        if services is None:
            services = [
                "Strategic Planning",
                "Market Research",
                "Digital Transformation",
                "Change Management",
                "Leadership Coaching"
            ]
        
        if options is None:
            options = {
                'lowContrast': True,
                'missingAltText': True,
                'noStructure': True,
                'rasterizedText': True,
                'improperHeadings': True,
                'noLanguage': True
            }
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Page 1: About Us
        pdf.add_page()
        
        # Apply low contrast if selected
        if options.get('lowContrast', True):
            pdf.set_text_color(180, 180, 180)
        else:
            pdf.set_text_color(0, 0, 0)
        
        pdf.set_font("Helvetica", 'B', 20)
        pdf.cell(0, 10, company_name, ln=True, align="C")
        pdf.ln(5)
        
        pdf.set_font("Helvetica", '', 14)
        if options.get('lowContrast', True):
            pdf.set_text_color(150, 150, 150)
        
        about_text = (
            f"{company_name} is a forward-thinking advisory firm helping businesses "
            "navigate complex strategic challenges. Our multidisciplinary team brings deep "
            "industry expertise, data-driven insights, and innovative solutions to every project.\n\n"
            "We partner with organizations to transform operations, optimize performance, "
            "and unlock sustainable growth. Our mission is to empower clients to thrive "
            "in a rapidly changing world."
        )
        pdf.multi_cell(0, 10, about_text)
        
        # Page 2: Our Services
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 18)
        if options.get('lowContrast', True):
            pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 10, "Our Services", ln=True)
        
        # Improper heading hierarchy if selected
        if options.get('improperHeadings', True):
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(0, 8, "Service Offerings", ln=True)
        
        pdf.set_font("Helvetica", '', 12)
        services_text = "\n".join([f"• {service}" for service in services])
        pdf.multi_cell(0, 8, services_text)
        
        # Add image without alt text if selected
        if options.get('missingAltText', True):
            img = Image.new("RGB", (400, 200), color=(200, 200, 200))
            draw = ImageDraw.Draw(img)
            draw.text((120, 90), "Team Meeting (No Alt Text)", fill=(100, 100, 100))
            
            temp_img_path = os.path.join(self.output_dir, "temp_img.png")
            img.save(temp_img_path)
            pdf.image(temp_img_path, x=40, y=100, w=120)
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
        
        # Page 3: Contact
        pdf.add_page()
        
        # Rasterized text if selected
        if options.get('rasterizedText', True):
            img_text = Image.new("RGB", (600, 150), color=(255, 255, 255))
            draw = ImageDraw.Draw(img_text)
            draw.text((50, 50), f"Contact: contact@{company_name.lower().replace(' ', '')}.com", fill=(120, 120, 120))
            
            temp_text_img_path = os.path.join(self.output_dir, "temp_text.png")
            img_text.save(temp_text_img_path)
            pdf.image(temp_text_img_path, x=30, y=40, w=150)
            if os.path.exists(temp_text_img_path):
                os.remove(temp_text_img_path)
        else:
            pdf.set_font("Helvetica", '', 12)
            pdf.cell(0, 10, f"Contact: contact@{company_name.lower().replace(' ', '')}.com", ln=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"inaccessible_{company_name.lower().replace(' ', '_')}_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, filename)
        
        pdf.output(output_path)
        return output_path
    
    def get_generated_pdfs(self):
        """Get list of all generated PDFs"""
        if not os.path.exists(self.output_dir):
            return []
        
        pdfs = [f for f in os.listdir(self.output_dir) if f.endswith('.pdf')]
        return sorted(pdfs, reverse=True)
