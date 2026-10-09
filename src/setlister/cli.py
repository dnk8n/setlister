"""Command line interface. Start with `setlister doctor`, then `setlister run URL`."""

from __future__ import annotations

import getpass
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from setlister import __version__
from setlister.config import load_config
from setlister.secrets import KNOWN_SECRETS, RedactingFilter, delete_secret, set_secret, where_is

app = typer.Typer(help=__doc__, no_args_is_help=True, add_completion=False)
config_app = typer.Typer(help="Store API keys in your OS keychain (never in files).")
app.add_typer(config_app, name="config")
console = Console(stderr=True)

ConfigOpt = Annotated[Path | None, typer.Option("--config", "-c", help="Path to setlister.toml")]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    for h in logging.getLogger().handlers:
        h.addFilter(RedactingFilter())


@app.command()
def run(
    url: Annotated[
        str | None, typer.Argument(help="Link to the online set (YouTube, SoundCloud, Mixcloud, …)")
    ] = None,
    original: Annotated[
        Path | None,
        typer.Option(
            "--original",
            "-o",
            help="Your original recording (avoids a download; may be longer than the online copy)",
        ),
    ] = None,
    history: Annotated[
        list[Path] | None,
        typer.Option(
            "--history",
            "-H",
            help="DJ software history (.txt / .m3u8); repeat for each file or each DJ",
        ),
    ] = None,
    online_audio: Annotated[
        Path | None, typer.Option("--online-audio", help="A local copy of the online audio")
    ] = None,
    offline: Annotated[
        bool, typer.Option(help="No network: only local files and audio matching")
    ] = False,
    title: Annotated[
        str | None, typer.Option(help="Title for the output (defaults to the online title)")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="Output directory (default: out/)")
    ] = None,
    skip_doctor: Annotated[bool, typer.Option(help="Don't check configuration first")] = False,
    config: ConfigOpt = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Build a timestamped, linked, annotated tracklist for a set."""
    from setlister.doctor import render, run_checks
    from setlister.pipeline import RunInputs
    from setlister.pipeline import run as run_pipeline

    _setup_logging(verbose)
    if not (url or original or online_audio):
        raise typer.BadParameter("give a URL, --original or --online-audio")
    cfg, _ = load_config(config)
    if out:
        cfg.output.directory = out
    if not skip_doctor and not render(run_checks(cfg, network=not offline)):
        console.print("[red]Fix the required items above, then run again.[/]")
        raise typer.Exit(2)
    inputs = RunInputs(
        url=url,
        original=original,
        online_audio=online_audio,
        histories=history or [],
        offline=offline,
        title=title,
    )
    sl, outdir = run_pipeline(inputs, cfg)
    named = sum(1 for e in sl.entries if not e.is_unknown)
    console.print(
        f"[green]Done:[/] {named} tracks identified, {len(sl.entries) - named} unknown. "
        f"See {outdir}/README.md for how to publish."
    )


@app.command()
def doctor(config: ConfigOpt = None, offline: bool = False) -> None:
    """Check tools, keys and services, and explain what each one unlocks."""
    from setlister.doctor import render, run_checks

    cfg, path = load_config(config)
    console.print(f"config: {path or 'defaults (no setlister.toml found)'}")
    ok = render(run_checks(cfg, network=not offline))
    raise typer.Exit(0 if ok else 2)


@app.command()
def locate(
    recording: Annotated[Path, typer.Argument(help="The set recording")],
    tracks: Annotated[list[Path], typer.Argument(help="Audio files to look for")],
    config: ConfigOpt = None,
) -> None:
    """Find where local audio files occur in a recording (debugging aid)."""
    from setlister.audio.features import features_for
    from setlister.audio.matcher import MixIndex
    from setlister.audio.matcher import locate as locate_one
    from setlister.timefmt import format_timestamp

    cfg, _ = load_config(config)
    index = MixIndex(features_for(recording, cfg.audio.analysis_sr, cfg.cache_dir))
    for t in tracks:
        m = locate_one(
            index,
            features_for(t, cfg.audio.analysis_sr, cfg.cache_dir),
            max_rate_change=cfg.audio.max_tempo_change,
        )
        if m:
            print(
                f"{format_timestamp(m.start, force_hours=True)}–{format_timestamp(m.end, force_hours=True)}"
                f"  rate {m.rate:.3f}  confidence {m.confidence:.0%}  {t.name}"
            )
        else:
            print(f"not found  {t.name}")


@app.command()
def version() -> None:
    print(__version__)


@config_app.command("list")
def config_list() -> None:
    """Show which keys are set (never their values)."""
    for spec in KNOWN_SECRETS.values():
        found = where_is(spec.name)
        print(f"{spec.name:20} {'set (' + found + ')' if found else 'not set':22} {spec.unlocks}")


@config_app.command("set")
def config_set(name: str) -> None:
    """Store a key in the OS keychain. The value is read without echoing."""
    if name not in KNOWN_SECRETS:
        raise typer.BadParameter(f"unknown key; choose from {', '.join(KNOWN_SECRETS)}")
    console.print(f"{KNOWN_SECRETS[name].unlocks}\nGet one at {KNOWN_SECRETS[name].signup_url}")
    value = getpass.getpass(f"{name}: ").strip()
    if not value:
        raise typer.Exit(1)
    set_secret(name, value)
    console.print(f"[green]saved {name} to the keychain[/]")


@config_app.command("unset")
def config_unset(name: str) -> None:
    delete_secret(name)
    console.print(f"removed {name} from the keychain")


if __name__ == "__main__":
    app()
