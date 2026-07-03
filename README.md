# unitree_rerun_sdk

Independent Unitree lowstate recorder with an optional Rerun export path.

The robot-side C++ recorder is intentionally small:

- depends on Unitree SDK2 and C++17
- no ROS dependency
- no Rerun C++ SDK dependency
- no YAML/JSON/protobuf dependency
- writes actual wall-clock timestamps in nanoseconds

Install Unitree SDK2 before building this recorder:

```bash
git clone https://github.com/unitreerobotics/unitree_sdk2.git
cd unitree_sdk2
mkdir -p build
cd build
cmake ..
make -j8
sudo make install
```

If Unitree SDK2 is installed somewhere other than the default system prefix,
make sure that prefix is visible through `CMAKE_PREFIX_PATH` when configuring
this project.

Install the Python Rerun SDK for conversion and viewing:

```bash
pip3 install rerun-sdk
```

This avoids building the C++ Rerun SDK and Arrow stack on the robot.

## Output

The recorder subscribes to `rt/lowstate`, samples motor/IMU state, and writes:

```text
unitree_logs/YYYYMMDD_HHMMSS/
  telemetry.bin  # compact robot-side recording
  summary.csv    # low-rate readable health summary
  meta.txt       # session/config metadata
```

`telemetry.bin` contains:

- motor `q`, `dq`, `tau_est`
- motor case/winding temperature
- motor state word
- IMU quaternion, gyro, accel, rpy, temperature
- sequence, dropped sample count, Unitree source tick

Reserved raw fields such as `q_raw`, `dq_raw`, and `ddq_raw` are not recorded.

## Build

```bash
cd unitree_rerun_sdk
mkdir -p build
cd build
cmake ..
make -j8
```

## Record

Edit `examples/recorder.conf` for your network interface. On this machine the wired interface is `eno1`:

```ini
network_mode=0
network_interface=eno1
sample_hz=20
output_dir=./unitree_logs
```

Start recording:

```bash
unitree_rerun_sdk/build/unitree_rerun_recorder \
  --config unitree_rerun_sdk/examples/recorder.conf
```

Stop with `Ctrl-C`.

## Convert To Rerun

Install Python Rerun SDK once:

```bash
pip3 install rerun-sdk
```

Convert a session:

```bash
python3 unitree_rerun_sdk/tools/telemetry_to_rerun.py \
  unitree_logs/YYYYMMDD_HHMMSS/telemetry.bin
```

Open it:

```bash
rerun unitree_logs/YYYYMMDD_HHMMSS/recording.rrd
```

The `.rrd` groups time-series data under:

- `robot/motors/q`
- `robot/motors/dq`
- `robot/motors/tau_est`
- `robot/motors/temp_case`
- `robot/motors/temp_winding`
- `robot/motors/state`
- `robot/imu/rpy`
- `robot/imu/gyro`
- `robot/imu/accel`
- `robot/imu/temperature`
- `robot/health/summary`

## Extract TN Demand Data

Rerun is intentionally not used for torque-speed analysis. Extract TN demand
data to CSV instead:

```bash
python3 unitree_rerun_sdk/tools/extract_tn.py \
  unitree_logs/YYYYMMDD_HHMMSS/telemetry.bin
```

This writes:

```text
unitree_logs/YYYYMMDD_HHMMSS/tn_csv/
  tn_all.csv
  m00.csv
  m01.csv
  ...
```

Each row contains signed and absolute speed/torque:

- `speed_rad_s`
- `speed_rpm`
- `torque_nm`
- `abs_speed_rpm`
- `abs_torque_nm`

Export selected motors only:

```bash
python3 unitree_rerun_sdk/tools/extract_tn.py \
  unitree_logs/YYYYMMDD_HHMMSS/telemetry.bin \
  --motor m00 --motor m07
```

Plot extracted TN scatter data against a Unitree actuator torque-speed limit:

```bash
python3 unitree_rerun_sdk/tools/plot_tn.py \
  unitree_logs/YYYYMMDD_HHMMSS/tn_csv \
  --actuator Go2HV
```

This writes dependency-free SVG plots and an over-limit summary:

```text
unitree_logs/YYYYMMDD_HHMMSS/tn_plots/
  tn_all.svg
  m00.svg
  m01.svg
  summary.csv
```

Available `--actuator` values mirror Unitree's published `UnitreeActuatorCfg`
classes: `Go2HV`, `M107_15`, `M107_24`, `N5010_16`, `N5020_16`,
`N7520_14p3`, `N7520_22p5`, and `W4010_25`.

## Demo Data

Generate synthetic data and convert it:

```bash
python3 unitree_rerun_sdk/tools/generate_demo_telemetry.py \
  -o unitree_logs/demo/telemetry.bin

python3 unitree_rerun_sdk/tools/telemetry_to_rerun.py \
  unitree_logs/demo/telemetry.bin

rerun unitree_logs/demo/recording.rrd
```

Extract demo TN CSV:

```bash
python3 unitree_rerun_sdk/tools/extract_tn.py \
  unitree_logs/demo/telemetry.bin
```

## Runtime Policy

The DDS callback only validates CRC, checks the sampling interval, copies fields into a fixed-size sample, and pushes it into a bounded queue. Disk writes and `summary.csv` formatting happen in the writer thread.

If the queue is full, the oldest sample is dropped and `dropped_samples` is incremented. This keeps recorder backpressure away from the DDS callback.
