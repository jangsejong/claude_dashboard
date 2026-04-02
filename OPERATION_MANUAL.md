# Claude Usage Dashboard - 운영자 매뉴얼

TSP팀(5명) Claude Code Max 사용량 모니터링 시스템 운영 가이드

---

## 1. 시스템 구조

```
[tsp-01] collector ──┐
[tsp-02] collector ──┤
[tsp-03] collector ──┼──▶ [tsp-03 서버] API(:8000) ──▶ PostgreSQL(:5432)
[tsp-04] collector ──┤                                      │
[tsp-05] collector ──┘                               Grafana(:3000)
```

- **서버**: tsp-03 (WSL2) — Docker로 API, DB, Grafana 운영
- **서버 IP**: 100.76.175.42 (Tailscale), WSL 내부 172.27.202.25
- **수집기**: 각 개발자 PC에서 `~/.claude` 로그를 파싱하여 API로 전송

---

## 2. 서버 관리 (tsp-03에서 실행)

### 2-1. 서비스 시작

```bash
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml up -d
```

### 2-2. 서비스 중지

```bash
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml down
```

### 2-3. 서비스 상태 확인

```bash
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml ps
```

### 2-4. 로그 확인

```bash
# API 로그
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml logs api

# Grafana 로그
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml logs grafana

# PostgreSQL 로그
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml logs postgres
```

### 2-5. 서비스 재시작

```bash
# 전체 재시작
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml restart

# Grafana만 재시작
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml restart grafana
```

### 2-6. Windows 포트포워딩 (tsp-03 Windows CMD에서)

WSL2 포트를 외부에 노출하기 위해 **Windows 터미널**에서 실행:

```cmd
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=172.27.202.25
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=172.27.202.25
```

설정 확인:

```cmd
netsh interface portproxy show all
```

삭제 시:

```cmd
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=3000 listenaddress=0.0.0.0
```

---

## 3. 개발자 PC 설치 (tsp-01 ~ tsp-05)

### 3-1. collector 파일 복사

```bash
mkdir -p ~/claude-collector
scp tsp-03@100.76.175.42:~/workspace/pjt/claude_dashboard/collector/claude_collector.py ~/claude-collector/
```

또는 직접 파일을 복사해도 됩니다. 필요한 파일은 `claude_collector.py` 1개뿐입니다.

### 3-2. 의존성 설치

```bash
pip install requests
```

### 3-3. 연결 테스트

```bash
curl http://100.76.175.42:8000/health
```

`{"status":"ok"}` 이 나오면 정상입니다.

### 3-4. collector 실행 테스트

각 PC에 맞게 `--user`와 `--machine`을 변경:

```bash
# tsp-01의 경우
python3 ~/claude-collector/claude_collector.py \
  --user tsp-01 \
  --machine tsp-01 \
  --api-url http://100.76.175.42:8000

# tsp-02의 경우
python3 ~/claude-collector/claude_collector.py \
  --user tsp-02 \
  --machine tsp-02 \
  --api-url http://100.76.175.42:8000

# tsp-03의 경우 (서버 자체)
python3 ~/claude-collector/claude_collector.py \
  --user tsp-03 \
  --machine tsp-03 \
  --api-url http://localhost:8000

# tsp-04의 경우
python3 ~/claude-collector/claude_collector.py \
  --user tsp-04 \
  --machine tsp-04 \
  --api-url http://100.76.175.42:8000

# tsp-05의 경우
python3 ~/claude-collector/claude_collector.py \
  --user tsp-05 \
  --machine tsp-05 \
  --api-url http://100.76.175.42:8000
```

`Sent N usage records.` 가 출력되면 성공입니다.

### 3-5. crontab 등록 (10분마다 자동 수집)

```bash
crontab -e
```

아래 한 줄 추가 (user/machine은 각 PC에 맞게 변경):

```
*/10 * * * * python3 ~/claude-collector/claude_collector.py --user tsp-01 --machine tsp-01 --api-url http://100.76.175.42:8000 >> /tmp/claude-collector.log 2>&1
```

crontab 등록 확인:

```bash
crontab -l
```

### 3-6. 전체 데이터 재전송 (필요시)

기존 상태를 무시하고 모든 로그를 다시 전송합니다 (서버에서 중복 자동 처리):

```bash
python3 ~/claude-collector/claude_collector.py \
  --user tsp-01 \
  --machine tsp-01 \
  --api-url http://100.76.175.42:8000 \
  --full-scan
```

---

## 4. 대시보드 접속

### 4-1. 같은 네트워크에서

브라우저로 접속:

```
http://100.76.175.42:3000
```

- ID: `admin`
- PW: `admin`

### 4-2. SSH 터널링 (외부 접속)

```bash
ssh -L 3000:172.27.202.25:3000 user@100.76.175.42
```

이후 브라우저에서 `http://localhost:3000` 접속

---

## 5. API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/health` | GET | 서버 상태 확인 |
| `/ready` | GET | DB 연결 상태 확인 |
| `/usage` | POST | 사용량 데이터 전송 (collector가 사용) |
| `/usage/today` | GET | 오늘 총 토큰 |
| `/usage/yesterday` | GET | 어제 총 토큰 |
| `/usage/week` | GET | 이번 주 총 토큰 |
| `/usage/month` | GET | 이번 달 총 토큰 |
| `/usage/sessions` | GET | 오늘 세션 목록 (limit 파라미터) |

---

## 6. 트러블슈팅

### collector가 데이터를 보내지 못하는 경우

```bash
# 1. API 서버 접근 확인
curl http://100.76.175.42:8000/health

# 2. 실패 기록 확인
cat ~/.claude-usage-collector-failures.jsonl

# 3. 수집 상태 초기화 후 재전송
rm ~/.claude-usage-collector-state.json
python3 ~/claude-collector/claude_collector.py --user tsp-XX --machine tsp-XX --api-url http://100.76.175.42:8000
```

### Grafana에서 No Data 표시

```bash
# 1. DB에 데이터 있는지 확인
curl http://100.76.175.42:8000/usage/today

# 2. Grafana에서 Data Sources > PostgreSQL > Test 버튼 클릭

# 3. Grafana 재시작
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml restart grafana
```

### Docker 컨테이너가 안 뜨는 경우

```bash
# 컨테이너 상태 확인
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml ps -a

# 특정 컨테이너 로그 확인
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml logs api --tail 50

# 전체 재생성
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml down
docker compose -f ~/workspace/pjt/claude_dashboard/docker/docker-compose.yml up -d --build
```

### cron이 실행되지 않는 경우

```bash
# cron 서비스 상태 확인
sudo service cron status

# cron 서비스 시작
sudo service cron start

# 실행 로그 확인
cat /tmp/claude-collector.log
```

### Windows 재부팅 후 포트포워딩 재설정

Windows 재부팅 시 WSL2 IP가 변경될 수 있습니다:

```bash
# WSL에서 현재 IP 확인
hostname -I
```

Windows CMD에서 포트포워딩 재설정:

```cmd
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=3000 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<새IP>
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=<새IP>
```

---

## 7. 각 PC별 설정 요약

| PC | --user | --machine | --api-url | cron |
|----|--------|-----------|-----------|------|
| tsp-01 | tsp-01 | tsp-01 | http://100.76.175.42:8000 | */10 * * * * |
| tsp-02 | tsp-02 | tsp-02 | http://100.76.175.42:8000 | */10 * * * * |
| tsp-03 | tsp-03 | tsp-03 | http://localhost:8000 | */10 * * * * |
| tsp-04 | tsp-04 | tsp-04 | http://100.76.175.42:8000 | */10 * * * * |
| tsp-05 | tsp-05 | tsp-05 | http://100.76.175.42:8000 | */10 * * * * |

---

## 8. 파일 구조

```
pjt/claude_dashboard/
├── backend/                  # FastAPI API 서버
│   ├── main.py               # API 엔드포인트
│   ├── models.py             # Pydantic 모델
│   ├── db.py                 # DB 연결
│   ├── requirements.txt
│   └── Dockerfile
├── collector/                # 로그 수집기
│   ├── claude_collector.py   # 각 PC에 배포하는 파일
│   ├── requirements.txt
│   └── README.md
├── docker/                   # Docker 설정
│   ├── docker-compose.yml
│   └── init.sql              # DB 스키마
├── dashboard/                # Grafana 설정
│   └── grafana/provisioning/
│       ├── datasources/datasource.yml
│       └── dashboards/
│           ├── dashboards.yml
│           └── json/claude-usage.json
├── README.md
└── OPERATION_MANUAL.md       # 이 문서
```
