#!/bin/bash
# 여러 세션으로 나뉘어 녹화된 로컬 데이터셋들을 하나로 병합
# 사용법: HF_USER=본인계정 OUTPUT_NAME=grad_block_final REPO_IDS="'a','b','c'" ./merge_dataset.sh

lerobot-edit-dataset \
  --repo_id ${HF_USER}/${OUTPUT_NAME} \
  --operation.type merge \
  --operation.repo_ids "[${REPO_IDS}]"

lerobot-edit-dataset --repo_id ${HF_USER}/${OUTPUT_NAME} --operation.type info

hf upload ${HF_USER}/${OUTPUT_NAME} \
  ~/.cache/huggingface/lerobot/${HF_USER}/${OUTPUT_NAME} \
  --repo-type=dataset
