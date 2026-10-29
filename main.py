#!/usr/bin/env python
import sys
from pathlib import Path

# 현재 디렉터리를 모듈 탐색 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from llm_wiki.main import main

if __name__ == "__main__":
    main()
