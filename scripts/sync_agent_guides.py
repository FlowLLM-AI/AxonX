"""Copy canonical development guides into the distributable Agent resources and Skill."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_METADATA = (
    "---\nname: axonx\n"
    "description: Use AxonX for quantitative research, research plugin development, task execution and observation, "
    "and inspection of logs, dependencies, and artifacts. "
    "Use when the request involves AxonX Tasks or research workflows.\n"
    "---\n\n"
)


def generated_guides(root: Path = ROOT) -> dict[Path, str]:
    """Keep package resources usable in wheels and checkouts without symlink support."""
    guides = {}
    for language in ("en", "zh"):
        source = root / f"docs/{language}/dev_guide.md"
        guides[root / f"axonx/app/components/agent/guides/{language}.md"] = source.read_text(encoding="utf-8")
    guides[root / "skills/axonx/SKILL.md"] = SKILL_METADATA + guides[root / "axonx/app/components/agent/guides/en.md"]
    return guides


def main() -> None:
    """Write generated resources, or fail when any resource needs regeneration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in generated_guides().items():
        if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != content:
            stale.append(str(path.relative_to(ROOT)))
            if not args.check:
                if path.is_symlink():
                    path.unlink()
                path.write_text(content, encoding="utf-8")
    if stale and args.check:
        raise SystemExit("Stale Agent guides: " + ", ".join(stale) + "; run python -m scripts.sync_agent_guides")


if __name__ == "__main__":
    main()
