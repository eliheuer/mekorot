# Sources

Active Google Fonts build inputs:

- `Mekorot.designspace`
- `Mekorot-Regular.ufo`
- `Mekorot-ExtraBold.ufo`
- `Mekorot-Italic.designspace`
- `Mekorot-Italic.ufo`
- `Mekorot-ExtraBoldItalic.ufo`

The active source path is designspace/UFO so the family can be edited in
Runebender and built through the Google Fonts workflow. Historical Glyphs
snapshots live in `archive/` and are not active build inputs.

Font engineering notes:

- The Latin glyphs are forked from Crimson Pro.
- Active sources use a 1024 UPM grid.
- Arabic/Perso-Arabic glyphs were merged from Open Gate Naskh with
  `scripts/merge_open_gate_naskh_arabic.py`; see
  `documentation/arabic-merge-notes.md`.
