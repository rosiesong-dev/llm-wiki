---
title: Kafka vs RabbitMQ
type: comparison
summary: 결제 큐 후보 두 가지 비교 (예시)
updated: '2026-10-29'
---

# Kafka vs RabbitMQ

| 항목 | Kafka | RabbitMQ |
|---|---|---|
| 모델 | 로그 기반 스트리밍 | 브로커 기반 큐 |
| 재처리 | 오프셋으로 다시 읽기 쉬움 | 기본적으로 소비 후 삭제 |
| 처리량 | 매우 높음 | 높음 |
| 결정 | **채택** | 보류 |

출처: [[2026-10-26 결제 큐 아키텍처 회의록]]

