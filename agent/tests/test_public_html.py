from src.product.public_html import is_public_html_path, render_public_html


INDEX = """<!doctype html><html><head><title>Old</title><meta name="description" content="old" /></head><body><div id="root"></div><script src="/assets/app.js"></script></body></html>"""


def test_public_route_allowlist_excludes_private_apps():
    assert is_public_html_path("/")
    assert is_public_html_path("/stock/600519.SH")
    assert is_public_html_path("/docs/data-hub/quickstart")
    assert not is_public_html_path("/me")
    assert not is_public_html_path("/account")
    assert not is_public_html_path("/agent")


def test_renderer_injects_route_metadata_and_escapes_path_values():
    html = render_public_html(INDEX, "/stock/%3Cscript%3Ealert(1)%3C/script%3E", "https://sigmx.cn")
    assert "SigmX 个股研究" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert 'rel="canonical"' in html
    assert 'application/ld+json' in html
    assert "/assets/app.js" in html
