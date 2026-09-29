"""
로봇/실제 카메라 없이, 서버-Jetson 간 네트워크 + 추론 왕복 시간(latency)만 먼저 재보는 스크립트.
"""

import argparse
import pickle
import socket
import struct
import time

import cv2
import numpy as np


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
    payload = pickle.dumps(obj)
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def dummy_jpg_bytes():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server_host", type=str, required=True)
    parser.add_argument("--server_port", type=int, default=9999)
    parser.add_argument("--n_trials", type=int, default=30)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.server_host, args.server_port))
    print(f"연결됨: {args.server_host}:{args.server_port}")

    dummy_img = dummy_jpg_bytes()
    latencies = []

    for i in range(args.n_trials):
        request = {
            "images": {"top": dummy_img, "wrist": dummy_img},
            "state": [0.0] * 6,
        }
        t0 = time.time()
        send_msg(sock, request)
        response = recv_msg(sock)
        latency_ms = (time.time() - t0) * 1000
        latencies.append(latency_ms)
        print(f"trial {i+1}: {latency_ms:.1f}ms, action={response['action'][:3]}...")

    sock.close()

    print("\n=== 결과 ===")
    print(f"평균 latency: {sum(latencies)/len(latencies):.1f}ms")
    print(f"최대 latency: {max(latencies):.1f}ms")
    print(f"최소 latency: {min(latencies):.1f}ms")
    print(f"\n참고: 30fps 카메라 기준 한 프레임은 약 33ms입니다.")
    print(f"평균 latency가 이보다 훨씬 크면(예: 100ms 이상) 실시간 제어에 지장이 있을 수 있습니다.")


if __name__ == "__main__":
    main()
