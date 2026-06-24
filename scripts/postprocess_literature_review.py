"""One-shot post-processor to clean leaked paper UUIDs from an existing
literature review markdown file.

Background
----------
A previous version of the review-generation pipeline occasionally let
``project_paper_id`` UUIDs leak into the rendered prose in three ways:

1. Parenthesised:   ``... trajectory (58e090c2-1f14-4005-80bc-e8270e1c3694) ...``
2. Single bracket:  ``... finding [7feb6873-4492-4a45-8158-6141f03ff4cf] ...``
3. Comma list:      ``... coverage [99369ec6-..., 8f013674-...] ...``

The current pipeline strips these patterns at generation time. This
script applies the same stripping pass to an already-generated report
on disk, so legacy reports do not need a full regenerate.

Usage
-----
::

    python scripts/postprocess_literature_review.py \\
        /path/to/Literature_Review__..._modifications_ (4).md

The script overwrites the input file in place. A ``.bak`` copy is left
next to the original.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Allow running this script as ``python scripts/postprocess_literature_review.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.report_generation import _strip_inlined_uuids  # noqa: E402

_UUID_REGEX = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def postprocess_markdown(md: str) -> tuple[str, int]:
    """Strip all inlined paper UUIDs from a literature review markdown.

    The script does not have access to the report's project_paper table, so
    we treat every UUID found in the file as "in the references list" and
    strip it without warnings. This is safe: the only UUIDs in a literature
    review are the project_paper_ids, and they all belong in the
    citation_paper_ids -> ``<sup>[N]</sup>`` rendering anyway.

    Returns:
        (cleaned_markdown, replacements_count)
    """
    all_uuids = set(_UUID_REGEX.findall(md))
    ref_map = {uuid: "[?]" for uuid in all_uuids}
    return _strip_inlined_uuids(md, ref_map)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strip leaked paper UUIDs from a literature review markdown file."
    )
    parser.add_argument("path", type=Path, help="Path to the markdown file to clean.")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a .bak copy of the original file.",
    )
    args = parser.parse_args()

    if not args.path.is_file():
        parser.error(f"Input file does not exist: {args.path}")

    original = args.path.read_text(encoding="utf-8")
    cleaned, replacements = postprocess_markdown(original)

    if not args.no_backup:
        backup = args.path.with_suffix(args.path.suffix + ".bak")
        shutil.copy2(args.path, backup)
        print(f"Backup written: {backup}")

    args.path.write_text(cleaned, encoding="utf-8")
    print(f"Stripped {replacements} inlined UUID(s) from {args.path}")
    remaining = _UUID_REGEX.findall(cleaned)
    if remaining:
        print(
            f"WARNING: {len(remaining)} UUID(s) remain in the cleaned output. "
            "Inspect the file manually."
        )
        for uuid in remaining[:5]:
            print(f"  - {uuid}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
