import time
from pathlib import Path
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.robots.so_follower import SO100Follower, SO100FollowerConfig
# [변경] 클래스명에서 100이 제외되었습니다.
from lerobot.teleoperators.so_leader import SOLeaderConfig, SOLeader
# [변경] utils가 아니라 common 폴더에서 가져옵니다.
from lerobot.common.control_utils import init_keyboard_listener, control_loop
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_rerun
from lerobot.processor import make_default_processors

NUM_EPISODES = 5
FPS = 30  # 카메라 하드웨어 스펙에 맞춰 30으로 설정 (20으로 설정 시 크래시 발생 방지)
RESET_TIME_SEC = 3
TASK_DESCRIPTION = "My task description"

# CLI 로그 기준 정확한 포트 및 ID 매핑
FOLLOWER_ARM_ID = "follower"
FOLLOWER_ARM_PORT = "/dev/so101_follower"
LEADER_ARM_ID = "leader"
LEADER_ARM_PORT = "/dev/so101_leader"


# --------------------------------------------------------------------------------
# 시간 제한 대신 키 입력(next_episode)으로 종료되는 커스텀 레코드 루프 함수 정의
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
    is_reset_loop=False,  # 리셋 루프인지를 판별하기 위한 플래그
    reset_time_s=3,       # 리셋 루프일 때만 사용할 시간 제한
):
    """
    기존 record_loop를 대체하는 커스텀 루프.
    - 일반 에피소드 녹화 시: 시간 제한 없이 무한 루프 돌며 `events["next_episode"]` 키 입력 시 종료.
    - 리셋 루프 시: 기존처럼 지정된 시간(reset_time_s) 동안만 작동.
    """
    start_time = time.perf_counter()
    
    # lerobot의 common 제어기 루프 사용
    for _ in control_loop(fps):
        # 1. 키 입력에 의한 탈출 조건 확인 (pynput 정상 로드 시에만 작동)
        if events is not None:
            if events["stop_recording"] or events["exit_early"] or events["rerecord_episode"]:
                break
                
            # [핵심 수정] 일반 녹화일 때 사용자가 '다음 에피소드(next_episode)' 키를 누르면 루프 탈출
            if not is_reset_loop and events["next_episode"]:
                events["next_episode"] = False  # 이벤트 플래그 초기화
                break

        # [리셋용] 리셋 루프일 때는 기존처럼 시간 기준으로 자동 탈출
        if is_reset_loop and (time.perf_counter() - start_time >= reset_time_s):
            break

        # 2. 로봇 제어 및 데이터 수집 시퀀스
        # 리더 로봇(Teleop)에서 액션 읽기
        action = teleop.read()
        processed_action = teleop_action_processor(action)

        # 팔로워 로봇에 액션 명령 전달 및 관측치(Observation) 획득
        observation = robot.step(processed_action)
        
        # 프로세서를 통한 데이터 정제
        processed_observation = robot_observation_processor(observation)
        processed_robot_action = robot_action_processor(processed_action)

        # 데이터셋 저장 (리셋 루프가 아니고 데이터셋 객체가 제공되었을 때만)
        if not is_reset_loop and dataset is not None:
            frame = {**processed_robot_action, **processed_observation}
            if single_task:
                frame["task"] = single_task
            dataset.add_frame(frame)


# --------------------------------------------------------------------------------
# 메인 제어 파트
# --------------------------------------------------------------------------------

# CLI 제공 사양 기반 듀얼 카메라 구성 적용
robot_config = SO100FollowerConfig(
    id=FOLLOWER_ARM_ID,
    port=FOLLOWER_ARM_PORT,
    cameras={
        "top": OpenCVCameraConfig(index_or_path=Path("/dev/cam_top"), width=640, height=480, fps=FPS),
        "wrist": OpenCVCameraConfig(index_or_path=Path("/dev/cam_wrist"), width=640, height=480, fps=FPS)
    }
)

# [변경] 최신 SOLeaderConfig 클래스 사용
teleop_config = SOLeaderConfig(
    id=LEADER_ARM_ID,
    port=LEADER_ARM_PORT,
)

# Initialize the robot and teleoperator
robot = SO100Follower(robot_config)
teleop = SOLeader(teleop_config)  # [변경] 최신 SOLeader 클래스 사용

# [변경] 최신 API 반영: features 구조를 패키지가 내부에서 직접 구성하도록 생략
dataset = LeRobotDataset.create(
    repo_id="s1eepypillow/my_task",
    fps=FPS,
    robot_type=robot.name,
    use_videos=True,
    image_writer_threads=4,
)

# Initialize the keyboard listener (Headless 환경 대비 예외처리 추가)
try:
    _, events = init_keyboard_listener()
except Exception:
    print("Warning: pynput keyboard listener failed. (Headless Mode)")
    events = None

init_rerun(session_name="recording")

# Connect the robot and teleoperator
robot.connect()
teleop.connect()

# Create the required processors
teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

episode_idx = 0
while episode_idx < NUM_EPISODES and (events is None or not events["stop_recording"]):
    log_say(f"Recording episode {episode_idx + 1} of {NUM_EPISODES}")

    # 커스텀 레코드 루프 실행 (키 입력으로 종료)
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
        display_data=False,  # Jetson GUI 부하 최소화를 위해 False 권장
        is_reset_loop=False,  # 일반 에피소드 수집 모드
    )

    # Reset the environment if not stopping or re-recording
    if events is not None and not events["stop_recording"] and (episode_idx < NUM_EPISODES - 1 or events["rerecord_episode"]):
        log_say("Reset the environment")
        
        # 리셋 루프 실행 (리셋은 지정된 시간 초과 시 자동 종료)
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
            is_reset_loop=True,       # 리셋 모드 활성화
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

# Clean up
log_say("Stop recording")
robot.disconnect()
teleop.disconnect()
