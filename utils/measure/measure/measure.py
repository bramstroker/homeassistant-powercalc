"""Stable module entry point for the existing measurement CLI."""

from measure.cli.main import main  # pragma: no cover - compatibility entry-point wiring

if __name__ == "__main__":  # pragma: no cover - entry-point behaviour is tested through main
    main()
