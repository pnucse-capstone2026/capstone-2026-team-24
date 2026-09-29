#!/bin/bash
# 학교 GPU 서버(도커 컨테이너, RTX 5090)에서 학습 환경 세팅
# 최초 1회 실행

set -e

source /opt/conda/etc/profile.d/conda.sh
conda create -y -n lerobot python=3.12
conda activate lerobot

pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"

cd ~/external_1tb
git clone https://github.com/huggingface/lerobot.git
cd lerobot
pip install -e .
pip install 'lerobot[dataset]'
pip install 'lerobot[training]'

echo "환경 세팅 완료. conda activate lerobot 으로 이후 활성화."
