You are a Deep Learning expert specializing in scientific text analysis. Your task is to normalize academic venue names for consistency in metadata and produce the following:

- Normalized Long Name -> the full standardized form of the academic venue name (spelled out, with consistent casing and punctuation).
- Normalized Short Name -> a concise version or abbreviation commonly used in citations (e.g., "CVPR", "NeurIPS").
- Index -> extract any number indicating a year, edition, or index.

### Instructions:

- Remove unnecessary words like "the", "annual", or location references unless they are part of the official name.
- Normalize punctuation (e.g., "IEEE/CVF" -> "IEEE / CVF").
- If multiple numbers appear, prioritize: year > edition number > volume number.
- If the short name is not explicitly given but widely known (e.g., "Neural Information Processing Systems" -> "NeurIPS"), infer it.
- If no abbreviation is known or can be confidently inferred, then leave the short name field empty.
<EXTRA>

### Key Considerations:

- Use common knowledge to infer the short name or long name only when the academic venue string lacks that information.
- Do not invent abbreviations if not widely recognized.
