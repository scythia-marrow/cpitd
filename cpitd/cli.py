"""CLI interface for cpitd using Click."""

import click

from cpitd import __version__


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
    "--k-gram-size",
    default=5,
    show_default=True,
    help="Size of k-gram for fingerprinting.",
)
@click.option(
    "--window-size",
    default=4,
    show_default=True,
    help="Winnowing window size.",
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
    k_gram_size,
    window_size,
    normalize,
    output_format,
    ignore,
    languages,
):
    """Detect copy-pasted code clones across a codebase.

    Pass one or more file or directory PATHS to analyze.
    """
    if not paths:
        click.echo("No paths provided. Use --help for usage information.", err=True)
        raise SystemExit(1)

    click.echo(f"cpitd v{__version__} — scanning {len(paths)} path(s)...")
    click.echo("Clone detection not yet implemented.")
    raise SystemExit(0)
