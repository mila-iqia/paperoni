#!/usr/bin/env python3
"""Load data_dir/**/prompt/*.json, fix missing metadata, verify round-trip.

For each prompt file:
- Load with ParsedResponseSerializer and the proper content_type
- If response._ is not available, use _generate_metadata to regenerate it
- If response._.parsed is not of type content_type, deserialize the "parsed" field
- Dump to tmp, load back, verify response._ is identical
- With --replace: overwrite fixed files with verified content
"""

import argparse
import json
import shutil
import sys
import tempfile
from io import BytesIO
from pathlib import Path

import serieux
from google.genai import types
from serieux.features.comment import comment_field

import paperoni.refinement.llm_common as llm_common
from paperoni.prompt import (
    ParsedResponseSerializer,
    _generate_metadata,
)
from paperoni.refinement.llm_norm_author import model as norm_author_model
from paperoni.refinement.llm_norm_venues import model as norm_venue_model
from paperoni.refinement.llm_process_affiliation import (
    model as process_affiliation_model,
)


def get_content_type_for_prompt(prompt_name: str) -> type | None:
    """Map prompt directory name to content_type for ParsedResponseSerializer."""
    mapping = {
        "pdf": llm_common.Analysis,
        "html": llm_common.Analysis,
        "llm_norm_author": norm_author_model.Analysis,
        "llm_norm_venues": norm_venue_model.Analysis,
        "llm_process_affiliation": process_affiliation_model.Analysis,
    }
    return mapping.get(prompt_name)


def load_and_fix(path: Path, content_type: type) -> types.GenerateContentResponse:
    """Load a prompt file, fix metadata if needed, return response with valid response._."""
    serializer = ParsedResponseSerializer[content_type]
    data: dict = json.loads(path.read_bytes())
    parsed_model: dict = data["parsed"]
    fixed = False

    try:
        # Try normal load first (works when $comment is present)
        with path.open("rb") as f:
            response: types.GenerateContentResponse = serializer.load(f)
    except AttributeError:
        metadata = data.get(comment_field, {})
        data[comment_field] = metadata
        response = serializer.load(BytesIO(json.dumps(data).encode("utf-8")))
        fixed = True

    # Check if parsed is correct type
    if not isinstance(response._.parsed, content_type):
        response.parsed = parsed_model
        response._ = _generate_metadata(response, content_type)
        fixed = True

    assert isinstance(response._.parsed, content_type)

    return response, fixed


def verify_response(
    path: Path,
    response: types.GenerateContentResponse,
    tmp_path: Path,
    content_type: type,
    fixed: bool,
) -> tuple[bool, str | None]:
    """Dump to tmp, load back, verify round-trip and parsed consistency.

    Returns (success, error_message). error_message is None when success is True.
    """
    serializer = ParsedResponseSerializer[content_type]

    with tmp_path.open("wb") as f:
        serializer.dump(response, f)

    with tmp_path.open("rb") as f:
        reloaded = serializer.load(f)

    if response._ != reloaded._:
        return False, "Round-trip verification failed: metadata differs"

    if fixed:
        data: dict = json.loads(path.read_bytes())
        if serieux.deserialize(content_type, data["parsed"]) != response._.parsed:
            return False, "Parsed model differs after fix"

    return True, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fix missing metadata in prompt JSON files and verify round-trip."
    )
    parser.add_argument(
        "data_dir",
        type=Path,
        help="Data directory containing prompt files",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace fixed files with verified content after successful verification",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir: Path = args.data_dir.resolve()
    replace: bool = args.replace

    if not data_dir.exists():
        print(f"Data dir not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    prompt_files = sorted(data_dir.glob("**/prompt/*"))
    errors: list[tuple[Path, str]] = []
    fixed: list[Path] = []
    verified: list[Path] = []
    replaced: list[Path] = []

    for path in prompt_files:
        if not path.is_file():
            continue

        _fixed = False

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            rel = path.relative_to(data_dir)
            prompt_name = rel.parts[0]
            content_type = get_content_type_for_prompt(prompt_name)

            if content_type is None:
                continue  # Skip unknown prompt types

            # Load and fix
            response, _fixed = load_and_fix(path, content_type)
            if _fixed:
                fixed.append(path)

            ok, err_msg = verify_response(path, response, tmp_path, content_type, _fixed)
            if not ok:
                errors.append((path, err_msg))
            else:
                verified.append(path)
                if replace and _fixed:
                    shutil.copy(tmp_path, path)
                    replaced.append(path)

        except Exception as e:
            errors.append((path, f"{type(e).__name__}: {e}"))
        finally:
            tmp_path.unlink(missing_ok=True)

    print(f"Fixed: {len(fixed)}/{len(prompt_files)} files")
    print(f"Verified: {len(verified)}/{len(prompt_files)} files")
    if replace:
        print(f"Replaced: {len(replaced)} files")
    if errors:
        print(f"\nErrors ({len(errors)} files):", file=sys.stderr)
        for path, msg in errors[:20]:
            print(f"  {path}: {msg}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
