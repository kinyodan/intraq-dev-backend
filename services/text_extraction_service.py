import json
import re
from html import unescape
from bs4 import BeautifulSoup


def extract_email_reply_snippet(full_email_str: str, max_length: int = 200) -> str:
    """
    Extract only newest reply content from webhook email payload.
    Removes HTML, quoted history, signatures, and trims snippet.
    """
    try:
        email_data = json.loads(full_email_str)
    except Exception:
        return ""

    # Prefer plain text first
    content = email_data.get("text")

    # Fallback to html if text missing
    if not content or content == "None":
        html_content = email_data.get("html", "")
        soup = BeautifulSoup(html_content, "html.parser")
        content = soup.get_text("\n")

    if not content:
        return ""

    content = unescape(content)

    # Stop at common reply separators
    reply_separators = [
        r"\nOn .* wrote:",
        r"\nFrom: .*",
        r"\nSent: .*",
        r"\n---+.*Original Message.*",
    ]

    for pattern in reply_separators:
        parts = re.split(pattern, content, flags=re.IGNORECASE)
        if parts:
            content = parts[0]

    # Remove quoted lines starting with >
    lines = content.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith(">"):
            continue

        cleaned_lines.append(line)

    cleaned = " ".join(cleaned_lines)

    # Remove excessive whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned[:max_length]