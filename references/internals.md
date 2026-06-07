# Internals

How the three helpers in [`scripts/render_markmap.py`](../scripts/render_markmap.py) work, and the non-obvious decisions behind them. Read this when changing the renderer, the frontmatter handling, or the search filter.

## Pipeline

```
source.md  ──►  filter / set expand level  ──►  build_html()  ──►  markmap-autoloader (CDN)  ──►  SVG
 (outline)        (manipulate the text)          (HTML + CSS)        (JS in an iframe)            (screen)
```

Everything is done by **manipulating the Markdown text** and then handing it to markmap's autoloader. There is no call into the markmap JS API — expansion and search are pure text transforms, which keeps the skill framework-agnostic and trivial to test.

## `build_html(src, height, background)`

Produces a self-contained HTML document: an inline `<style>`, the `markmap-autoloader` `<script>`, and a single `<div class="markmap">` holding the Markdown.

Three things here are load-bearing:

1. **White font needs two selectors.** markmap draws labels as SVG `<text>` *and*, for richer nodes, as `<foreignObject>` HTML. Styling only one leaves half the labels dark. Both are forced with `!important`:
   ```css
   svg.markmap text { fill: #ffffff !important; }
   svg.markmap foreignObject, svg.markmap foreignObject * { color: #ffffff !important; }
   ```
2. **Dark background travels with the white font.** White on white is invisible — the most common "renders blank" report. A standalone file opens on the browser's white default, and a Streamlit `components.html` iframe is white by default too; neither inherits the host's dark theme. So `build_html` paints its own dark backdrop (`#0e1117`) unless you explicitly pass `background="transparent"` for a host you know is dark.
3. **The source is HTML-escaped (`html.escape`, `quote=False`).** The autoloader reads the Markdown from the div's `textContent`, which the browser decodes back to the original characters — so escaping round-trips losslessly. Without it, a `</div>`, `List<String>`, or `&` in the outline breaks out of the div and silently truncates the map. Escaping the three structural characters fixes that while leaving the Markdown markmap sees byte-identical.

The CDN is pinned to the `@0.18` minor (patch releases still float). `@latest` can ship breaking autoloader changes; bump the minor deliberately after testing.

## `set_expand_level(src, level)`

Sets `initialExpandLevel` in the frontmatter. `level` 1/2/3 expands that many levels; `-1` expands everything.

All edits are **scoped to the leading `---...---` frontmatter block** and applied **in place**. The function tries four branches in order:

1. Rewrite an existing `initialExpandLevel` directive (the common case).
2. Inject under a block-style `markmap:` key, preserving its indentation.
3. Merge into an inline-mapping `markmap: { ... }` key.
4. Insert a fresh `markmap:` block just inside the opening fence when the frontmatter has no markmap key.

A minimal frontmatter is prepended **only** when the source has none at all.

Why the care: a naive `re.sub` over the whole document has two failure modes that this design avoids — it rewrites the literal string `initialExpandLevel:` if it appears in *body prose*, and it stacks a **second** `---` block on top of existing frontmatter. markmap reads only the first frontmatter block, so a stacked block silently drops the user's other settings (`colorFreezeLevel`, `maxWidth`, …).

## `filter_markmap(src, query)`

Returns `(filtered_src, n_matches)`. Keeps every node that **matches** the query, plus its **ancestors** (path to root) and its **descendants** (subtree), then forces expand-all so the result is fully visible. Matching is accent-insensitive via `_norm` (Unicode NFD strips combining marks).

The subtlety is ancestry. Heading level (`#`-rank) and list-item level (`last_heading + 1 + indent`) share one integer space, so a flat depth comparison mis-nests structure — e.g. an `H4` that follows a bullet gets a larger number than the bullet and is wrongly treated as its child. The fix is to build an **explicit parent tree** with a *kind-aware* stack:

- A **heading** pops the stack back to the nearest shallower *heading* (clearing any open bullets), so a heading is never parented to a bullet regardless of raw numbers.
- A **bullet** pops nodes at its level-or-deeper but stops at its governing heading.

Two more parsing details matter: indentation is measured after `expandtabs(2)` so a tab counts as one level (not zero from `1 // 2`), and the list-item regex accepts `-`, `*`, `+`, and ordered markers (`1.` / `1)`) — markmap renders all of these, so search must recognize all of them or it silently wipes the tree on the first query.

## Tests

[`evals/test_render_markmap.py`](../evals/test_render_markmap.py) is a dependency-free regression suite (stdlib only). Each check is labeled with the finding it locks down (see [lessons.md](lessons.md)). Run it from the skill root:

```bash
python evals/test_render_markmap.py
```
