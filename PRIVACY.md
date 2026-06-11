# Privacy Policy — mindmap-markmap-viewer

_Last updated: 2026-06-09_

**Short version: this plugin collects nothing, sends nothing, and phones home to no one.**

## What the plugin does

mindmap-markmap-viewer turns Markdown text into an interactive mind map. All processing happens **locally on your machine**, using the Python standard library and JavaScript libraries (markmap.js, d3) that are **bundled inside the plugin** at pinned versions.

## Data collection

- **No data is collected.** The plugin has no telemetry, no analytics, no account, and no server component.
- **No network requests.** The generated HTML inlines all of its dependencies; it opens fully offline. The plugin itself makes zero network calls at generation time and at viewing time.
- **Your content stays yours.** The Markdown you map and the HTML/SVG/PNG files produced are written only to the output location you choose on your own machine. Nothing is uploaded anywhere by this plugin.

## Third parties

- There are none. No CDN, no external API, no third-party service is contacted by the plugin or by the files it generates.
- The bundled open-source libraries (d3 — ISC; markmap — MIT) are static local files; their provenance and exact versions are documented in [`assets/vendor/README.md`](assets/vendor/README.md).

## Claude itself

When you use this plugin through Claude (Claude Code or the Claude app), the content you ask Claude to process is handled under [Anthropic's own privacy policy](https://www.anthropic.com/legal/privacy). This plugin adds no data handling on top of that.

## Contact

Questions: open an issue at <https://github.com/Jaderson-bit/mindmap-markmap-viewer/issues> or e-mail <jadersonmv@gmail.com>.
