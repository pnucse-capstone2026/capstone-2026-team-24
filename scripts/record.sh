#!/bin/bash
# Jetson Orin Nano에서 실행: teleoperation으로 데이터 수집
# 사용법: HF_USER=본인계정 TAG=fixed ./record.sh
# repo_id는 태그+타임스탬프로 자동 생성됨

TAG=${TAG:-untagged}

lerobot-record \
    --teleop.type=so101_leader \
    --teleop.port=/dev/so101_leader \
    --teleop.id=leader \
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
    --dataset.single_task="task1" \
    --dataset.repo_id=${HF_USER}/grad_block_$(date +%Y%m%d_%H%M%S)_${TAG} \
    --dataset.num_episodes=10 \
    --dataset.episode_time_s=40 \
    --dataset.reset_time_s=5 \
    --display_data=false \
    --dataset.push_to_hub=false
