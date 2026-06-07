#!/usr/bin/env python3
"""Regression suite for mindmap-markmap-viewer.

Run from anywhere:  python evals/test_render_markmap.py
Each block names the adversarial-review finding(s) it locks down. Exit code is
non-zero if any check fails, so this doubles as a CI gate.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from render_markmap import build_html, set_expand_level, filter_markmap, _norm  # noqa: E402

ok = True


def check(name, cond):
    global ok
    print(("PASS" if cond else "FAIL"), "-", name)
    ok = ok and cond


def fences(s):
    """Count '---' fence lines (a single frontmatter block has exactly 2)."""
    return sum(1 for ln in s.split("\n") if ln.strip() == "---")


# ===== build_html: HTML escaping (#9 </div>, #10 raw <,>,&) =====
h = build_html("# T\n- close with </div>\n- second")
check("#9 </div> in source does not create a second closing div",
      h.count("</div>") == 1 and "&lt;/div&gt;" in h)
h2 = build_html("# List<String> generic & <b>bold</b>")
check("#10 raw <,>,& escaped, not emitted literally",
      "List&lt;String&gt;" in h2 and "List<String>" not in h2 and "&amp;" in h2)
check("dark background by default", "background: #0e1117;" in build_html("- x"))
check("background override to transparent",
      "background: transparent;" in build_html("- x", background="transparent"))
check("CDN pinned @0.18, not @latest",
      "markmap-autoloader@0.18" in build_html("- x") and "@latest" not in build_html("- x"))
check("white-font text + foreignObject selectors present",
      "svg.markmap text { fill: #ffffff !important; }" in h and "foreignObject *" in h)

# ===== set_expand_level: frontmatter-scoped, in-place injection =====
common = "---\nmarkmap:\n  initialExpandLevel: 1\n  maxWidth: 380\n---\n# Root"
out = set_expand_level(common, -1)
check("rewrite existing directive (common path)",
      "initialExpandLevel: -1" in out and fences(out) == 2 and "maxWidth: 380" in out)

out = set_expand_level("---\ntitle: foo\n---\n\n# Root", 1)
check("#1 frontmatter without markmap key stays a single block",
      fences(out) == 2 and "title: foo" in out and "initialExpandLevel: 1" in out)

out = set_expand_level("---\nmarkmap: {colorFreezeLevel: 2}\n---\n\n# Root", 2)
check("#2 inline markmap mapping merged, colorFreezeLevel kept",
      fences(out) == 2 and "colorFreezeLevel: 2" in out
      and "initialExpandLevel: 2" in out and out.count("markmap:") == 1)

out = set_expand_level("---\nmarkmap:\n  colorFreezeLevel: 2\n---\n\n# Notes\n- set initialExpandLevel: 0 to collapse", 3)
check("#3 body prose 'initialExpandLevel: 0' untouched",
      "initialExpandLevel: 0 to collapse" in out and "initialExpandLevel: 3" in out and fences(out) == 2)

out = set_expand_level("---\n  markmap:\n    colorFreezeLevel: 2\n---\n\n# Root", 3)
check("#4 indented markmap key injected in place (single block)",
      fences(out) == 2 and "initialExpandLevel: 3" in out)

out = set_expand_level("# Root\n## B", -1)
check("no-frontmatter -> prepend minimal frontmatter",
      out.startswith("---\nmarkmap:\n  initialExpandLevel: -1") and "# Root" in out)

twice = set_expand_level(set_expand_level("# Root", 1), 3)
check("idempotent (one directive after re-run)",
      twice.count("initialExpandLevel") == 1 and "initialExpandLevel: 3" in twice)

# ===== filter_markmap: hierarchy =====
filt, n = filter_markmap("# Root\n- a\n\t- b match\n", "b match")
check("#5 tab-indented child keeps its real parent '- a'",
      "- a" in filt and "\t- b match" in filt and n == 1)

filt, n = filter_markmap("# Title\n## A\n- a1 match\n#### C\n- c1\n", "a1")
check("#6 matched bullet a1 excludes the later #### C heading subtree",
      "- a1 match" in filt and "#### C" not in filt and "- c1" not in filt)

filt2, _ = filter_markmap("# Title\n## A\n- a1\n#### C\n- c1\n", "C")
check("#6b heading C (a section under A) keeps C and its child",
      "#### C" in filt2 and "- c1" in filt2)

filt, n = filter_markmap("# Root\n## Branch\n* Star matchme\n1. Num matchme\n+ Plus matchme\n", "matchme")
check("#12 *, numbered, and + markers all searchable",
      n == 3 and "* Star matchme" in filt and "1. Num matchme" in filt and "+ Plus matchme" in filt)

classic = ("---\nmarkmap:\n  initialExpandLevel: 1\n---\n"
           "# Root\n## Branch A\n- leaf a1\n## Branch B\n- leaf b1\n  - deep b1\n- leaf b2\n## Branch C\n- leaf c1\n")
filt, n = filter_markmap(classic, "leaf b1")
check("regression: keeps Root + Branch B + matched subtree",
      "# Root" in filt and "## Branch B" in filt and "- leaf b1" in filt and "  - deep b1" in filt)
check("regression: excludes sibling branches A and C",
      "Branch A" not in filt and "leaf a1" not in filt and "Branch C" not in filt and "leaf c1" not in filt)
check("regression: forces expand-all", "initialExpandLevel: -1" in filt)

filt, n = filter_markmap("# Root\n- Compliância fiscal\n", "compliancia")
check("accent-insensitive search matches 'Compliância'", n == 1)
check("_norm strips accents", _norm("COMPLIÂNCIA") == "compliancia")

filt, n = filter_markmap("", "anything")
check("#8 empty input -> 0 matches (documented blank-canvas)", n == 0)

# ===== example.md renders into a markmap div =====
with open(os.path.join(HERE, "..", "assets", "example.md"), encoding="utf-8") as f:
    example = f.read()
rendered = build_html(set_expand_level(example, 1))
check("example.md builds a non-empty markmap document",
      '<div class="markmap">' in rendered and "Branch A" in rendered)

print("\n=> ALL PASSED" if ok else "\n=> SOME FAILED")
sys.exit(0 if ok else 1)
