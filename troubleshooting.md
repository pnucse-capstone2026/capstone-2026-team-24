# 트러블슈팅 기록

## 환경 세팅 (학교 서버, 도커 컨테이너 / RTX 5090)

### Python 버전 요구사항 불일치
- 증상: `Package 'lerobot' requires a different Python: 3.10.20 not in '>=3.12'`
- 원인: LeRobot 최신 버전은 Python 3.12 이상 요구
- 해결: `conda create -y -n lerobot python=3.12`로 재생성

### extras 패키지 누락 (반복적으로 발생)
- `ImportError: 'datasets' is required` → `pip install 'lerobot[dataset]'`
- `ImportError: 'accelerate' is required` → `pip install 'lerobot[training]'`
- 참고: 한번에 `pip install 'lerobot[all]'`로 설치하면 반복을 줄일 수 있음

### ACT 하이퍼파라미터 제약 위반
- 증상: `ValueError: chunk size is the upper bound for n_action_steps. Got 100 for n_action_steps and 60 for chunk_size.`
- 원인: `chunk_size`만 변경하고 `n_action_steps`(기본 100)를 같이 안 낮춤. 제약: `n_action_steps <= chunk_size`
- 해결: 두 값을 항상 함께 지정 (`--policy.chunk_size=60 --policy.n_action_steps=60`)

### 학습 종료 시 Hub 업로드 에러
- 증상: `ValueError: 'repo_id' argument missing. Please specify it to push the model to the hub.`
- 원인: `push_to_hub` 기본값이 true인데 목적지 미지정
- 해결: `--policy.push_to_hub=false`로 끄고, 학습 후 `hf upload`로 수동 업로드

### pip 캐시 권한 경고
- 증상: `WARNING: The directory '/root/.cache/pip' ... not writable`
- 영향: 학습/설치에 지장 없음, 무시 가능 (도커 root 환경 특성)

---

## Jetson Orin Nano 배포 관련

### LeRobot 버전 불일치로 인한 policy config 파싱 실패
- 증상: `DecodingError: The fields 'pretrained_revision' are not valid for ACTConfig`
- 원인: 학습 서버(LeRobot 0.6.1)와 Jetson(0.5.2) 버전 차이로 config.json 필드 불일치
- 해결: 새 정책 다운로드 후 `config.json`에서 `pretrained_revision` 필드를 수동 삭제 (Python으로 json 로드→pop→저장)
- 참고: 새 모델 업로드할 때마다 반복 필요할 수 있음. 근본 해결은 Jetson LeRobot 버전 업데이트 (단, 아래 PyTorch/NumPy 이슈 재발 가능성 있음)

### GPU 미지원 (Compute Capability 8.7)
- 증상: `torch.AcceleratorError: CUDA error: no kernel image is available for execution on the device`
- 원인: 일반 pip PyTorch가 Jetson Orin GPU(CC 8.7)용 커널을 포함하지 않음
- 해결:
  1. JetPack 버전 확인: `cat /etc/nv_tegra_release` (R36.4.7 = JetPack 6.2)
  2. 기존 PyTorch 제거 후 Jetson 전용 wheel 설치:
     ```
     pip uninstall torch torchvision torchaudio -y
     pip install torch==2.8.0 torchvision==0.23.0 --index-url=https://pypi.jetson-ai-lab.io/jp6/cu126
     ```
- 참고: `pypi.jetson-ai-lab.dev` 도메인은 DNS 조회 실패 이력 있음(`Could not resolve host`) → `.io` 미러 사용

### NumPy 버전 충돌
- 증상: `RuntimeError: Numpy is not available` (Jetson wheel이 NumPy 1.x 기준 컴파일됨)
- 해결: `pip install numpy==1.26.1`

### feetech-servo-sdk 누락
- 증상: `ImportError: 'feetech-servo-sdk' is required but not installed`
- 원인: 학교 서버(로봇 미연결 환경)에서 실수로 `lerobot-rollout` 실행 시도
- 해결: 로봇 제어 명령(`lerobot-record`, `lerobot-rollout`)은 반드시 Jetson에서만 실행. 서버는 학습 전용
- 참고: 학교 서버에서 실수로 `hf download`한 것은 부작용 없음(단순 파일 저장), 문제되는 것은 로봇 연결이 필요한 명령어뿐

---

## 캘리브레이션 관련

### 캘리브레이션 파일 관리
- `--robot.id` 옵션을 지정하지 않으면 `None.json`으로 별도 저장되어, 이후 명령어마다 다른 캘리브레이션을 참조하는 문제 발생 가능
- **항상 `--robot.id=follower`를 명시**하여 모든 명령어(record/rollout)가 동일 캘리브레이션 파일을 참조하도록 통일할 것
- 캘리브레이션 파일 삭제 전 반드시 백업:
  ```
  cp ~/.cache/huggingface/lerobot/calibration/robots/so_follower/follower.json ~/follower_calibration_backup_$(date +%Y%m%d).json
  ```
- 재캘리브레이션 중 리더-팔로워 물리적 정렬 상태에 주의 (정렬 안 된 상태로 "중간 위치" 기록 시 이후 재현성 문제 발생 가능)
- 재캘리브레이션(관절 전체범위 스윕) 도중 물리적 무리가 갈 수 있으므로, teleoperation 시작 직후 리더-팔로워 위치 차이가 크지 않은지 확인 후 진행

---

## 학습 로그 관리

### 로그 파일이 저장되지 않음
- 증상: 학습 완료 후 loss 기록을 다시 확인할 수 없음
- 원인: `lerobot-train` 명령어 실행 시 `2>&1 | tee <파일>.log`를 누락
- 해결: 항상 아래 형태로 실행
  ```
  lerobot-train ... 2>&1 | tee outputs/train/<실험명>/train.log
  ```
- 권장: `output_dir`과 로그 파일 경로를 함께 관리하여 실험명 혼동 방지

---

## W&B (Weights & Biases) 연동

### 가입 플랜
- 학교 프로젝트이므로 **Academic** 플랜 선택 (Professional 대비 더 넉넉한 무료 한도)
- 개인 실험 추적(loss 로깅) 용도로는 결제 정보 등록 없이 완전 무료로 사용 가능

### 설정
```bash
pip install wandb
wandb login   # API 키 붙여넣기 (wandb.ai/authorize에서 발급)
```
학습 명령어에 아래 옵션 추가:
```bash
--wandb.enable=true --wandb.project=<프로젝트명>
```

### output_dir 재사용 시 에러
- 증상: `FileExistsError: Output directory ... already exists and resume is False`
- 원인: `mkdir -p`로 output_dir을 미리 만들어두면 LeRobot이 "기존 학습 결과 덮어쓰기 방지" 안전장치로 막음
- 해결: 미리 폴더를 만들지 말고 `lerobot-train`이 자동 생성하도록 둘 것. 재사용하려면 `--resume=true` 사용하거나 폴더를 삭제 후 재실행

### tee 로그 저장 실패
- 증상: `tee: outputs/train/.../train.log: No such file or directory`
- 원인: output_dir 하위 폴더가 아직 생성되기 전(학습 시작 극초반) 시점에 tee가 그 경로를 찾으려다 실패
- 영향: 학습 자체(`lerobot-train` 프로세스)는 정상 진행되며 영향 없음. 콘솔 로그가 파일로 저장되지 않을 뿐
- 대응: W&B를 켜둔 경우 손실 기록은 W&B 대시보드에 남으므로 로컬 로그 파일 없어도 무방. 로컬 로그가 꼭 필요하면 현재 디렉토리에 별도 파일명으로 저장 후 학습 종료 후 이동:
  ```bash
  ... 2>&1 | tee train_실험명.log
  ```

---

## GPU 자원 관련

### 병렬 학습 시 메모리/속도 트레이드오프
- 두 개의 `lerobot-train`을 동시 실행(예: chunk30 + klw1) 시 RTX 5090(32GB)에서도 batch_size를 낮춰야 할 수 있음
- `nvidia-smi`로 메모리 사용량과 GPU 사용률(%) 사전 확인 후 batch_size 조정 권장
- batch_size 축소는 gradient noise 증가 및 실질 학습 데이터량 감소로 이어질 수 있어, 여러 하이퍼파라미터를 동시에 비교할 때는 이 차이를 명시적으로 기록해둘 것
