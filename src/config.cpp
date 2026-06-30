#include "unitree_rerun_sdk/config.h"

#include <algorithm>
#include <cctype>
#include <fstream>

namespace unitree_rerun {
namespace {

std::string trim(const std::string& in)
{
    size_t begin = 0;
    while (begin < in.size() && std::isspace(static_cast<unsigned char>(in[begin]))) ++begin;
    size_t end = in.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(in[end - 1]))) --end;
    return in.substr(begin, end - begin);
}

std::string lower(std::string in)
{
    std::transform(in.begin(), in.end(), in.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return in;
}

bool parseUint32(const std::string& value, uint32_t& out)
{
    try {
        size_t idx = 0;
        const unsigned long parsed = std::stoul(value, &idx, 0);
        if (idx != value.size()) return false;
        out = static_cast<uint32_t>(parsed);
        return true;
    } catch (...) {
        return false;
    }
}

}  // namespace

bool parseBool(const std::string& value, bool& out)
{
    const std::string v = lower(trim(value));
    if (v == "1" || v == "true" || v == "yes" || v == "on") {
        out = true;
        return true;
    }
    if (v == "0" || v == "false" || v == "no" || v == "off") {
        out = false;
        return true;
    }
    return false;
}

bool loadConfigFile(const std::string& path, RecorderConfig& config, std::string& error)
{
    std::ifstream in(path);
    if (!in) {
        error = "failed to open config: " + path;
        return false;
    }

    std::string line;
    int line_no = 0;
    while (std::getline(in, line)) {
        ++line_no;
        const size_t comment = line.find('#');
        if (comment != std::string::npos) line.resize(comment);
        line = trim(line);
        if (line.empty()) continue;

        const size_t eq = line.find('=');
        if (eq == std::string::npos) {
            error = "invalid config line " + std::to_string(line_no) + ": " + line;
            return false;
        }

        const std::string key = lower(trim(line.substr(0, eq)));
        const std::string value = trim(line.substr(eq + 1));

        try {
            if (key == "network_mode") {
                config.network_mode = std::stoi(value);
            } else if (key == "network_interface") {
                config.network_interface = value;
            } else if (key == "topic") {
                config.topic = value;
            } else if (key == "output_dir") {
                config.output_dir = value;
            } else if (key == "motor_count") {
                uint32_t parsed = 0;
                if (!parseUint32(value, parsed) || parsed == 0 || parsed > kMaxMotorCount) {
                    error = "invalid motor_count at line " + std::to_string(line_no);
                    return false;
                }
                config.motor_count = parsed;
            } else if (key == "sample_hz") {
                config.sample_hz = std::stod(value);
            } else if (key == "summary_hz") {
                config.summary_hz = std::stod(value);
            } else if (key == "max_queue_samples") {
                config.max_queue_samples = static_cast<size_t>(std::stoull(value));
            } else if (key == "validate_crc") {
                bool enabled = true;
                if (!parseBool(value, enabled)) {
                    error = "invalid validate_crc boolean at line " + std::to_string(line_no);
                    return false;
                }
                config.validate_crc = enabled;
            }
        } catch (const std::exception& e) {
            error = "invalid value at line " + std::to_string(line_no) + ": " + e.what();
            return false;
        }
    }

    if (config.sample_hz <= 0.0) {
        error = "sample_hz must be > 0";
        return false;
    }
    if (config.summary_hz < 0.0) {
        error = "summary_hz must be >= 0";
        return false;
    }
    return true;
}

}  // namespace unitree_rerun
