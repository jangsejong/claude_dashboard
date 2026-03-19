# Claude Code Max 사용량 모니터링 대시보드

팀(5명)의 Claude Code Max ($100 요금제) 사용량을 모니터링하는 내부 대시보드 시스템입니다.

## 중요: API 미제공

**Claude Code Max 요금제는 사용량 API를 제공하지 않습니다.**  
이 시스템은 Anthropic 공식 API가 아닌, **각 개발자 PC의 로컬 로그(`~/.claude`)만 파싱**하여 토큰 사용량을 수집합니다. 공식 대시보드가 없기 때문에 자체 구축한 모니터링입니다.

## 목적

- 개발자별 Claude 사용량 확인
- 일/주/월 단위 토큰 사용량 모니터링
- Claude Max 사용률 추정 (200k tokens/day 가정, 비공식)
- 프로젝트별 사용량 분석
- 팀 전체 사용량 추적

## 구조

```
pjt/claude_dashboard/
├── backend/          # FastAPI + PostgreSQL
├── collector/        # 로그 수집 에이전트 (각 개발자 PC에서 실행)
├── docker/           # docker-compose (postgres, api, grafana)
└── dashboard/        # Grafana 프로비저닝
```

## 빠른 시작

1. **서버 (한 번만)**  
   `docker compose -f pjt/claude_dashboard/docker/docker-compose.yml up -d` 로 postgres, API, Grafana 기동.

2. **개발자 PC**  
   `collector/claude_collector.py` 를 5분마다 실행 (cron 등).  
   `~/.claude/projects/` 아래 JSONL 로그를 읽어 API로 전송.

3. **대시보드**  
   Grafana (기본 3000 포트)에서 토큰/개발자/프로젝트별 통계 확인.

자세한 설정은 [collector/README.md](collector/README.md), [docker/](docker/) 내 주석을 참고하세요.
