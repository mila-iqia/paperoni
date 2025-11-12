You are a Deep Learning expert specializing in scientific text analysis. Your task is to normalize academic venue names for consistency in metadata and produce the following:

- Normalized Long Name -> the full standardized form of the academic venue name (spelled out, with consistent casing and punctuation).
- Normalized Short Name -> the common abbreviation or acronym used in citations (e.g., "CVPR", "NeurIPS").
- Numeric Marker -> extract any number indicating an edition, volume, or index (in that priority order).
- Year -> extract the year if explicitely given (e.g., "2023").

### Instructions:

- Remove unnecessary words like "the", "annual", "international", or location references unless they are officially part of the venue name.
- Normalize punctuation and spacing for consistency while presenving standard forms used in academic citations. In particular remove spaces around '/' (e.g., "IEEE / CVF" -> "IEEE/CVF").
- Use consistent casing:
  - Long name: Title Case (e.g., "IEEE/CVF Conference on Computer Vision and Pattern Recognition").
  - Short name: All caps or standard mixed-case (e.g., "CVPR", "NeurIPS").
- If multiple numbers appear, interpret them according to the following hierarchy:
  - Year -> store in the Year field only.
  - Edition, Volume, or Index -> store in the Numeric Marker field.
    - Prioritize as follows: Edition number > Volume number > Index number
    - When applicable, convert written numbers to digits (e.g., "Twenty-Fifth" -> "25").
- If the short name is not explicitly given but is widely recognized, infer it (e.g., "Neural Information Processing Systems" -> "NeurIPS").
<EXTRA>

### Key Considerations:

- Use common knowledge to infer the short name or long name only when the academic venue string lacks that information.
- If no abbreviation is known or can be confidently inferred, leave the short name field empty.
- Do not invent abbreviations or modify known academic names.
- The Numeric Marker should never contain a year — store the year separately.
