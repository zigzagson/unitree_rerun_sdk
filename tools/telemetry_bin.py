#!/usr/bin/env python3
"""Read unitree_rerun telemetry.bin files."""

from __future__ import annotations

import math
import struct
from typing import BinaryIO, Iterator


HEADER = struct.Struct("<8sIIIQddI64s32s112s")
RECORD_PREFIX = struct.Struct("<QQQQIBB2x")
MOTOR = struct.Struct("<fffhhI")
IMU = struct.Struct("<13fh2x")
MAGIC = b"URLOG001"
RAD_S_TO_RPM = 60.0 / (2.0 * math.pi)


def _decode_c_string(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def read_header(f: BinaryIO) -> dict:
    raw = f.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError("file is too small to contain a telemetry header")

    (
        magic,
        header_size,
        version,
        motor_count,
        start_unix_time_ns,
        sample_hz,
        summary_hz,
        _reserved,
        topic,
        network_interface,
        _reserved_bytes,
    ) = HEADER.unpack(raw)

    if magic != MAGIC:
        raise ValueError(f"invalid telemetry magic: {magic!r}")
    if header_size != HEADER.size:
        raise ValueError(f"unsupported header size: {header_size}")
    if version != 1:
        raise ValueError(f"unsupported telemetry version: {version}")

    return {
        "version": version,
        "motor_count": motor_count,
        "start_unix_time_ns": start_unix_time_ns,
        "sample_hz": sample_hz,
        "summary_hz": summary_hz,
        "topic": _decode_c_string(topic),
        "network_interface": _decode_c_string(network_interface),
    }


def iter_samples(f: BinaryIO, motor_count: int) -> Iterator[dict]:
    record_size = RECORD_PREFIX.size + motor_count * MOTOR.size + IMU.size
    while True:
        raw = f.read(record_size)
        if not raw:
            return
        if len(raw) != record_size:
            raise ValueError(f"truncated record: got {len(raw)} bytes, expected {record_size}")

        offset = 0
        (
            unix_time_ns,
            steady_time_ns,
            sequence,
            dropped_samples,
            source_tick,
            mode_pr,
            mode_machine,
        ) = RECORD_PREFIX.unpack_from(raw, offset)
        offset += RECORD_PREFIX.size

        q = []
        dq = []
        tau = []
        temp_case = []
        temp_winding = []
        motor_state = []
        for _ in range(motor_count):
            q_i, dq_i, tau_i, temp_case_i, temp_winding_i, state_i = MOTOR.unpack_from(raw, offset)
            offset += MOTOR.size
            q.append(q_i)
            dq.append(dq_i)
            tau.append(tau_i)
            temp_case.append(temp_case_i)
            temp_winding.append(temp_winding_i)
            motor_state.append(state_i)

        imu_values = IMU.unpack_from(raw, offset)
        yield {
            "unix_time_ns": unix_time_ns,
            "steady_time_ns": steady_time_ns,
            "sequence": sequence,
            "dropped_samples": dropped_samples,
            "source_tick": source_tick,
            "mode_pr": mode_pr,
            "mode_machine": mode_machine,
            "q": q,
            "dq": dq,
            "tau": tau,
            "temp_case": temp_case,
            "temp_winding": temp_winding,
            "motor_state": motor_state,
            "imu_quat": list(imu_values[0:4]),
            "imu_gyro": list(imu_values[4:7]),
            "imu_accel": list(imu_values[7:10]),
            "imu_rpy": list(imu_values[10:13]),
            "imu_temp": imu_values[13],
        }


def motor_names(motor_count: int) -> list[str]:
    return [f"m{i:02d}" for i in range(motor_count)]
