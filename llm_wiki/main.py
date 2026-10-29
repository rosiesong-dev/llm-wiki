import argparse
import json
import logging
import re
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from llm_wiki.config import AppConfig
from llm_wiki.confluence import ConfluenceClient, ConfluencePage, save_windows_credential
from llm_wiki.llm import Prompts, create_llm_client
from llm_wiki.rag import Embedder, MarkdownChunker, VectorStore
from llm_wiki.slack import SlackClient, day_to_llm_text, day_to_transcript_md, save_slack_token
from llm_wiki.ticket import JiraTicketProvider, LocalMarkdownTicketProvider, TicketDrafter, TicketProvider
from llm_wiki.wiki import PAGE_TYPES, WikiDocument, WikiFrontmatter, WikiLinker, WikiLog, WikiManager, lint_wiki

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("llm-wiki")

def ingest_summary(config: AppConfig, llm, wiki_mgr: WikiManager, doc: WikiDocument, source_text: str,
                   source_label: str, link: bool = True) -> None:
    """Ingest 공통 처리: 요약 페이지 저장 → 엔티티·개념 페이지 생성/갱신 및 [[링크]] 연결 → index.md 갱신 → log.md 기록"""
    doc.frontmatter.type = "summary"
    saved_path = wiki_mgr.save_wiki_document(doc)
    console.print(f"[green]✓ 요약 페이지 저장: {saved_path}[/green]")

    details = [f"원본: {source_label}", f"요약: [[{doc.frontmatter.title}]]"]
    if link:
        console.print("[cyan]엔티티·개념 페이지 연결 중...[/cyan]")
        linked = WikiLinker(llm, wiki_mgr).link_source(doc, source_text)
        if linked["created"]:
            details.append("새 페이지: " + ", ".join(f"[[{t}]]" for t in linked["created"]))
        if linked["updated"]:
            details.append("갱신: " + ", ".join(f"[[{t}]]" for t in linked["updated"]))
        console.print(f"[green]✓ 엔티티·개념 새 페이지 {len(linked['created'])}개, 갱신 {len(linked['updated'])}개[/green]")
    WikiLog(config.wiki_storage_path).append("ingest", doc.frontmatter.title, details)

def run_check_user(config: AppConfig, base_url: str = "http://wiki.example.com/confluence") -> None:
    """Confluence /rest/api/user/current 엔드포인트 확인"""
    console.print(f"[cyan]Confluence 현재 사용자 확인 요청 중: {base_url}/rest/api/user/current[/cyan]")
    client = ConfluenceClient(base_url=base_url)
    try:
        user_info = client.get_current_user()
        console.print(Panel(
            json.dumps(user_info, ensure_ascii=False, indent=2),
            title="👤 Confluence 현재 사용자 정보",
            style="green",
        ))
    except Exception as e:
        console.print(f"[red]사용자 정보 확인 실패: {e}[/red]")

def run_set_credential(target: str = "wiki.example.com", username: str = "user@example.com") -> None:
    """Windows Credential Manager에 Confluence 계정 안전하게 저장"""
    import getpass
    console.print(f"[bold cyan]Windows 자격 증명 관리자에 '{target}' ({username}) 계정 정보 등록[/bold cyan]")
    password = getpass.getpass("Confluence 비밀번호 또는 개인 액세스 토큰(PAT) 입력: ")
    if not password:
        console.print("[red]비밀번호가 입력되지 않았습니다.[/red]")
        return
    success = save_windows_credential(target, username, password)
    if success:
        console.print(f"[bold green]✓ Windows 자격 증명 관리자에 '{target}' ({username}) 등록 완료![/bold green]")
        console.print("[dim]이제 API 호출 시 암호화된 저장소에서 안전하게 불러와 인증합니다.[/dim]")
    else:
        console.print("[red]자격 증명 저장에 실패했습니다.[/red]")

def run_fetch_page(config: AppConfig, page_id: str, base_url: str = "http://wiki.example.com/confluence", mock: bool = False) -> None:
    """특정 페이지(회의록 등)를 Confluence에서 가져와 위키화 및 RAG 인덱싱까지 원스톱 실행"""
    console.print(f"[bold yellow]=== Confluence 페이지 [{page_id}] 수집 및 위키화 시작 ===[/bold yellow]")
    raw_confluence_dir = config.raw_storage_path / "confluence"
    wiki_mgr = WikiManager(config.wiki_storage_path)
    llm = create_llm_client(config)

    page: ConfluencePage
    if mock:
        console.print("[yellow]Mock 시뮬레이션 데이터를 사용합니다...[/yellow]")
        pages = ConfluenceClient.generate_sample_raw_pages(raw_confluence_dir)
        page = pages[0]
    else:
        client = ConfluenceClient(base_url=base_url)
        try:
            page = client.fetch_page_by_id(page_id)
            ConfluenceClient.save_raw_pages(raw_confluence_dir, [page])
            console.print(f"[green]✓ Confluence 원본 수집 성공: [{page.id}] {page.title}[/green]")
        except Exception as e:
            console.print(f"[red]Confluence 페이지 가져오기 실패: {e}[/red]")
            console.print("[yellow]💡 팁: 'python main.py set-credential'로 윈도우 자격증명을 먼저 등록하거나, --mock 옵션을 사용할 수 있습니다.[/yellow]")
            return

    # 2. 위키 요약 및 마크다운 생성
    console.print(f"[cyan]AI({config.llm_backend.upper()})를 활용하여 회의록 요약 및 마크다운 위키 문서 생성 중...[/cyan]")
    metadata = f"ID: {page.id}, Space: {page.space_id}, 작성자: {page.author_id}, 버전: {page.version_number}"
    source_text = page.to_plain_text()
    prompt = Prompts.build_wiki_summary_prompt(page.title, source_text, metadata)
    markdown_output = llm.generate_text(prompt)
    if llm.last_was_mock and not mock:
        console.print("[red]LLM 호출 실패로 Mock 응답이 반환되어 저장을 중단합니다. (Ollama/Gemini 상태를 확인하세요)[/red]")
        return

    doc = WikiDocument.parse(markdown_output, config.wiki_storage_path / page.title)
    doc.frontmatter.title = page.title
    doc.frontmatter.source_id = f"confluence-{page.id}"
    ingest_summary(config, llm, wiki_mgr, doc, source_text, f"Confluence {page.space_id}/{page.id}", link=not mock)

    # 3. RAG 인덱싱
    console.print("[cyan]회의록 내용을 RAG 벡터 인덱스에 반영 중...[/cyan]")
    run_index(config)
    console.print(f"[bold green]=== 완료! 이제 'python main.py ask \"질문\"' 또는 'python main.py chat'으로 회의록 내용을 물어볼 수 있습니다! ===[/bold green]")

def run_set_gemini_key() -> None:
    """Windows 자격 증명 관리자에 Gemini API 키 저장 (.env에 평문으로 두지 않음)"""
    import getpass
    import keyring
    from llm_wiki.config import GEMINI_CREDENTIAL
    key = getpass.getpass("Gemini API Key 입력 (AI Studio에서 발급): ").strip()
    if not key:
        console.print("[red]키가 입력되지 않았습니다.[/red]")
        return
    keyring.set_password(*GEMINI_CREDENTIAL, key)
    console.print("[bold green]✓ Windows 자격 증명 관리자에 Gemini API 키 등록 완료 (target: gemini)[/bold green]")

def run_set_claude_key() -> None:
    """Windows 자격 증명 관리자에 Claude(Anthropic) API 키 저장 (.env에 평문으로 두지 않음)"""
    import getpass
    import keyring
    from llm_wiki.config import CLAUDE_CREDENTIAL
    key = getpass.getpass("Claude API Key 입력 (Claude Console에서 발급, sk-ant-...): ").strip()
    if not key:
        console.print("[red]키가 입력되지 않았습니다.[/red]")
        return
    keyring.set_password(*CLAUDE_CREDENTIAL, key)
    console.print("[bold green]✓ Windows 자격 증명 관리자에 Claude API 키 등록 완료 (target: claude)[/bold green]")

def run_set_slack_token() -> None:
    """Windows 자격 증명 관리자에 Slack Bot 토큰 저장"""
    import getpass
    token = getpass.getpass("Slack Bot Token (xoxb-...) 입력: ").strip()
    if not token.startswith("xoxb-"):
        console.print("[red]xoxb- 로 시작하는 Bot 토큰을 입력해 주세요.[/red]")
        return
    save_slack_token(token)
    console.print("[bold green]✓ Windows 자격 증명 관리자에 Slack Bot 토큰 등록 완료 (target: slack)[/bold green]")

def run_fetch_slack(config: AppConfig, channel_id: str, days: Optional[int] = None) -> None:
    """Slack 채널 메시지(스레드 포함)를 storage/raw/slack/{채널명}/YYYY-MM-DD.json 으로 수집"""
    from datetime import datetime, timedelta
    client = SlackClient()
    channel = client.get_channel(channel_id)
    oldest = (datetime.now() - timedelta(days=days)).timestamp() if days else None
    period = f"최근 {days}일" if days else "전체 기간"
    console.print(f"[cyan]Slack #{channel['name']} ({channel_id}) {period} 메시지 수집 중...[/cyan]")

    messages = client.fetch_history(channel_id, oldest=oldest)
    replies = sum(len(m.get("_replies", [])) for m in messages)
    saved = SlackClient.save_raw_by_date(config.raw_storage_path / "slack", channel, messages)
    console.print(
        f"[bold green]✓ 메시지 {len(messages)}개 (스레드 댓글 {replies}개) → "
        f"{len(saved)}개 날짜 파일 저장: {config.raw_storage_path / 'slack' / channel['name']}[/bold green]"
    )

def run_build_slack_wiki(config: AppConfig, channel: Optional[str] = None, date: Optional[str] = None,
                         force: bool = False, link: bool = True) -> None:
    """storage/raw/slack/{채널명}/YYYY-MM-DD.json → wiki/slack/ 날짜별 요약 문서 (LLM 요약 + 원문 대화)"""
    raw_slack_dir = config.raw_storage_path / "slack"
    wiki_mgr = WikiManager(config.wiki_storage_path)
    llm = create_llm_client(config)

    pattern = f"{channel or '*'}/{date or '*'}.json"
    day_files = sorted(raw_slack_dir.glob(pattern))
    if not day_files:
        console.print(f"[yellow]처리할 Slack 원본이 없습니다 ({raw_slack_dir / pattern}). 먼저 'fetch-slack'을 실행하세요.[/yellow]")
        return

    built = 0
    for path in day_files:
        day = json.loads(path.read_text(encoding="utf-8"))
        ch_name, day_str = day["channel"]["name"], day["date"]
        title = f"Slack #{ch_name} {day_str}"
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
        target = config.wiki_storage_path / PAGE_TYPES["summary"] / "slack" / f"{safe_title}.md"
        # 원본 수집 이후 이미 만든 문서는 건너뜀 (--force로 재생성)
        if target.exists() and not force and target.stat().st_mtime >= path.stat().st_mtime:
            console.print(f"[dim]- 건너뜀 (최신): {title}[/dim]")
            continue

        conversation = day_to_llm_text(day)
        if not conversation.strip():
            continue
        console.print(f"[cyan]Slack 대화 요약 중: {title} (메시지 {day['message_count']}개)[/cyan]")
        markdown_output = llm.generate_text(Prompts.build_slack_digest_prompt(ch_name, day_str, conversation))
        if llm.last_was_mock:
            console.print(f"[red]LLM 호출 실패로 Mock 응답이 반환되어 '{title}' 저장을 중단합니다.[/red]")
            return

        doc = WikiDocument.parse(markdown_output.strip().removeprefix("```markdown").removesuffix("```").strip(), target)
        doc.frontmatter.title = title
        doc.frontmatter.category = "slack"
        doc.frontmatter.source_id = f"slack-{day['channel']['id']}-{day_str}"
        doc.body = doc.body.rstrip() + "\n\n" + day_to_transcript_md(day)
        ingest_summary(config, llm, wiki_mgr, doc, conversation, f"Slack #{ch_name} {day_str} (메시지 {day['message_count']}개)",
                       link=link)
        built += 1

    console.print(f"[bold green]✓ Slack 위키 문서 {built}개 생성 완료[/bold green]")
    if built:
        console.print("[cyan]RAG 벡터 인덱스 갱신 중...[/cyan]")
        run_index(config)

def run_sync(config: AppConfig, mock: bool = False) -> None:
    raw_confluence_dir = config.raw_storage_path / "confluence"
    if mock or not config.confluence_base_url:
        console.print("[yellow]Confluence 샘플 데이터를 시뮬레이션(Mock) 수집합니다...[/yellow]")
        pages = ConfluenceClient.generate_sample_raw_pages(raw_confluence_dir)
        console.print(f"[green]✓ 총 {len(pages)}개의 Confluence 원본 문서 수집 완료 (경로: {raw_confluence_dir})[/green]")
    else:
        client = ConfluenceClient(
            base_url=config.confluence_base_url,
            email=config.confluence_email or "",
            api_token=config.confluence_api_token or "",
        )
        space_key = config.confluence_space_key or "DEV"
        pages = client.fetch_pages_by_space(space_key)
        ConfluenceClient.save_raw_pages(raw_confluence_dir, pages)
        console.print(f"[green]✓ Confluence [{space_key}] 스페이스로부터 {len(pages)}개 문서 수집 완료[/green]")

def run_build_wiki(config: AppConfig) -> None:
    raw_confluence_dir = config.raw_storage_path / "confluence"
    wiki_mgr = WikiManager(config.wiki_storage_path)
    llm = create_llm_client(config)

    if not raw_confluence_dir.exists():
        console.print("[red]수집된 원본 데이터가 없습니다. 먼저 'sync' 명령을 실행하세요.[/red]")
        return

    # storage/raw/confluence/{스페이스 키}/*.json (Mock 샘플은 _sample/)
    json_files = list(raw_confluence_dir.rglob("*.json"))
    if not json_files:
        console.print("[yellow]처리할 원본 JSON 파일이 없습니다.[/yellow]")
        return

    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            page = ConfluencePage(**data)
            console.print(f"[cyan]문서 요약 및 위키 변환 중: [{page.id}] {page.title}[/cyan]")

            metadata = f"ID: {page.id}, Space: {page.space_id}, 작성자: {page.author_id}, 버전: {page.version_number}"
            source_text = page.to_plain_text()
            prompt = Prompts.build_wiki_summary_prompt(page.title, source_text, metadata)
            markdown_output = llm.generate_text(prompt)
            if llm.last_was_mock and path.parent.name != "_sample":
                console.print("[red]LLM 호출 실패로 Mock 응답이 반환되어 중단합니다.[/red]")
                return

            doc = WikiDocument.parse(markdown_output, config.wiki_storage_path / page.title)
            doc.frontmatter.title = page.title
            doc.frontmatter.source_id = f"confluence-{page.id}"
            ingest_summary(config, llm, wiki_mgr, doc, source_text, f"Confluence {page.space_id}/{page.id}",
                           link=not llm.last_was_mock)
        except Exception as e:
            logger.error(f"위키 생성 오류 {path}: {e}")

    console.print(f"[bold green]✓ 모든 위키 문서 생성 및 최상위 색인({config.wiki_storage_path / 'index.md'}) 갱신 완료![/bold green]")

def run_index(config: AppConfig) -> None:
    wiki_mgr = WikiManager(config.wiki_storage_path)
    llm = create_llm_client(config)
    store = VectorStore(config.index_storage_path)
    embedder = Embedder(llm)

    docs = wiki_mgr.load_all_documents()
    console.print(f"[cyan]RAG 인덱싱 대상 위키 문서: {len(docs)}개[/cyan]")

    all_embedded = []
    for doc in docs:
        chunks = MarkdownChunker.chunk_document(doc)
        console.print(f"- '{doc.frontmatter.title}' 청크 분할: {len(chunks)}개")
        for chunk in chunks:
            all_embedded.append(embedder.embed_chunk(chunk))

    # 위키 전체를 매번 다시 임베딩하므로 기존 인덱스를 비우고 재구축 (중복 청크 방지)
    store.clear()
    store.add_chunks(all_embedded)
    store.save()
    console.print(f"[bold green]✓ RAG 벡터 인덱스 구축 완료 (총 청크 수: {store.chunk_count})[/bold green]")
    WikiLog(config.wiki_storage_path).append("index", "RAG 벡터 인덱스 재구축", [f"문서 {len(docs)}개, 청크 {store.chunk_count}개"])

def run_search(config: AppConfig, query: str, top_k: int = 3) -> None:
    llm = create_llm_client(config)
    store = VectorStore(config.index_storage_path)

    console.print(f"[cyan]질의 임베딩 생성 및 시맨틱 검색 중: '{query}'[/cyan]")
    query_vec = llm.generate_embedding(query)
    results = store.search(query_vec, top_k=top_k, query_text=query)

    table = Table(title=f"🔍 검색 결과 (상위 {len(results)}건)")
    table.add_column("No.", justify="right", style="cyan")
    table.add_column("문서 제목", style="green")
    table.add_column("섹션", style="magenta")
    table.add_column("유사도", justify="right", style="yellow")
    table.add_column("내용 발췌", style="white")

    for i, res in enumerate(results, 1):
        content_preview = res.chunk.chunk.content.replace("\n", " ")[:80] + "..."
        table.add_row(
            str(i),
            res.chunk.chunk.document_title,
            res.chunk.chunk.section_title,
            f"{res.score:.4f}",
            content_preview,
        )

    console.print(table)

def run_ask(config: AppConfig, question: str, top_k: int = 8, save_as: Optional[str] = None,
            save_title: Optional[str] = None) -> None:
    llm = create_llm_client(config)
    store = VectorStore(config.index_storage_path)
    wiki_mgr = WikiManager(config.wiki_storage_path)

    console.print(Panel(f"[bold cyan]질문:[/bold cyan] {question}", title="❓ 사내 LLM-Wiki 질의응답"))

    # 1. index.md(전체 목차)를 가장 먼저 읽음
    index_file = config.wiki_storage_path / "index.md"
    wiki_index = index_file.read_text(encoding="utf-8") if index_file.exists() else ""

    # 2. RAG 시맨틱 검색으로 관련 페이지 섹션 찾기
    query_vec = llm.generate_embedding(question)
    results = store.search(query_vec, top_k=top_k, query_text=question)

    if not results:
        console.print("[yellow]색인된 위키 문서가 없습니다. 먼저 'python main.py index'를 실행해 주세요.[/yellow]")
        return

    context_lines = []
    for i, res in enumerate(results, 1):
        context_lines.append(
            f"--- [참고 {i}]: [[{res.chunk.chunk.document_title}]] ({res.chunk.chunk.section_title}) ---\n"
            f"{res.chunk.chunk.content}\n"
        )
    context = "\n".join(context_lines)

    # 3. LLM 질의응답 생성
    prompt = Prompts.build_qa_prompt(question, context, wiki_index)
    # 짧은 답변 + 속도 우선 (Gemini는 thinking 생략)
    answer = llm.generate_text(prompt, max_output_tokens=400, fast=True)
    if llm.last_was_mock:
        console.print("[red]LLM 호출에 실패해 답변을 만들지 못했습니다. (Gemini: 'python main.py set-gemini-key'로 API 키 등록 / Claude: 'python main.py set-claude-key'로 API 키 등록 / Gemma: Ollama 실행 확인)[/red]")
        return

    # 4. 결과 출력
    console.print(Panel(answer, title="💡 AI 답변", style="green"))

    sources = list(dict.fromkeys(res.chunk.chunk.document_title for res in results))
    console.print("[dim]📚 참조한 위키 지식 출처:[/dim]")
    for res in results:
        console.print(f" [dim]- [[{res.chunk.chunk.document_title}]] > {res.chunk.chunk.section_title} (유사도: {res.score:.2f})[/dim]")

    # 5. 쓸모 있는 답변은 위키 페이지로 다시 저장 (Query 결과가 위키에 쌓이도록)
    details = ["참조: " + ", ".join(f"[[{t}]]" for t in sources)]
    if save_as and not llm.last_was_mock:
        fm = WikiFrontmatter(title=save_title or question, type=save_as, summary=question, tags=["query"])
        body = f"# {fm.title}\n\n> 질문: {question}\n\n## 답변\n\n{answer.strip()}\n\n## 출처\n" + \
               "\n".join(f"- [[{t}]]" for t in sources) + "\n"
        doc = WikiDocument(wiki_mgr.path_for(fm), fm, body, sources)
        saved = wiki_mgr.save_wiki_document(doc)
        details.append(f"답변 저장: [[{fm.title}]] ({save_as})")
        console.print(f"[bold green]✓ 답변을 위키 페이지로 저장: {saved}[/bold green]")
    WikiLog(config.wiki_storage_path).append("query", question, details)

def run_lint(config: AppConfig) -> None:
    """위키 구조 점검: 깨진 링크, 고아 페이지, 한 줄 요약 누락, 출처 없는 엔티티·개념"""
    report = lint_wiki(WikiManager(config.wiki_storage_path))
    table = Table(title=f"🩺 위키 점검 결과 (문제 {report.issue_count}건)")
    table.add_column("항목", style="cyan")
    table.add_column("건수", justify="right", style="yellow")
    table.add_column("대상", style="white")
    broken = [f"{p} → {', '.join(ls)}" for p, ls in report.broken_links.items()]
    for name, items in [("깨진 링크 (없는 페이지로 연결)", broken), ("고아 페이지 (들어오는 링크 없음)", report.orphans),
                        ("한 줄 요약 없음", report.no_summary), ("출처 없는 엔티티·개념", report.unsourced)]:
        table.add_row(name, str(len(items)), "\n".join(items[:15]) + (" ..." if len(items) > 15 else ""))
    console.print(table)
    WikiLog(config.wiki_storage_path).append("lint", f"구조 점검 - 문제 {report.issue_count}건", [
        f"깨진 링크 {sum(len(v) for v in report.broken_links.values())}건, 고아 페이지 {len(report.orphans)}건, "
        f"요약 없음 {len(report.no_summary)}건, 출처 없음 {len(report.unsourced)}건",
    ])

def run_chat(config: AppConfig) -> None:
    console.print("[bold green]=== 사내 LLM-Wiki 대화형 챗봇에 오신 것을 환영합니다! (종료: exit 또는 quit) ===[/bold green]\n")
    while True:
        try:
            question = console.input("[bold cyan]질문 입력 > [/bold cyan]").strip()
            if not question:
                continue
            if question.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]대화를 종료합니다.[/yellow]")
                break
            run_ask(config, question)
            console.print("\n" + "-" * 60 + "\n")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]대화를 종료합니다.[/yellow]")
            break

def run_ticket(config: AppConfig, requirement: str, provider_name: str = "local") -> None:
    llm = create_llm_client(config)
    store = VectorStore(config.index_storage_path)
    drafter = TicketDrafter(llm, store)

    console.print(Panel(f"[bold cyan]이슈 요구사항:[/bold cyan] {requirement}", title="📝 RAG 기반 티켓 자동 생성"))
    draft, contexts = drafter.draft_ticket(requirement)

    console.print(f"[yellow]참조된 위키 지식 (총 {len(contexts)}건):[/yellow]")
    for c in contexts:
        console.print(f" - [[{c.chunk.chunk.document_title}]] (섹션: {c.chunk.chunk.section_title}, 유사도: {c.score:.2f})")

    console.print("\n[bold green]생성된 티켓 초안:[/bold green]")
    console.print(f"제목: {draft.title}")
    console.print(f"유형: {draft.issue_type} | 우선순위: {draft.priority}")
    console.print(f"라벨: {draft.labels} | 추천 담당: {draft.suggested_assignee}")
    console.print("\n[white]" + draft.description + "[/white]\n")

    provider: TicketProvider
    if provider_name == "jira":
        provider = JiraTicketProvider(
            base_url=config.jira_base_url or "https://your-domain.atlassian.net",
            project_key=config.jira_project_key or "DEV",
            email=config.jira_email,
            api_token=config.jira_api_token,
        )
    else:
        provider = LocalMarkdownTicketProvider(config.tickets_storage_path / "LOCAL")

    result = provider.issue_ticket(draft)
    console.print(Panel(
        f"[bold]프로바이더:[/bold] {result.provider}\n"
        f"[bold]티켓 ID:[/bold] {result.ticket_id}\n"
        f"[bold]경로 / URL:[/bold] {result.url}\n"
        f"[bold]상태:[/bold] {result.status}",
        title="🚀 티켓 발행 완료",
        style="green",
    ))

def main() -> None:
    config = AppConfig.load()
    config.ensure_directories()

    parser = argparse.ArgumentParser(
        prog="llm-wiki",
        description="Python LLM-Wiki: Confluence 수집, Gemini AI, Gemma AI or Claude 위키 생성, RAG 지식 검색 및 티켓 발행 자동화 시스템",
    )
    parser.add_argument(
        "--backend",
        choices=["gemini", "gemma", "claude"],
        default=None,
        help="사용할 LLM 백엔드 선택 (기본값: .env의 LLM_BACKEND)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check-user
    check_p = subparsers.add_parser("check-user", help="Confluence /rest/api/user/current 현재 로그인 사용자 확인")
    check_p.add_argument("--url", default="http://wiki.example.com/confluence", help="Confluence Base URL")

    # set-credential
    cred_p = subparsers.add_parser("set-credential", help="Windows 자격 증명 관리자에 Confluence 계정 안전하게 저장")
    cred_p.add_argument("--target", default="wiki.example.com", help="자격 증명 타겟 이름")
    cred_p.add_argument("--username", default="user@example.com", help="사용자명 (이메일)")

    # fetch-page
    fetch_p = subparsers.add_parser("fetch-page", help="특정 Confluence 페이지(회의록 등)를 가져와 위키화 및 RAG 인덱싱")
    fetch_p.add_argument("page_id", help="가져올 Confluence Page ID (예: 3768355)")
    fetch_p.add_argument("--url", default="http://wiki.example.com/confluence", help="Confluence Base URL")
    fetch_p.add_argument("--mock", action="store_true", help="샘플 회의록 데이터로 시뮬레이션")

    # set-gemini-key
    subparsers.add_parser("set-gemini-key", help="Windows 자격 증명 관리자에 Gemini API 키 저장")

    # set-claude-key
    subparsers.add_parser("set-claude-key", help="Windows 자격 증명 관리자에 Claude(Anthropic) API 키 저장")

    # set-slack-token
    subparsers.add_parser("set-slack-token", help="Windows 자격 증명 관리자에 Slack Bot 토큰 저장")

    # fetch-slack
    slack_p = subparsers.add_parser("fetch-slack", help="Slack 채널 메시지(스레드 포함)를 storage/raw/slack/{채널명}/에 수집")
    slack_p.add_argument("--channel", default=None, help="Slack 채널 ID (기본값: .env의 SLACK_CHANNEL_ID)")
    slack_p.add_argument("--days", type=int, default=None, help="최근 N일만 수집 (기본값: 전체 기간)")

    # build-slack-wiki
    sw_p = subparsers.add_parser("build-slack-wiki", help="수집한 Slack 대화를 날짜별 위키 문서로 정리하고 RAG 인덱싱")
    sw_p.add_argument("--channel", default=None, help="채널 이름 (기본값: 수집된 전체 채널)")
    sw_p.add_argument("--date", default=None, help="특정 날짜만 (YYYY-MM-DD)")
    sw_p.add_argument("--force", action="store_true", help="이미 만든 문서도 다시 생성")
    sw_p.add_argument("--no-link", action="store_true", help="엔티티·개념 페이지 연결 단계 생략 (빠름)")

    # sync
    sync_p = subparsers.add_parser("sync", help="Confluence에서 이슈 및 업무 문서 수집")
    sync_p.add_argument("--mock", action="store_true", help="샘플 데이터 시뮬레이션 수집")

    # build-wiki
    subparsers.add_parser("build-wiki", help="storage/raw/ 원본을 AI로 요약하여 Markdown 위키 생성")

    # index
    subparsers.add_parser("index", help="위키 문서를 청킹 및 임베딩하여 RAG 벡터 인덱스 생성")

    # search
    search_p = subparsers.add_parser("search", help="사내 위키 지식 시맨틱 검색")
    search_p.add_argument("query", help="검색할 질의어")
    search_p.add_argument("-k", "--top-k", type=int, default=3, help="상위 몇 건을 가져올지 지정")

    # ask (Q&A)
    ask_p = subparsers.add_parser("ask", help="사내 위키 지식 기반 자연어 Q&A")
    ask_p.add_argument("question", help="궁금한 질문 (예: '결제 타임아웃 조치 방안이 뭐야?')")
    ask_p.add_argument("-k", "--top-k", type=int, default=8, help="참조할 위키 섹션 수 (기본 8)")
    ask_p.add_argument("--save", dest="save_as", default=None, choices=["synthesis", "comparison", "concept", "overview"],
                       help="답변을 해당 종류의 위키 페이지로 저장 (예: --save comparison)")
    ask_p.add_argument("--title", dest="save_title", default=None, help="저장할 페이지 제목 (기본값: 질문)")

    # lint
    subparsers.add_parser("lint", help="위키 구조 점검 (깨진 링크, 고아 페이지, 요약 누락, 출처 없는 페이지)")

    # chat (Interactive)
    subparsers.add_parser("chat", help="대화형 챗봇 모드로 위키 지식 질의응답")

    # ticket
    ticket_p = subparsers.add_parser("ticket", help="RAG 지식을 활용하여 이슈/요구사항 티켓 작성 및 발행")
    ticket_p.add_argument("requirement", help="티켓으로 만들 이슈 현상이나 요구사항")
    ticket_p.add_argument("-p", "--provider", default="local", choices=["local", "jira"], help="발행 대상 프로바이더")

    # pipeline
    pipe_p = subparsers.add_parser("pipeline", help="[수집 -> 위키 생성 -> RAG 인덱싱] 전체 파이프라인 일괄 실행")
    pipe_p.add_argument("--mock", action="store_true", help="샘플 데이터 시뮬레이션 모드로 실행")

    args = parser.parse_args()

    if args.backend:
        config.llm_backend = args.backend

    if args.command == "check-user":
        run_check_user(config, base_url=args.url)
    elif args.command == "set-credential":
        run_set_credential(target=args.target, username=args.username)
    elif args.command == "fetch-page":
        run_fetch_page(config, page_id=args.page_id, base_url=args.url, mock=args.mock)
    elif args.command == "set-gemini-key":
        run_set_gemini_key()
    elif args.command == "set-claude-key":
        run_set_claude_key()
    elif args.command == "set-slack-token":
        run_set_slack_token()
    elif args.command == "fetch-slack":
        channel_id = args.channel or config.slack_channel_id
        if not channel_id:
            console.print("[red]--channel 또는 .env의 SLACK_CHANNEL_ID를 지정해 주세요.[/red]")
            return
        run_fetch_slack(config, channel_id=channel_id, days=args.days)
    elif args.command == "build-slack-wiki":
        run_build_slack_wiki(config, channel=args.channel, date=args.date, force=args.force, link=not args.no_link)
    elif args.command == "sync":
        run_sync(config, mock=args.mock)
    elif args.command == "build-wiki":
        run_build_wiki(config)
    elif args.command == "index":
        run_index(config)
    elif args.command == "search":
        run_search(config, query=args.query, top_k=args.top_k)
    elif args.command == "ask":
        run_ask(config, question=args.question, top_k=args.top_k, save_as=args.save_as, save_title=args.save_title)
    elif args.command == "lint":
        run_lint(config)
    elif args.command == "chat":
        run_chat(config)
    elif args.command == "ticket":
        run_ticket(config, requirement=args.requirement, provider_name=args.provider)
    elif args.command == "pipeline":
        console.print("[bold yellow]=== 1단계: Confluence 데이터 수집 ===[/bold yellow]")
        run_sync(config, mock=args.mock)
        console.print(f"[bold yellow]=== 2단계: {config.llm_backend.upper()} 위키 문서 요약 및 생성 ===[/bold yellow]")
        run_build_wiki(config)
        console.print("[bold yellow]=== 3단계: RAG 벡터 인덱싱 구축 ===[/bold yellow]")
        run_index(config)
        console.print("[bold green]=== 파이프라인 완료! 'python main.py ticket' 명령어로 티켓을 자동 발행할 수 있습니다. ===[/bold green]")

if __name__ == "__main__":
    main()
