"""
Reusable helpers to render and manipulate markmap.js mind maps from Markdown.

Framework-agnostic:
    build_html(src, height, background)     -> full HTML string (white font on dark bg)
    set_expand_level(src, level)            -> set initialExpandLevel in the frontmatter
    filter_markmap(src, query)              -> (filtered_src, n_matches); match + ancestors + descendants
    _norm(s)                                -> accent-insensitive, lowercased string

Streamlit (optional):
    render_markmap(src, height, background) -> embeds build_html() via st.components iframe
"""

import html
import re
import unicodedata


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def build_html(src: str, height: int = 850, background: str = "#0e1117") -> str:
    """Return a self-contained HTML document that renders `src` as a markmap
    with a WHITE font, using the markmap-autoloader from a CDN.

    `background` defaults to a dark color (Streamlit's dark-theme bg) because the
    white font is INVISIBLE on a light surface. Standalone HTML opens on the
    browser's white default, so the renderer must paint its own dark backdrop.
    Pass background="transparent" only when you KNOW the host is already dark and
    you want the map to blend into it seamlessly.

    `src` is HTML-escaped before it goes in the <div>. The autoloader reads the
    Markdown from the div's textContent, which the browser decodes back to the
    original characters -- so escaping round-trips losslessly while stopping any
    `<`, `>`, or `&` in the outline (e.g. `</div>`, `List<String>`) from breaking
    out of the div and silently truncating the map.
    """
    safe = html.escape(str(src), quote=False)
    # CDN pinned to the 0.18 minor (patch releases still float). @latest can ship
    # breaking autoloader API changes; bump the minor deliberately after testing.
    return f"""<!doctype html>
<meta charset="utf-8">
<style>
  html, body {{ margin:0; padding:0; background: {background}; }}
  svg.markmap {{ width: 100%; height: {height - 12}px; }}
  /* === WHITE FONT (style BOTH the SVG <text> and the <foreignObject> HTML) === */
  svg.markmap text {{ fill: #ffffff !important; }}
  svg.markmap foreignObject,
  svg.markmap foreignObject * {{ color: #ffffff !important; }}
  svg.markmap a {{ color: #7fd1ff !important; }}
  svg.markmap code {{ color: #ffd479 !important; background: rgba(255,255,255,.08); }}
</style>
<script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.18"></script>
<div class="markmap">{safe}</div>
"""


def render_markmap(src: str, height: int = 850, background: str = "#0e1117"):
    """Embed build_html() inside Streamlit (isolated iframe). The iframe carries
    its own dark background by default, so the map stays readable even under a
    light Streamlit theme; pass background="transparent" to blend into a dark host."""
    import streamlit.components.v1 as components
    components.html(build_html(src, height, background), height=height, scrolling=True)


# --------------------------------------------------------------------------- #
# Expand level
# --------------------------------------------------------------------------- #
def set_expand_level(src: str, level: int) -> str:
    """Set `initialExpandLevel` in the markmap frontmatter. level = -1 expands all.

    Every edit is scoped to the leading `---...---` frontmatter block, so body
    prose that merely mentions "initialExpandLevel" is never rewritten. Injection
    happens IN PLACE; a fresh frontmatter block is prepended only when the source
    has no frontmatter at all -- never stacked on top of an existing one (which
    would yield two `---` blocks, of which markmap reads only the first)."""
    src = str(src)
    directive = f"initialExpandLevel: {level}"

    fm_match = re.match(r"\A---\n.*?\n---\n", src, re.DOTALL)
    if not fm_match:
        # No frontmatter at all -> create a minimal one.
        return f"---\nmarkmap:\n  {directive}\n---\n\n{src}"

    fm = fm_match.group(0)
    rest = src[fm_match.end():]

    # 1) Rewrite an existing directive (the common case).
    new_fm, n = re.subn(r"initialExpandLevel:\s*-?\d+", directive, fm)
    if n:
        return new_fm + rest

    # 2) Inject under a block-style `markmap:` key, preserving its indentation.
    new_fm, n = re.subn(
        r"^([ \t]*)markmap:[ \t]*\n",
        rf"\g<1>markmap:\n\g<1>  {directive}\n",
        fm, count=1, flags=re.MULTILINE,
    )
    if n:
        return new_fm + rest

    # 3) Merge into an inline-mapping `markmap: { ... }` key.
    def _merge_inline(m):
        inner = m.group(2).strip()
        body = directive + (", " + inner if inner else "")
        return f"{m.group(1)}{{{body}}}"

    new_fm, n = re.subn(
        r"^([ \t]*markmap:[ \t]*)\{(.*?)\}[ \t]*$",
        _merge_inline, fm, count=1, flags=re.MULTILINE,
    )
    if n:
        return new_fm + rest

    # 4) Frontmatter exists but has no markmap: key -> insert a block just inside
    #    the opening fence, rather than stacking a second frontmatter document.
    new_fm = re.sub(r"\A---\n", f"---\nmarkmap:\n  {directive}\n", fm, count=1)
    return new_fm + rest


# --------------------------------------------------------------------------- #
# Search / filter
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Lowercase and strip accents (Unicode NFD) for robust matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower()


# A list item: dash/star/plus, or an ordered marker like "1." / "1)".
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)]) (.*)$")


def filter_markmap(src: str, query: str):
    """Keep nodes matching `query` + their ancestors (path to root) + their
    descendants (subtree). Returns (filtered_src, n_matches). Forces expand-all.

    Hierarchy is reconstructed into an explicit parent tree, which fixes three
    ways a flat depth-integer goes wrong: a heading is never mistaken for a child
    of a bullet (heading `#`-rank and bullet indent live in one number space);
    tabs and 2-/4-space indents map to the same level (`expandtabs`); and
    `*`/`+`/numbered markers count as nodes just like `-`."""
    src = str(src)
    fm, body = "", src
    fm_match = re.match(r"\A---\n.*?\n---\n", src, re.DOTALL)
    if fm_match:
        fm = fm_match.group(0)
        body = src[fm_match.end():]

    q = _norm(query)
    kinds, levels, lines, matched = [], [], [], []
    last_h = 0
    for line in body.split("\n"):
        if not line.strip():
            continue
        if line.startswith("#"):  # heading: level = number of leading '#'
            rank = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            last_h = rank
            kinds.append("h")
            levels.append(rank)
        else:  # list item: level relative to the last heading + indentation
            m = _BULLET.match(line)
            if not m:
                continue
            indent = len(m.group(1).expandtabs(2)) // 2
            text = m.group(2)
            kinds.append("b")
            levels.append(last_h + 1 + indent)
        lines.append(line)
        matched.append(q in _norm(text))

    n = len(lines)

    # Assign each node a parent via a kind-aware stack. A heading pops back to the
    # nearest shallower heading (clearing any open bullets), so a heading is never
    # parented to a bullet even when its '#'-rank happens to exceed a bullet level.
    # A bullet pops nodes at its level-or-deeper but stops at its governing heading.
    parent = [None] * n
    stack = []
    for i in range(n):
        if kinds[i] == "h":
            while stack and not (kinds[stack[-1]] == "h" and levels[stack[-1]] < levels[i]):
                stack.pop()
        else:
            while stack and levels[stack[-1]] >= levels[i]:
                stack.pop()
        parent[i] = stack[-1] if stack else None
        stack.append(i)

    keep = [False] * n
    matches = 0
    # Each match: keep it and walk up marking its ancestors (path to the root).
    for i in range(n):
        if matched[i]:
            matches += 1
            j = i
            while j is not None and not keep[j]:
                keep[j] = True
                j = parent[j]
    # Descendants: keep any node that has a matched ancestor (its whole subtree).
    for i in range(n):
        if keep[i]:
            continue
        j = parent[i]
        while j is not None:
            if matched[j]:
                keep[i] = True
                break
            j = parent[j]

    # Emit kept lines, with a blank after each heading so adjacent branches don't
    # run together when bullets follow immediately.
    out = []
    for i in range(n):
        if not keep[i]:
            continue
        out.append(lines[i])
        if kinds[i] == "h":
            out.append("")
    filtered = (fm + "\n" + "\n".join(out)) if fm else "\n".join(out)
    return set_expand_level(filtered, -1), matches
