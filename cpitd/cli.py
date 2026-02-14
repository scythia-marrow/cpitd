"""CLI interface for cpitd using Click."""

import sys

import click

from cpitd import __version__
from cpitd.config import Config
from cpitd.pipeline import scan_and_report
from cpitd.tokenizer import NormalizationLevel


@click.command()
@click.version_option(version=__version__, prog_name="cpitd")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--min-tokens",
    default=50,
    show_default=True,
    help="Minimum token sequence length to report.",
)
@click.option(
    "--normalize",
    type=click.IntRange(0, 2),
    default=0,
    show_default=True,
    help="Token normalization level (0=exact, 1=identifiers, 2=literals+identifiers).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"]),
    default="human",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--ignore",
    multiple=True,
    help="Glob patterns to exclude (repeatable).",
)
@click.option(
    "--languages",
    multiple=True,
    help="Restrict to specific languages (repeatable).",
)
def main(
    paths,
    min_tokens,
    normalize,
    output_format,
    ignore,
    languages,
):
    """Detect copy-pasted code clones across a codebase.

    Pass one or more file or directory PATHS to analyze.
    Defaults to the current directory if none are given.
    """
    if not paths:
        paths = (".",)

    config = Config(
        min_tokens=min_tokens,
        normalize=NormalizationLevel(normalize),
        output_format=output_format,
        ignore_patterns=tuple(ignore),
        languages=tuple(languages),
    )

    reports = scan_and_report(config, paths, out=sys.stdout)
    raise SystemExit(1 if reports else 0)
