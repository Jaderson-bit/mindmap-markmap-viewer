#!/usr/bin/env python3
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
from pathlib import Path


# Vendored markmap stack (pinned exact versions; see assets/vendor/). Loaded as
# local files so the generated map opens OFFLINE -- no CDN, no network request.
# Order matters: d3 is a global peer of markmap-view; lib/toolbar augment the
# same `window.markmap` namespace.
_VENDOR_JS = ("d3.min.js", "markmap-view.min.js", "markmap-lib.min.js", "markmap-toolbar.min.js")
_VENDOR_CSS = "markmap-toolbar.min.css"


def _default_vendor_uri() -> str:
    """file:// URI of this skill's bundled `assets/vendor/` directory.

    Used as the default `vendor` prefix so a standalone build_html() call opens
    offline on THIS machine with no extra setup ("referenciar localmente"). For a
    portable/shareable bundle, write_mindmap() copies the folder next to the HTML
    and you point `vendor` at the relative "vendor" path instead."""
    return (Path(__file__).resolve().parent.parent / "assets" / "vendor").as_uri()


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
# Browser-side init (plain JS constant -> no f-string brace escaping). Reads the
# Markdown from #markmap-source.textContent (the browser decodes the HTML escapes
# losslessly), transforms it in-browser, and wires up the toolbar.
_INIT_JS = r"""
(function () {
  var M = window.markmap;
  var svg = document.getElementById("markmap");
  var srcEl = document.getElementById("markmap-source");
  if (!M || !M.Markmap || !M.Transformer) {
    document.body.insertAdjacentHTML("beforeend",
      '<p style="color:#ff8a8a;font-family:system-ui,sans-serif;padding:1rem">' +
      "Could not load the markmap libraries. Keep the <code>vendor/</code> folder " +
      "next to this HTML file so the map can open offline.</p>");
    return;
  }
  var transformer = new M.Transformer();
  var result = transformer.transform(srcEl.textContent);
  var fm = result.frontmatter || {};
  var mm = M.Markmap.create(svg, M.deriveOptions(fm.markmap), result.root);

  function setFold(node, fold) {
    node.payload = Object.assign({}, node.payload, { fold: fold });
    (node.children || []).forEach(function (c) { setFold(c, fold); });
  }
  // Re-render WITHOUT re-initializing. setData(DATA) re-runs the internal data
  // init, which re-derives every node's fold from initialExpandLevel and would
  // wipe the manual fold set below. setData() with NO arg keeps state.data
  // (our mutated fold) and just re-renders.
  function rerender() { return Promise.resolve(mm.setData()).then(function () { mm.fit(); }); }

  if (window.__MM_TOOLBAR__ !== false && M.Toolbar) {
    // Material "unfold_more"/"unfold_less" icons; built via Toolbar.icon (a DOM
    // node) like the built-in items -- a plain HTML string would render as text.
    var UNFOLD_MORE = "M12 5.83L15.17 9l1.41-1.41L12 3 7.41 7.59 8.83 9 12 5.83zm0 12.34L8.83 15l-1.41 1.41L12 21l4.59-4.59L15.17 15 12 18.17z";
    var UNFOLD_LESS = "M7.41 18.59L8.83 20 12 16.83 15.17 20l1.41-1.41L12 14l-4.59 4.59zm9.18-13.18L15.17 4 12 7.17 8.83 4 7.41 5.41 12 10l4.59-4.59z";
    var tb = M.Toolbar.create(mm);
    tb.setBrand(false);
    tb.register({
      id: "expandAll", title: "Expand all", content: M.Toolbar.icon(UNFOLD_MORE),
      onClick: function () { setFold(mm.state.data, 0); rerender(); }
    });
    tb.register({
      id: "collapseAll", title: "Collapse all", content: M.Toolbar.icon(UNFOLD_LESS),
      onClick: function () { (mm.state.data.children || []).forEach(function (c) { setFold(c, 1); }); rerender(); }
    });
    tb.setItems(["zoomIn", "zoomOut", "fit", "expandAll", "collapseAll"]);
    var el = tb.render();
    el.style.position = "fixed";
    el.style.right = "14px";
    el.style.bottom = "14px";
    document.body.appendChild(el);
  }
})();
"""


def build_html(src: str, height: int = 850, background: str = "#0e1117",
               vendor: str = None, toolbar: bool = True) -> str:
    """Return a self-contained HTML document that renders `src` as a markmap with
    a WHITE font, loading the markmap stack from LOCAL vendored files so the map
    opens OFFLINE -- no CDN, no network request.

    `vendor` is the URL/path prefix for the `<script src>`/`<link>` tags. It
    defaults to this skill's bundled `assets/vendor/` (a file:// URI), so a
    standalone call works offline on this machine immediately. For a portable
    bundle, pass a relative prefix (e.g. "vendor") and ship that folder beside the
    HTML -- write_mindmap() does this for you.

    `background` defaults to a dark color because the white font is INVISIBLE on a
    light surface. Standalone HTML opens on the browser's white default, so the
    renderer must paint its own dark backdrop. Pass background="transparent" only
    when you KNOW the host is already dark and want the map to blend into it.

    `src` is HTML-escaped before it goes in the source div. The browser decodes
    the div's textContent back to the original characters -- so escaping
    round-trips losslessly while stopping any `<`, `>`, or `&` in the outline
    (e.g. `</div>`, `List<String>`) from breaking out of the div and truncating
    the map. `toolbar=False` renders without the navigation toolbar.
    """
    if vendor is None:
        vendor = _default_vendor_uri()
    vendor = str(vendor).rstrip("/")
    safe = html.escape(str(src), quote=False)
    scripts = "\n".join('<script src="%s/%s"></script>' % (vendor, f) for f in _VENDOR_JS)
    return (
        "<!doctype html>\n"
        '<meta charset="utf-8">\n'
        f'<link rel="stylesheet" href="{vendor}/{_VENDOR_CSS}">\n'
        "<style>\n"
        f"  html, body {{ margin:0; padding:0; background: {background}; }}\n"
        f"  #markmap {{ width:100%; height:{height - 12}px; display:block; }}\n"
        "  /* === WHITE FONT (style BOTH the SVG <text> and the <foreignObject> HTML) === */\n"
        "  svg.markmap text { fill: #ffffff !important; }\n"
        "  svg.markmap foreignObject, svg.markmap foreignObject * { color: #ffffff !important; }\n"
        "  svg.markmap a { color: #7fd1ff !important; }\n"
        "  svg.markmap code { color: #ffd479 !important; background: rgba(255,255,255,.08); }\n"
        "</style>\n"
        '<svg id="markmap" class="markmap"></svg>\n'
        f'<div id="markmap-source" style="display:none">{safe}</div>\n'
        f"<script>window.__MM_TOOLBAR__ = {'true' if toolbar else 'false'};</script>\n"
        f"{scripts}\n"
        f"<script>{_INIT_JS}</script>\n"
    )


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
