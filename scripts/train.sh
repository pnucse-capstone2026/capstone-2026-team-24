#!/bin/bash
# 학교 GPU 서버에서 ACT 정책 학습
# 사전 준비: tmux new -s train  (세션 안에서 이 스크립트 실행)
# 사용법: HF_USER=본인계정 DATASET_NAME=grad_block_final EXP_NAME=v6 \
#         CHUNK_SIZE=60 KL_WEIGHT=10 BATCH_SIZE=64 ./train.sh

source /opt/conda/etc/profile.d/conda.sh
conda activate lerobot
cd ~/external_1tb/lerobot

CHUNK_SIZE=${CHUNK_SIZE:-60}
KL_WEIGHT=${KL_WEIGHT:-10}
BATCH_SIZE=${BATCH_SIZE:-64}

mkdir -p outputs/train/${EXP_NAME}

hf download ${HF_USER}/${DATASET_NAME} \
  --repo-type=dataset \
  --local-dir ~/external_1tb/datasets/${DATASET_NAME}

lerobot-train \
  --dataset.repo_id=${HF_USER}/${DATASET_NAME} \
  --dataset.root=/root/external_1tb/datasets/${DATASET_NAME} \
  --policy.type=act \
  --output_dir=outputs/train/${EXP_NAME} \
  --job_name=${EXP_NAME} \
  --policy.device=cuda \
  --batch_size=${BATCH_SIZE} \
  --steps=100000 \
  --policy.chunk_size=${CHUNK_SIZE} \
  --policy.n_action_steps=${CHUNK_SIZE} \
  --policy.kl_weight=${KL_WEIGHT} \
  --policy.push_to_hub=false \
  --wandb.enable=false 2>&1 | tee outputs/train/${EXP_NAME}/train.log

echo "=== 최근 loss 값 ==="
grep "loss" outputs/train/${EXP_NAME}/train.log | tail -20

hf upload ${HF_USER}/task1_act_policy_${EXP_NAME} \
  outputs/train/${EXP_NAME}/checkpoints/last/pretrained_model
