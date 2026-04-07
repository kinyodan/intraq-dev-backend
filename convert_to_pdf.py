#!/usr/bin/env python3
"""
Convert Markdown to PDF using available tools
"""

import subprocess
import os
import sys

# File paths
md_file = os.path.expanduser("~/dev/dataentry/backend/client1_normalization_profile.md")
pdf_file = os.path.expanduser("~/dev/dataentry/backend/client1_normalization_profile.pdf")
html_file = os.path.expanduser("~/dev/dataentry/backend/client1_normalization_profile.html")

def markdown_to_html():
    """Convert markdown to HTML"""
    import markdown
    
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Convert to HTML with extensions
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
    
    # Wrap in HTML with basic styling
    html_full = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Client Normalization Profile</title>
<style>
body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    line-height: 1.6;
    max-width: 900px;
    margin: 40px auto;
    padding: 20px;
    color: #333;
}}
h1 {{
    color: #2c3e50;
    border-bottom: 3px solid #3498db;
    padding-bottom: 10px;
}}
h2 {{
    color: #34495e;
    border-bottom: 2px solid #95a5a6;
    padding-bottom: 5px;
    margin-top: 30px;
}}
h3 {{
    color: #2980b9;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 20px 0;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 12px;
    text-align: left;
}}
th {{
    background-color: #3498db;
    color: white;
}}
tr:nth-child(even) {{
    background-color: #f2f2f2;
}}
code {{
    background-color: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
}}
pre {{
    background-color: #f4f4f4;
    padding: 15px;
    border-radius: 5px;
    overflow-x: auto;
}}
blockquote {{
    border-left: 4px solid #3498db;
    padding-left: 15px;
    color: #666;
    font-style: italic;
}}
hr {{
    border: none;
    height: 2px;
    background: linear-gradient(to right, #3498db, #2c3e50);
    margin: 30px 0;
}}
</style>
</head>
<body>
{html_content}
</body>
</html>'''
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_full)
    
    print(f"✓ Created HTML: {html_file}")
    return html_file

def html_to_pdf_wkhtmltopdf():
    """Try using wkhtmltopdf"""
    try:
        subprocess.run(['wkhtmltopdf', '--version'], capture_output=True, check=True)
        subprocess.run([
            'wkhtmltopdf',
            '--enable-local-file-access',
            '--page-size', 'A4',
            '--margin-top', '15mm',
            '--margin-bottom', '15mm',
            '--margin-left', '15mm',
            '--margin-right', '15mm',
            html_file, pdf_file
        ], check=True)
        print(f"✓ Created PDF using wkhtmltopdf: {pdf_file}")
        return True
    except:
        return False

def html_to_pdf_chrome():
    """Try using Chrome/Chromium headless"""
    chrome_cmds = ['google-chrome', 'chromium', 'chromium-browser', 'chrome']
    
    for cmd in chrome_cmds:
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            subprocess.run([
                cmd,
                '--headless',
                '--disable-gpu',
                '--no-sandbox',
                '--print-to-pdf=' + pdf_file,
                '--run-all-compositor-stages-before-draw',
                '--virtual-time-budget=10000',
                html_file
            ], check=True, capture_output=True)
            print(f"✓ Created PDF using {cmd}: {pdf_file}")
            return True
        except:
            continue
    return False

def html_to_pdf_libreoffice():
    """Try using LibreOffice"""
    try:
        output_dir = os.path.dirname(pdf_file)
        subprocess.run([
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            html_file
        ], check=True, capture_output=True)
        
        # LibreOffice names the output based on input
        lo_pdf = html_file.replace('.html', '.pdf')
        if os.path.exists(lo_pdf):
            os.rename(lo_pdf, pdf_file)
            print(f"✓ Created PDF using LibreOffice: {pdf_file}")
            return True
    except Exception as e:
        print(f"LibreOffice failed: {e}")
    return False

def main():
    print("Converting Markdown to PDF...")
    print("=" * 50)
    
    # Step 1: Convert Markdown to HTML
    html = markdown_to_html()
    
    # Step 2: Try different PDF converters
    if html_to_pdf_wkhtmltopdf():
        return
    elif html_to_pdf_chrome():
        return
    elif html_to_pdf_libreoffice():
        return
    else:
        print("\n❌ No PDF converter available.")
        print(f"✓ HTML version created: {html_file}")
        print("You can open the HTML file in a browser and print to PDF.")
        
        # Also create a text version
        txt_file = pdf_file.replace('.pdf', '.txt')
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Text version created: {txt_file}")

if __name__ == "__main__":
    main()
