# Claude Usage Collector

각 개발자 PC에서 **로컬에 저장된 Claude Code 로그**(`~/.claude`)만 읽어 사용량 API로 전송하는 에이전트입니다.  
**Claude Code Max 요금제는 API를 제공하지 않으므로**, 공식 API가 아닌 이 로그 파싱으로만 사용량을 수집합니다.

## 설치

```bash
pip install -r requirements.txt
```

## 사용

```bash
# 기본: 현재 사용자/호스트명, ~/.claude, http://localhost:8000
python claude_collector.py

# 옵션
python claude_collector.py --user tom --machine tsp-01 --api-url http://your-server:8000 --api-key YOUR_API_KEY
```

환경 변수: `USER`, `HOSTNAME`, `CLAUDE_USAGE_API_URL`, `API_KEY`

## 동작

1. `~/.claude/projects` 아래의 모든 `*.jsonl` (및 `sessions/*.jsonl`) 탐색
2. `type: "assistant"` 이고 `message.usage` 가 있는 라인만 추출
3. `~/.claude-usage-collector-state.json` 에 파일별 마지막 라인 번호 저장 → 다음 실행 시 **증분만** 전송
4. **POST /usage** 로 배치 전송. 실패 시 재시도 후 실패분은 `~/.claude-usage-collector-failures.jsonl` 에 적재

## Cron (5분마다)

```bash
*/5 * * * * cd /path/to/pjt/claude_dashboard/collector && python claude_collector.py --api-url http://YOUR_API:8000 >> /var/log/claude-collector.log 2>&1
```
