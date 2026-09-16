---
name: gamma-to-ppt
description: Recreate public Gamma webpages (gamma.site or accessible Gamma presentation pages) as editable PowerPoint/PPTX files or Feishu slides. Use for page-by-page conversion that preserves source content, composition, icons, and colors, or for repairing visual differences in existing conversions; not for freely rewriting or redesigning presentations.
---

# Gamma to Editable PPT

Use the user-specified Gamma webpage as the visual and content reference for an editable presentation. Reproduce text, relationships between shapes, image placement, icons, colors, spacing, and page order. Do not simply transfer the copy into a generic template.

## Scope and Deliverables

- Follow the requested destination: a PPTX file, a new Feishu presentation, or an existing presentation. Continue when the available context is sufficient; ask only when an unresolved destination affects delivery.
- Preserve the source language and complete content by default. Do not expand, omit, rewrite, or add diagram entries absent from the source unless the user explicitly requests those changes.
- Represent text, flows, arrows, ring diagrams, icons, and callouts with native editable objects in the target format. Source photographs, textures, and assets that are already bitmaps may remain images.
- Use screenshots for visual inspection, never as substitutes for entire slides or complex diagrams in the deliverable. Inserting an SVG as a single image does not make its components editable.
- Exporting source files may reduce work, but a successful export does not prove a faithful conversion. Check composition, icons, and editability after import.
- Do not promise automatic pixel-level fidelity across renderers. Rebuild from the source and correct visible differences; identify specific pages and differences where font, animation, or aspect-ratio limitations remain.

## Read the Source and Map Pages

1. Open the specified page and confirm its visible content and loading state. Choose a stable desktop viewport and record its dimensions and zoom. Wait for fonts, images, and lazy-loaded content; inspect every card rather than only the first screen.
2. If the normal export option is available, download and inspect the original PPTX. If export access is denied but the public page is readable, rebuild from that page. Do not bypass permissions or repeatedly retry the same restricted entry point.
3. Retrieve the visible DOM, styles, SVGs, and source images using webpage-reading methods permitted in the current environment. If a tool permits only rendered DOM access, do not read hidden application state or bypass that restriction through another method.
4. Gamma has used `[data-card-id]` for cards and `aside.gml-callout` for callouts. Treat these as locator hints: verify them on the current page before use, and do not treat historical selectors as a fixed protocol.
5. Record each page's original text, layout type, image URLs and cropping, major boundaries, fonts, colors, icon paths, and shape order. Do not directly copy entries that exist in JSON or HTML but are not displayed on the webpage; first explain the discrepancy with the visible page.
6. Establish an explicit mapping: source card ID / source index -> output page index / target slide ID. Derive the page count from the current source, not a fixed count from an earlier task.

Keep `source/`, `assets/`, `pages/`, `qa/`, and a manifest in the task directory when useful. Record the source URL, retrieval time, viewport, page mapping, target dimensions, editable object types, original bitmap assets, and unresolved differences. Do not write business content, login data, or document tokens into the skill repository.

When merging another presentation, confirm source page indices and actual slide IDs, then read the native pages to insert. Insert them at the requested position and update the mapping. For example, "before the last page" requires locating the original final page before insertion, rather than appending. Transfer dependent media, fonts, and themes, then verify rendering and page order in the destination. Preserve the source document.

## Preserve the Layout

Read the target canvas dimensions first. Map the source card's effective content area to the destination while preserving image placement on the left or right, column proportions, hierarchy, connection directions, nesting, shape counts, and the correspondence and order of text and graphics.

- Scale the source composition uniformly and translate it into the target content area as needed. Do not stretch horizontal and vertical coordinates independently, turning circles into ellipses.
- If source and target aspect ratios differ, prioritize composition and readability, then adjust whitespace or target dimensions. Never silently crop content; explain the tradeoff if it cannot fit.
- Check whether the actual fonts are available. Substitutions affect line wrapping, character widths, and baselines. Do not solve every overflow by shrinking the font.
- Layer order is part of the layout. Stack backgrounds, connectors, main graphics, icons, and text as in the source, ensuring new backgrounds do not cover existing text.
- If an automatic layout changes during conversion, redraw its components. Do not change source relationships merely because a target template is more convenient.

Validate the highest-risk pages first, then apply the same rules to the remaining slides: dense text, image/text columns, complex vector diagrams, and callouts. This exposes font, path, and scaling problems before bulk generation.

## Rebuild Editable Vectors

Prefer reusing source SVG geometry and converting it into native target paths. When vectors are unavailable, redraw the reference with native components. Use standard shapes for ordinary circles, rectangles, and lines, and freeform paths for complex outlines.

Preserve the `viewBox` origin, nested transforms, fill rules, strokes, opacity, and clipping semantics when processing SVGs. Do not merely extract and concatenate every `d` attribute. Apply transforms to the coordinates, then convert them into the target shape's local coordinate system. If the destination does not support arcs, approximate them with sufficiently accurate Bezier curves and inspect error at the output size. Do not assume a fixed segment count is accurate for every graphic.

Check native paths for the following:

- Preserve each subpath's starting point and closure semantics. Do not fill the holes in hollow icons.
- Match path bounds to the shape's dimensions and position. Include nonzero viewBox origins in transforms.
- Account for stroke width during scaling so small icons neither become too heavy nor disappear.
- Keep diagram segments as separate objects, with icons and labels also separate. Group them for convenient movement when useful, and verify they can be ungrouped and edited.
- Verify the actual target renderer's support for gradients, opacity, strokes, and path syntax rather than inferring support from the format name.

For example, a segmented flywheel must retain its segment count, gaps, inner and outer contours, rotation, and icon order. Do not replace it with a few ordinary sectors or a single image. Preserve tangency in nested tangent circles rather than converting them into concentric circles. Arrow sequences must contain only entries actually displayed on the webpage.

## Callouts: Icons, Colors, and Vertical Alignment

Inventory callouts on every page, including all success, warning, information, and other types present. Read source SVGs and computed styles rather than substituting emoji or approximate characters. Gamma may define colors through `data-variant` and `--callout-<variant>-bg` / `--callout-<variant>-icon`; verify this on the current page. Do not apply one background color to every callout.

The background, icon, and text must be independently editable objects. Reserve a horizontal slot for the icon, calculate the text width, then inspect wrapping and height. Center the icon and body text independently within the full callout area; do not derive icon placement from the top of the first text line.

Given background position and dimensions `(bx, by, bw, bh)`, actual icon height `ih`, icon slot width `slot`, left and right padding `pl` and `pr`, and icon-to-text gap `gap`:

```text
center_y = by + bh / 2
icon_y = center_y - ih / 2
text_x = bx + pl + slot + gap
text_width = bx + bw - pr - text_x
text_y = by
text_height = bh
text_vertical_alignment = middle
text_padding_top = text_padding_bottom
```

If the destination cannot vertically center content within a text box, measure the laid-out text height and position it on the same centerline. Center multiline text as a whole, not just its first line. Even when bounding-box centers match, visually inspect glyph baselines and visible icon contours; transparent margins can cause apparent misalignment.

## Write to the Destination

### Feishu Slides

Use the available `lark-slides` capabilities and their editing and XML schema documentation. Use the corresponding Drive import capability when importing PPTX. Check tool support first; do not substitute APIs for other document types. If these tools are unavailable, use supported UI operations or deliver a local PPTX, clearly identifying any online deliverable that has not been created. Do not claim it has been published.

When creating a presentation, record its presentation ID, slide IDs, and write results. Before modifying an existing presentation, reread its current XML and revision because the user may have edited it since the previous turn. Do not overwrite the latest document with an older local copy of the entire presentation.

Use block-level replacement for local alignment, icon, and color edits. Replace an entire slide only when it genuinely requires rebuilding. Typical Feishu shortcut commands are shown below; verify them with the current CLI help before execution:

```bash
lark-cli slides +xml-get --as user --presentation TARGET_ID --output before.xml
lark-cli slides +replace-slide --as user --presentation TARGET_ID \
  --slide-id SLIDE_ID --parts @parts.json
```

In `parts.json`, replacements use `action: block_replace`, `block_id`, and `replacement`; insertions use `action: block_insert` and `insertion`. Coordinate changes still require the complete target block XML. Do not assume a field-level patch exists. Store XML in JSON files to avoid shell-escaping damage.

The following structure expresses vertical centering for native Feishu text. Obtain dimensions, font sizes, and fonts from the current presentation:

```xml
<shape type="text" topLeftX="80" topLeftY="490" width="820" height="34">
  <content fontSize="12" verticalAlign="middle" paddingTop="0" paddingBottom="0"
    textAlign="left" color="rgba(255,255,255,1)" lineSpacing="multiple:1.1">
    <p>Preserve the original callout text</p>
  </content>
</shape>
```

A rectangular background is not a container; place icons and text alongside it in the same layer hierarchy. Use shape-local coordinates for custom paths. Upload image assets as required by the tool and use media tokens; do not assume external image URLs will render directly. Run the destination skill's XML validation before submitting complete pages.

After a failed write or interrupted batch, read back the destination to determine which pages or elements succeeded, then resume the remaining work. Do not blindly replay insertions and create duplicates. The server may omit default attributes. For example, if readback omits `verticalAlign`, consider the current schema's defaults and actual rendering before concluding that centering failed.

### Local PPTX

Use the available presentation-generation capabilities to write native text boxes, shapes, freeform paths, and groups. Embedding an SVG as an image preserves appearance but does not satisfy component-level editability. Reopen or render the saved PPTX and inspect fonts, path holes, layering, and text wrapping. If importing into Feishu, inspect the imported result as well; local rendering does not replace online verification.

## Verify and Deliver

Perform both structural and visual checks. Neither replaces the other.

- **Content and page order**: Check original text, numbers, labels, and order on every page. Identify user-requested additions or removals and confirm insertion positions. Ensure no content is lost, no pages are duplicated, and no hidden entries are added.
- **Object editability**: Verify text, paths, and icons remain native objects by selecting them or inspecting the file's object structure. Image counts alone do not prove editability; check each image's purpose.
- **Geometry**: Check for out-of-bounds objects, unintended overlap, and cropping. Ensure callout backgrounds, text boxes, and icons share the intended centerline, horizontal spacing is reasonable, and multiline text is not truncated.
- **Visual fidelity**: Compare source and output page by page at a consistent scale. Pay particular attention to complex diagram relationships, icon holes, gradients, photo cropping, and font wrapping. Screenshots or PDFs may support inspection, but must not be embedded in the deliverable as substitutes for editable objects.
- **Preservation during edits**: Read back the latest result after local repairs and confirm page order, body text, and untouched pages remain intact. Compare text semantically by page/block, accounting for server normalization and empty content automatically added to shapes without text.

Record the pages checked, differences found, and repair status. Recheck affected pages after repairs. Do not claim full fidelity merely because a tool call succeeded, or repeat every expensive step after a local change. Deliver an accessible file or online link and accurately describe verified editability and any specific remaining limitations.
