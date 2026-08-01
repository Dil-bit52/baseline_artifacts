#include "lifecycle_observer.hpp"

#include <iomanip>
#include <stdexcept>
#include <utility>

namespace fast_lio_lifecycle
{

PassiveVoxelLifecycleObserver::PassiveVoxelLifecycleObserver(LifecycleObserverConfig config)
    : config_(std::move(config))
{
    if (!config_.enabled)
    {
        return;
    }
    if (!std::isfinite(config_.voxel_size) || config_.voxel_size <= 0.0)
    {
        throw std::invalid_argument("lifecycle_observer.voxel_size must be finite and positive");
    }
    if (!std::isfinite(config_.time_bin_sec) || config_.time_bin_sec <= 0.0)
    {
        throw std::invalid_argument("lifecycle_observer.time_bin_sec must be finite and positive");
    }
    if (!std::isfinite(config_.flush_interval_sec) || config_.flush_interval_sec <= 0.0)
    {
        throw std::invalid_argument("lifecycle_observer.flush_interval_sec must be finite and positive");
    }
    if (config_.output_directory.empty())
    {
        throw std::invalid_argument("lifecycle_observer.output_directory is required when enabled");
    }

    output_directory_ = std::filesystem::path(config_.output_directory);
    std::filesystem::create_directories(output_directory_);

    frame_stream_.open(output_directory_ / "frame_lifecycle.csv", std::ios::out | std::ios::trunc);
    checkpoint_stream_.open(
        output_directory_ / "voxel_lifecycle_checkpoints.csv", std::ios::out | std::ios::trunc);
    if (!frame_stream_ || !checkpoint_stream_)
    {
        throw std::runtime_error("failed to open lifecycle observer output files");
    }
    frame_stream_ << "timestamp,frame_index,input_points,observed_voxels,new_voxels,reobserved_voxels,total_tracked_voxels,elapsed_ms\n";
    checkpoint_stream_ << "checkpoint_timestamp,voxel_x,voxel_y,voxel_z,first_seen_time,last_seen_time,total_point_hits,observed_frames,active_time_bins,sum_x,sum_y,sum_z\n";
    voxels_.max_load_factor(0.8F);
    voxels_.reserve(1000000U);
    checkpoint_new_keys_.reserve(250000U);
}

PassiveVoxelLifecycleObserver::~PassiveVoxelLifecycleObserver()
{
    try
    {
        finalize();
    }
    catch (...)
    {
        // Destructors must not throw during ROS shutdown. Earlier checkpoints remain recoverable.
    }
}

void PassiveVoxelLifecycleObserver::write_checkpoint(double timestamp)
{
    if (!config_.enabled || checkpoint_new_keys_.empty())
    {
        frame_stream_.flush();
        checkpoint_stream_.flush();
        return;
    }
    checkpoint_stream_ << std::fixed << std::setprecision(9);
    for (const VoxelKey &key : checkpoint_new_keys_)
    {
        const auto it = voxels_.find(key);
        if (it == voxels_.end())
        {
            continue;
        }
        const VoxelLifecycleInfo &info = it->second;
        checkpoint_stream_ << timestamp << ',' << key.x << ',' << key.y << ',' << key.z << ','
                           << info.first_seen_time << ',' << info.last_seen_time << ','
                           << info.total_point_hits << ',' << info.observed_frames << ','
                           << info.active_time_bins << ',' << info.sum_x << ',' << info.sum_y << ','
                           << info.sum_z << '\n';
        ++checkpoint_rows_;
    }
    checkpoint_new_keys_.clear();
    frame_stream_.flush();
    checkpoint_stream_.flush();
}

void PassiveVoxelLifecycleObserver::write_final_csv()
{
    const std::filesystem::path temporary = output_directory_ / "voxel_lifecycle_final.csv.tmp";
    const std::filesystem::path final_path = output_directory_ / "voxel_lifecycle_final.csv";
    std::ofstream stream(temporary, std::ios::out | std::ios::trunc);
    if (!stream)
    {
        throw std::runtime_error("failed to open final lifecycle CSV");
    }
    stream << "voxel_x,voxel_y,voxel_z,center_x,center_y,center_z,mean_x,mean_y,mean_z,first_seen_time,last_seen_time,lifespan_sec,total_point_hits,observed_frames,active_time_bins\n";

    stream << std::fixed << std::setprecision(9);
    for (const auto &entry : voxels_)
    {
        const VoxelKey &key = entry.first;
        const VoxelLifecycleInfo &info = entry.second;
        const double hits = static_cast<double>(info.total_point_hits);
        stream << key.x << ',' << key.y << ',' << key.z << ','
               << (static_cast<double>(key.x) + 0.5) * config_.voxel_size << ','
               << (static_cast<double>(key.y) + 0.5) * config_.voxel_size << ','
               << (static_cast<double>(key.z) + 0.5) * config_.voxel_size << ','
               << info.sum_x / hits << ',' << info.sum_y / hits << ',' << info.sum_z / hits << ','
               << info.first_seen_time << ',' << info.last_seen_time << ','
               << std::max(0.0, info.last_seen_time - info.first_seen_time) << ','
               << info.total_point_hits << ',' << info.observed_frames << ','
               << info.active_time_bins << '\n';
    }
    stream.flush();
    if (!stream)
    {
        throw std::runtime_error("failed while writing final lifecycle CSV");
    }
    stream.close();
    std::error_code error;
    std::filesystem::remove(final_path, error);
    error.clear();
    std::filesystem::rename(temporary, final_path, error);
    if (error)
    {
        throw std::runtime_error("failed to atomically publish final lifecycle CSV: " + error.message());
    }
}

double PassiveVoxelLifecycleObserver::percentile95_ms() const
{
    if (elapsed_ms_.empty())
    {
        return 0.0;
    }
    std::vector<double> sorted = elapsed_ms_;
    std::sort(sorted.begin(), sorted.end());
    const std::size_t index = static_cast<std::size_t>(
        std::ceil(0.95 * static_cast<double>(sorted.size()))) - 1U;
    return sorted[std::min(index, sorted.size() - 1U)];
}

void PassiveVoxelLifecycleObserver::write_summary_json()
{
    const std::filesystem::path temporary = output_directory_ / "lifecycle_run_summary.json.tmp";
    const std::filesystem::path final_path = output_directory_ / "lifecycle_run_summary.json";
    std::ofstream stream(temporary, std::ios::out | std::ios::trunc);
    if (!stream)
    {
        throw std::runtime_error("failed to open lifecycle summary JSON");
    }
    const double duration = frame_count_ > 0
        ? std::max(0.0, last_frame_timestamp_ - first_frame_timestamp_)
        : 0.0;
    const double mean_ms = frame_count_ > 0
        ? total_observer_ms_ / static_cast<double>(frame_count_)
        : 0.0;
    stream << std::fixed << std::setprecision(9)
           << "{\n"
           << "  \"schema_version\": 1,\n"
           << "  \"variant\": \"B2 Passive Voxel Lifecycle Observer\",\n"
           << "  \"status\": \"finalized\",\n"
           << "  \"frame_id\": \"camera_init\",\n"
           << "  \"source_cloud\": \"feats_down_world after map_incremental\",\n"
           << "  \"config\": {\n"
           << "    \"enabled\": true,\n"
           << "    \"voxel_size\": " << config_.voxel_size << ",\n"
           << "    \"time_bin_sec\": " << config_.time_bin_sec << ",\n"
           << "    \"flush_interval_sec\": " << config_.flush_interval_sec << ",\n"
           << "    \"output_directory\": \"" << config_.output_directory << "\"\n"
           << "  },\n"
           << "  \"frames\": " << frame_count_ << ",\n"
           << "  \"sensor_start_time\": " << (frame_count_ > 0 ? first_frame_timestamp_ : 0.0) << ",\n"
           << "  \"sensor_end_time\": " << (frame_count_ > 0 ? last_frame_timestamp_ : 0.0) << ",\n"
           << "  \"sensor_duration_sec\": " << duration << ",\n"
           << "  \"total_input_points\": " << total_input_points_ << ",\n"
           << "  \"total_finite_points\": " << total_finite_points_ << ",\n"
           << "  \"total_tracked_voxels\": " << voxels_.size() << ",\n"
           << "  \"checkpoint_rows\": " << checkpoint_rows_ << ",\n"
           << "  \"invalid_timestamp_frames\": " << invalid_timestamp_frames_ << ",\n"
           << "  \"non_monotonic_timestamp_frames\": " << non_monotonic_timestamp_frames_ << ",\n"
           << "  \"observer_elapsed_ms\": {\n"
           << "    \"mean\": " << mean_ms << ",\n"
           << "    \"p95\": " << percentile95_ms() << ",\n"
           << "    \"max\": " << max_observer_ms_ << ",\n"
           << "    \"sum\": " << total_observer_ms_ << "\n"
           << "  },\n"
           << "  \"outputs\": {\n"
           << "    \"frame_lifecycle_csv\": \"frame_lifecycle.csv\",\n"
           << "    \"checkpoint_csv\": \"voxel_lifecycle_checkpoints.csv\",\n"
           << "    \"voxel_lifecycle_final_csv\": \"voxel_lifecycle_final.csv\"\n"
           << "  }\n"
           << "}\n";
    stream.flush();
    if (!stream)
    {
        throw std::runtime_error("failed while writing lifecycle summary JSON");
    }
    stream.close();
    std::error_code error;
    std::filesystem::remove(final_path, error);
    error.clear();
    std::filesystem::rename(temporary, final_path, error);
    if (error)
    {
        throw std::runtime_error("failed to atomically publish lifecycle summary JSON: " + error.message());
    }
}

void PassiveVoxelLifecycleObserver::finalize()
{
    if (!config_.enabled || finalized_)
    {
        return;
    }
    if (frame_count_ > 0)
    {
        write_checkpoint(last_frame_timestamp_);
    }
    write_final_csv();
    write_summary_json();
    frame_stream_.flush();
    checkpoint_stream_.flush();
    frame_stream_.close();
    checkpoint_stream_.close();
    finalized_ = true;
}

}  // namespace fast_lio_lifecycle
