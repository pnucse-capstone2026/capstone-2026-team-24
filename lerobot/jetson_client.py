"""
Jetson 쪽 실시간 추론 클라이언트.

개선 사항
- 카메라를 별도 thread에서 지속적으로 읽음
- 메인 loop는 최신 프레임만 사용
- JPEG quality 조절
- TCP_NODELAY 적용
- latency 세부 측정
- 서버 응답 대기와 로컬 처리 시간을 분리
- 기존 action/state 형식 유지
- target_hz로 loop 속도 제한
- 종료 시 초기 위치로 복귀
- dry_run: 실제 로봇 구동 없이 통신/속도만 테스트
- max_steps: 최대 step 수 제한
- environment_state: task 구분값을 서버 request에 포함
- 안전장치: NaN/Inf action 차단, step당 최대 변화량(delta) 제한,
  (선택) joint 별 최소/최대 위치 제한, 연속 위험 action 감지 시 비상 정지

주의:
  --debug를 켜면 매 step마다 print가 여러 번 실행되어 I/O 오버헤드가
  더해지고, 특히 ssh/serial 콘솔처럼 출력이 느린 환경에서는 실제 loop
  주기가 늘어나 로봇이 느리게/끊기듯 움직일 수 있다. 실제 수집/운용
  시에는 --debug를 끄고 실행할 것 (튜닝할 때만 켜서 확인).

사용법:

# Task1
python jetson_client.py \
    --server_host localhost \
    --server_port 9999 \
    --environment_state 0 \
    --duration 180 \
    --max_steps 100

# Task2
python jetson_client.py \
    --server_host localhost \
    --server_port 9999 \
    --environment_state 1 \
    --duration 180 \
    --max_steps 100

# 실제 로봇을 움직이지 않고 테스트만 하고 싶을 때
python jetson_client.py \
    --server_host localhost \
    --server_port 9999 \
    --environment_state 0 \
    --dry_run \
    --max_steps 200 \
    --debug
"""

import argparse
import math
import pickle
import socket
import struct
import threading
import time

import cv2

from lerobot.robots.so_follower.so_follower import SO101Follower
from lerobot.robots.so_follower.config_so_follower import SO101FollowerConfig
from lerobot.cameras.opencv import OpenCVCamera, OpenCVCameraConfig


# ============================================================
# Robot state/action key 정의
# ============================================================

STATE_KEYS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]

ACTION_KEYS = STATE_KEYS


# ============================================================
# 통신
# ============================================================

def recv_exact(sock, n):
    buf = b""

    while len(buf) < n:
        chunk = sock.recv(n - len(buf))

        if not chunk:
            raise ConnectionError("서버 연결이 끊겼습니다.")

        buf += chunk

    return buf


def recv_msg(sock):
    length_bytes = recv_exact(sock, 4)
    length = struct.unpack(">I", length_bytes)[0]

    payload = recv_exact(sock, length)

    return pickle.loads(payload)


def send_msg(sock, obj):
    payload = pickle.dumps(
        obj,
        protocol=pickle.HIGHEST_PROTOCOL,
    )

    sock.sendall(
        struct.pack(">I", len(payload)) + payload
    )


# ============================================================
# JPEG
# ============================================================

def frame_to_jpg_bytes(frame, quality=75):
    ok, buf = cv2.imencode(
        ".jpg",
        frame,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            quality,
        ],
    )

    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")

    return buf.tobytes()


# ============================================================
# Robot state helper
# ============================================================

def get_robot_state_list(robot, obs=None):
    """
    robot의 현재 state를 list[float]로 반환한다.
    (기존 loop 안의 state 추출 로직을 재사용하기 위해 분리)
    """

    if obs is None:
        obs = robot.get_observation()

    state = obs.get("observation.state", None)

    if state is None:

        try:
            state = [
                obs[key]
                for key in STATE_KEYS
            ]

        except KeyError as e:
            raise KeyError(
                "SO101 observation에서 "
                f"{e}를 찾을 수 없습니다.\n"
                f"현재 keys={list(obs.keys())}"
            )

    return (
        state.tolist()
        if hasattr(state, "tolist")
        else list(state)
    )


class SafetyStopError(Exception):
    """
    연속으로 위험한(비정상적인) action이 들어와서
    더 이상 진행하면 안 될 때 발생시키는 예외.

    바닥을 쾅쾅 찍는 것처럼 튀는 action이 반복될 때
    loop를 강제 종료시키고 초기 위치로 복귀시키기 위함.
    """
    pass


def sanitize_action(
    action,
    previous_safe_action,
    max_delta=None,
    joint_min=None,
    joint_max=None,
):
    """
    서버에서 받은 action을 로봇에 보내기 전에 검증/보정한다.

    1. NaN/Inf 값 -> 직전 안전한 action 값으로 대체
    2. joint_min/joint_max가 주어지면 해당 범위로 clamp
    3. max_delta가 주어지면 직전 action 대비 변화량을 clamp
       (한 step에 너무 크게 움직여서 바닥을 찍는 것을 방지)

    Returns:
        (safe_action, was_unsafe)
        was_unsafe: NaN/Inf가 있었거나 delta/range clamp가
                    실제로 적용됐으면 True
    """

    n = len(action)
    safe_action = list(action)
    was_unsafe = False

    for i in range(n):

        value = safe_action[i]
        prev_value = previous_safe_action[i]

        # ---------------------------------------------------
        # 1. NaN / Inf 체크
        # ---------------------------------------------------

        if (
            value is None
            or math.isnan(value)
            or math.isinf(value)
        ):
            safe_action[i] = prev_value
            was_unsafe = True
            continue

        value = float(value)

        # ---------------------------------------------------
        # 2. joint 범위 clamp
        # ---------------------------------------------------

        if joint_min is not None and value < joint_min[i]:
            value = joint_min[i]
            was_unsafe = True

        if joint_max is not None and value > joint_max[i]:
            value = joint_max[i]
            was_unsafe = True

        # ---------------------------------------------------
        # 3. step당 최대 변화량 clamp
        # ---------------------------------------------------

        if max_delta is not None:

            delta = value - prev_value

            if delta > max_delta[i]:
                value = prev_value + max_delta[i]
                was_unsafe = True

            elif delta < -max_delta[i]:
                value = prev_value - max_delta[i]
                was_unsafe = True

        safe_action[i] = value

    return safe_action, was_unsafe


def parse_per_joint_arg(raw, n, name):
    """
    "--max_action_delta 8.0" 처럼 값 1개를 주면 모든 joint에 동일 적용,
    "--max_action_delta 8,8,8,8,8,4" 처럼 콤마로 n개를 주면 joint별로 적용.
    """

    if raw is None:
        return None

    parts = [p.strip() for p in str(raw).split(",")]

    try:
        values = [float(p) for p in parts]
    except ValueError:
        raise ValueError(
            f"{name} 파싱 실패: '{raw}' "
            "(숫자 1개 또는 콤마로 구분된 숫자 n개여야 함)"
        )

    if len(values) == 1:
        return values * n

    if len(values) != n:
        raise ValueError(
            f"{name} 값 개수가 안 맞습니다: "
            f"{len(values)}개 (joint 수={n})"
        )

    return values


def move_to_home(robot, current_state, home_state, duration=2.0, hz=20.0):
    """
    current_state -> home_state 로 선형 보간하며 부드럽게 이동.
    갑자기 튀는 동작을 막기 위해 여러 step에 나눠서 전송한다.
    """

    steps = max(1, int(duration * hz))
    interval = 1.0 / hz

    print(
        f"[클라이언트] 초기 위치로 복귀 중... "
        f"(duration={duration:.1f}s, steps={steps})"
    )

    for i in range(1, steps + 1):
        alpha = i / steps

        interp_state = [
            current_state[j]
            + (home_state[j] - current_state[j]) * alpha
            for j in range(len(ACTION_KEYS))
        ]

        action_dict = {
            key: float(value)
            for key, value in zip(
                ACTION_KEYS,
                interp_state,
            )
        }

        robot.send_action(action_dict)

        time.sleep(interval)

    print("[클라이언트] 초기 위치 복귀 완료")


# ============================================================
# Camera Worker
# ============================================================

class CameraWorker:
    """
    카메라를 별도 thread에서 계속 읽고
    가장 최신 프레임만 유지한다.

    main loop는 camera.read()를 기다리지 않는다.
    """

    def __init__(self, camera, name):
        self.camera = camera
        self.name = name

        self.latest_frame = None

        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"camera-{name}",
        )

        self.read_count = 0
        self.last_read_time = None
        self.last_exception = None

    def start(self):
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():

            try:
                frame = self.camera.read()

                with self.lock:
                    self.latest_frame = frame
                    self.read_count += 1
                    self.last_read_time = time.perf_counter()

            except Exception as e:
                self.last_exception = e

                print(
                    f"[카메라:{self.name}] read 오류: {e}"
                )

                time.sleep(0.01)

    def get_latest(self):
        with self.lock:
            if self.latest_frame is None:
                return None

            # numpy frame을 그대로 사용하기 때문에
            # worker가 다음 프레임을 쓰기 전에 copy한다.
            return self.latest_frame.copy()

    def stop(self):
        self.stop_event.set()

        if self.thread.is_alive():
            self.thread.join(timeout=2.0)


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--server_host",
        type=str,
        required=True,
    )

    parser.add_argument(
        "--server_port",
        type=int,
        default=9999,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=180.0,
    )

    parser.add_argument(
        "--jpeg_quality",
        type=int,
        default=75,
    )

    parser.add_argument(
        "--target_hz",
        type=float,
        default=30.0,
        help="loop 목표 속도(Hz). 0 이하면 속도 제한 없음.",
    )

    parser.add_argument(
        "--no_return_home",
        action="store_true",
        help="종료 시 초기 위치로 복귀하지 않음",
    )

    parser.add_argument(
        "--home_duration",
        type=float,
        default=2.0,
        help="초기 위치로 복귀하는 데 걸리는 시간(초)",
    )

    parser.add_argument(
        "--dry_run",
        action="store_true",
        help=(
            "실제로 robot.send_action()을 호출하지 않고 "
            "통신/속도/안전장치만 테스트"
        ),
    )

    parser.add_argument(
        "--max_steps",
        type=int,
        default=0,
        help="최대 step 수 (0 이하면 제한 없음, duration과 함께 적용됨)",
    )

    parser.add_argument(
        "--environment_state",
        type=int,
        choices=[0, 1],
        required=True,
        help="task 구분: 0=task1, 1=task2 (서버 request에 그대로 실려감)",
    )

    # -----------------------------------------------------------
    # 안전장치 (바닥 찍는 문제 방지)
    # -----------------------------------------------------------

    parser.add_argument(
        "--max_action_delta",
        type=str,
        default=None,
        help=(
            "step당 joint별 최대 변화량. "
            "'8.0' (전체 동일) 또는 '8,8,8,8,8,4' (joint별) 형식. "
            "단위는 로봇 raw position 단위와 동일하니 실제 값을 보면서 튜닝할 것. "
            "지정 안 하면 delta clamp 비활성화."
        ),
    )

    parser.add_argument(
        "--joint_min",
        type=str,
        default=None,
        help="joint별 최소 위치. '--max_action_delta'와 같은 형식.",
    )

    parser.add_argument(
        "--joint_max",
        type=str,
        default=None,
        help="joint별 최대 위치. '--max_action_delta'와 같은 형식.",
    )

    parser.add_argument(
        "--max_consecutive_unsafe",
        type=int,
        default=15,
        help=(
            "이 값만큼 연속으로 위험한(clamp된) action이 들어오면 "
            "loop를 강제 종료하고 초기 위치로 복귀"
        ),
    )

    parser.add_argument(
        "--debug",
        action="store_true",
    )

    parser.add_argument(
        "--print_every",
        type=int,
        default=10,
        help="몇 step마다 debug 출력할지",
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # 안전장치 파라미터 파싱 (joint 수 = 6)
    # --------------------------------------------------------

    n_joints = len(ACTION_KEYS)

    max_action_delta = parse_per_joint_arg(
        args.max_action_delta,
        n_joints,
        "--max_action_delta",
    )

    joint_min = parse_per_joint_arg(
        args.joint_min,
        n_joints,
        "--joint_min",
    )

    joint_max = parse_per_joint_arg(
        args.joint_max,
        n_joints,
        "--joint_max",
    )

    if args.dry_run:
        print(
            "[클라이언트] *** DRY RUN 모드: "
            "robot.send_action()이 호출되지 않습니다 ***"
        )

    # ========================================================
    # Robot
    # ========================================================

    robot_config = SO101FollowerConfig(
        port="/dev/so101_follower",
        id="follower",
    )

    robot = SO101Follower(robot_config)

    robot.connect()

    print("[클라이언트] 로봇 연결 완료")

    # finally 블록에서 참조할 수 있도록 미리 선언
    home_state_list = None

    # ========================================================
    # Cameras
    # ========================================================

    top_cam = OpenCVCamera(
        OpenCVCameraConfig(
            index_or_path="/dev/cam_top",
            width=640,
            height=480,
            fps=30,
        )
    )

    wrist_cam = OpenCVCamera(
        OpenCVCameraConfig(
            index_or_path="/dev/cam_wrist",
            width=640,
            height=480,
            fps=30,
        )
    )

    top_cam.connect()
    wrist_cam.connect()

    print("[클라이언트] 카메라 연결 완료")

    # ========================================================
    # Camera workers
    # ========================================================

    top_worker = CameraWorker(
        top_cam,
        "top",
    )

    wrist_worker = CameraWorker(
        wrist_cam,
        "wrist",
    )

    top_worker.start()
    wrist_worker.start()

    print("[클라이언트] 카메라 worker 시작")

    # --------------------------------------------------------
    # 첫 프레임 확보
    # --------------------------------------------------------

    print("[클라이언트] 첫 카메라 프레임 대기...")

    wait_start = time.perf_counter()

    while True:

        top_frame = top_worker.get_latest()
        wrist_frame = wrist_worker.get_latest()

        if top_frame is not None and wrist_frame is not None:
            break

        if time.perf_counter() - wait_start > 5.0:
            raise RuntimeError(
                "5초 동안 카메라 프레임을 얻지 못했습니다."
            )

        time.sleep(0.001)

    print("[클라이언트] 첫 프레임 확보")

    # --------------------------------------------------------
    # 초기 위치(home) 저장
    # --------------------------------------------------------

    if not args.no_return_home:

        try:
            home_state_list = get_robot_state_list(robot)

            print(
                "[클라이언트] 초기 위치 저장 완료: "
                f"{home_state_list}"
            )

        except Exception as e:
            print(
                f"[클라이언트] 초기 위치 저장 실패, "
                f"복귀 기능이 비활성화됩니다: {e}"
            )
            home_state_list = None

    # ========================================================
    # Socket
    # ========================================================

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    # 작은 packet을 즉시 전송
    sock.setsockopt(
        socket.IPPROTO_TCP,
        socket.TCP_NODELAY,
        1,
    )

    print(
        f"[클라이언트] 서버 연결 시도: "
        f"{args.server_host}:{args.server_port}"
    )

    sock.connect(
        (
            args.server_host,
            args.server_port,
        )
    )

    print(
        f"[클라이언트] 서버 연결됨: "
        f"{args.server_host}:{args.server_port}"
    )

    # ========================================================
    # Main loop
    # ========================================================

    start_time = time.perf_counter()

    step = 0

    previous_action = None

    # delta clamp 기준이 되는 "마지막으로 실제 로봇에 보낸(혹은 보낼 예정인)
    # 안전한 action". 처음에는 아직 없으므로 None -> 첫 loop에서
    # 로봇의 현재 state로 초기화한다.
    previous_safe_action = None
    consecutive_unsafe_count = 0
    last_slow_print_time = 0.0

    target_interval = (
        1.0 / args.target_hz
        if args.target_hz > 0
        else None
    )

    try:

        while (
            time.perf_counter() - start_time
            < args.duration
        ) and (
            args.max_steps <= 0
            or step < args.max_steps
        ):

            loop_start = time.perf_counter()

            # =================================================
            # 1. 최신 camera frame 가져오기
            # =================================================

            t = time.perf_counter()

            top_frame = top_worker.get_latest()
            wrist_frame = wrist_worker.get_latest()

            camera_ms = (
                time.perf_counter() - t
            ) * 1000.0

            if top_frame is None or wrist_frame is None:
                print(
                    "[클라이언트] 카메라 프레임 없음"
                )
                continue

            # =================================================
            # 2. Robot state
            # =================================================

            t = time.perf_counter()

            state_list = get_robot_state_list(robot)

            state_ms = (
                time.perf_counter() - t
            ) * 1000.0

            # 첫 loop: delta clamp 기준을 로봇의 실제 현재 위치로 설정
            if previous_safe_action is None:
                previous_safe_action = list(state_list)

            # =================================================
            # 3. JPEG
            # =================================================

            t = time.perf_counter()

            top_jpg = frame_to_jpg_bytes(
                top_frame,
                args.jpeg_quality,
            )

            wrist_jpg = frame_to_jpg_bytes(
                wrist_frame,
                args.jpeg_quality,
            )

            jpeg_ms = (
                time.perf_counter() - t
            ) * 1000.0

            # =================================================
            # 4. Request
            # =================================================

            request = {
                "images": {
                    "top": top_jpg,
                    "wrist": wrist_jpg,
                },
                "state": state_list,
                "environment_state": [
                    args.environment_state
                ],
            }

            # =================================================
            # 5. Send
            # =================================================

            t = time.perf_counter()

            send_msg(
                sock,
                request,
            )

            send_ms = (
                time.perf_counter() - t
            ) * 1000.0

            # =================================================
            # 6. Server response
            # =================================================

            t = time.perf_counter()

            response = recv_msg(sock)

            recv_ms = (
                time.perf_counter() - t
            ) * 1000.0

            # =================================================
            # 7. Action
            # =================================================

            action = response["action"]

            # 서버가 list를 반환하는 현재 구조 유지
            if not isinstance(action, (list, tuple)):
                raise TypeError(
                    "서버 action이 list/tuple이 아닙니다: "
                    f"{type(action)}"
                )

            if len(action) != len(ACTION_KEYS):
                raise ValueError(
                    f"action dimension 오류: "
                    f"{len(action)} != {len(ACTION_KEYS)}"
                )

            # =================================================
            # 7-1. 안전장치: NaN/Inf 차단 + 범위 clamp + delta clamp
            # =================================================

            safe_action, was_unsafe = sanitize_action(
                action,
                previous_safe_action,
                max_delta=max_action_delta,
                joint_min=joint_min,
                joint_max=joint_max,
            )

            if was_unsafe:

                consecutive_unsafe_count += 1

                # 상세 clamp 로그는 --debug일 때만 출력한다.
                # (매 step 무조건 print하면 그 자체가 loop 지연의
                #  원인이 되므로, 평소에는 카운트만 하고 조용히 clamp)
                if args.debug:
                    print(
                        f"[안전장치] STEP {step}: action이 clamp됨 "
                        f"(원본={list(action)}, "
                        f"보정={safe_action}, "
                        f"연속 {consecutive_unsafe_count}회)"
                    )

                if (
                    args.max_consecutive_unsafe > 0
                    and consecutive_unsafe_count
                    >= args.max_consecutive_unsafe
                ):
                    # 비상 정지는 debug 여부와 상관없이 항상 알려야 한다.
                    raise SafetyStopError(
                        f"위험한 action이 연속 "
                        f"{consecutive_unsafe_count}회 감지되어 "
                        "안전을 위해 정지합니다."
                    )

            else:
                consecutive_unsafe_count = 0

            previous_safe_action = list(safe_action)

            action_dict = {
                key: float(value)
                for key, value in zip(
                    ACTION_KEYS,
                    safe_action,
                )
            }

            # =================================================
            # 8. Robot send
            # =================================================

            t = time.perf_counter()

            if args.dry_run:

                if args.debug and step % args.print_every == 0:
                    print(
                        f"[DRY RUN] STEP {step}: "
                        f"전송 생략 -> {action_dict}"
                    )

            else:
                robot.send_action(action_dict)

            robot_ms = (
                time.perf_counter() - t
            ) * 1000.0

            # =================================================
            # Total (sleep 이전, 순수 처리 시간)
            # =================================================

            total_ms = (
                time.perf_counter()
                - loop_start
            ) * 1000.0

            # =================================================
            # Debug
            # =================================================
            #
            # 주의: 이 블록 전체가 --debug일 때만 실행된다.
            # print()는 (특히 ssh/serial 콘솔에서) 생각보다 느려서
            # 매 step마다 여러 번 호출하면 그 자체가 loop 지연의
            # 원인이 될 수 있다. 그래서:
            #  1) "느려서" 찍는 로그는 print_every와 무관하게
            #     매 step 출력되지 않도록 최소 간격(1초)을 둔다.
            #  2) 여러 줄을 print() 여러 번이 아니라 한 번에 출력한다.

            periodic_debug = (
                args.debug
                and step % args.print_every == 0
            )

            now = time.perf_counter()

            slow_debug = (
                args.debug
                and total_ms > 100.0
                and (now - last_slow_print_time) > 1.0
            )

            if periodic_debug or slow_debug:

                last_slow_print_time = now

                fps = (
                    1000.0 / total_ms
                    if total_ms > 0
                    else 0
                )

                lines = [
                    "",
                    "=" * 70,
                    f"STEP {step}"
                    + ("  [SLOW]" if slow_debug and not periodic_debug else ""),
                    "=" * 70,
                    (
                        f"[TIMING] "
                        f"camera={camera_ms:.1f}ms "
                        f"state={state_ms:.1f}ms "
                        f"jpeg={jpeg_ms:.1f}ms "
                        f"send={send_ms:.1f}ms "
                        f"recv={recv_ms:.1f}ms "
                        f"robot={robot_ms:.1f}ms "
                        f"total={total_ms:.1f}ms"
                    ),
                    (
                        f"[RATE] {fps:.2f} Hz (처리시간 기준, "
                        f"target={args.target_hz:.1f} Hz)"
                    ),
                    (
                        f"[JPEG] "
                        f"top={len(top_jpg) / 1024:.1f} KB "
                        f"wrist={len(wrist_jpg) / 1024:.1f} KB"
                    ),
                    f"[STATE] {state_list}",
                    f"[ACTION] {action}",
                ]

                if previous_action is not None:

                    delta = [
                        float(a) - float(b)
                        for a, b in zip(
                            action,
                            previous_action,
                        )
                    ]

                    lines.append(f"[ACTION DELTA] {delta}")

                # 여러 print() 대신 한 번의 print()로 출력 (I/O 호출 최소화)
                print("\n".join(lines))

            previous_action = list(action)

            step += 1

            # =================================================
            # 9. Rate limiting (target_hz 유지)
            # =================================================

            if target_interval is not None:

                elapsed = (
                    time.perf_counter() - loop_start
                )

                sleep_time = target_interval - elapsed

                if sleep_time > 0:
                    time.sleep(sleep_time)

                elif args.debug and step % args.print_every == 0:
                    print(
                        f"[경고] target_hz={args.target_hz:.1f} "
                        f"유지 불가 (처리시간 "
                        f"{elapsed * 1000.0:.1f}ms > "
                        f"목표주기 {target_interval * 1000.0:.1f}ms)"
                    )

    except KeyboardInterrupt:

        print(
            "\n[클라이언트] Ctrl+C 종료"
        )

    except SafetyStopError as e:

        print(
            f"\n[안전장치] 비상 정지: {e}"
        )

    finally:

        print(
            "[클라이언트] 종료 처리..."
        )

        try:
            sock.close()
        except Exception:
            pass

        try:
            top_worker.stop()
            wrist_worker.stop()
        except Exception:
            pass

        # -----------------------------------------------------
        # 초기 위치로 복귀
        # -----------------------------------------------------

        if args.dry_run:
            print(
                "[클라이언트] DRY RUN 모드라 초기 위치 복귀도 "
                "실제로 전송하지 않습니다."
            )

        elif not args.no_return_home and home_state_list is not None:

            try:
                current_state_list = get_robot_state_list(robot)

                move_to_home(
                    robot,
                    current_state_list,
                    home_state_list,
                    duration=args.home_duration,
                )

            except Exception as e:
                print(
                    f"[클라이언트] 초기 위치 복귀 실패: {e}"
                )

        try:
            robot.disconnect()
        except Exception:
            pass

        try:
            top_cam.disconnect()
        except Exception:
            pass

        try:
            wrist_cam.disconnect()
        except Exception:
            pass

        print("[클라이언트] 종료 완료")


if __name__ == "__main__":
    main()