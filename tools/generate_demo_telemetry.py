#!/usr/bin/env python3
"""Generate a small synthetic telemetry.bin file for local Rerun checks."""

from __future__ import annotations

import argparse
import math
import struct
import time
from pathlib import Path


HEADER = struct.Struct("<8sIIIQddI64s32s112s")
RECORD_PREFIX = struct.Struct("<QQQQIBB2x")
MOTOR = struct.Struct("<fffhhI")
IMU = struct.Struct("<13fh2x")
MAGIC = b"URLOG001"


def fixed_bytes(value: str, width: int) -> bytes:
    raw = value.encode("utf-8")[: width - 1]
    return raw + b"\0" * (width - len(raw))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=Path("/tmp/unitree_demo/telemetry.bin"))
    parser.add_argument("--motors", type=int, default=12)
    parser.add_argument("--samples", type=int, default=240)
    parser.add_argument("--hz", type=float, default=60.0)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    start_ns = time.time_ns()

    with args.output.open("wb") as f:
        f.write(
            HEADER.pack(
                MAGIC,
                HEADER.size,
                1,
                args.motors,
                start_ns,
                args.hz,
                1.0,
                0,
                fixed_bytes("demo/lowstate", 64),
                fixed_bytes("demo0", 32),
                b"\0" * 112,
            )
        )

        for seq in range(args.samples):
            t = seq / args.hz
            unix_ns = start_ns + int(t * 1_000_000_000)
            f.write(RECORD_PREFIX.pack(unix_ns, int(t * 1_000_000_000), seq, 0, seq, 0, 0))

            for motor in range(args.motors):
                phase = t * 2.0 + motor * 0.17
                q = 0.45 * math.sin(phase)
                dq = 0.9 * math.cos(phase)
                tau = 7.5 * math.sin(phase + 0.55) - 1.3 * dq
                temp_case = int(38 + 5 * math.sin(t * 0.4 + motor * 0.1))
                temp_winding = temp_case + 6 + int(abs(tau) * 0.35)
                f.write(MOTOR.pack(q, dq, tau, temp_case, temp_winding, 0))

            roll = 0.05 * math.sin(t)
            pitch = 0.03 * math.cos(t * 0.8)
            yaw = 0.25 * math.sin(t * 0.25)
            f.write(
                IMU.pack(
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.01 * math.sin(t),
                    0.02 * math.cos(t),
                    0.03,
                    0.1 * math.sin(t),
                    0.1 * math.cos(t),
                    9.81,
                    roll,
                    pitch,
                    yaw,
                    42,
                )
            )

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
