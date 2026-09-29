import time
from pathlib import Path
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.robots.so_follower import SO100Follower, SO100FollowerConfig
from lerobot.teleoperators.so_leader import SO100LeaderConfig
from lerobot.teleoperators.so_leader.so100_leader import SO100Leader
from lerobot.utils.control_utils import init_keyboard_listener, control_loop
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_rerun
from lerobot.processor import make_default_processors

NUM_EPISODES = 5
FPS = 30  # 카메라 하드웨어 지원 스펙에 맞춰 30으로 고정
RESET_TIME_SEC = 3
TASK_DESCRIPTION = "My task description"

# CLI 로그 기준 포트 및 ID 매핑
FOLLOWER_ARM_ID = "follower"
FOLLOWER_ARM_PORT = "/dev/so101_follower"
LEADER_ARM_ID = "leader"
LEADER_ARM_PORT = "/dev/so101_leader"


# --------------------------------------------------------------------------------
# 커스텀 레코드 루프 함수 정의 (키 입력으로 종료)
# --------------------------------------------------------------------------------
def custom_record_loop(
    robot,
    events,
    fps,
    teleop_action_processor,
    robot_action_processor,
    robot_observation_processor,
    teleop=None,
    dataset=None,
    single_task=None,
    display_data=True,
    is_reset_loop=False,
    reset_time_s=3,
):
    start_time = time.perf_counter()
    
    for _ in control_loop(fps):
        # 1. 키 입력 확인 (pynput 정상 동작 시)
        if events is not None:
            if events["stop_recording"] or events["exit_early"] or events["rerecord_episode"]:
                break
                
            if not is_reset_loop and events["next_episode"]:
                events["next_episode"] = False
                break

        # 리셋 루프 시간 제한 탈출
        if is_reset_loop and (time.perf_counter() - start_time >= reset_time_s):
            break

        # 2. 제어 시퀀스
        action = teleop.read()
        processed_action = teleop_action_processor(action)

        observation = robot.step(processed_action)
        
        processed_observation = robot_observation_processor(observation)
        processed_robot_action = robot_action_processor(processed_action)

        # 데이터셋 프레임 추가
        if not is_reset_loop and dataset is not None:
            frame = {**processed_robot_action, **processed_observation}
            if single_task:
                frame["task"] = single_task
            dataset.add_frame(frame)


# --------------------------------------------------------------------------------
# 메인 제어 파트
# --------------------------------------------------------------------------------

# CLI에 제공하셨던 듀얼 카메라 사양 그대로 반영
robot_config = SO100FollowerConfig(
    id=FOLLOWER_ARM_ID,
    port=FOLLOWER_ARM_PORT,
    cameras={
        "top": OpenCVCameraConfig(index_or_path=Path("/dev/cam_top"), width=640, height=480, fps=FPS),
        "wrist": OpenCVCameraConfig(index_or_path=Path("/dev/cam_wrist"), width=640, height=480, fps=FPS)
    }
)

teleop_config = SO100LeaderConfig(
    id=LEADER_ARM_ID,
    port=LEADER_ARM_PORT,
)

robot = SO100Follower(robot_config)
teleop = SO100Leader(teleop_config)

# [핵심 수정] 최신 API 반영: features 구조를 패키지가 내부에서 직접 구성하도록 변경
dataset = LeRobotDataset.create(
    repo_id="s1eepypillow/my_task",  # 사용자 환경에 맞게 수정 가능
    fps=FPS,
    robot_type=robot.name,
    use_videos=True,
    image_writer_threads=4,
)

# 키보드 리스너 초기화 (실패 시 예외 처리 추가)
try:
    _, events = init_keyboard_listener()
except Exception:
    print("Warning: pynput keyboard listener failed. Please check if 'pynput' is installed.")
    events = None

init_rerun(session_name="recording")

robot.connect()
teleop.connect()

teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

episode_idx = 0
while episode_idx < NUM_EPISODES and (events is None or not events["stop_recording"]):
    log_say(f"Recording episode {episode_idx + 1} of {NUM_EPISODES}")

    custom_record_loop(
        robot=robot,
        events=events,
        fps=FPS,
        teleop_action_processor=teleop_action_processor,
        robot_action_processor=robot_action_processor,
        robot_observation_processor=robot_observation_processor,
        teleop=teleop,
        dataset=dataset,
        single_task=TASK_DESCRIPTION,
        display_data=False,  # Jetson GUI 크래시 방지 위해 False 권장
        is_reset_loop=False,
    )

    if events is not None and not events["stop_recording"] and (episode_idx < NUM_EPISODES - 1 or events["rerecord_episode"]):
        log_say("Reset the environment")
        
        custom_record_loop(
            robot=robot,
            events=events,
            fps=FPS,
            teleop_action_processor=teleop_action_processor,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            teleop=teleop,
            single_task=TASK_DESCRIPTION,
            display_data=False,
            is_reset_loop=True,
            reset_time_s=RESET_TIME_SEC,
        )

    if events is not None and events["rerecord_episode"]:
        log_say("Re-recording episode")
        events["rerecord_episode"] = False
        events["exit_early"] = False
        dataset.clear_episode_buffer()
        continue

    dataset.save_episode()
    episode_idx += 1

log_say("Stop recording")
robot.disconnect()
teleop.disconnect()
