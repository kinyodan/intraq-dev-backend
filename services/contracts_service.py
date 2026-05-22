from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime


class IntraqContractGenerator:
    """
    Elegant & Professional Contract Generator for Intraq
    """

    def __init__(self):
        # Intraq Brand Colors
        self.primary = colors.HexColor('#f97316')
        self.dark = colors.HexColor('#0f172a')
        self.slate = colors.HexColor('#1e2937')
        self.light = colors.HexColor('#e2e8f0')
        self.gray = colors.HexColor('#64748b')

    def _header_footer(self, canvas, doc):
        canvas.saveState()
        header_y = doc.height + doc.topMargin - 25
        
        # Header
        canvas.setFillColor(self.dark)
        canvas.rect(0, header_y - 8, doc.width, 70, fill=1)
        
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 24)
        canvas.drawString(50, header_y + 38, "INTRAQ")
        
        canvas.setFillColor(self.primary)
        canvas.setFont("Helvetica-Bold", 24)
        canvas.drawString(145, header_y + 38, "DATA")
        
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 24)
        canvas.drawString(215, header_y + 38, "SOLUTIONS")
        
        canvas.setFillColor(self.light)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(50, header_y + 18, "Professional Data Operations • Built for Impact in Africa")
        
        canvas.setStrokeColor(self.primary)
        canvas.setLineWidth(4)
        canvas.line(50, header_y - 8, doc.width - 50, header_y - 8)

        # Footer
        canvas.setFillColor(self.gray)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(50, 30, "© 2026 Intraq Data Solutions Ltd. • Nairobi, Kenya")
        canvas.drawRightString(doc.width - 50, 30, f"Page {doc.page} • Confidential")
        
        canvas.restoreState()

    def generate_contract(self, 
                         client_name: str,
                         client_company: str,
                         service_description: str,
                         contract_value: float,
                         contract_duration: str,
                         start_date: str,
                         output_filename: str = "Intraq_Contract.pdf"):
        
        doc = SimpleDocTemplate(
            output_filename,
            pagesize=A4,
            rightMargin=50,
            leftMargin=50,
            topMargin=125,
            bottomMargin=70
        )

        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle('Title', parent=styles['Title'], 
                                    fontSize=26, textColor=self.dark, spaceAfter=12, alignment=1)
        
        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], 
                                       fontSize=13, textColor=self.primary, alignment=1, spaceAfter=15)
        
        heading_style = ParagraphStyle('Heading', parent=styles['Heading1'], 
                                      fontSize=15, textColor=self.dark, spaceAfter=8, spaceBefore=12)
        
        normal_style = ParagraphStyle('Normal', parent=styles['Normal'], 
                                     fontSize=11.5, leading=17, textColor=self.dark, spaceAfter=8)

        story = []

        # ================== TITLE ==================
        story.append(Paragraph("SERVICE AGREEMENT", title_style))
        story.append(Paragraph("Data Operations Partnership", subtitle_style))
        story.append(Spacer(1, 25))

        # ================== ELEGANT BETWEEN THE PARTIES ==================
        story.append(Paragraph("BETWEEN THE PARTIES", heading_style))
        story.append(Spacer(1, 10))

        parties_text = f"""
        This Service Agreement is made and entered into on {datetime.now().strftime('%d %B, %Y')}, by and between:

        <b>Intraq Data Operations</b><br/>
        (hereinafter referred to as the <b>“Provider”</b>)

        <br/><br/>

        <b>AND</b>

        <br/><br/>

        <b>{client_company}</b><br/>
        {client_name}<br/>
        (hereinafter referred to as the <b>“Client”</b>)
        """

        story.append(Paragraph(parties_text, normal_style))
        story.append(Spacer(1, 2))

        # ================== SCOPE OF SERVICES ==================
        story.append(Paragraph("1. SCOPE OF SERVICES", heading_style))
        story.append(Paragraph(service_description, normal_style))
        story.append(Spacer(1, 2))

        # ================== COMMERCIAL TERMS ==================
        story.append(Paragraph("2. COMMERCIAL TERMS", heading_style))
        
        terms_data = [
            ["Service Fee:", f"KES {contract_value:,.2f}"],
            ["Duration:", contract_duration],
            ["Start Date:", start_date],
            ["Payment Terms:", "50% upfront • 50% upon completion and approval"],
        ]
        
        t = Table(terms_data, colWidths=[160, 300])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), self.slate),
            ('TEXTCOLOR', (0,0), (0,-1), colors.white),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 1, self.gray),
            ('BOTTOMPADDING', (0,0), (-1,-1), 9),
        ]))
        story.append(t)
        story.append(Spacer(1, 20))

        # ================== SIGNATURE SECTION (Kept Together) ==================
        signature_section = [
            Paragraph("3. ACCEPTANCE & SIGNATURES", heading_style),
            Spacer(1, 25),
            
            Table([
                ["For Intraq Data Solutions:", "_" * 55],
                ["Name:", "Daniel Kinyo"],
                ["Title:", "Founder & Director"],
                ["Date:", datetime.now().strftime("%d %B %Y")],
                ["", ""],
                ["For the Client:", "_" * 55],
                ["Name:", client_name],
                ["Title:", "____________________________"],
                ["Date:", "____________________________"],
            ], colWidths=[200, 280]),
        ]

        story.append(KeepTogether(signature_section))

        # Build the PDF
        doc.build(story, onFirstPage=self._header_footer, onLaterPages=self._header_footer)

        print(f"✅ Elegant Professional Contract successfully generated: {output_filename}")
        return output_filename

if __name__ == "__main__":
    generator = IntraqContractGenerator()
    
    generator.generate_contract(
        client_name="Grace Njeri",
        client_company="African Centre for Women, Information and Communications Technology",
        service_description="""
        Provision of high-volume data entry, cleaning, validation, and structuring services 
        for beneficiary records, household surveys, and program monitoring data collected 
        under the UK DAP Digital Inclusion Project (DEGESI) in Turkana, Elgeyo Marakwet, 
        Garissa, and Wajir counties.
        """,
        contract_value=450000,
        contract_duration="3 Months",
        start_date="1st June 2026"
    )        