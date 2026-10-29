# AI Seed Questions: Expansion Guide

Working reference for the `ai` category: [`ai_questions.json`](ai_questions.json),
100 questions added 2026-10-29.

Read [`system_design_coverage.md`](system_design_coverage.md) first. It holds the
rules every seed file follows: the `concept` and `format` fields, the dedup rule,
the question template, and the option-length limits. This file only covers what
is different about `ai`.

- **Inventory** is generated, never hand-maintained. `python seeds/generate_coverage.py`
  validates every seed file and rewrites [`coverage_report.md`](coverage_report.md),
  whose `ai` section lists each concept with its format and difficulty.
- **Loading** needs the category row first. Apply
  [`0007_add_ai_category.up.sql`](../migrations/0007_add_ai_category.up.sql), then
  send the file to `POST /api/v1/questions/bulk`, which rejects unknown category slugs.

## Scope

`ai` is applied LLM engineering: what a software engineer needs to build on
language models. Questions come from these areas:

- **LLM fundamentals**, where they change app behavior: tokens, context windows,
  sampling, hallucination, reasoning tokens, the KV cache
- **Prompting and structured output**
- **Embeddings and vector search**
- **RAG**
- **MCP**
- **Agents and tool use**
- **Evals and observability**
- **Safety and security**
- **Production**: cost, latency, caching, serving
- **Fine-tuning and adaptation**, at the level of choosing between them and RAG

Out of scope: classic ML (train/test splits, gradient descent, classifier
metrics) and model internals that do not change how an app is built. If those
are ever wanted, give them their own category rather than widening this one.

## Formats

Recall and situational questions share one file. Unlike the system-design
situational set, most `ai` situational questions test a concept that has no
recall question yet. A few revisit a recall concept (same `concept` slug,
different `format`), which the dedup rule allows. The rest show up under
"Situational-only concepts" at the end of the coverage report: treat that list
as the backlog for new recall questions.

## Difficulty, calibrated for AI

The seniority mapping in the shared guide applies. In this category:

- `beginner`: what a token, an embedding, RAG, MCP, or prompt injection is; who
  executes a tool call.
- `intermediate`: trade-offs and mechanics, such as hybrid search, HNSW vs
  IVFFlat, who controls each MCP primitive, JSON mode vs Structured Outputs.
- `advanced`: failure modes and internals, such as filtered ANN queries returning
  too few rows, MCP token passthrough, nondeterminism at temperature 0, data
  exfiltration through agents.

## Named products: verify before writing

Questions may name products and specs, and those facts drift fast. Check every
product claim against a primary source when you write it, not from memory. The
2026-10-29 batch was checked against the sources below. Re-check the listed
questions when a source ships a breaking change, and at least every six months.

| Source checked on 2026-10-29 | Questions that depend on it |
|---|---|
| Claude API documentation | Chatbot forgets the user's name; Returning a tool result to Claude; Returning parallel tool results; Agent fails after a tool crashes; Prompt cache never hits; What prompt caching reuses; When to use a batch API; Billing for reasoning tokens; Usage jumps after a model migration; Agent with 300 tools picks badly |
| Anthropic prompting guide and engineering posts | Structuring prompts with XML tags; Contract Q&A misses clauses; Agentic workflow patterns; Translation drafts miss nuance; Cost of multi-agent systems; Contextual retrieval |
| MCP specification, revision 2026-07-28 | What MCP is; MCP roles; MCP server primitives; MCP transports; MCP vs function calling; Who controls each MCP primitive; MCP server breaks after adding logs; Two MCP servers both expose search; MCP elicitation; MCP tool errors vs protocol errors; MCP tool annotations; MCP authorization by transport; MCP server forwards the client's token; Local MCP server reachable from a web page; Hidden instructions in a tool description |
| pgvector README | pgvector HNSW vs IVFFlat; Filtered vector query returns 3 rows; pgvector query ignores the index |
| OpenAI API documentation | JSON mode vs Structured Outputs; Normalized embedding vectors; Shortening embeddings; When to use a batch API; What prompt caching reuses; Billing for reasoning tokens |
| OWASP Top 10 for LLM Applications 2025 | Prompt injection; API key in the system prompt; Inbox assistant can delete mail |

Not re-fetched, because they describe stable library behavior or published
papers: LangChain's text splitter, LangGraph checkpointers, LangSmith and
Langfuse, Ragas, Cohere Rerank, GraphRAG, vLLM, "Lost in the Middle" (Liu et al.,
2023), and self-consistency (Wang et al., 2022).

### Facts left out on purpose

These were true until recently, so they are easy to write from memory and are
now wrong. Do not reintroduce them without re-checking:

- **Claude assistant prefill** returns a 400 on current Claude models; structured
  outputs replace it.
- **Forced tool use** (`tool_choice` of `any` or `tool`) returns a 400 on the
  newest Claude models.
- **Extended thinking with `budget_tokens`** has been replaced by adaptive
  thinking plus an effort setting on current Claude models.
- **`temperature`, `top_p`, and `top_k`** are rejected by the newest Claude
  models, so sampling questions stay generic rather than Claude-specific.
- **MCP sampling, roots, and logging** are deprecated as of spec revision
  2026-07-28.
- **The MCP `initialize` handshake, protocol-level sessions, and the
  `Mcp-Session-Id` header** are gone from revision 2026-07-28; every request is
  self-contained.
- **MCP Dynamic Client Registration** is deprecated in favor of Client ID
  Metadata Documents, and the HTTP+SSE transport has been deprecated since
  2025-03-26.
- **Exact prompt-cache prices** vary by model (Anthropic cache reads range from
  0.025x to 0.1x the base input price), so questions describe caching
  qualitatively.

## Authoring notes specific to `ai`

- The quiz renders question text as plain text, so write identifiers such as
  tool_result or stop_reason as plain words, not in backticks.
- The best distractors are real neighboring concepts: top-k sampling vs
  retrieval top-k, elicitation vs sampling in MCP, the other OWASP category
  names, compaction vs clearing old tool results.
- A distractor may name a deprecated feature (MCP sampling, for example), but
  never describe a deprecated feature as current in a correct answer or an
  explanation.

## Gap list: safe expansion targets

Concepts with no coverage yet. Pull from here first:

- Multimodal input: image tokens and what they cost
- Voice and realtime agents
- Guardrail classifiers (Llama Guard, moderation endpoints)
- Agent-to-agent protocols (A2A) and how they differ from MCP
- Agent memory: long-term stores and what to write back to them
- Semantic caching and its similarity-threshold risk
- Model routing and cascades vs one stronger model at lower effort
- Synthetic data for evals, and red-teaming
- Late-interaction retrieval (ColBERT) and multi-vector indexes
- Continuous batching and mixture-of-experts serving
- Data retention and zero-data-retention agreements
- MCP extensions (Tasks, MCP Apps) once they stabilize
- Recall counterparts for the situational-only concepts in the coverage report
