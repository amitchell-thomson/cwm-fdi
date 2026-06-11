"""wattcher — live CPU power/energy/thermal dashboard (RAPL-backed on Linux)."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="wattcher",
        description="Live CPU power, thermal, utilisation and C-state dashboard.",
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=1.0, help="sampling interval in seconds"
    )
    args = parser.parse_args()

    from wattcher.app import WattcherApp
    from wattcher.sample import SensorError
    from wattcher.sensors.linux import LinuxSource

    try:
        source = LinuxSource()
    except SensorError as exc:
        raise SystemExit(f"wattcher: {exc}")
    WattcherApp(source, interval=args.interval).run()


if __name__ == "__main__":
    main()
