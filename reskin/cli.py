"""CLI entry point for the reskin pipeline."""

from __future__ import annotations

from pathlib import Path

import click

from .config import load_config
from .utils import setup_logging, logger


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """Reskin Pipeline — Offline AI reskin generator for Unreal Engine assets."""
    setup_logging(verbose)


@cli.command()
@click.option("-p", "--project", type=click.Path(exists=True, path_type=Path), help="UE project path (overrides config)")
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True, path_type=Path), help="Skin config YAML")
def extract(project: Path | None, config_path: Path) -> None:
    """Extract and categorize textures from a UE project."""
    from .extractor import extract as run_extract

    config = load_config(config_path)
    if project:
        config.ue_project_path = project

    manifest_path = run_extract(config)
    click.echo(f"Extraction complete: {manifest_path}")


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True, path_type=Path), help="Skin config YAML")
@click.option("-b", "--backend", type=click.Choice(["lucy", "stability", "comfyui", "local"]), help="Override generation backend")
def generate(config_path: Path, backend: str | None) -> None:
    """Generate reskinned textures using AI."""
    from .generator import generate as run_generate

    config = load_config(config_path)
    if backend:
        config.backend = backend

    manifest_path = run_generate(config)
    click.echo(f"Generation complete: {manifest_path}")


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True, path_type=Path), help="Skin config YAML")
def bake(config_path: Path) -> None:
    """Bake generated textures into UE-compatible formats."""
    from .baker import bake as run_bake
    from .consistency import consistency_pass

    config = load_config(config_path)
    bake_manifest = run_bake(config)

    if config.quality.consistency_pass:
        logger.info("Running consistency pass...")
        consistency_pass(config)

    click.echo(f"Bake complete: {bake_manifest}")


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True, path_type=Path), help="Skin config YAML")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Override output directory")
def package(config_path: Path, output: Path | None) -> None:
    """Package baked assets into a UE plugin skin."""
    from .packager import package as run_package

    config = load_config(config_path)
    if output:
        config.output_dir = output

    package_dir = run_package(config)
    click.echo(f"Package ready at: {package_dir}")


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True, path_type=Path), help="Skin config YAML")
@click.option("-b", "--backend", type=click.Choice(["lucy", "stability", "comfyui", "local"]), help="Override generation backend")
def run(config_path: Path, backend: str | None) -> None:
    """Run the full reskin pipeline end-to-end."""
    from .extractor import extract as run_extract
    from .generator import generate as run_generate
    from .baker import bake as run_bake
    from .consistency import consistency_pass
    from .packager import package as run_package

    config = load_config(config_path)
    if backend:
        config.backend = backend

    click.echo(f"=== Reskin Pipeline: {config.name} ===\n")

    # Step 1: Extract
    click.echo("--- Step 1/4: Extraction ---")
    run_extract(config)

    # Step 2: Generate
    click.echo("\n--- Step 2/4: Generation ---")
    run_generate(config)

    # Step 3: Bake
    click.echo("\n--- Step 3/4: Baking ---")
    run_bake(config)

    if config.quality.consistency_pass:
        click.echo("\n--- Step 3.5/4: Consistency Pass ---")
        consistency_pass(config)

    # Step 4: Package
    click.echo("\n--- Step 4/4: Packaging ---")
    package_dir = run_package(config)

    click.echo(f"\n=== Done! Skin packaged at: {package_dir} ===")
    click.echo("Copy this folder into your UE project's Plugins/ directory and enable it.")


if __name__ == "__main__":
    cli()
