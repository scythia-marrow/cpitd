"""CLI interface for cpitd using Click."""

import sys

import click

from cpitd import __version__
from cpitd.config import Config, ConfigFileError, build_config, load_file_config
from cpitd.pipeline import scan_and_report
from cpitd.reporter import CloneCluster, compute_file_stats
from cpitd.tokenizer import NormalizationLevel


def _expand_cli_param(name: str, value: object) -> tuple[str, object]:
    """Map a CLI parameter name and value to its Config-compatible equivalent.

    Handles renaming short CLI names (e.g. ``--ignore`` → ``ignore_patterns``)
    and converting tuple-typed multi-value options.

    Returns:
        A (config_field_name, converted_value) pair.
    """
    if name == "normalize":
        return name, NormalizationLevel(value)
    if name in ("ignore", "suppress", "languages"):
        config_key = {"ignore": "ignore_patterns", "suppress": "suppress_patterns"}.get(
            name, name
        )
        return config_key, tuple(value)
    return name, value


def _collect_explicit_args(ctx: click.Context, **kwargs: object) -> dict[str, object]:
    """Return only the kwargs whose values were explicitly set on the command line."""
    return dict(
        _expand_cli_param(param_name, value)
        for param_name, value in kwargs.items()
        if ctx.get_parameter_source(param_name)
        is click.core.ParameterSource.COMMANDLINE
    )


def _threshold_exceeded(
    config: Config,
    clusters: list[CloneCluster],
    file_token_counts: dict[str, int],
) -> bool:
    """Check --fail-above thresholds, printing to stderr if exceeded."""
    if config.fail_above_count is not None and len(clusters) > config.fail_above_count:
        print(
            f"cpitd: warning: too many clone groups {len(clusters)} "
            f"(limit: {config.fail_above_count})",
            file=sys.stderr,
        )
        return True

    if config.fail_above_pct is not None:
        file_stats = compute_file_stats(clusters, file_token_counts)
        for fs in file_stats:
            if fs.duplication_pct > config.fail_above_pct:
                print(
                    f"cpitd: threshold exceeded: {fs.file} has "
                    f"{fs.duplication_pct}% duplication "
                    f"(limit: {config.fail_above_pct}%)",
                    file=sys.stderr,
                )
                return True

    return False


@click.command()
@click.version_option(version=__version__, prog_name="cpitd")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--min-tokens",
    default=20,
    show_default=True,
    help="Minimum pygments token count to report a clone group.",
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
    type=click.Choice(["human", "json", "sarif"]),
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
@click.option(
    "--suppress",
    multiple=True,
    help="Glob patterns to suppress clone groups (repeatable). "
    "If any source line in a clone chunk matches, the group is suppressed.",
)
@click.option(
    "--cache",
    is_flag=True,
    default=False,
    help="Cache per-file index data to speed up repeated scans (requires git).",
)
@click.option(
    "--cache-path",
    type=click.Path(),
    default=None,
    help="Path for the cache file (default: .cpitd-cache.json in scan root).",
)
@click.option(
    "--fail-above-pct",
    type=float,
    default=None,
    help="Exit 1 if any file's duplication percentage exceeds this threshold.",
)
@click.option(
    "--fail-above-count",
    type=int,
    default=None,
    help="Exit 1 if total clone groups exceed this count.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Print diagnostic warnings to stderr (skipped files, etc.).",
)
@click.option(
    "--no-text",
    "show_text",
    is_flag=True,
    flag_value=False,
    default=True,
    help="Suppress clone source text from output.",
)
@click.pass_context
def main(
    ctx,
    paths,
    min_tokens,
    normalize,
    output_format,
    cache,
    cache_path,
    fail_above_pct,
    fail_above_count,
    ignore,
    languages,
    suppress,
    verbose,
    show_text,
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
        cache=cache,
        cache_path=cache_path,
        fail_above_pct=fail_above_pct,
        fail_above_count=fail_above_count,
        ignore=ignore,
        languages=languages,
        suppress=suppress,
        verbose=verbose,
        show_text=show_text,
    )

    try:
        file_config = load_file_config()
    except ConfigFileError as exc:
        raise click.ClickException(str(exc)) from None

    config = build_config(cli_overrides, file_config)

    try:
        clusters, file_token_counts = scan_and_report(config, paths, out=sys.stdout)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError) as exc:
        raise click.ClickException(f"scan failed: {exc}") from None

    if _threshold_exceeded(config, clusters, file_token_counts):
        raise SystemExit(1)

    raise SystemExit(1 if clusters else 0)
