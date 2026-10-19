#!/usr/bin/env python3
"""Validate product documentation structure and relative links."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCT_DIR = ROOT / "docs" / "product"
REQUIRED_DOCS = [
    PRODUCT_DIR / "README.md",
    PRODUCT_DIR / "intraday-heatmap.md",
    PRODUCT_DIR / "templates" / "module-product-doc.md",
]
REQUIRED_HEADINGS = [
    "产品目标与非目标",
    "用户与使用场景",
    "输入参数与默认值",
    "输出内容与页面结构",
    "指标口径",
    "数据源、缓存与数据快照",
    "验证方法论",
    "API 契约",
    "交互流程与状态",
    "边界条件与已知限制",
    "性能预算与失败处理",
    "验收标准",
    "变更记录与相关文档",
]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def check_required_files(errors: list[str]) -> None:
    for path in REQUIRED_DOCS:
        if not path.exists():
            errors.append(f"missing required document: {path.relative_to(ROOT)}")


def check_headings(errors: list[str]) -> None:
    path = PRODUCT_DIR / "intraday-heatmap.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"{path.relative_to(ROOT)} missing heading: {heading}")


def check_links(errors: list[str]) -> None:
    for path in [PRODUCT_DIR / "README.md", PRODUCT_DIR / "intraday-heatmap.md"]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for target in LINK_PATTERN.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#", 1)[0]
            resolved = (path.parent / clean).resolve()
            if not resolved.exists():
                errors.append(
                    f"{path.relative_to(ROOT)} broken relative link: {target}"
                )


def check_rules(errors: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        text = agents.read_text(encoding="utf-8")
        if "产品文档" not in text:
            errors.append("AGENTS.md missing product documentation rule")
        if "同一提交" not in text:
            errors.append("AGENTS.md missing same-commit product doc rule")
    pr = ROOT / ".github" / "pull_request_template.md"
    if not pr.exists():
        errors.append("missing .github/pull_request_template.md")
    elif "产品文档" not in pr.read_text(encoding="utf-8"):
        errors.append("PR template missing product documentation checklist")


def main() -> int:
    errors: list[str] = []
    check_required_files(errors)
    check_headings(errors)
    check_links(errors)
    check_rules(errors)
    if errors:
        print("product-doc-check: failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("product-doc-check: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
