import json
import logging
from typing import List
import numpy as np
import requests

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", embedding_model: str = "text-embedding-004"):
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model

    def generate_text(self, prompt: str) -> str:
        """Gemini 텍스트 생성 (위키 요약 및 티켓 초안 작성)"""
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            logger.warning("GEMINI_API_KEY 미설정 - 시뮬레이션(Mock) 응답을 반환합니다.")
            return self._mock_generate(prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ]
        }

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        try:
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        except Exception as e:
            logger.error(f"Gemini 응답 파싱 오류: {e}")
            raise RuntimeError(f"Gemini API 오류: {data}")

        return ""

    def generate_embedding(self, text: str) -> List[float]:
        """Gemini 텍스트 임베딩 생성 (RAG용)"""
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return self._mock_embedding(text)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.embedding_model}:embedContent?key={self.api_key}"
        payload = {
            "content": {
                "parts": [{"text": text}]
            }
        }

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        embedding = data.get("embedding", {}).get("values")
        if embedding:
            return embedding
        return self._mock_embedding(text)

    def _mock_generate(self, prompt: str) -> str:
        if "티켓 초안" in prompt or "엔지니어링 티켓" in prompt:
            return json.dumps({
                "title": "[결제장애] HikariCP 풀 고갈 및 504 타임아웃 해결을 위한 비동기 큐 전환",
                "issue_type": "Incident",
                "priority": "High",
                "labels": ["payment", "database", "concurrency", "hikari"],
                "description": (
                    "## 이슈 현황\n"
                    "- 결제 모듈에서 트래픽 급증 시 HikariCP max-pool-size(10) 초과로 인한 504 타임아웃 발생\n\n"
                    "## 참조 지식\n"
                    "- [[결제 서비스 504 타임아웃 장애 분석 및 대책]]\n\n"
                    "## 제안 작업\n"
                    "1. 임시 조치: max-pool-size를 30으로 상향\n"
                    "2. 근본 대책: Kafka 기반 비동기 결제 대기열 파이프라인 도입"
                ),
                "suggested_assignee": "Backend Team"
            }, ensure_ascii=False, indent=2)
        else:
            return """---
title: "결제 서비스 504 타임아웃 장애 분석 및 대책"
category: "issues"
tags: ["결제", "트래픽", "데이터베이스", "장애대응"]
source_id: "confluence-1001"
summary: "결제 요청 급증 시 커넥션 풀 고갈로 인한 504 장애 분석 및 Kafka 기반 큐 도입 대책"
---

# 결제 서비스 504 타임아웃 장애 분석 및 대책

## 1. 개요 (Summary)
결제 모듈에서 특정 시간대 동시 트래픽 급증 시 발생한 504 타임아웃 이슈에 대한 분석 및 후속 조치 가이드입니다.

## 2. 배경 및 원인 분석 (Background & Root Cause)
- **증상**: 500 TPS 인입 시 HikariCP 커넥션 락 경합 및 대기열 포화.
- **원인**: 기본 설정된 커넥션 풀(10) 부족.

## 3. 핵심 조치 및 해결 방법 (Action Items & Resolution)
- 임시 풀 크기를 30으로 확장하고 connection-timeout을 3초로 튜닝.
- 장기적으로 비동기 이벤트 큐([[Kafka_결제_아키텍처]])로 부하 분산 구조 구현.

## 4. 재발 방지 및 관련 지식 (Lessons Learned & Reference)
- [[Kubernetes 클러스터 리소스 가이드라인]]을 참조하여 파드 리소스 임계치도 함께 모니터링할 것.
"""

    def _mock_embedding(self, text: str) -> List[float]:
        vec = np.zeros(768, dtype=np.float32)
        for i, b in enumerate(text.encode("utf-8")):
            vec[i % 768] += float(b) / 255.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()
