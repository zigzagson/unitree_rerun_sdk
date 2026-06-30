#ifndef UNITREE_RERUN_SDK_TELEMETRY_WRITER_H
#define UNITREE_RERUN_SDK_TELEMETRY_WRITER_H

#include "unitree_rerun_sdk/config.h"
#include "unitree_rerun_sdk/telemetry_sample.h"

#include <atomic>
#include <condition_variable>
#include <deque>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>

namespace unitree_rerun {

class TelemetryWriter {
public:
    TelemetryWriter();
    ~TelemetryWriter();

    TelemetryWriter(const TelemetryWriter&) = delete;
    TelemetryWriter& operator=(const TelemetryWriter&) = delete;

    bool start(const RecorderConfig& config, uint64_t start_unix_time_ns, std::string& error);
    void stop();
    void enqueue(const TelemetrySample& sample);

    const std::string& sessionDir() const { return session_dir_; }
    const std::string& dataPath() const { return data_path_; }
    uint64_t droppedSamples() const { return dropped_samples_.load(); }

private:
    bool openSession(uint64_t start_unix_time_ns, std::string& error);
    bool writeHeader(uint64_t start_unix_time_ns, std::string& error);
    void writerLoop();
    void writeSample(const TelemetrySample& sample);
    void writeSummaryIfDue(const TelemetrySample& sample);

    RecorderConfig config_;

    std::atomic<bool> running_;
    std::thread writer_thread_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::deque<TelemetrySample> queue_;
    std::atomic<uint64_t> dropped_samples_;

    std::ofstream data_stream_;
    std::ofstream summary_stream_;
    std::string session_dir_;
    std::string data_path_;
    uint64_t last_summary_ns_;
};

}  // namespace unitree_rerun

#endif  // UNITREE_RERUN_SDK_TELEMETRY_WRITER_H
