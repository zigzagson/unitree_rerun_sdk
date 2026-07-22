#include "unitree_rerun_sdk/telemetry_writer.h"
#include "unitree_rerun_sdk/time_utils.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <sys/stat.h>
#include <sys/types.h>

namespace unitree_rerun {
namespace {

constexpr std::array<char, 8> kMagic = {'U', 'R', 'L', 'O', 'G', '0', '0', '1'};
constexpr uint32_t kHeaderSize = 256;
constexpr uint32_t kFormatVersion = 2;

bool ensureDirExists(const std::string& dir, std::string& error)
{
    struct stat st;
    if (stat(dir.c_str(), &st) == 0) {
        if (!S_ISDIR(st.st_mode)) {
            error = "path exists but is not a directory: " + dir;
            return false;
        }
        return true;
    }
    if (mkdir(dir.c_str(), 0755) != 0) {
        error = "failed to create directory " + dir + ": " + std::strerror(errno);
        return false;
    }
    return true;
}

template <typename T>
void writePod(std::ofstream& out, const T& value)
{
    out.write(reinterpret_cast<const char*>(&value), sizeof(T));
}

void writeFixedString(std::ofstream& out, const std::string& value, size_t width)
{
    std::array<char, 128> buffer{};
    const size_t n = std::min(value.size(), std::min(width, buffer.size()) - 1);
    std::memcpy(buffer.data(), value.data(), n);
    out.write(buffer.data(), static_cast<std::streamsize>(width));
}

}  // namespace

TelemetryWriter::TelemetryWriter()
    : running_(false)
    , dropped_samples_(0)
    , last_summary_ns_(0)
{
}

TelemetryWriter::~TelemetryWriter()
{
    stop();
}

bool TelemetryWriter::start(
    const RecorderConfig& config, uint64_t start_unix_time_ns, std::string& error)
{
    stop();
    config_ = config;
    dropped_samples_.store(0);
    last_summary_ns_ = 0;

    if (!openSession(start_unix_time_ns, error)) {
        stop();
        return false;
    }

    running_.store(true);
    writer_thread_ = std::thread(&TelemetryWriter::writerLoop, this);
    return true;
}

void TelemetryWriter::stop()
{
    if (running_.exchange(false)) {
        queue_cv_.notify_all();
        if (writer_thread_.joinable()) writer_thread_.join();
    }

    if (data_stream_.is_open()) {
        data_stream_.flush();
        data_stream_.close();
    }
    if (summary_stream_.is_open()) {
        summary_stream_.flush();
        summary_stream_.close();
    }

    std::lock_guard<std::mutex> lock(queue_mutex_);
    queue_.clear();
}

void TelemetryWriter::enqueue(const TelemetrySample& sample)
{
    if (!running_.load()) return;

    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        if (queue_.size() >= config_.max_queue_samples) {
            queue_.pop_front();
            dropped_samples_.fetch_add(1);
        }
        TelemetrySample copy = sample;
        copy.dropped_samples = dropped_samples_.load();
        queue_.push_back(copy);
    }
    queue_cv_.notify_one();
}

bool TelemetryWriter::openSession(uint64_t start_unix_time_ns, std::string& error)
{
    if (!ensureDirExists(config_.output_dir, error)) return false;

    session_dir_ = config_.output_dir + "/" + timestampForPath(start_unix_time_ns);
    if (!ensureDirExists(session_dir_, error)) return false;

    data_path_ = session_dir_ + "/telemetry.bin";
    data_stream_.open(data_path_, std::ios::out | std::ios::binary | std::ios::trunc);
    if (!data_stream_) {
        error = "failed to open telemetry file: " + data_path_;
        return false;
    }
    if (!writeHeader(start_unix_time_ns, error)) return false;

    summary_stream_.open(session_dir_ + "/summary.csv", std::ios::out | std::ios::trunc);
    if (summary_stream_) {
        summary_stream_ << "unix_time_ns,iso_time,seq,mode_machine,max_temp,max_temp_motor,"
                        << "avg_temp,imu_temp,max_abs_tau,max_abs_dq,dropped_samples,"
                        << "lowcmd_received,lowcmd_sequence,lowcmd_age_ms\n";
    }

    std::ofstream meta(session_dir_ + "/meta.txt", std::ios::out | std::ios::trunc);
    if (meta) {
        meta << "format=unitree_rerun_telemetry_bin\n"
             << "format_version=" << kFormatVersion << "\n"
             << "start_unix_time_ns=" << start_unix_time_ns << "\n"
             << "start_iso_time=" << isoTime(start_unix_time_ns) << "\n"
             << "telemetry=telemetry.bin\n"
             << "summary=summary.csv\n"
             << "topic=" << config_.topic << "\n"
             << "lowcmd_topic=" << config_.lowcmd_topic << "\n"
             << "network_mode=" << config_.network_mode << "\n"
             << "network_interface=" << config_.network_interface << "\n"
             << "motor_count=" << config_.motor_count << "\n"
             << "sample_hz=" << config_.sample_hz << "\n"
             << "summary_hz=" << config_.summary_hz << "\n";
    }

    return true;
}

bool TelemetryWriter::writeHeader(uint64_t start_unix_time_ns, std::string& error)
{
    data_stream_.write(kMagic.data(), static_cast<std::streamsize>(kMagic.size()));
    writePod(data_stream_, kHeaderSize);
    writePod(data_stream_, kFormatVersion);
    writePod(data_stream_, config_.motor_count);
    writePod(data_stream_, start_unix_time_ns);
    writePod(data_stream_, config_.sample_hz);
    writePod(data_stream_, config_.summary_hz);
    const uint32_t reserved = 0;
    writePod(data_stream_, reserved);
    writeFixedString(data_stream_, config_.topic, 64);
    writeFixedString(data_stream_, config_.network_interface, 32);
    writeFixedString(data_stream_, config_.lowcmd_topic, 64);

    const std::array<char, 48> reserved_bytes{};
    data_stream_.write(reserved_bytes.data(), static_cast<std::streamsize>(reserved_bytes.size()));

    if (!data_stream_) {
        error = "failed to write telemetry header";
        return false;
    }
    return true;
}

void TelemetryWriter::writerLoop()
{
    while (running_.load()) {
        TelemetrySample sample;
        bool has_sample = false;
        {
            std::unique_lock<std::mutex> lock(queue_mutex_);
            queue_cv_.wait_for(lock, std::chrono::milliseconds(200), [this] {
                return !queue_.empty() || !running_.load();
            });
            if (!queue_.empty()) {
                sample = queue_.front();
                queue_.pop_front();
                has_sample = true;
            }
        }

        if (has_sample) writeSample(sample);
    }

    while (true) {
        TelemetrySample sample;
        {
            std::lock_guard<std::mutex> lock(queue_mutex_);
            if (queue_.empty()) break;
            sample = queue_.front();
            queue_.pop_front();
        }
        writeSample(sample);
    }
}

void TelemetryWriter::writeSample(const TelemetrySample& sample)
{
    writePod(data_stream_, sample.unix_time_ns);
    writePod(data_stream_, sample.steady_time_ns);
    writePod(data_stream_, sample.sequence);
    writePod(data_stream_, sample.dropped_samples);
    writePod(data_stream_, sample.source_tick);
    writePod(data_stream_, sample.mode_pr);
    writePod(data_stream_, sample.mode_machine);
    const uint16_t reserved = 0;
    writePod(data_stream_, reserved);

    for (uint32_t i = 0; i < config_.motor_count; ++i) {
        writePod(data_stream_, sample.q[i]);
        writePod(data_stream_, sample.dq[i]);
        writePod(data_stream_, sample.tau_est[i]);
        writePod(data_stream_, sample.temp_case[i]);
        writePod(data_stream_, sample.temp_winding[i]);
        writePod(data_stream_, sample.motor_state[i]);
    }

    for (float value : sample.imu_quat) writePod(data_stream_, value);
    for (float value : sample.imu_gyro) writePod(data_stream_, value);
    for (float value : sample.imu_accel) writePod(data_stream_, value);
    for (float value : sample.imu_rpy) writePod(data_stream_, value);
    writePod(data_stream_, sample.imu_temp);
    writePod(data_stream_, reserved);

    writePod(data_stream_, sample.lowcmd_steady_time_ns);
    writePod(data_stream_, sample.lowcmd_sequence);
    const uint8_t lowcmd_received = sample.lowcmd_received ? 1 : 0;
    writePod(data_stream_, lowcmd_received);
    writePod(data_stream_, sample.lowcmd_mode_pr);
    writePod(data_stream_, sample.lowcmd_mode_machine);
    const std::array<uint8_t, 5> lowcmd_padding{};
    data_stream_.write(
        reinterpret_cast<const char*>(lowcmd_padding.data()),
        static_cast<std::streamsize>(lowcmd_padding.size()));
    for (uint32_t value : sample.lowcmd_reserve) writePod(data_stream_, value);
    writePod(data_stream_, sample.lowcmd_crc);

    const std::array<uint8_t, 3> motor_cmd_padding{};
    for (uint32_t i = 0; i < config_.motor_count; ++i) {
        writePod(data_stream_, sample.cmd_mode[i]);
        data_stream_.write(
            reinterpret_cast<const char*>(motor_cmd_padding.data()),
            static_cast<std::streamsize>(motor_cmd_padding.size()));
        writePod(data_stream_, sample.cmd_q[i]);
        writePod(data_stream_, sample.cmd_dq[i]);
        writePod(data_stream_, sample.cmd_tau[i]);
        writePod(data_stream_, sample.cmd_kp[i]);
        writePod(data_stream_, sample.cmd_kd[i]);
        writePod(data_stream_, sample.cmd_reserve[i]);
    }

    writeSummaryIfDue(sample);
}

void TelemetryWriter::writeSummaryIfDue(const TelemetrySample& sample)
{
    if (!summary_stream_ || config_.summary_hz <= 0.0) return;

    const uint64_t interval_ns = static_cast<uint64_t>((1.0 / config_.summary_hz) * 1000000000.0);
    if (last_summary_ns_ != 0 && sample.unix_time_ns - last_summary_ns_ < interval_ns) return;

    float max_temp = -10000.0f;
    float temp_sum = 0.0f;
    float max_abs_tau = 0.0f;
    float max_abs_dq = 0.0f;
    int max_temp_motor = -1;
    for (uint32_t i = 0; i < config_.motor_count; ++i) {
        const float hottest = std::max(static_cast<float>(sample.temp_case[i]),
                                       static_cast<float>(sample.temp_winding[i]));
        temp_sum += hottest;
        if (hottest > max_temp) {
            max_temp = hottest;
            max_temp_motor = static_cast<int>(i);
        }
        max_abs_tau = std::max(max_abs_tau, std::abs(sample.tau_est[i]));
        max_abs_dq = std::max(max_abs_dq, std::abs(sample.dq[i]));
    }

    const double lowcmd_age_ms = sample.lowcmd_received
        ? static_cast<double>(sample.steady_time_ns - sample.lowcmd_steady_time_ns) / 1000000.0
        : -1.0;

    summary_stream_ << sample.unix_time_ns << ','
                    << isoTime(sample.unix_time_ns) << ','
                    << sample.sequence << ','
                    << static_cast<unsigned>(sample.mode_machine) << ','
                    << max_temp << ','
                    << max_temp_motor << ','
                    << (temp_sum / static_cast<float>(config_.motor_count)) << ','
                    << sample.imu_temp << ','
                    << max_abs_tau << ','
                    << max_abs_dq << ','
                    << sample.dropped_samples << ','
                    << (sample.lowcmd_received ? 1 : 0) << ','
                    << sample.lowcmd_sequence << ','
                    << lowcmd_age_ms << '\n';
    last_summary_ns_ = sample.unix_time_ns;
}

}  // namespace unitree_rerun
