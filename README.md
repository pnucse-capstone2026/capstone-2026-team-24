### 1. 프로젝트 배경

#### 1.1. 시장 현황 및 문제점
* **산업 현장의 조작 작업 자동화**: 제조 및 물류 산업 현장에서는 물체를 집어 지정된 위치로 이동시키는 Pick-and-Place 작업을 로봇 매니퓰레이터로 자동화하여 생산 공정의 효율을 높이고 있습니다.
* **규칙 기반 제어의 한계**: 기존 시스템은 작업 대상과 환경이 일정하다는 가정하에 사람이 사전에 정의한 궤적과 순서에 따라 로봇을 제어하는 방식을 주로 사용해 왔습니다. 실제 작업 환경에서는 물체가 무작위로 배치되거나 주변 환경이 변화하는 등 불확실성이 존재하며, 기존 방식은 이러한 새로운 조건에 대응하기 위해 매번 복잡한 규칙과 예외 상황을 추가로 설계해야 하는 한계가 있습니다.
* **다단계 정밀 작업에서의 누적 오차**: 여러 개의 블록을 순차적으로 적재하는 수직 적재 작업의 경우, 각 단계에서 발생한 객체 인식 및 위치 제어 오차가 연쇄적으로 누적되어 작업 실패로 이어지는 기술적 복잡성이 존재합니다.

#### 1.2. 필요성과 기대효과
* **AI 기반 지능형 자율 제어 시스템의 필요성**: 정형화된 환경에서의 단순 반복 작업에서 벗어나, 카메라 등 비전 센서를 통해 주변 상황을 실시간으로 관측하고 적절한 행동을 스스로 판단하여 결정하는 지능형 로봇 시스템으로의 패러다임 전환이 필수적입니다.
* **모방학습을 통한 제어 복잡성 해소**: 조작자가 원격 조작을 통해 직접 시연한 행동 궤적 데이터를 활용하여 정책을 학습시키면, 복잡한 제어 규칙을 사람이 직접 작성하지 않고도 로봇이 실제 작업에 필요한 동작을 효과적으로 습득할 수 있습니다.
* **기존 연구의 한계 극복 및 환경 적응력 확보**: 대상의 시작 위치가 고정된 제한적인 기존 환경을 넘어서기 위해 본 프로젝트가 필요합니다. 시각적 노이즈가 존재하고 블록의 위치가 무작위로 변하는 복잡한 환경에서도 안정적인 조작 성능을 확보하는 효과를 기대할 수 있습니다.
* **최종 기대효과**: 결과적으로 카메라를 통한 작업 환경 인식과 행동 생성을 연결하여, 무작위 배치된 블록들에 대해 연속적인 이동 및 적재 작업을 자율적으로 완수하는 지능형 로봇 제어 시스템을 구현할 수 있습니다.

### 2. 개발 목표

#### 2.1. 목표 및 세부 내용
본 프로젝트의 최종 목표는 LeRobot SO-101 로봇 팔을 활용하여 무작위로 배치된 블록을 비전 센서로 인식하고, 지정된 영역에 자율적으로 이동 및 적재할 수 있는 지능형 로봇 제어 시스템을 구축하는 것입니다.
* **Teleoperation 기반 데이터 수집**: Leader-Follower 구조를 활용해 조작자의 직관적인 조작 궤적과 상단 및 손목 카메라의 영상 정보를 동기화하여 고품질의 시연 데이터를 구축합니다.
* **ACT(Action Chunking Transformer) 모델 적용**: 일정 길이의 연속된 행동 시퀀스를 한 번에 예측하는 ACT 모델을 도입하여, 시계열적 누적 오차를 줄이고 로봇 조작의 부드러움과 작업 연속성을 확보합니다.
* **단일 모델 기반 멀티태스킹**: 데이터셋에 `observation.environment_state` 속성을 추가하여, 하나의 인공지능 모델이 Task 1(5개의 블록을 W 형태로 구역 내 배치)과 Task 2(블록 수직 적재)를 명확히 구분하고 수행하도록 설계합니다.
* **서버-클라이언트 실시간 제어 분산 구조**: 카메라 영상 수집 및 실제 로봇 제어는 Jetson Orin Nano가 담당하고, 무거운 정책 추론은 연산 성능이 뛰어난 GPU 서버가 담당하는 분산 아키텍처를 구축하여 약 30Hz의 안정적인 실시간 제어 주기를 달성합니다.

#### 2.2. 기존 서비스 대비 차별성
기존 오픈소스 데이터셋을 활용한 선행 연구들은 단일한 검은색 배경에서 물체의 시작 위치가 고정된 제한적 환경을 전제로, 단일 블록을 통 안에 넣는 단순한 태스크만을 수행한다는 한계가 있었습니다. 본 프로젝트는 이를 극복하기 위해 다음과 같은 차별성을 가집니다.
* **복잡한 시각적 환경 및 태스크 연속성 극복**: 검은색과 흰색이 교차하는 격자무늬 배경을 사용하여 비전 모델의 강건한 특징 추출을 유도하였으며, 단일 블록 조작을 넘어 5개의 블록을 연속적으로 파지하고 정밀하게 수직으로 적재하는 고난도 작업을 구현했습니다.
* **다양한 공간적 상태 전이(State Transition) 학습**: 단순히 에피소드 수만 늘리는 것이 아니라 블록의 좌/우측 편향, 상/하측 집중, 경계 인접 등 다양한 위치 조건을 의도적으로 설계하여 모델의 공간적 일반화 성능을 극대화했습니다.
* **DAgger(Dataset Aggregation) 파이프라인 도입**: 단순 행동 복제(Behavior Cloning) 시 발생하는 누적 오차 및 이탈 문제를 해결하기 위해, 로봇이 오작동을 일으키는 취약 상태에서 전문가가 실시간으로 개입해 올바른 복구 궤적을 제공하고 이를 재학습하는 혁신적인 능동적 교정 시스템을 구축했습니다.

#### 2.3. 사회적 가치 도입 계획
* **제조 및 물류 산업의 유연한 자동화 기여**: 작업 대상의 위치나 주변 환경이 변화할 때마다 사람이 제어 규칙을 추가해야 했던 기존 규칙 기반 제어의 한계를 벗어나, 환경 변화에 스스로 대응하는 지능형 시스템을 통해 산업 현장의 효율성과 생산성을 높입니다.
* **경량화 모델 채택을 통한 친환경적 AI 실현**: 최소 수십억 개의 파라미터와 막대한 컴퓨팅 자원을 요구하는 거대 범용 로봇 모델 대신, 약 8,000만 개의 파라미터로 구성된 경량화 ACT 모델을 채택했습니다. 이를 통해 엣지 디바이스와 단일 GPU 환경에서도 원활한 학습 및 실시간 제어가 가능하도록 하여 전력 소모를 최소화합니다.
* **안전 기반 제어를 통한 하드웨어 지속가능성 확보**: 인공지능 모델의 예측 오류가 하드웨어 파손으로 이어지지 않도록, 각 관절의 허용 위치 범위와 Step당 최대 변화량을 물리적으로 제한하는 이중 안전 로직을 구현하여 로봇 시스템의 안전성과 수명을 보장합니다.

### 3. 시스템 설계

#### 3.1. 시스템 구성도

<img alt="image" src="images/시스템 구성도.png" />

본 프로젝트의 시스템은 로봇의 실시간 제어와 고연산 AI 추론의 부하를 분산하기 위해 서버-클라이언트 기반의 구조로 설계되었습니다.

* **Jetson Client (엣지 제어 환경)**: 실제 로봇(LeRobot SO-101)과 연결되어 작업 공간의 카메라 영상(상단/손목)과 로봇의 현재 관절 상태를 수집합니다. 수집된 영상은 JPEG로 압축되어 관절 데이터와 함께 서버로 전송되며, 서버로부터 수신된 동작 명령을 팔로워 암에 즉각적으로 적용합니다.

* **추론 Server (GPU 서버)**: 클라이언트로부터 TCP Socket을 통해 전달받은 관측 데이터를 ACT 정책 모델에 입력하여 다음 로봇의 행동을 Chunk 단위로 생성하고 이를 다시 클라이언트로 반환합니다.

#### 3.2. 사용 기술

**Hardware**
* **Edge Device**: Jetson Orin Nano (ARM64 아키텍처) 
* **Server Device**: NVIDIA RTX 5090 (32GB VRAM GPU 서버) 
* **Robot**: LeRobot SO-101 (Leader-Follower 구조, 6자유도 매니퓰레이터) 
* **Sensor**: 640x480 해상도(30FPS)의 상단(Top-view) 및 손목(Wrist-view) 카메라 

**Software & Environment**
* **OS / Environment**: JetPack 6.2.2, Docker 컨테이너, Conda 가상환경 
* **Robot Control**: LeRobot Framework, ROS 2 
* **통신 (Network)**: TCP Socket 통신 , USB Serial/UVC 통신

**AI & Machine Learning**
* **Core Model**: ACT (Action Chunking with Transformers), DAgger (Dataset Aggregation) 알고리즘 
* **Framework**: PyTorch (CUDA 기반 GPU 연산 환경) 
* **Vision Processing**: OpenCV (카메라 인터페이스 및 실시간 프레임 획득/압축) 
* **MLOps & Tracking**: Hugging Face Hub (학습 데이터셋 및 정책 모델 Checkpoint 관리), Weights & Biases (W&B, 학습 Loss 및 지표 모니터링) 

### 4. 개발 결과
#### 4.1. 전체 시스템 흐름도

<img alt="image" src="images/시스템 개발 파이프라인.png" />

#### 4.2. 기능 설명 및 주요 기능 명세서

로봇 팔 제어 시스템의 핵심 기능과 각 기능별 입력/출력 명세는 다음과 같습니다.

| 기능명 | 입력 (Input) | 출력 (Output) | 상세 설명 |
| :--- | :--- | :--- | :--- |
| **Teleoperation 데이터 수집** | 조작자의 Leader Arm 물리적 조작 | Follower Arm 동작 수행 및 시연 에피소드 로깅 | 사용자가 Leader Arm을 조작하면 Follower Arm이 이를 따라하며, 상단/손목 카메라 영상과 관절 상태를 실시간으로 기록하여 학습 데이터셋을 구축합니다. |
| **ACT 기반 행동 추론** | 실시간 카메라 영상(Top, Wrist), 로봇 관절 상태(`observation.state`), Task 조건(`environment_state`) | 행동 청크 (Action Chunk) | 서버의 GPU 환경에서 동작하며, 입력된 비전 및 상태 데이터를 바탕으로 향후 연속된 목표 관절 궤적을 한 번에 예측합니다. |
| **서버-클라이언트 실시간 통신** | 압축된 카메라 영상(JPEG) 및 현재 로봇 관절 상태 | ACT 모델이 추론한 다음 목표 행동 명령 (Action Command) | Jetson Client에서 소켓 통신을 통해 데이터를 송신하고, 서버로부터 수신한 행동 명령을 30Hz로 로봇에 적용합니다. |
| **Temporal Ensembling 제어** | 현재 스텝 및 이전 스텝들에서 예측된 중첩 행동 청크들 | 가중 평균된 최종 단일 행동 명령 | 매 제어 주기마다 새로운 관측을 통해 행동을 예측하되, 시계열 상에서 중첩되는 예측값들을 지수 가중 평균하여 로봇의 덜컹거림을 완화하고 부드러운 궤적을 생성합니다. |
| **제어 안전 로직 (Safety Constraint)** | 추론 서버로부터 수신된 정책 출력(목표 관절 각도) | 안전 범위 내의 최종 관절 제어값 | 모델의 예측 오류로 인한 급격한 움직임을 방지하기 위해, 각 관절의 물리적 허용 범위와 1 Step당 최대 변화량을 제한합니다. |
| **DAgger 기반 교정 (Correction)** | 실패 및 OOD 상태 진입 시 텔레오퍼레이터의 즉각적인 개입 | 기존 데이터셋에 병합될 정상 복구 궤적 데이터 | 로봇이 목표 영역을 오인식하거나 특정 위치에서 멈출 때 전문가가 개입하여 정상 궤적으로 복구하는 행동을 시연하고, 이를 데이터로 저장하여 모델을 재학습합니다. |
>
#### 4.3. 디렉토리 구조

보고서에 명시된 주요 모듈(LeRobot 기반 환경, TCP 소켓 통신, Jetson 엣지 클라이언트 및 GPU 서버 분산 처리)을 바탕으로 구성한 예상 디렉토리 구조입니다.

```text
📦 lerobot_project
 ┣ 📂 client_jetson/           # Jetson Orin Nano (Edge) 실행 환경
 ┃ ┣ 📜 camera_worker.py       # 실시간 상단/손목 카메라 영상 수집 및 JPEG 압축 스레드
 ┃ ┣ 📜 robot_controller.py    # SO-101 Follower Arm 관절 제어 및 안전 로직 적용
 ┃ ┗ 📜 tcp_client.py          # 서버로 상태 전송 및 행동 명령 수신 (TCP Socket)
 ┣ 📂 server_gpu/              # GPU 추론 및 학습 서버 환경
 ┃ ┣ 📜 tcp_server.py          # 클라이언트 요청 수신 및 추론 결과 반환
 ┃ ┣ 📜 act_inference.py       # ACT 모델 로드, Temporal Ensembling 추론 및 Environment State 반영
 ┃ ┗ 📜 train_act.py           # Hugging Face Hub 데이터셋 로드 및 ACT 파라미터 학습 실행
 ┣ 📂 data_collection/         # 데이터 수집 및 DAgger 파이프라인
 ┃ ┣ 📜 teleoperation.py       # Leader-Follower 원격 조작 기록 및 LeRobot 포맷 변환
 ┃ ┗ 📜 dagger_correction.py   # 전문가 개입(Human-Gated) 실패 구간 보정 데이터 기록
 ┣ 📂 config/                  # 설정 파일
 ┃ ┣ 📜 act_policy_config.yaml # Chunk Size, Action Steps 등 하이퍼파라미터 설정
 ┃ ┗ 📜 safety_limits.yaml     # 관절별 최대/최소 가동 범위 및 Step당 최대 변화량 설정
 ┗ 📜 README.md
```
#### 4.4. 산업체 멘토링 의견 및 반영 사항
본 프로젝트 진행 과정에서 산학협력 멘토의 피드백을 수렴하여 시스템 아키텍처를 개선하였습니다.

* 멘토링 의견: 초기에는 Jetson Orin Nano 내부에서 모델 추론까지 직접 수행하는 '로컬 추론' 방식으로 시스템을 구성하였으나, 산학협력 멘토로부터 "로컬 추론과 서버 추론 방식 중 실제 로봇 제어 시스템에 가장 적합하고 안정적인 구조를 명확하게 검증하고 결정할 필요가 있다"는 피드백을 받았습니다.

> 피드백을 반영하여 로컬 추론 방식과 서버 추론 방식 두 가지 아키텍처를 모두 구현하고 실제 환경에서 제어 성능을 비교 평가하였습니다. 평가 결과, Jetson 장치 하나에서 영상 처리, 제어, 추론 연산을 동시에 수행하는 것보다 역할을 분리하는 것이 유리하다고 판단하였습니다. 최종적으로 GPU 서버에서 연산량이 높은 ACT 정책 추론을 전담하고, Jetson Orin Nano는 카메라 데이터 수집과 실시간 로봇 제어만을 담당하는 '서버-클라이언트 기반 분산 구조'로 시스템을 수정하였습니다. 이를 통해 네트워크 오버헤드를 포함하고도 평균 30Hz의 안정적인 실시간 제어 주기를 달성할 수 있었습니다.

### 5. 설치 및 실행 방법
>
#### 5.1. 설치절차 및 실행 방법

##### 5.1.1. 환경 세팅 (학교 GPU 서버, 최초 1회)
```bash
bash scripts/setup_env.sh
```

##### 5.1.2. 데이터 수집 (Jetson Orin Nano)
```bash
export HF_USER=s1eepypillow
bash scripts/record.sh
```

##### 5.1.3. 데이터셋 병합
```bash
export HF_USER=s1eepypillow
bash scripts/merge_dataset.sh
```

##### 5.1.4. ACT 학습 (학교 GPU 서버)
```bash
tmux new -s train
export HF_USER=s1eepypillow
bash scripts/train.sh
# Ctrl+B, D 로 세션에서 빠져나오기 (백그라운드로 계속 진행됨)
```

##### 5.1.5. 실물 로봇 배포 및 평가 (Jetson Orin Nano)
```bash
export HF_USER=s1eepypillow
bash scripts/rollout.sh
```

#### 5.2. 오류 발생 시 해결 방법
##### 5.2.1. CPU Starvation
* 증상: 데이터 수집 중 프레임이 유실(Frame Drop)되거나 로봇의 움직임이 뚝뚝 끊기는 현상이 발생하며, 콘솔에 제어 루프의 Hz가 설정값보다 크게 낮아지는 경고가 출력됩니다. (예: The record loop is running slower at 15.5 Hz.)
* 원인: Jetson Orin Nano와 같은 엣지 디바이스에서 카메라 영상 처리, 네트워크 송신, 로봇 제어 명령이 동시에 실행되면서 CPU 자원이 부족해져 발생하는 현상입니다.
* 해결 방법:
    * 백그라운드에서 실행 중인 불필요한 프로세스를 모두 종료하여 CPU 자원을 확보합니다.
    * 실시간 제어 루프 내의 불필요한 디버그 출력(print 문 등)을 최소화합니다.
    * Jetson Orin Nano의 전원 모드를 최대 성능 모드(예: MAXN)로 변경하여 연산 성능을 끌어올립니다.

##### 5.1.2. 포트(Port) 인식 문제
* 증상: 로봇 팔(Leader/Follower) 또는 카메라 장치가 /dev/ttyUSB* 또는 /dev/video* 경로에 제대로 마운트되지 않거나, 실행 시 장치를 찾을 수 없다는 에러(Device not found)가 발생합니다.
* 원인: USB 케이블 접촉 불량, 허브 전력 부족, 또는 장치가 예기치 않게 연결 해제된 후 시스템에 고스트 포트로 남아 있는 경우 발생합니다.
* 해결 방법:
    * 문제가 발생한 장치의 USB 케이블을 물리적으로 분리한 후 재연결합니다.
    * 터미널에서 ls /dev/ttyUSB* 또는 ls /dev/video* 명령어를 통해 포트가 정상적으로 할당되었는지 재확인합니다.
    * 포트 권한 문제일 경우 sudo chmod 777 /dev/ttyUSB* 명령어를 통해 접근 권한을 부여합니다.

##### 5.2.3. 서버 통신 오류 (추론 서버 접속 불가)
* 증상: GPU 추론 서버와 TCP 소켓 통신을 시도할 때 Connection Refused 에러가 발생하거나, 타임아웃으로 인해 로봇 제어 루프가 실행되지 않습니다.
* 원인: 네트워크 연결이 불안정하거나 원격 GPU 서버의 추론 스크립트가 비정상 종료된 경우 발생합니다.
* 해결 방법 (로컬 폴백 모드):
원격 서버 통신이 불가능한 상황이라면, 분산 처리 아키텍처를 우회하고 Jetson Orin Nano 자체에서 로컬 추론을 실행하는 명령어로 전환해야 합니다.
    - 추론 서버에 의존하는 스크립트 대신, 배포 시 준비된 로컬 실행 명령어를 사용하여 Jetson 디바이스 단독으로 모델을 구동합니다. (단, 서버 추론에 비해 제어 Hz가 다소 낮아질 수 있습니다.)

### 6. 소개 자료 및 시연 영상
#### 6.1. 프로젝트 소개 자료
[![발표 자료](https://github.com/user-attachments/assets/6bbf73ca-a69c-4c12-9fe6-b74a31475e43)](https://canva.link/gwikvqrvoe0xnjp)
#### 6.2. 시연 영상
> 영상 링크 또는 주요 장면 설명

### 7. 팀 구성

#### 7.1. 팀원별 소개 및 역할 분담

*   **윤주연 (202255576, forsterix104@gmail.com)** 
    *   모방학습을 위한 Pick & Place 데이터셋 수집 
    *   모델 분석 및 하이퍼파라미터 테스팅 
    *   서버를 통한 모델 학습 환경 구축 

*   **강태훈 (202155503, kangth2103@gmail.com)** 
    *   LeRobot SO-101 하드웨어 구성 
    *   데이터셋 수집 전략 수립 및 수정 
    *   DAgger Correction을 위한 경로 수정 데이터셋 수집 

*   **송명근 (202355713, smk00513@naver.com)** 
    *   LeRobot SO-101 제어 환경 구축 
    *   다중 과제 해결을 위한 멀티태스크 환경 구축 
    *   모델 학습 및 수행 결과 분석 

#### 7.2. 팀원 별 참여 후기

**👩‍💻 윤주연**
> 모델의 성능을 극대화하기 위해 다양한 하이퍼파라미터 중에서 최적의 값을 찾아내는 테스팅 과정을 담당했습니다. 이 과정에서 CVAE 기반의 ACT 모델 구조와 잠재 공간에 대해 심도 있게 연구하게 되었고, 결과적으로 프로젝트의 전반적인 완성도를 높이는 데 큰 도움이 되었습니다.

**👨‍💻 강태훈**
> 모델의 한계를 극복하기 위해 DAgger 기반의 복구 궤적 데이터셋을 현 프로젝트에 적용하는 과정에서 많은 시행착오를 겪었습니다. 로봇이 헷갈려 하는 구간에서 어떤 방식의 실패-복구 데이터를 쌓아야 할지 수집 전략을 고민하며, 데이터 품질 관리와 시스템 안정화에 기여할 수 있었습니다.

**👨‍💻 송명근**
> Environment State를 활용하여 단일 ACT 모델이 멀티태스킹(Task 1, Task 2)이 가능한지 고민하고 이를 시스템에 직접 적용해 보았습니다. 이 과정에서 여러 시행착오를 거쳤지만, 결과적으로 환경 변화와 다양한 조건에서도 유연하게 동작하는 강건한(Robust) 제어 모델을 구축하는 데 기여할 수 있어 뜻깊었습니다.

## 8. 참고 문헌 및 출처

### 📖 논문 및 알고리즘 연구 (Research & Papers)
* **모방학습 (Imitation Learning/ACT)**: [Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware](https://arxiv.org/abs/2304.13705)

* **LeRobot 오픈소스 라이브러리 논문**: LEROBOT: AN OPEN-SOURCE LIBRARY FOR END-TO-END ROBOT LEARNING


### 🤖 하드웨어 스펙 (Hardware & Specs)

* **하드웨어 스택 명세서**: [LeRobot SO-101 Hardware Stack (Hugging Face)](https://huggingface.co/docs/lerobot/so101)
* **Jetson Orin Nano 스펙**: 
  * [Waveshare Wiki Overview](https://www.waveshare.com/wiki/Jetson_Orin_Nano#Overview)
  * [Jetbot Bill of Materials (Orin)](https://jetbot.org/master/bill_of_materials_orin.html)

### 💻 프레임워크 및 데이터셋 (Software & Dataset)
* **LeRobot 공식 GitHub**: [huggingface/lerobot](https://github.com/huggingface/lerobot/tree/main)
* **LeRobot 데이터셋 재생 가이드**: [Roboseasy Dataset Replay Docs](https://roboseasy.ai/docs/lerobot-so-arm/dataset-replay)
* **Pick & Place 데이터셋 예시**: [LeRobot-SO101-Pick-Place (Hugging Face)](https://huggingface.co/datasets/aswinkumar99/LeRobot-SO101-Pick-Place)

### ⚙️ 환경 구축 및 초기 설정 (Environment Setup & Configuration)
* **Jetson Orin Nano 초기 설정**
  * [NVIDIA Developer Get Started Guide](https://developer.nvidia.com/embedded/learn/get-started-jetson-orin-nano-devkit#intro)
  * [NVIDIA SDK Manager 다운로드 및 실행](https://docs.nvidia.com/sdk-manager/download-run-sdkm/index.html)

* **LeRobot 환경 구현 가이드**
  * [Medium: LeRobot on Jetson Orin Nano](https://medium.com/@marko.briesemann/lerobot-on-jetson-orin-nano-seeed-studio-82986429509a)
  * [Jetson AI Lab: LeRobot on Jetson (Docker 기반)](https://www.jetson-ai-lab.com/archive/lerobot.html)
