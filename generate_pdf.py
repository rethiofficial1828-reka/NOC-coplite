#!/usr/bin/env python3
"""
Convert PROJECT_REPORT.md to a professional PDF.
Uses markdown → HTML → WeasyPrint PDF pipeline.
Strips mermaid blocks (they're not renderable in static PDF).
"""
import sys
import os
import re

# Read markdown source
md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PROJECT_REPORT.md")
with open(md_path, "r") as f:
    md_content = f.read()

# Remove mermaid code blocks (not renderable in PDF)
md_content = re.sub(r'```mermaid.*?```', '<p><em>[Mermaid diagram — view in GitHub for interactive rendering]</em></p>', md_content, flags=re.DOTALL)

try:
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
    from markdown.extensions.toc import TocExtension
except ImportError:
    print("ERROR: 'markdown' package not found. Install with: pip install markdown")
    sys.exit(1)

# Convert MD to HTML
html_body = markdown.markdown(
    md_content,
    extensions=['tables', 'fenced_code', 'toc', 'nl2br']
)

# Professional CSS for PDF
css = """
@page {
    size: A4;
    margin: 20mm 18mm 20mm 18mm;
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9px;
        color: #6b7280;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    @top-right {
        content: "CONFIDENTIAL — Internal Review";
        font-size: 8px;
        color: #9ca3af;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-style: italic;
    }
}

@page :first {
    @top-right { content: none; }
}

* { box-sizing: border-box; }

body {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1f2937;
    max-width: 100%;
}

h1 {
    font-size: 22pt;
    font-weight: 800;
    color: #0f172a;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 8px;
    margin-top: 30px;
    margin-bottom: 16px;
    page-break-after: avoid;
}

h1:first-of-type {
    font-size: 26pt;
    text-align: center;
    border-bottom: 4px solid #1e40af;
    padding-bottom: 12px;
    margin-top: 0;
    background: linear-gradient(135deg, #0f172a, #1e3a5f);
    color: white;
    padding: 20px 16px 14px 16px;
    border-radius: 8px;
    margin-bottom: 24px;
}

h2 {
    font-size: 15pt;
    font-weight: 700;
    color: #1e40af;
    margin-top: 24px;
    margin-bottom: 10px;
    border-bottom: 1.5px solid #dbeafe;
    padding-bottom: 5px;
    page-break-after: avoid;
}

h3 {
    font-size: 12.5pt;
    font-weight: 700;
    color: #1e3a5f;
    margin-top: 18px;
    margin-bottom: 8px;
    page-break-after: avoid;
}

h4 {
    font-size: 11pt;
    font-weight: 600;
    color: #374151;
    margin-top: 14px;
    margin-bottom: 6px;
}

p { margin: 6px 0; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 16px 0;
    font-size: 9.5pt;
    page-break-inside: auto;
}

thead tr {
    background: #1e3a5f;
    color: white;
}

th {
    padding: 8px 10px;
    text-align: left;
    font-weight: 700;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

td {
    padding: 6px 10px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: top;
}

tbody tr:nth-child(even) {
    background: #f8fafc;
}

tbody tr:hover {
    background: #eff6ff;
}

code {
    background: #f1f5f9;
    color: #dc2626;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: 'Consolas', 'Fira Code', monospace;
    font-size: 9pt;
}

pre {
    background: #0f172a;
    color: #e2e8f0;
    padding: 14px 16px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 8.5pt;
    line-height: 1.5;
    margin: 10px 0 14px 0;
    page-break-inside: avoid;
    border-left: 4px solid #2563eb;
}

pre code {
    background: none;
    color: #e2e8f0;
    padding: 0;
    font-size: 8.5pt;
}

ul, ol {
    margin: 6px 0 10px 20px;
    padding-left: 10px;
}

li { margin: 3px 0; }

strong { color: #0f172a; }

em { color: #4b5563; }

hr {
    border: none;
    border-top: 2px solid #e5e7eb;
    margin: 20px 0;
}

/* Status markers */
td:first-child { font-weight: 600; }

/* Highlight FAIL/PASS/RISK markers */
"""

full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <title>NOC Copilot — Project Report</title>
    <style>{css}</style>
</head>
<body>
{html_body}
</body>
</html>"""

# Write intermediate HTML
html_path = md_path.replace(".md", ".html")
with open(html_path, "w") as f:
    f.write(full_html)
print(f"HTML written to {html_path}")

# Try WeasyPrint for PDF
pdf_path = md_path.replace(".md", ".pdf")
try:
    from weasyprint import HTML
    HTML(filename=html_path).write_pdf(pdf_path)
    print(f"PDF generated: {pdf_path}")
except ImportError:
    print("WeasyPrint not available. Trying alternative...")
    # Fallback: use pdfkit if available
    try:
        import pdfkit
        pdfkit.from_file(html_path, pdf_path)
        print(f"PDF generated via pdfkit: {pdf_path}")
    except ImportError:
        print(f"No PDF engine available. HTML file ready at: {html_path}")
        print("Install WeasyPrint: pip install weasyprint")
        print("Or use the HTML file directly — it renders beautifully in any browser.")
        sys.exit(0)
