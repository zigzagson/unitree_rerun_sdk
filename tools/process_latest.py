#!/usr/bin/env python3
"""Convert the latest session, extract TN CSV, and plot TN SVGs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DEFAULT_ACTUATOR_MAP = Path("config/motor_actuators.conf")


def latest_session_dir(logs_dir: Path = Path("unitree_logs")) -> Path:
    sessions = sorted(path for path in logs_dir.iterdir() if (path / "telemetry.bin").is_file())
    if not sessions:
        raise FileNotFoundError(f"no telemetry sessions found under {logs_dir}")
    return sessions[-1]


def resolve_session(path: Path | None) -> Path:
    if path is None:
        return latest_session_dir()
    if path.name == "telemetry.bin":
        return path.parent
    return path


def run_step(label: str, args: list[str]) -> None:
    print(f"[process_latest] {label}", flush=True)
    subprocess.run(args, cwd=REPO_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session",
        type=Path,
        nargs="?",
        help="Session directory or telemetry.bin. Default: latest unitree_logs session",
    )
    parser.add_argument(
        "--actuator",
        default="Go2HV",
        help="Fallback actuator for motors missing from --actuator-map. Default: Go2HV",
    )
    parser.add_argument(
        "--actuator-map",
        type=Path,
        default=DEFAULT_ACTUATOR_MAP,
        help="Motor-to-actuator config passed to plot_tn.py. Default: config/motor_actuators.conf",
    )
    parser.add_argument(
        "--motor",
        action="append",
        help="Motor filter passed to extract_tn.py and plot_tn.py, e.g. m00. Can be used multiple times",
    )
    parser.add_argument("--max-samples", type=int, default=0, help="Limit samples for conversion and TN extraction")
    parser.add_argument("--skip-rerun", action="store_true", help="Skip telemetry_to_rerun.py")
    parser.add_argument("--skip-tn", action="store_true", help="Skip extract_tn.py")
    parser.add_argument("--skip-plot", action="store_true", help="Skip plot_tn.py")
    args = parser.parse_args()

    session = resolve_session(args.session)
    telemetry = session / "telemetry.bin"
    if not telemetry.is_file():
        raise FileNotFoundError(f"missing telemetry.bin: {telemetry}")

    if not args.skip_rerun:
        cmd = [sys.executable, str(TOOLS_DIR / "telemetry_to_rerun.py"), str(session)]
        if args.max_samples:
            cmd += ["--max-samples", str(args.max_samples)]
        run_step("convert telemetry.bin to recording.rrd", cmd)

    if not args.skip_tn:
        cmd = [sys.executable, str(TOOLS_DIR / "extract_tn.py"), str(session)]
        if args.max_samples:
            cmd += ["--max-samples", str(args.max_samples)]
        for motor in args.motor or []:
            cmd += ["--motor", motor]
        run_step("extract TN CSV", cmd)

    if not args.skip_plot:
        cmd = [sys.executable, str(TOOLS_DIR / "plot_tn.py"), str(session), "--actuator", args.actuator]
        if args.actuator_map:
            cmd += ["--actuator-map", str(args.actuator_map)]
        for motor in args.motor or []:
            cmd += ["--motor", motor]
        run_step("plot TN SVG", cmd)

    print(f"[process_latest] done: {session}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
