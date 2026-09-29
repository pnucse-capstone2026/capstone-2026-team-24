"""
실시간 ACT inference server.

개선 사항
- CUDA warm-up
- OpenCV JPEG decode
- torch inference_mode
- TCP_NODELAY
- inference 세부 timing
- processor pipeline 유지
- 기존 action output 형식 유지
- (추가) environment_state 지원: Task1/Task2 통합 모델용 task_id 전달
- (추가) --dataset_root 지원: 로컬 데이터셋 경로로 통계 로드

사용법 (Task1/Task2 통합 모델):

python server_inference.py \
    --policy_path s1eepypillow/task12_act_v2 \
    --dataset_repo_id s1eepypillow/grad_block_merged_task12_v2 \
    --dataset_root /root/external_1tb/datasets/grad_block_merged_task12_v2 \
    --port 9999 \
    --use_env_state \
    --debug

요청(request) 형식 (클라이언트가 보내는 것):
    {
        "images": {"top": jpg_bytes, "wrist": jpg_bytes},
        "state": [float, ...],
        "environment_state": [float]   # 선택. 예: [0.0]=Task1, [1.0]=Task2
    }
"""

import argparse
import pickle
import socket
import struct
import time

import cv2
import numpy as np
import torch

from lerobot.policies.act.modeling_act import ACTPolicy


# ============================================================
# Socket
# ============================================================

def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("연결이 끊겼습니다.")
        buf += chunk
    return buf


def recv_msg(conn):
    length_bytes = recv_exact(conn, 4)
    length = struct.unpack(">I", length_bytes)[0]
    payload = recv_exact(conn, length)
    return pickle.loads(payload)


def send_msg(conn, obj):
    payload = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    conn.sendall(struct.pack(">I", len(payload)) + payload)


# ============================================================
# JPEG decode
# ============================================================

def jpg_bytes_to_tensor(jpg_bytes, device):
    """
    JPEG -> OpenCV -> numpy -> torch -> CUDA
    """
    arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        raise RuntimeError("JPEG decode 실패")

    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0

    tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0)
    return tensor.to(device, non_blocking=True)


# ============================================================
# CUDA warm-up
# ============================================================

def warmup_policy(policy, device, height=480, width=640, use_env_state=False):
    """
    첫 inference의 CUDA initialization 비용을 실제 client 연결 전에 처리한다.
    """
    print("[서버] CUDA warm-up 시작")

    dummy_image = torch.zeros((1, 3, height, width), dtype=torch.float32, device=device)
    dummy_state = torch.zeros((1, 6), dtype=torch.float32, device=device)

    batch = {
        "observation.images.top": dummy_image,
        "observation.images.wrist": dummy_image,
        "observation.state": dummy_state,
    }

    if use_env_state:
        batch["observation.environment_state"] = torch.zeros(
            (1, 1), dtype=torch.float32, device=device
        )

    if device.startswith("cuda"):
        torch.cuda.synchronize()

    t0 = time.perf_counter()

    with torch.inference_mode():
        _ = policy.select_action(batch)

    if device.startswith("cuda"):
        torch.cuda.synchronize()

    elapsed = (time.perf_counter() - t0) * 1000.0
    print(f"[서버] CUDA warm-up 완료: {elapsed:.1f} ms")


# ============================================================
# Processor 로딩 (dataset_root 지원, 여러 시그니처 시도)
# ============================================================

def load_processors(policy, args):
    """
    make_pre_post_processors의 정확한 인자 시그니처가 lerobot 버전마다
    다를 수 있어, dataset_root -> dataset_repo_id 순으로 시도한다.
    둘 다 실패하면 (None, None)을 반환하고 원인을 출력한다.
    """
    if args.dataset_repo_id is None and args.dataset_root is None:
        print("[서버] dataset_repo_id/dataset_root가 없습니다.")
        print("[서버] processor 없이 진행합니다 (정규화 미적용 위험 있음).")
        return None, None

    try:
        from lerobot.policies import make_pre_post_processors
    except Exception as e:
        print("[서버] processor import 실패:")
        print(f"        {type(e).__name__}: {e}")
        return None, None

    # 1차 시도: dataset_root 포함
    if args.dataset_root is not None:
        try:
            print(f"[서버] dataset_root로 processor 로드 시도: {args.dataset_root}")
            pre, post = make_pre_post_processors(
                policy_cfg=policy.config,
                pretrained_path=args.policy_path,
                dataset_stats=None,
                dataset_root=args.dataset_root,
            )
            print("[서버] processor 로드 완료 (dataset_root 사용)")
            return pre, post
        except TypeError as e:
            print(f"[서버] dataset_root 인자를 지원하지 않는 버전으로 보임: {e}")
        except Exception as e:
            print("[서버] dataset_root 기반 processor 생성 실패:")
            print(f"        {type(e).__name__}: {e}")

    # 2차 시도: dataset_repo_id만 사용 (기존 방식)
    if args.dataset_repo_id is not None:
        try:
            print(f"[서버] dataset_repo_id로 processor 로드 시도: {args.dataset_repo_id}")
            pre, post = make_pre_post_processors(
                policy_cfg=policy.config,
                pretrained_path=args.policy_path,
                dataset_stats=None,
            )
            print("[서버] processor 로드 완료 (dataset_repo_id 사용)")
            return pre, post
        except Exception as e:
            print("[서버] dataset_repo_id 기반 processor 생성도 실패:")
            print(f"        {type(e).__name__}: {e}")

    print("[서버] processor 로드 최종 실패, None으로 진행합니다.")
    return None, None


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy_path", type=str, required=True)
    parser.add_argument("--dataset_repo_id", type=str, default=None)
    parser.add_argument(
        "--dataset_root",
        type=str,
        default=None,
        help="로컬 데이터셋 경로 (있으면 이걸로 정규화 통계를 로드 시도)",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--debug_every", type=int, default=10)
    parser.add_argument(
        "--use_env_state",
        action="store_true",
        help="Task1/Task2 통합 모델처럼 observation.environment_state를 쓰는 정책일 때 지정",
    )
    args = parser.parse_args()

    # ========================================================
    # Device
    # ========================================================
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[서버] device={device}")

    # ========================================================
    # Policy
    # ========================================================
    print(f"[서버] 정책 로드 중: {args.policy_path}")
    policy = ACTPolicy.from_pretrained(args.policy_path)
    policy.to(device)
    policy.eval()
    print("[서버] 정책 로드 완료")

    # ========================================================
    # Policy config
    # ========================================================
    if args.debug:
        print()
        print("========== POLICY CONFIG ==========")
        print("normalization_mapping =", policy.config.normalization_mapping)
        print("input_features =", policy.config.input_features)
        print("output_features =", policy.config.output_features)
        print("====================================")

    # ========================================================
    # Processor
    # ========================================================
    print("[서버] processor 준비")
    preprocessor, postprocessor = load_processors(policy, args)

    # ========================================================
    # Warm-up
    # ========================================================
    try:
        warmup_policy(policy, device, 480, 640, use_env_state=args.use_env_state)
    except Exception as e:
        print("[서버] warm-up 실패:")
        print(f"        {type(e).__name__}: {e}")

    # ========================================================
    # Socket
    # ========================================================
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.bind((args.host, args.port))
    sock.listen(1)
    print(f"[서버] {args.host}:{args.port} 에서 대기 중...")

    # ========================================================
    # Client loop
    # ========================================================
    while True:
        conn, addr = sock.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[서버] 연결됨: {addr}")

        try:
            policy.reset()
            step = 0

            while True:
                loop_start = time.perf_counter()

                # 1. Receive
                t = time.perf_counter()
                request = recv_msg(conn)
                recv_ms = (time.perf_counter() - t) * 1000.0

                # 2. JPEG decode
                t = time.perf_counter()
                images = {}
                if "top" in request["images"]:
                    images["top"] = jpg_bytes_to_tensor(request["images"]["top"], device)
                if "wrist" in request["images"]:
                    images["wrist"] = jpg_bytes_to_tensor(request["images"]["wrist"], device)
                image_ms = (time.perf_counter() - t) * 1000.0

                # 3. State
                t = time.perf_counter()
                state = torch.tensor(request["state"], dtype=torch.float32, device=device).unsqueeze(0)

                env_state = None
                if request.get("environment_state") is not None:
                    env_state = torch.tensor(
                        request["environment_state"], dtype=torch.float32, device=device
                    ).unsqueeze(0)
                state_ms = (time.perf_counter() - t) * 1000.0

                # 4. Batch
                batch = {"observation.state": state}
                if "top" in images:
                    batch["observation.images.top"] = images["top"]
                if "wrist" in images:
                    batch["observation.images.wrist"] = images["wrist"]
                if env_state is not None:
                    batch["observation.environment_state"] = env_state

                # 5. Preprocess
                pre_ms = 0.0
                if preprocessor is not None:
                    t = time.perf_counter()
                    batch = preprocessor(batch)
                    pre_ms = (time.perf_counter() - t) * 1000.0

                # 6. ACT inference
                t = time.perf_counter()
                with torch.inference_mode():
                    action = policy.select_action(batch)
                if device.startswith("cuda"):
                    torch.cuda.synchronize()
                policy_ms = (time.perf_counter() - t) * 1000.0

                # 7. Postprocess
                post_ms = 0.0
                if postprocessor is not None:
                    t = time.perf_counter()
                    action = postprocessor(action)
                    post_ms = (time.perf_counter() - t) * 1000.0

                # 8. Convert action
                if isinstance(action, dict):
                    action_dict = action
                    action_list = [float(v) for v in action_dict.values()]
                else:
                    if isinstance(action, torch.Tensor):
                        action_list = action[0].detach().cpu().tolist()
                    else:
                        action_list = list(action)

                # 9. Send
                t = time.perf_counter()
                send_msg(conn, {"action": action_list})
                send_ms = (time.perf_counter() - t) * 1000.0

                # Total
                total_ms = (time.perf_counter() - loop_start) * 1000.0

                # Debug
                if args.debug and (step % args.debug_every == 0 or total_ms > 100.0):
                    print()
                    print("=" * 70)
                    print(f"[SERVER STEP {step}]")
                    print("=" * 70)
                    print(
                        f"[TIMING] recv={recv_ms:.1f}ms image={image_ms:.1f}ms "
                        f"state={state_ms:.1f}ms pre={pre_ms:.1f}ms policy={policy_ms:.1f}ms "
                        f"post={post_ms:.1f}ms send={send_ms:.1f}ms total={total_ms:.1f}ms"
                    )
                    fps = 1000.0 / total_ms if total_ms > 0 else 0
                    print(f"[SERVER RATE] {fps:.2f} Hz")
                    print("[ACTION]", action_list)

                step += 1

        except ConnectionError:
            print(f"[서버] 연결 종료: {addr}")

        except Exception as e:
            print(f"[서버] 오류: {type(e).__name__}: {e}")

        finally:
            conn.close()


if __name__ == "__main__":
    main()
