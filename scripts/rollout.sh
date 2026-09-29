#!/bin/bash
# Jetson Orin Nano에서 학습된 정책으로 실물 로봇 제어
# 사용법: HF_USER=본인계정 POLICY_NAME=task1_act_policy_v6 ./rollout.sh
# 참고: 새 정책 다운로드 후 config.json의 pretrained_revision 필드 제거가
#       필요할 수 있음 (docs/troubleshooting.md 참고)

lerobot-rollout \
  --strategy.type=base \
  --policy.path=${HF_USER}/${POLICY_NAME} \
  --robot.type=so101_follower \
  --robot.port=/dev/so101_follower \
  --robot.id=follower \
  --robot.cameras='{
      top: {
          type: opencv,
          index_or_path: /dev/cam_top,
          width: 640,
          height: 480,
          fps: 30
      },
      wrist: {
          type: opencv,
          index_or_path: /dev/cam_wrist,
          width: 640,
          height: 480,
          fps: 30
      }
  }' \
  --task="task1" \
  --duration=180
