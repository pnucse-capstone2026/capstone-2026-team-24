from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.robots.so_follower import SOFollower, SOFollowerConfig
from lerobot.teleoperators.so_leader import SOLeaderConfig, SOLeader
from lerobot.common.control_utils import init_keyboard_listener
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_rerun
from lerobot.scripts.lerobot_record import record_loop
from lerobot.processor import make_default_processors

NUM_EPISODES = 10
FPS = 30
EPISODE_TIME_SEC = 60
RESET_TIME_SEC = 10
TASK_DESCRIPTION = "My task description"
FOLLOWER_ARM_ID="so101_follower_arm"
FOLLOWER_ARM_PORT="/dev/ttyACM0"
LEADER_ARM_ID="so101_leader_arm"
LEADER_ARM_PORT="dev/ttyACM1"

# Create configuration
robot_config = SOFollowerConfig(
    id=FOLLOWER_ARM_ID,
    port=FOLLOWER_ARM_PORT,
    cameras={
        "front": OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=FPS) # Optional: fourcc="MJPG" for troubleshooting OpenCV async error.
    }
)

teleop_config = SOLeaderConfig(
    id=LEADER_ARM_ID,
    port=LEADER_ARM_PORT,
)



# Initialize the robot and teleoperator
robot = SOFollower(robot_config)
teleop = SOLeader(teleop_config)

# 피처 수동 설정 코드를 전부 지우고 바로 데이터셋을 생성합니다.
dataset = LeRobotDataset.create(
    repo_id="<hf_username>/<dataset_repo_id>",
    fps=FPS,
    robot_type=robot.name,
    use_videos=True,
    image_writer_threads=4,
)


# Initialize the keyboard listener and rerun visualization
_, events = init_keyboard_listener()
init_rerun(session_name="recording")

# Connect the robot and teleoperator
robot.connect()
teleop.connect()

# Create the required processors
teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

episode_idx = 0
while episode_idx < NUM_EPISODES and not events["stop_recording"]:
    log_say(f"Recording episode {episode_idx + 1} of {NUM_EPISODES}")

    record_loop(
        robot=robot,
        events=events,
        fps=FPS,
        teleop_action_processor=teleop_action_processor,
        robot_action_processor=robot_action_processor,
        robot_observation_processor=robot_observation_processor,
        teleop=teleop,
        dataset=dataset,
        control_time_s=EPISODE_TIME_SEC,
        single_task=TASK_DESCRIPTION,
        display_data=True,
    )

    # Reset the environment if not stopping or re-recording
    if not events["stop_recording"] and (episode_idx < NUM_EPISODES - 1 or events["rerecord_episode"]):
        log_say("Reset the environment")
        record_loop(
            robot=robot,
            events=events,
            fps=FPS,
            teleop_action_processor=teleop_action_processor,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            teleop=teleop,
            control_time_s=RESET_TIME_SEC,
            single_task=TASK_DESCRIPTION,
            display_data=True,
        )

    if events["rerecord_episode"]:
        log_say("Re-recording episode")
        events["rerecord_episode"] = False
        events["exit_early"] = False
        dataset.clear_episode_buffer()
        continue

    dataset.save_episode()
    episode_idx += 1

# Clean up
log_say("Stop recording")
robot.disconnect()
teleop.disconnect()
dataset.push_to_hub()


