from pathlib import Path

from tools.check_web_runtime_mocks import scan_runtime_mocks


def test_detects_runtime_demo_copy_and_business_arrays_but_ignores_tests(tmp_path: Path) -> None:
    page_dir = tmp_path / "frontend" / "src" / "pages"
    page_dir.mkdir(parents=True)
    (page_dir / "Page.tsx").write_text(
        'const rows = [{name: "虚构公司", score: 88}];\n<span>演示数据</span>\n',
        encoding="utf-8",
    )
    test_dir = page_dir / "__tests__"
    test_dir.mkdir()
    (test_dir / "Page.test.tsx").write_text(
        'const rows = [{name: "测试公司"}];\n演示数据\n', encoding="utf-8"
    )

    violations = scan_runtime_mocks(tmp_path)

    assert {item.reason for item in violations} == {
        "demo-marker",
        "page-business-array",
    }
    assert {item.path.name for item in violations} == {"Page.tsx"}


def test_allows_navigation_options_and_product_copy(tmp_path: Path) -> None:
    page_dir = tmp_path / "frontend" / "src" / "components"
    page_dir.mkdir(parents=True)
    (page_dir / "Navigation.tsx").write_text(
        'const links = [{to: "/", label: "首页"}];\nconst options = [10, 20, 50];\n',
        encoding="utf-8",
    )

    assert scan_runtime_mocks(tmp_path) == []
