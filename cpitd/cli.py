"""CLI interface for cpitd using Click."""

import sys

import click

from cpitd import __version__
from cpitd.config import ConfigFileError, build_config, load_file_config
from cpitd.pipeline import scan_and_report
from cpitd.tokenizer import NormalizationLevel


def _collect_explicit_args(ctx: click.Context, **kwargs: object) -> dict[str, object]:
    """Return only the kwargs whose values were explicitly set on the command line."""
    explicit: dict[str, object] = {}
    for param_name, value in kwargs.items():
        source = ctx.get_parameter_source(param_name)
        if source is click.core.ParameterSource.COMMANDLINE:
            if param_name == "normalize":
                explicit[param_name] = NormalizationLevel(value)
            elif param_name in {"ignore", "languages"}:
                # Map CLI names to Config field names, convert to tuple
                field = "ignore_patterns" if param_name == "ignore" else "languages"
                explicit[field] = tuple(value)
            else:
                explicit[param_name] = value
    return explicit


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
@click.pass_context
def main(
    ctx,
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

    cli_overrides = _collect_explicit_args(
        ctx,
        min_tokens=min_tokens,
        normalize=normalize,
        output_format=output_format,
        ignore=ignore,
        languages=languages,
    )

    try:
        file_config = load_file_config()
    except ConfigFileError as exc:
        raise click.ClickException(str(exc)) from None

    config = build_config(cli_overrides, file_config)

    reports = scan_and_report(config, paths, out=sys.stdout)
    raise SystemExit(1 if reports else 0)
