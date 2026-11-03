"""Command-line conversion for individual files and directory trees."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .parser import ConversionError, GitBookParser, to_xml


def main(argv=None):
    argument_parser = argparse.ArgumentParser(description="Convert GitBook Markdown to semantic XML (schema version 1).")
    argument_parser.add_argument("input", type=Path, help="Markdown file or directory")
    argument_parser.add_argument("-o", "--output", type=Path, help="Output file, or output directory for a directory input")
    argument_parser.add_argument("--permissive", action="store_true", help="Preserve unknown GitBook directives rather than rejecting them")
    argument_parser.add_argument("--compact", action="store_true", help="Disable XML indentation")
    argument_parser.add_argument("--force", action="store_true", help="Allow replacing existing output files")
    args = argument_parser.parse_args(argv)
    try:
        if not args.input.exists():
            raise ConversionError(f"Input does not exist: {args.input}")
        directory = args.input.is_dir()
        if directory and args.output is None:
            raise ConversionError("Directory conversion requires --output DIRECTORY")
        if directory and args.output.resolve().is_relative_to(args.input.resolve()):
            raise ConversionError("Output directory must be outside the input tree")
        files = sorted(p for p in args.input.rglob("*")
                       if p.is_file() and p.suffix.lower() == ".md"
                       and not any(part in {".git", ".obsidian", ".venv", "node_modules"}
                                   for part in p.relative_to(args.input).parts)) if directory else [args.input]
        if not files:
            raise ConversionError("No Markdown files found")
        parser = GitBookParser(strict=not args.permissive)
        # Validate and render the entire batch before writing anything. This also
        # catches colliding output paths (e.g. note.md and note.MD).
        results = []
        destinations = set()
        errors = []
        for file in files:
            relative = file.relative_to(args.input) if directory else Path(file.name)
            target = args.output / relative.with_suffix(".xml") if directory else args.output
            if target is not None:
                resolved = target.resolve()
                if resolved == file.resolve():
                    raise ConversionError("Output would overwrite the Markdown input")
                if resolved in destinations:
                    raise ConversionError(f"Multiple sources map to {target}")
                destinations.add(resolved)
                if target.exists() and not args.force:
                    raise ConversionError(f"Output exists: {target}; use --force to replace it")
            try:
                root = parser.parse(file.read_text(encoding="utf-8"), source_path=relative.as_posix())
                results.append((target, to_xml(root, pretty=not args.compact)))
            except (ConversionError, UnicodeError) as error:
                errors.append(f"{relative}: {error}")
        if errors:
            raise ConversionError("\n".join(errors))
        for target, xml in results:
            if target is None:
                sys.stdout.write(xml)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("w" if args.force else "x", encoding="utf-8", newline="\n") as handle:
                    handle.write(xml)
        if directory or args.output:
            print(f"Converted {len(results)} document(s).", file=sys.stderr)
        return 0
    except (ConversionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
