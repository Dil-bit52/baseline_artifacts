#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

#include <pcl/point_cloud.h>

namespace fast_lio_lifecycle
{

struct LifecycleObserverConfig
{
    bool enabled = false;
    double voxel_size = 0.5;
    double time_bin_sec = 30.0;
    double flush_interval_sec = 60.0;
    std::string output_directory;
};

struct VoxelKey
{
    int64_t x = 0;
    int64_t y = 0;
    int64_t z = 0;

    bool operator==(const VoxelKey &other) const noexcept
    {
        return x == other.x && y == other.y && z == other.z;
    }

    bool operator<(const VoxelKey &other) const noexcept
    {
        if (x != other.x) return x < other.x;
        if (y != other.y) return y < other.y;
        return z < other.z;
    }
};

struct VoxelKeyHash
{
    std::size_t operator()(const VoxelKey &key) const noexcept
    {
        const auto mix = [](uint64_t value) {
            value ^= value >> 33U;
            value *= 0xff51afd7ed558ccdULL;
            value ^= value >> 33U;
            value *= 0xc4ceb9fe1a85ec53ULL;
            value ^= value >> 33U;
            return value;
        };
        const uint64_t hx = mix(static_cast<uint64_t>(key.x));
        const uint64_t hy = mix(static_cast<uint64_t>(key.y));
        const uint64_t hz = mix(static_cast<uint64_t>(key.z));
        return static_cast<std::size_t>(hx ^ (hy << 1U) ^ (hz << 7U));
    }
};

struct VoxelLifecycleInfo
{
    double first_seen_time = std::numeric_limits<double>::infinity();
    double last_seen_time = -std::numeric_limits<double>::infinity();
    uint64_t total_point_hits = 0;
    uint32_t observed_frames = 0;
    uint32_t active_time_bins = 0;
    double sum_x = 0.0;
    double sum_y = 0.0;
    double sum_z = 0.0;
    int64_t last_time_bin = std::numeric_limits<int64_t>::min();
};

class PassiveVoxelLifecycleObserver
{
public:
    explicit PassiveVoxelLifecycleObserver(LifecycleObserverConfig config);
    ~PassiveVoxelLifecycleObserver();

    PassiveVoxelLifecycleObserver(const PassiveVoxelLifecycleObserver &) = delete;
    PassiveVoxelLifecycleObserver &operator=(const PassiveVoxelLifecycleObserver &) = delete;

    bool enabled() const noexcept { return config_.enabled; }

    template <typename PointT>
    void observe_frame(const pcl::PointCloud<PointT> &cloud, double timestamp)
    {
        if (!config_.enabled)
        {
            return;
        }

        const auto start = std::chrono::steady_clock::now();
        if (!std::isfinite(timestamp))
        {
            ++invalid_timestamp_frames_;
            return;
        }
        if (frame_count_ > 0 && timestamp < last_frame_timestamp_)
        {
            ++non_monotonic_timestamp_frames_;
        }
        if (frame_count_ == 0)
        {
            first_frame_timestamp_ = timestamp;
            last_flush_timestamp_ = timestamp;
        }

        struct FrameAggregate
        {
            uint64_t hits = 0;
            double sum_x = 0.0;
            double sum_y = 0.0;
            double sum_z = 0.0;
        };

        std::unordered_map<VoxelKey, FrameAggregate, VoxelKeyHash> frame_voxels;
        frame_voxels.reserve(std::max<std::size_t>(16U, cloud.points.size() / 2U));

        uint64_t finite_points = 0;
        for (const auto &point : cloud.points)
        {
            const double x = static_cast<double>(point.x);
            const double y = static_cast<double>(point.y);
            const double z = static_cast<double>(point.z);
            if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z))
            {
                continue;
            }
            ++finite_points;
            const VoxelKey key{
                static_cast<int64_t>(std::floor(x / config_.voxel_size)),
                static_cast<int64_t>(std::floor(y / config_.voxel_size)),
                static_cast<int64_t>(std::floor(z / config_.voxel_size))};
            auto &aggregate = frame_voxels[key];
            ++aggregate.hits;
            aggregate.sum_x += x;
            aggregate.sum_y += y;
            aggregate.sum_z += z;
        }

        const int64_t time_bin = static_cast<int64_t>(
            std::floor((timestamp - first_frame_timestamp_) / config_.time_bin_sec));
        uint64_t new_voxels = 0;
        uint64_t reobserved_voxels = 0;
        for (const auto &entry : frame_voxels)
        {
            const VoxelKey &key = entry.first;
            const FrameAggregate &aggregate = entry.second;
            auto [it, inserted] = voxels_.try_emplace(key);
            VoxelLifecycleInfo &info = it->second;
            if (inserted)
            {
                info.first_seen_time = timestamp;
                info.last_seen_time = timestamp;
                info.active_time_bins = 1;
                info.last_time_bin = time_bin;
                checkpoint_new_keys_.push_back(key);
                ++new_voxels;
            }
            else
            {
                info.first_seen_time = std::min(info.first_seen_time, timestamp);
                info.last_seen_time = std::max(info.last_seen_time, timestamp);
                if (info.last_time_bin != time_bin)
                {
                    ++info.active_time_bins;
                    info.last_time_bin = time_bin;
                }
                ++reobserved_voxels;
            }
            info.total_point_hits += aggregate.hits;
            ++info.observed_frames;
            info.sum_x += aggregate.sum_x;
            info.sum_y += aggregate.sum_y;
            info.sum_z += aggregate.sum_z;
        }

        ++frame_count_;
        total_input_points_ += cloud.points.size();
        total_finite_points_ += finite_points;
        last_frame_timestamp_ = std::max(last_frame_timestamp_, timestamp);

        if (timestamp - last_flush_timestamp_ >= config_.flush_interval_sec)
        {
            write_checkpoint(timestamp);
            last_flush_timestamp_ = timestamp;
        }

        const double elapsed_ms = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - start).count();
        elapsed_ms_.push_back(elapsed_ms);
        total_observer_ms_ += elapsed_ms;
        max_observer_ms_ = std::max(max_observer_ms_, elapsed_ms);

        frame_stream_ << std::fixed << std::setprecision(9)
                      << timestamp << ',' << frame_count_ << ',' << cloud.points.size() << ','
                      << frame_voxels.size() << ',' << new_voxels << ',' << reobserved_voxels << ','
                      << voxels_.size() << ',' << std::setprecision(6) << elapsed_ms << '\n';
        if (frame_count_ % 100U == 0U)
        {
            frame_stream_.flush();
        }
    }

    void finalize();

private:
    void write_checkpoint(double timestamp);
    void write_final_csv();
    void write_summary_json();
    double percentile95_ms() const;

    LifecycleObserverConfig config_;
    std::filesystem::path output_directory_;
    std::ofstream frame_stream_;
    std::ofstream checkpoint_stream_;
    std::unordered_map<VoxelKey, VoxelLifecycleInfo, VoxelKeyHash> voxels_;
    std::vector<VoxelKey> checkpoint_new_keys_;
    std::vector<double> elapsed_ms_;
    uint64_t frame_count_ = 0;
    uint64_t total_input_points_ = 0;
    uint64_t total_finite_points_ = 0;
    uint64_t checkpoint_rows_ = 0;
    uint64_t invalid_timestamp_frames_ = 0;
    uint64_t non_monotonic_timestamp_frames_ = 0;
    double first_frame_timestamp_ = std::numeric_limits<double>::quiet_NaN();
    double last_frame_timestamp_ = -std::numeric_limits<double>::infinity();
    double last_flush_timestamp_ = std::numeric_limits<double>::quiet_NaN();
    double total_observer_ms_ = 0.0;
    double max_observer_ms_ = 0.0;
    bool finalized_ = false;
};

}  // namespace fast_lio_lifecycle
