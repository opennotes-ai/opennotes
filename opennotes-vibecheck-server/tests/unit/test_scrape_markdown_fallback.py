from __future__ import annotations

from src.routes.scrape import _markdown_fallback_from_html


def test_markdown_fallback_excludes_stylesheet_content() -> None:
    html = (
        "<html><head>"
        "<link rel='stylesheet' href='https://cdn.example.com/article.css'>"
        "<style>.hero{width:200px;height:150px}</style>"
        "<script>alert('x')</script>"
        "</head><body><h1>Article title</h1><p>Article body</p></body></html>"
    )

    markdown = _markdown_fallback_from_html(html)

    assert "Article title" in markdown
    assert "Article body" in markdown
    assert "hero" not in markdown
    assert "width" not in markdown
    assert "article.css" not in markdown
    assert "alert" not in markdown
