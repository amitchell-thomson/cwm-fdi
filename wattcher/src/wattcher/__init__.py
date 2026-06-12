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
    sub = parser.add_subparsers(dest="command")
    curve = sub.add_parser(
        "curve", help="measure the utilisation/frequency power curves (drives load)"
    )
    curve.add_argument(
        "--levels", help="comma-separated utilisation %% levels, e.g. 0,25,50,75,100"
    )
    curve.add_argument(
        "--settle", type=float, default=1.5, help="seconds to let each load level settle"
    )
    curve.add_argument(
        "--window", type=float, default=2.0, help="seconds to average power at each level"
    )
    args = parser.parse_args()

    if args.command == "curve":
        from wattcher.curve import run_curve

        levels = [int(x) for x in args.levels.split(",")] if args.levels else None
        run_curve(levels=levels, settle=args.settle, window=args.window)
        return

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
