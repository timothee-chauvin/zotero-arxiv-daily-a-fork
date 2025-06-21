import datetime
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Any

from loguru import logger

from paper import ArxivPaper

framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
    .section-header {
      font-size: 24px;
      font-weight: bold;
      color: #2c3e50;
      margin: 20px 0 16px 0;
      padding-bottom: 8px;
      border-bottom: 2px solid #3498db;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""


def get_empty_html():
    block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        No Papers Today. Take a Rest!
    </td>
  </tr>
  </table>
  """
    return block_template


def get_stats_html(papers: list[ArxivPaper], debug_info: dict[str, Any]):
    stats_parts = []
    stats_parts.append("<div style='font-family: Arial, sans-serif; margin-bottom: 24px;'>")
    stats_parts.append("<h3>Statistics:</h3>")
    stats_parts.append("<ul>")
    stats_parts.append(f"<li>Min Score: {debug_info['min_score']:.2f}</li>")
    stats_parts.append(f"<li>Max Score: {debug_info['max_score']:.2f}</li>")
    stats_parts.append(f"<li>Threshold: {debug_info['threshold']}</li>")
    stats_parts.append(f"<li>Matching Papers: {len(papers)} / {debug_info['papers_considered']}</li>")
    stats_parts.append("</ul>")
    stats_parts.append("</div>")
    return "".join(stats_parts)


def get_toc_html(
    papers_by_section: dict[str | None, list[ArxivPaper]],
    debug_info: dict[str | None, dict],
    global_debug_info: dict[str, Any],
):
    """Generate Table of Contents with debug information."""
    toc_parts = []
    toc_parts.append("<div style='font-family: Arial, sans-serif; margin-bottom: 24px;'>")
    toc_parts.append("<h3>Table of Contents:</h3>")

    # Create table structure
    toc_parts.append("""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; font-size: 14px;">
        <thead>
            <tr style="background-color: #f5f5f5;">
                <th style="text-align: left; padding: 10px;">Tag</th>
                <th style="text-align: center; padding: 10px;">Min Score</th>
                <th style="text-align: center; padding: 10px;">Max Score</th>
                <th style="text-align: center; padding: 10px;">Threshold</th>
                <th style="text-align: center; padding: 10px;">Matching</th>
            </tr>
        </thead>
        <tbody>
    """)

    threshold = global_debug_info["threshold"]
    papers_considered = global_debug_info["papers_considered"]

    for section_name in sorted(papers_by_section.keys()):
        papers = papers_by_section.get(section_name, [])
        matching_papers = len(papers)
        section_debug = debug_info.get(section_name, {}) if debug_info else {}

        # Get debug info values
        min_score = section_debug["min_score"]
        max_score = section_debug["max_score"]

        # Create table row
        toc_parts.append("<tr>")

        # Tag column - with link if there are matching papers
        if matching_papers == 0:
            toc_parts.append(f'<td style="padding: 8px;">{section_name}</td>')
        else:
            section_id = section_name.lower().replace(" ", "-").replace("_", "-")
            toc_parts.append(f'<td style="padding: 8px;"><a href="#{section_id}">{section_name}</a></td>')

        # Other columns
        toc_parts.append(f'<td style="text-align: center; padding: 8px;">{min_score:.2f}</td>')
        toc_parts.append(f'<td style="text-align: center; padding: 8px;">{max_score:.2f}</td>')
        toc_parts.append(f'<td style="text-align: center; padding: 8px;">{threshold}</td>')
        toc_parts.append(f'<td style="text-align: center; padding: 8px;">{matching_papers} / {papers_considered}</td>')

        toc_parts.append("</tr>")

    toc_parts.append("</tbody>")
    toc_parts.append("</table>")
    toc_parts.append("</div>")

    return "".join(toc_parts)


def get_section_header_html(section_name: str):
    section_id = section_name.lower().replace(" ", "-").replace("_", "-")
    return f'<div class="section-header" id="{section_id}">{section_name}</div>'


def get_block_html(
    title: str,
    authors: str,
    score: float,
    arxiv_id: str,
    abstract: str,
    pdf_url: str,
):
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {title}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 8px 0;">
            {authors}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Score:</strong> {score:.2f}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>arXiv ID:</strong> {arxiv_id}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Abstract:</strong> {abstract}
        </td>
    </tr>

    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">PDF</a>
        </td>
    </tr>
</table>
"""
    return block_template.format(
        title=title,
        authors=authors,
        score=score,
        arxiv_id=arxiv_id,
        abstract=abstract,
        pdf_url=pdf_url,
    )


def render_email(
    papers_by_tag: dict[str | None, list[ArxivPaper]],
    debug_info: dict[str | None, dict],
    global_debug_info: dict[str, Any],
):
    all_parts = []
    total_papers = sum(len(papers) for papers in papers_by_tag.values())
    use_sections = global_debug_info["use_sections"]

    if total_papers == 0:
        if debug_info:
            empty_content = get_stats_html(papers_by_tag[None], debug_info[None] | global_debug_info) + get_empty_html()
            return framework.replace("__CONTENT__", empty_content)
        return framework.replace("__CONTENT__", get_empty_html())

    if use_sections:
        all_parts.append(get_toc_html(papers_by_tag, debug_info, global_debug_info))
    else:
        all_parts.append(get_stats_html(papers_by_tag[None], debug_info[None] | global_debug_info))

    for section_name, papers in papers_by_tag.items():
        if not papers:
            continue

        section_parts = []

        # Add section header only if using sections
        if use_sections:
            section_parts.append(get_section_header_html(section_name))

        for p in papers:
            authors = [a.name for a in p.authors[:5]]
            authors = ", ".join(authors)
            if len(p.authors) > 5:
                authors += ", ..."
            section_parts.append(get_block_html(p.title, authors, p.score, p.arxiv_id, p.summary, p.pdf_url))

        all_parts.extend(section_parts)

    content = "<br>" + "</br><br>".join(all_parts) + "</br>"
    return framework.replace("__CONTENT__", content)


def send_email(
    sender: str,
    receiver: str,
    password: str,
    smtp_server: str,
    smtp_port: int,
    html: str,
):
    def _format_addr(s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, "utf-8").encode(), addr))

    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = _format_addr(f"Github Action <{sender}>")
    msg["To"] = _format_addr(f"You <{receiver}>")
    today = datetime.datetime.now().strftime("%Y/%m/%d")
    msg["Subject"] = Header(f"Daily arXiv {today}", "utf-8").encode()

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
    except Exception as e:
        logger.warning(f"Failed to use TLS. {e}")
        logger.warning("Try to use SSL.")
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)

    server.login(sender, password)
    server.sendmail(sender, [receiver], msg.as_string())
    server.quit()
