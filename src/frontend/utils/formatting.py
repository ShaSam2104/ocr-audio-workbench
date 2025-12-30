"""Text formatting utilities."""
import re


def convert_markdown_to_html(text: str) -> str:
    """
    Convert markdown-style tags to HTML.
    Supports:
    - **bold** → <b>bold</b>
    - *italic* → <i>italic</i>
    - __underline__ → <u>underline</u>
    - ~~strikethrough~~ → <s>strikethrough</s>
    - ^superscript^ → <sup>superscript</sup>
    - ~subscript~ → <sub>subscript</sub>
    """
    if not text:
        return ""

    html = text
    # Order matters: do ** before *
    html = re.sub(r"\*\*([^\*]+)\*\*", r"<b>\1</b>", html)
    html = re.sub(r"__([^_]+)__", r"<u>\1</u>", html)
    html = re.sub(r"\*([^\*]+)\*", r"<i>\1</i>", html)
    html = re.sub(r"~~([^~]+)~~", r"<s>\1</s>", html)
    html = re.sub(r"\^([^^]+)\^", r"<sup>\1</sup>", html)
    html = re.sub(r"~([^~]+)~", r"<sub>\1</sub>", html)

    # Preserve line breaks
    html = html.replace("\n", "<br>")

    return html


def generate_excerpt(text: str, query: str, context_length: int = 100) -> str:
    """Generate an excerpt of text with query highlighted."""
    if not text or not query:
        return text[:context_length] + "..." if len(text) > context_length else text

    # Find position of query in text
    pos = text.lower().find(query.lower())

    if pos == -1:
        return text[:context_length] + "..." if len(text) > context_length else text

    # Generate context around match
    start = max(0, pos - context_length // 2)
    end = min(len(text), pos + context_length // 2)

    excerpt = text[start:end]
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."

    return excerpt
