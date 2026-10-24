# Attribution — medical-ppt-design (CC BY 4.0)

Layout geometry for FactDeck Template Library v1 (cover, section divider, and
key-points / pillar-card slot packs) is adapted from:

**medical-ppt-design**  
https://github.com/grotyx/medical-ppt-design  
License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)

Creator / source project: medical-ppt-design (Spine division academic medical
presentation system, originally described for SNUBH).

## Modifications in this adaptation

- **SNUBH branding removed.** No hospital logo, presenter defaults, affiliation
  strings, or institutional names are shipped or required. Logo slots are
  optional client brand only.
- **Color system replaced.** Starbucks / House-Green tokens are not used at
  runtime. Theme tokens come from FactDeck's journal (医学期刊风) and steel
  (临床会议风) academic palettes.
- **Typography.** FactDeck keeps Microsoft YaHei / Noto Sans CJK as the Chinese
  podium stack; Pretendard is not required.
- **Coordinates remapped** from 13.333" × 7.5" inches to FactDeck's 1280 × 720 px
  canvas (×96 dpi).
- **Scope.** Only cover, section divider, and key-points card families in v1;
  Patterns A–G / I–L from the upstream spec are not ported yet.

A copy of the upstream CC BY 4.0 license text is retained for reference under
`third_party/medical-ppt-design/LICENSE` when vendored; otherwise see the URI
above.

