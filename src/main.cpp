#include "unitree_rerun_sdk/config.h"
#include "unitree_rerun_sdk/recorder.h"

#include <atomic>
#include <csignal>
#include <iostream>
#include <string>

namespace {

std::atomic<bool> g_stop_requested(false);
unitree_rerun::Recorder* g_recorder = nullptr;

void signalHandler(int)
{
    g_stop_requested.store(true);
    if (g_recorder) {
        g_recorder->requestStop();
    }
}

void printUsage(const char* argv0)
{
    std::cout << "Usage: " << argv0 << " [--config recorder.conf]\n";
    std::cout << "Default config: recorder.conf next to the executable\n";
}

std::string defaultConfigPath(const char* argv0)
{
    const std::string exe_path = argv0 ? argv0 : "";
    const size_t slash = exe_path.find_last_of("/\\");
    if (slash == std::string::npos) {
        return "recorder.conf";
    }
    return exe_path.substr(0, slash + 1) + "recorder.conf";
}

}  // namespace

int main(int argc, char** argv)
{
    std::string config_path;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if ((arg == "--config" || arg == "-c") && i + 1 < argc) {
            config_path = argv[++i];
        } else if (arg == "--help" || arg == "-h") {
            printUsage(argv[0]);
            return 0;
        } else {
            std::cerr << "Unknown argument: " << arg << std::endl;
            printUsage(argv[0]);
            return 1;
        }
    }

    if (config_path.empty()) {
        config_path = defaultConfigPath(argv[0]);
    }

    unitree_rerun::RecorderConfig config;
    std::string error;
    if (!unitree_rerun::loadConfigFile(config_path, config, error)) {
        std::cerr << "Config error: " << error << std::endl;
        return 1;
    }

    std::cout << "[unitree_rerun] topic=" << config.topic
              << ", interface=" << config.network_interface
              << ", sample_hz=" << config.sample_hz
              << ", motor_count=" << config.motor_count
              << ", output_dir=" << config.output_dir
              << std::endl;

    unitree_rerun::Recorder recorder;
    g_recorder = &recorder;
    std::signal(SIGINT, signalHandler);
    std::signal(SIGTERM, signalHandler);

    if (!recorder.start(config, error)) {
        std::cerr << "Recorder start failed: " << error << std::endl;
        g_recorder = nullptr;
        return 1;
    }

    recorder.waitUntilStopped();
    g_recorder = nullptr;
    std::cout << "[unitree_rerun] stopped" << std::endl;
    return 0;
}
