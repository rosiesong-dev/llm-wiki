# 📚 llm-wiki: Collect & Analyze Confluence/Slack Meetings and Create Jira Tickets

> **A Python-based knowledge system that unifies a team's scattered work knowledge and issues, and automates everything up to ticket creation with Gemini / Gemma / Claude knowledge augmentation (RAG).**

---

## 📌 1. Overview

**llm-wiki** applies the **[LLM-Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)** proposed by Andrej Karpathy to an in-house environment.

> *"The knowledge is compiled once and then kept current, not re-derived on every query."*

It collects **Confluence meeting notes** and **Slack conversations** as raw sources, and an LLM (Gemini / Gemma / Claude) reads them to write and keep refining a **Markdown wiki whose pages link to each other**. The accumulated wiki answers questions (Q&A) and even issues **Jira tickets**.

| Classic RAG | llm-wiki (LLM-Wiki) |
|---|---|
| Searches raw chunks on every question | **Organizes sources up front** when they arrive (summaries · entities · concepts · synthesis) |
| Knowledge does not accumulate | Good answers are **saved back as wiki pages** |
| Vectors are not human-readable | Plain Markdown people can read and edit (Obsidian-compatible `[[links]]`) |

---

## 🏗️ 2. LLM-Wiki Architecture

### 2.1 Three Layers

```
┌──────────────────────────────────────────────────────────────────┐
│ ③ Schema   AGENTS.md          wiki structure · writing rules · flow │  ← refined by humans + LLM
├──────────────────────────────────────────────────────────────────┤
│ ② Wiki     storage/wiki/      wiki the LLM writes and keeps fixing  │  ← LLM writes, humans review
│            index.md · log.md · overview · synthesis ·             │
│            entities · concepts · comparisons · summaries          │
├──────────────────────────────────────────────────────────────────┤
│ ① Raw      storage/raw/confluence/{space}/  raw/slack/{channel}/  │  ← collected only, never edited
└──────────────────────────────────────────────────────────────────┘
```

| Layer | Location | Written by | Rule |
|---|---|---|---|
| ① **Raw sources** | `storage/raw/` | Collectors (`fetch-page`, `fetch-slack`) | **Immutable**, so the wiki can always be rebuilt from sources |
| ② **Wiki** | `storage/wiki/` | **LLM** (+ human review) | Six page types below, connected with `[[links]]` |
| ③ **Schema** | [`AGENTS.md`](AGENTS.md) | Humans + LLM | Wiki rules read by every agent (Codex, Cursor, Gemini CLI, …). Claude Code loads it via `@AGENTS.md` in `CLAUDE.md` |

### 2.2 Page Types (Frontmatter `type`)

| type | Folder | Contents | Example (in `storage/wiki/`) |
|---|---|---|---|
| `overview` | `overview/` | **Entry page** for the whole picture | 프로젝트 개요 (Project overview) |
| `synthesis` | `synthesis/` | **Status & conclusions** across sources (decisions · to-dos · open issues) | 프로젝트 진행 현황 (Project status) |
| `entity` | `entities/` | One page per **person · team · system · tool** | 홍길동, 김철수, Kafka |
| `concept` | `concepts/` | **Topics · terms · ideas** | 메시지 큐 (Message queue) |
| `comparison` | `comparisons/` | **Tables comparing** two or more things | Kafka vs RabbitMQ |
| `summary` | `summaries/{meetings,slack,issues,knowledge}/` | **One summary per source** | 2026-10-26 결제 큐 아키텍처 회의록, Slack #dev 2026-10-27 |

### 2.3 Pages Link to Each Other

```
            [[프로젝트 개요]] (overview)
                 │                 │
       [[프로젝트 진행 현황]]     [[홍길동]] (entity) ──── [[메시지 큐]] (concept)
          (synthesis)              │  ## 출처별 내용          │
                 │                 │  ### [[2026-10-26 … 회의록]]
                 ▼                 ▼                          ▼
     [[2026-10-26 … 회의록]] (summary) ── ## 관련 페이지 ── [[Kafka vs RabbitMQ]] (comparison)
```

| Direction | Rule |
|---|---|
| Summary → entity/concept | Link every mentioned item under `## 관련 페이지` (Related pages) at the end of the summary |
| Entity/concept → summary | Under `## 출처별 내용` (By source), add `### [[summary title]]` + the facts learned from that source (traceability) |
| Overview/synthesis → all | `[[links]]` inside body tables and sentences |
| Aliases | Frontmatter `aliases` (Slack ID, English name, …) also resolve to the same page |

### 2.4 Two Special Files

| File | Nature | Contents | Purpose |
|---|---|---|---|
| **`storage/wiki/index.md`** | **Content-oriented** table of contents | `[[link]]` + one-line summary for every page, **grouped by type** | **The LLM reads it first for every question** (`ask` sends it automatically). Regenerated whenever a page is saved |
| **`storage/wiki/log.md`** | **Time-oriented** record | When something was ingested, queried, linted or updated | Track history and recent changes. **Append-only** |

`log.md` format and viewing recent entries:
```markdown
## [2026-10-26 11:00] ingest | 2026-10-26 결제 큐 아키텍처 회의록
- 원본: Confluence DEV/2001
- 새 페이지: [[홍길동]], [[김철수]], [[Kafka]], [[메시지 큐]]
## [2026-10-28 09:30] query | 결제 큐는 무엇으로 결정됐어?
## [2026-10-28 09:45] lint | 구조 점검 - 문제 0건
```
```powershell
Select-String -Path storage\wiki\log.md -Pattern '^## \[' | Select-Object -Last 5   # last 5 operations
```

### 2.5 Three Operations

| Operation | Command | What it does |
|---|---|---|
| **Ingest** | `fetch-page <ID>`, `build-wiki`, `fetch-slack` → `build-slack-wiki` | ① Collect source → ② write a **summary page** → ③ **create/update entity & concept pages + bidirectional links** → ④ refresh `index.md` → ⑤ append to `log.md` |
| **Query** | `ask "question"` (`--save comparison`, …) | ① **Read `index.md` first** → ② RAG search for related pages → ③ answer with `[[sources]]` → ④ (optional) **save the answer as a wiki page** → ⑤ append to `log.md` |
| **Lint** | `lint` | Broken links, orphan pages (no inbound links), missing one-line summaries, unsourced entities/concepts → append to `log.md` |

```
          ┌────────────── Ingest ──────────────┐
 source ─▶│ summary · entities/concepts · links │──▶ wiki ◀──┐
          └─────────────────────────────────────┘      │      │ save good answers (--save)
 question ─▶ Query (index.md → related pages) ──▶ answer ┘      │
 periodic ─▶ Lint ──▶ issue list ──▶ fix (update) ──────────────┘
```

> [!WARNING]
> For entity/concept extraction, the LLM only picks names and facts; the code creates pages and links. **Names that do not actually appear in the source are discarded** (guards against small-model hallucination).
> Summaries from small models such as gemma3:4b still often contain factual errors, so review saved summaries against the source and record fixes in `log.md` as `update`. Tables (owner · due date) are copied verbatim from the source.

### 2.6 System Flow

```
[Confluence meeting notes] ─┐
                            ├─(collect)─▶ storage/raw/ (immutable) ─(LLM ingest)─▶ storage/wiki/ ─(embed)─▶ storage/index/
[Slack #dev] ───────────────┘                                                       │ index.md · log.md
                                                                                    ▼
                      [Issue Jira ticket] ◀─(ticket draft)─ [Query: index.md + RAG search + LLM answer]
```

---

## 📂 3. Project Structure

```text
llm-wiki/
├── .venv/                        # Python virtual environment
├── requirements.txt              # Dependencies (requests, pydantic, numpy, rich, keyring, mcp, …)
├── .env.example                  # API key & environment variable template
├── .env                          # Local settings (git-ignored)
├── main.py                       # CLI entry-point wrapper
├── README.md                     # This guide
├── AGENTS.md                     # ③ Schema: wiki rules (shared by all agents; write rules only here)
├── CLAUDE.md                     #   Claude Code bridge file (a single @AGENTS.md line)
│
├── storage/                      # [Data store] raw data fully separated from processed documents
│   ├── raw/                      # Collected sources (kept immutable)
│   │   ├── confluence/           # Confluence raw JSON, one folder per space key
│   │   │   ├── DEV/              #   Example space (confluence_page_{id}.json)
│   │   │   └── _sample/          #   Samples for --mock simulation (not a real space)
│   │   └── slack/                # Slack raw JSON, one folder per channel name
│   │       └── dev/              #   One file per day (KST) YYYY-MM-DD.json (thread replies included)
│   ├── wiki/                     # ② Wiki written and maintained by the LLM (folder per page type, linked with [[links]])
│   │   ├── index.md              #   Table of contents: every page link + one-line summary (read first on questions, auto-generated)
│   │   ├── log.md                #   Operation log: ingest / query / lint / update (append-only)
│   │   ├── overview/             #   Overview – entry page
│   │   ├── synthesis/            #   Synthesis – status & conclusions (decisions · to-dos · open issues)
│   │   ├── entities/             #   Entities – people · teams · systems · tools
│   │   ├── concepts/             #   Concepts – topics · terms · ideas
│   │   ├── comparisons/          #   Comparisons – A vs B tables
│   │   └── summaries/            #   Summaries – one page per source
│   │       ├── meetings/         #     Confluence meeting notes
│   │       ├── slack/            #     One Slack day (summary + original transcript) "Slack #{channel} YYYY-MM-DD.md"
│   │       ├── issues/           #     Incident / issue analyses
│   │       └── knowledge/        #     Other documents
│   ├── index/                    # RAG vector index cache (vector_index.json, fully rebuilt by `index`)
│   └── tickets/                  # Records of issued tickets, one folder per Jira project key
│       ├── index.md              #   List of all issued tickets (newest first, auto-generated)
│       ├── DEV/                  #   Example project ({KEY}.md, e.g. DEV-2.md)
│       └── LOCAL/                #   Local tickets created with --provider local (TICKET-*.md)
│
└── llm_wiki/                     # [Python package source]
    ├── __init__.py
    ├── config.py                 # Pydantic settings; ensures directories exist
    ├── main.py                   # CLI command implementations (Rich terminal UI)
    ├── jira_mcp.py               # MCP server for Jira Server (create/search issues from Claude Code)
    │
    ├── slack/                    # [Module] Slack integration
    │   └── client.py             # Slack Web API collector (channel history & threads, saved per day)
    │
    ├── confluence/               # [Module] Confluence integration
    │   ├── models.py             # ConfluencePage model & HTML → text conversion (to_plain_text)
    │   ├── client.py             # Confluence REST API collector & mock generator
    │   └── credential.py         # Read/store credentials (Windows Credential Manager / keyring)
    │
    ├── llm/                      # [Module] LLM generation
    │   ├── client.py             # BaseLLMClient + Gemini / Gemma (Ollama) / Claude clients (generate, embed, mock)
    │   ├── gemini.py             # (legacy, unused)
    │   └── prompts.py            # Prompt templates for wiki summaries, Q&A and ticket drafts
    │
    ├── wiki/                     # [Module] Markdown wiki engine
    │   ├── document.py           # Page types (PAGE_TYPES), frontmatter model, [[link]] extraction
    │   ├── manager.py            # Save into per-type folders, add links, generate index.md
    │   ├── linker.py             # Post-ingest: extract entities/concepts → create/update pages + bidirectional links
    │   ├── log.py                # Append to log.md (ingest / query / lint / update / index)
    │   └── lint.py               # Checks: broken links, orphans, missing summaries, unsourced pages
    │
    ├── rag/                      # [Module] RAG & semantic search
    │   ├── chunker.py            # Chunk Markdown by H2/H3 sections and paragraphs
    │   ├── embedder.py           # Vectorize text with Gemini / Gemma embedding models
    │   └── store.py              # Fast NumPy cosine-similarity vector store
    │
    └── ticket/                   # [Module] Ticket drafting & publishing (pluggable)
        ├── base.py               # TicketProvider abstract base class (ABC) & TicketDraft model
        ├── drafter.py            # Agent that combines RAG results into a high-quality ticket draft
        ├── record.py             # Record issued tickets under tickets/{project key}/ and refresh index.md
        └── providers/
            ├── local.py          # Local Markdown ticket provider (built in)
            └── jira.py           # Atlassian Jira Cloud REST API provider (extension)
```

### Storage Rules
| Data | Location | Folder key |
|---|---|---|
| Confluence source | `storage/raw/confluence/{space key}/confluence_page_{id}.json` | Space key of the page (`space.key` in the API response) |
| Slack source | `storage/raw/slack/{channel name}/YYYY-MM-DD.json` | Channel name, message date (KST). Thread replies go in the parent's `_replies` |
| Wiki page | `storage/wiki/{overview,synthesis,entities,concepts,comparisons}/{title}.md` | Page type (frontmatter `type`) |
| Source summary | `storage/wiki/summaries/{meetings,slack,issues,knowledge}/{title}.md` | `type: summary` + source kind (`category`) |
| Issued ticket | `storage/tickets/{project key}/{issue key}.md` | Project part of the Jira key (e.g. `DEV-2` → `DEV/`) |

> [!NOTE]
> Everything under `storage/` in this repository is **fictional example data** showing the structure. Real collected data is git-ignored.

---

## ⚡ 4. Setup & Running

### 1) Activate the virtual environment (PowerShell)
Move to the project folder (`llm-wiki`) and activate the virtual environment:

```powershell
cd C:\path\to\llm-wiki

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

> [!TIP]
> If PowerShell blocks script execution (`ExecutionPolicy`), run this once:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 2) Environment variables
Copy `.env.example` to `.env` and fill in your LLM API key and Confluence settings:
```powershell
copy .env.example .env
```

### 3) LLM settings (default: Gemini)
| Item | `.env` | Notes |
|---|---|---|
| Backend | `LLM_BACKEND=gemini` | `gemma` for local Ollama (slow on CPU, more summary/answer errors), `claude` for Claude |
| Generation model | `GEMINI_MODEL=gemini-2.5-flash` | |
| Embedding model | `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` | Rebuild the index with `python main.py index` after changing it |
| API key | (not stored in `.env`) | `python main.py set-gemini-key` → saved to the OS credential store (target: `gemini`) |

```powershell
python main.py set-gemini-key   # once (enter the key issued by AI Studio)
python main.py index            # rebuild the index because the embedding model changed
```
> [!NOTE]
> `ask` answers **short and fast**: 1–3 sentence conclusion + `출처: [[page]]` (sources), max 400 output tokens, Gemini thinking disabled.
> With Gemini, wiki content (internal documents) is sent to the Google API.

**Using Claude** (`LLM_BACKEND=claude`)
| Item | `.env` | Notes |
|---|---|---|
| Generation model | `CLAUDE_MODEL=claude-opus-5-5` | `ask` uses effort `low`, wiki generation uses `medium` |
| Embedding | `CLAUDE_EMBEDDING_BACKEND=gemma` | Claude has no embedding API, so `gemma` (Ollama) or `gemini` handles it. Re-run `python main.py index` after changing |
| API key | (not stored in `.env`) | `python main.py set-claude-key` → saved to the OS credential store (target: `claude`). The `ANTHROPIC_API_KEY` env var also works |

> With Claude, wiki content (internal documents) is sent to the Anthropic API.

---

## 🖥️ 5. CLI Reference

Run `python main.py <command>` with the virtual environment active.

### 1) Full pipeline (collect ➔ wiki ➔ index)
```powershell
python main.py pipeline --mock
```

### 2) Collect Confluence sources
```powershell
# One page (e.g. meeting notes) → storage/raw/confluence/{space key}/ → wiki → index
python main.py fetch-page 2001

# Whole space (CONFLUENCE_SPACE_KEY in .env)
python main.py sync

# Mock simulation (saved to storage/raw/confluence/_sample/)
python main.py sync --mock
```

### 3) Collect Slack channel messages
```powershell
# Once: store the bot token (xoxb-...) in the OS credential store (target: slack)
python main.py set-slack-token

# Collect the whole SLACK_CHANNEL_ID channel → storage/raw/slack/{channel name}/YYYY-MM-DD.json
python main.py fetch-slack

# Only the last N days / another channel
python main.py fetch-slack --days 3
python main.py fetch-slack --channel C0XXXXXXXXX

# Collected conversations → daily summaries in storage/wiki/summaries/slack/ + entity/concept links → refresh RAG index
python main.py build-slack-wiki                       # only newly collected days (skips existing pages)
python main.py build-slack-wiki --date 2026-10-27     # one day
python main.py build-slack-wiki --force               # regenerate everything
```
> A Slack wiki page has an **LLM summary** (summary · key discussions · shared files · decisions · requests & to-dos) and the **original transcript** (messages and threads verbatim), so anything the LLM missed is still searchable.
> [!NOTE]
> Bot scopes required: `channels:history`, `channels:read` (`groups:*` for private channels). Add `users:read` to get author names; otherwise user IDs are stored.

### 4) Confluence sources → wiki (Ingest)
```powershell
# All of storage/raw/confluence/ → summary pages + entity/concept links + refresh index.md & log.md
python main.py build-wiki
```

### 5) Build the RAG vector index
```powershell
python main.py index
```

### 6) Semantic search
```powershell
python main.py search "결제 504 타임아웃 장애" --top-k 3
```

### 7) Q&A over the wiki (Query)
```powershell
python main.py ask "Kafka 토픽 설계는 누가 맡았어?"          # reads index.md first, then answers from related pages
python main.py ask "PoC 기한은 언제야?" -k 6                  # retrieve more sections
python main.py ask "Kafka와 RabbitMQ 차이는?" --save comparison --title "Kafka vs RabbitMQ"   # save the answer as a wiki page
python main.py chat   # interactive mode
```
> Every question is logged in `log.md` as `query`; with `--save` (synthesis / comparison / concept / overview) the answer is saved as a wiki page of that type.
>
> Search is **hybrid**: 50% embedding cosine similarity + 50% Korean 2-character keyword match (IDF-weighted). Slack transcript chunks are scaled by 0.85 so curated summary/entity pages rank first (`KEYWORD_WEIGHT`, `TRANSCRIPT_PENALTY` in `llm_wiki/rag/store.py`).
> The default number of retrieved sections is 8. Small models like gemma3:4b sometimes misread tables (owner · due date); check the source page when you need an exact answer.

### 8) Lint the wiki
```powershell
python main.py lint    # broken links, orphan pages, missing one-line summaries, unsourced entities/concepts
```
> Lint only finds structural problems. Whether the content is true is judged by a human against the sources (`storage/raw/`).

### 9) Issue new tickets with RAG knowledge
```powershell
# Local Markdown ticket (created in storage/tickets/LOCAL/)
python main.py ticket "결제 요청 몰릴 때 504 에러 발생하는 이슈 조치 티켓 만들어줘" --provider local

# Jira ticket (Jira Cloud API v3; for Jira Server use the MCP server below)
python main.py ticket "결제 큐 비동기 전환 이슈" --provider jira
```

> [!TIP]
> The global option `--backend gemini|gemma|claude` overrides `LLM_BACKEND` in `.env`.

---

## 🎫 Jira MCP Server (Claude Code integration)

Older Jira Server versions do not support API tokens (PAT), so this project uses an MCP server (`llm_wiki/jira_mcp.py`) that authenticates with Basic auth using the `wiki.example.com` account stored in the OS credential store.

```powershell
# Register (once, user scope)
claude mcp add-json llm-wiki-jira '{\"type\":\"stdio\",\"command\":\"C:\\path\\to\\llm-wiki\\.venv\\Scripts\\python.exe\",\"args\":[\"-m\",\"llm_wiki.jira_mcp\"],\"env\":{\"PYTHONPATH\":\"C:\\path\\to\\llm-wiki\",\"PYTHONIOENCODING\":\"utf-8\"}}' --scope user
```

| Tool | Function |
|---|---|
| `jira_create_issue` | Create an issue + record it in `storage/tickets/{project key}/{KEY}.md` (set the evidence document in `source`) |
| `jira_record_issue` | Add or refresh an already-issued issue in the local records |
| `jira_search` / `jira_get_issue` | JQL search / details and comments |
| `jira_add_comment` | Add a comment |
| `jira_list_projects` / `jira_get_issue_types` | List projects / issue types and required fields |

> [!NOTE]
> Issue bodies use Jira wiki markup (`h2.`, `*`, `#`, `{code}`), not Markdown. Local records are converted to Markdown.

---

## 🔌 6. Ticket System Extension Interface (`TicketProvider` ABC)

Designed with Python `abc.ABC` so it can be extended to any issue tracker — Jira, GitHub Issues, ServiceNow, and more.

```python
from abc import ABC, abstractmethod
from llm_wiki.ticket.base import TicketDraft, TicketResult

class TicketProvider(ABC):
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier"""
        pass

    @abstractmethod
    def issue_ticket(self, draft: TicketDraft) -> TicketResult:
        """Publish a ticket draft to the target system via its API"""
        pass
```
To add a new provider, subclass it in `llm_wiki/ticket/providers/` and it plugs in right away.

### 🔄 Workflow Automation
Meeting content from Confluence and Slack is periodically collected and analyzed, an LLM extracts Action Items, and Jira tickets are created automatically.  
**crontab-based scheduling** is planned next to automate the entire workflow end to end.
