# Research — Minimal, Observable Tool-Calling Agent-Harness Patterns for an OpenRouter Assistant

> For Taxathon (FastAPI + OpenRouter, Python 3.12/uv). The build is judged first and heaviest on
> **harness quality**: are the four pillars (chat loop, tools, guardrails, observation) *real and
> ENFORCED + VISIBLE*, or cosmetic? This research compares (a) a hand-rolled minimal agent loop,
> (b) a small agent framework (Pydantic AI / OpenAI Agents SDK / LangGraph), and (c) a hybrid —
> specifically through the lens of *legibility to a judge who reads the code AND runs the system*.

- **Authored:** 2026-06-24
- **Researcher role** (architecture phase)
- **Method:** Web search + primary-source fetch (OpenRouter docs, Pydantic AI docs, OpenAI Agents
  SDK docs). Confidence is rated per claim; unverified items are flagged with "would confirm via X".

---

## Question

What is the best minimal, observable tool-calling agent-harness pattern for an OpenRouter-backed
FastAPI assistant, when the top judging criterion is whether the four pillars (chat loop, tools,
guardrails, observation) are *enforced and visible in code AND at runtime*, not cosmetic — and the
budget is hackathon-short?

## Short Answer

**Recommend a hand-rolled minimal agent loop (option a), with one deliberate borrow from frameworks:
emit OpenTelemetry-shaped structured trace events per turn.** For *this* brief, a hand-rolled loop
is the most legible: every pillar is a few dozen lines the judge can read top-to-bottom in one file,
with no framework abstraction to "trust." OpenRouter is a drop-in OpenAI-compatible Chat Completions
endpoint, so the loop is small and well-trodden. **Confidence: high** that hand-rolled maximizes
*legibility*; **medium** that it's the outright fastest to a working demo (Pydantic AI is close and
gives typed tools/guardrails for free).

The one framework I would *not* reach for here is the **OpenAI Agents SDK** — not because it's bad,
but because two of its defaults fight the OpenRouter + "visible, self-contained" requirements (it
defaults to OpenAI's Responses API, which must be flipped to Chat Completions for OpenRouter, and its
tracing defaults to exporting to *OpenAI's* hosted dashboard, which is the opposite of a
self-contained, judge-inspectable trail). Both are fixable in a couple of lines, but they're
friction and a "why is this calling OpenAI?" smell in a project that's explicitly OpenRouter-only.

If you prefer a framework's typed ergonomics over rolling your own dispatch, **Pydantic AI** is the
best fit: native `OpenRouterProvider`, code-enforced guardrails via `@output_validator` + `ModelRetry`
and Pydantic-validated tool/output schemas, and OpenTelemetry-native observation that runs to a local
collector without any vendor backend.

---

## Sources

Primary (fetched and read):
- OpenRouter — Tool & Function Calling: https://openrouter.ai/docs/guides/features/tool-calling
- OpenRouter — Streaming: https://openrouter.ai/docs/api/reference/streaming
- OpenRouter — Quickstart: https://openrouter.ai/docs/quickstart
- OpenRouter — OpenAI SDK integration: https://openrouter.ai/docs/guides/community/openai-sdk
- OpenAI Agents SDK — Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- OpenAI Agents SDK — Tracing: https://openai.github.io/openai-agents-python/tracing/
- OpenAI Agents SDK — Configuration: https://openai.github.io/openai-agents-python/config/
- Pydantic AI — OpenRouter model/provider: https://pydantic.dev/docs/ai/models/openrouter/
- Pydantic AI — Output (validators, ModelRetry): https://pydantic.dev/docs/ai/core-concepts/output/
- Pydantic AI — Logfire/OTel instrumentation: https://pydantic.dev/docs/ai/integrations/logfire/

Secondary / community (used for cross-checking, not as sole basis for a claim):
- LangGraph + OpenRouter walkthrough: https://wcsee.com/python-ai-agent-with-langgraph-and-openrouter/
- LangChain ChatOpenRouter integration: https://docs.langchain.com/oss/python/integrations/chat/openrouter
- pydantic-ai-guardrails (community): https://github.com/jagreehal/pydantic-ai-guardrails
- FastAPI + LangGraph production template: https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template
- OpenAI Agents SDK + OpenRouter issue #279: https://github.com/openai/openai-agents-python/issues/279

---

## Findings

### 0. The shared substrate: OpenRouter is plain OpenAI-compatible Chat Completions

**Confidence: high (primary source).** OpenRouter exposes the standard OpenAI Chat Completions API
at `https://openrouter.ai/api/v1`. Any client that speaks that API works by swapping `base_url` and
the API key. Tool calling uses the **identical OpenAI-standard shape**: a `tools` array of
`{"type":"function","function":{name,description,parameters(JSON Schema)}}`, the model returns
`finish_reason: "tool_calls"` with a `tool_calls` array, you execute locally and append
`role:"tool"` messages, and loop until `finish_reason` is no longer `tool_calls`. Streaming is the
standard SSE `stream:true` flow (with OpenRouter occasionally injecting `: OPENROUTER PROCESSING`
keep-alive comment lines you must skip).

Two real caveats from OpenRouter's own docs:
- **Not every model supports tools.** Filter to tool-capable models via
  `openrouter.ai/models?supported_parameters=tools`. **(high)**
- **Tool-call reliability varies by model/provider.** OpenRouter publishes a per-provider "Tool Call
  Error Rate." Pick a known-good model (e.g. a current Claude or GPT-class model) rather than a cheap
  fringe one. **(high; specific model choice is a separate decision — confirm by testing 1–2 candidates
  end-to-end with your actual tool schema.)**

Implication: **the agent loop is small and standard regardless of approach.** The frameworks don't
buy you OpenRouter compatibility (it's free); they buy you typing, dispatch plumbing, and
guardrail/trace scaffolding — which is exactly what you must weigh against *legibility*.

### 1. Mapping the four pillars to "enforced + visible" (the rubric that matters)

The brief's distinction is "it's in the prompt" (weak) vs "it's enforced and visible" (strong). For
each pillar, "enforced" = a code/schema mechanism that *cannot be bypassed by the model*, and
"visible" = a judge can see it in the source *and* observe it firing at runtime. Concretely:

| Pillar | "Enforced" means (code/schema) | "Visible" means (runtime) |
|---|---|---|
| Chat loop | A typed state object carried across turns server-side; turn count is code, not vibes | Multi-turn works; the ≤5-question budget is a counter the judge can watch decrement |
| Tools | Real function dispatch from a JSON-Schema tool registry; tax math executes in code | A tool call appears in the trace and a real filled PDF comes out |
| Guardrails | Schema validation of W-2/inputs; **tax math computed code-side and validated before PDF fill**; off-task refusal as a checked condition; SSN kept out of prompts/logs | A refusal visibly fires on an out-of-bounds request; logs show SSN redacted; a fabricated-number check rejects bad input |
| Observation | A structured per-turn trace record (decision, tool called, args [redacted], result, guardrail verdict) | A judge can read the trace in logs (and ideally a `/trace` view) and reconstruct what happened |

**The single most important guardrail decision for this project** (PRD §9, NFR Open Questions):
**tax math is computed deterministically in code, never by the LLM, and validated before it reaches
the PDF.** This is itself the strongest "enforced not cosmetic" story you can tell a judge, and it is
*approach-independent* — it lives in your tool implementation no matter which of (a)/(b)/(c) you pick.
The agent's job is to *gather inputs and call the compute tool*, not to do arithmetic. **(high — this
is the defensible architecture per the PRD's own accuracy stance.)**

### 2. Option (a): Hand-rolled minimal agent loop

**Shape.** ~1 file: a typed `AgentState` (pydantic `BaseModel` or dataclass) holding messages,
extracted W-2 fields, filing status, question count, and a trace list; a `TOOLS` registry mapping
name → (JSON Schema, python callable); a `while` loop that calls OpenRouter chat-completions, checks
`finish_reason`, dispatches `tool_calls` through the registry, appends results, and re-calls until the
model emits a final message. Guardrails are explicit `if`/validation gates around dispatch and around
the final answer. Observation is a function that appends a structured dict per turn.

**Pillar legibility (the decisive factor here):**
- **Chat loop — maximal.** The loop *is* the chat loop, in plain Python the judge reads in 60 seconds.
  Turn/question counting is an integer you increment — the ≤5-question budget is literally `if
  state.questions_asked >= 5`. **(high)**
- **Tools — maximal.** Dispatch is an explicit `registry[name](**args)`. The judge sees exactly which
  python function runs and that the 1040 computation/PDF-fill is real code. No "where does the
  framework actually call my tool?" indirection. **(high)**
- **Guardrails — maximal and unmissable.** Every guardrail is a visible code branch: validate W-2
  fields against a schema before use; reject/clamp out-of-range numbers; a cheap off-task check
  (keyword/classifier or a structured "is_on_task" check) that returns a canned refusal; redact SSN
  before logging and before any prompt. Because there's no framework, there is *zero* ambiguity about
  whether a guardrail is "in the prompt" vs enforced — it's an `if` that raises/refuses. This is the
  cleanest possible answer to the rubric's exact question. **(high)**
- **Observation — maximal, but you build it.** You write the per-turn trace record yourself, so you
  control its shape and can surface it (logs + an optional `/trace` endpoint or a trail panel in the
  minimal UI — a PRD stretch goal). Nothing is hidden in a vendor dashboard. **(high)**

**Costs.** You write streaming-SSE handling, the tool-dispatch loop, retry-on-transient-error, and
the trace format yourself. These are all standard and small, but they're *your* bugs. The error-prone
spots: correctly assembling streamed `tool_calls` deltas (arguments arrive as concatenated string
fragments), and looping termination. **(medium — well-documented, but the streamed-tool-call assembly
is the classic foot-gun; budget time to test it.)**

**Verdict:** Best *legibility per pillar*, lowest *conceptual* surface for a judge, moderate code you
own. For a build judged primarily on "can a judge see each pillar is real," this is the strongest fit.

### 3. Option (b): A small framework

#### 3a. Pydantic AI — the best framework fit for this brief

**OpenRouter integration — first-class. (high, primary source.)** Pydantic AI ships a native
`OpenRouterProvider` and an `openrouter:` model prefix:
```python
from pydantic_ai import Agent
agent = Agent('openrouter:anthropic/claude-sonnet-4.6')   # reads OPENROUTER_API_KEY
# or explicit:
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
model = OpenRouterModel('anthropic/claude-sonnet-4.6',
                        provider=OpenRouterProvider(api_key='...'))
```
No base_url fiddling, no Responses-vs-Chat-Completions issue. **(high)**

**Pillars:**
- **Tools — strong & typed.** `@agent.tool` functions; parameters are Python-typed and Pydantic
  validates them — the JSON Schema is *derived from your types*, so the schema-level guardrail is
  automatic and visible in the function signature. Tools receive `RunContext[Deps]` for typed
  dependency injection (your `AgentState`, W-2 data, etc.). **(high)**
- **Guardrails — code-enforced, not prompt. (high, primary source.)** `output_type` enforces a
  Pydantic-validated structured result. `@agent.output_validator` lets you raise `ModelRetry(...)`
  to *reject* a semantically-invalid output and force a retry (consumes a configurable retry budget,
  default 1). Tools can raise `ModelRetry` too. This is a genuine enforced guardrail layer in code.
  Community libs (`pydantic-ai-guardrails`/`-shields`) add `InputGuard`/`OutputGuard` with OTel spans
  if you want a packaged version — but you do *not* need them; the built-ins are enough. **(high)**
  - *Caveat (medium):* there is a known issue where raising `ModelRetry` inside an output validator
    *while streaming* can crash (GitHub #3393). If you stream final output AND use output-validator
    retries, test that path or validate before streaming the final turn. **Would confirm via** a quick
    repro against your pinned Pydantic AI version.
- **Chat loop — handled, slightly less raw.** Pydantic AI runs the tool loop internally; you carry
  state via message history (`result.all_messages()`) and typed deps. The loop is *real* but you read
  about it in their docs rather than seeing your own `while`. For a judge, this is "trust the
  well-known library" rather than "read the 30-line loop." **(high)**
- **Observation — excellent and vendor-neutral. (high, primary source.)**
  `logfire.instrument_pydantic_ai()` emits a span per run with child spans for each model call and
  each tool execution, over **plain OpenTelemetry** — it can export to *any* OTel collector
  (e.g. a local `otel-tui`) with **no Logfire account or backend required**. `capture_run_messages`
  and `result.all_messages()` give you the full decision/tool/result trail programmatically, which you
  can also dump to your own structured logs / `/trace` view. This is arguably *better* observation
  plumbing than you'd hand-roll, and it's standards-based, not a proprietary black box. **(high)**

**Net:** Pydantic AI keeps the pillars enforced-in-code (typed tools, validator-based guardrails) and
gives you free standards-based tracing. The mild legibility cost is that the chat loop itself is
inside the library. **Best framework choice; close second overall.**

#### 3b. OpenAI Agents SDK — capable, but two defaults fight this brief

**Guardrails — genuinely code-enforced. (high, primary source.)** `@input_guardrail` /
`@output_guardrail` (and tool-level variants) run real functions that return `GuardrailFunctionOutput`
with a `tripwire_triggered` bool; a tripped guardrail raises `InputGuardrailTripwireTriggered` /
`OutputGuardrailTripwireTriggered`, halting the run. This is exactly the "enforced + visible" model
the rubric rewards, and `output_info` carries structured reasoning you can log. **(high)**

**Two frictions for *this* project:**
1. **Defaults to OpenAI's Responses API.** For OpenRouter you must
   `set_default_openai_client(AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=...))`
   *and* `set_default_openai_api("chat_completions")` to force the Chat Completions path OpenRouter
   speaks. Without the flip, calls can 400 (cf. issue #279). It works, but it's extra config and a
   non-obvious failure mode. **(high)**
2. **Tracing defaults to exporting to OpenAI's hosted Traces dashboard.** Enabled by default, it uses
   a `BatchTraceProcessor` that ships traces to *OpenAI's* backend and even wants an OpenAI key for
   that export. For an OpenRouter-only, self-contained project you'd either disable it
   (`set_tracing_disabled(True)`) and lose the headline observability feature, or
   `set_trace_processors([...])` to redirect to a local/OTel sink. Either way you're configuring
   *away from* the default to avoid "why is this calling OpenAI?" — the opposite of frictionless, and
   a slightly awkward story to a judge inspecting a supposedly OpenRouter-only system. **(high)**

**Net:** Strong guardrail/trace primitives, but its happy path assumes OpenAI-the-provider. You spend
your first hour bending it to OpenRouter and redirecting tracing. Defensible, but more config-smell
than Pydantic AI for *this* exact stack. **Third choice.**

#### 3c. LangGraph — most power, most abstraction, least legible per pillar

**OpenRouter integration — works via `ChatOpenAI`. (high, community-confirmed):**
```python
ChatOpenAI(model=..., base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY,
           temperature=0.2).bind_tools(TOOLS)
```
State is a `StateGraph` over `MessagesState`; `ToolNode(TOOLS)` dispatches; `tools_condition` routes
model↔tools. Mature FastAPI+SSE streaming patterns and production templates exist. **(high)**

**Why it's the weakest fit for *this* rubric:** LangGraph's value is *complex* multi-node/branching
orchestration with checkpointed, durable state — which Taxathon does not need (ephemeral in-memory,
single short linear-ish conversation). What you pay for it is **the most indirection between the judge
and each pillar**: the "loop" is a compiled graph; tools dispatch through `ToolNode`/`tools_condition`;
guardrails aren't a first-class primitive (you implement them as nodes/conditional edges yourself);
observation typically points at LangSmith/Langfuse (another vendor backend) rather than a trail you
own. A judge has to understand graph semantics to verify the pillars. **For a brief that explicitly
rewards "real and enforced, not cosmetic," the abstraction works against you.** Use it only if you
*already* know LangGraph cold and intend to show off branching. **(high that it's over-powered here;
medium on the legibility penalty — depends on judge familiarity with LangGraph.)**

### 4. Option (c): Hybrid (the pragmatic refinement of the recommendation)

The cleanest hybrid is **hand-rolled loop + borrowed observability standard + Pydantic for schemas**:
- **Loop, dispatch, guardrails: hand-rolled** (max legibility per §2).
- **Schemas: Pydantic models** for `AgentState`, W-2 fields, the computed-1040 result, and tool
  arguments — so input/output validation (a guardrail) is declarative and visible, and you derive
  tool JSON Schemas from the models via `.model_json_schema()` rather than hand-writing them. **(high)**
- **Observation: structured per-turn trace dicts, optionally emitted as OpenTelemetry spans**
  (`opentelemetry-sdk` to a local console/collector exporter). You get a standards-based, vendor-free
  trail without adopting a whole agent framework. **(high)**

This hybrid keeps every pillar a thing the judge reads in *your* code, while not reinventing schema
validation or trace formats. It is the recommended concrete build.

### 5. Cross-cutting: what makes guardrails/observation *visible at runtime* (do this regardless)

- **A visible refusal path.** Include a guardrail that refuses off-task / tax-advice / non-tax
  requests with a canned message, and make sure the demo/tests trigger it once so the judge *sees* it
  fire. "Enforced" in code + "demonstrated" at runtime beats either alone. **(high — directly the
  rubric.)**
- **A pre-PDF validation gate.** Before filling the official 1040, run a code check that every
  populated line is present, numeric, and internally consistent (e.g. refund/owed = withholding −
  tax); reject and surface a calm error otherwise. This is the literal "no fabricated numbers reach
  the form" guarantee from NFR §Reliability — and it's a guardrail a judge can watch reject bad input.
  **(high)**
- **SSN handling.** Redact SSN-shaped values from logs and the trace, and keep raw SSN out of LLM
  prompts (compute code-side). Show a log line where it's redacted. **(high — NFR security mandate.)**
- **Surface the trail, not just emit it.** A tiny `/trace` JSON endpoint or a collapsible panel in the
  minimal UI turns "observation" from "it's in the logs" into "the judge can see it in the running
  system" — the PRD lists this as a stretch goal and it's high-leverage for the top-weighted criterion.
  **(high value, low cost.)**

---

## Risks and Unknowns

- **Model/tool-calling reliability on OpenRouter (medium).** Tool-call success varies by model. Mitigation:
  pick a known-reliable tool-capable model and test the *actual* tool schema end-to-end before committing.
  **Resolve by:** running 1–2 candidate models through one real W-2 → 1040 flow and comparing tool-call success.
- **Streamed tool-call assembly in the hand-rolled path (medium).** Assembling `tool_calls` argument
  fragments from SSE deltas is the classic foot-gun. **Resolve by:** a focused unit test; or only stream the
  final natural-language turn and use non-streamed calls for tool-deciding turns (simpler, still meets the
  "first token ~1–2s" feel on the answer turn).
- **Pydantic AI: ModelRetry-in-output-validator-while-streaming crash (medium, GitHub #3393).** If you
  adopt Pydantic AI *and* stream final output *and* use output-validator retries, this path may break on
  some versions. **Resolve by:** pin a version and repro, or validate before the streamed final turn.
- **OpenAI Agents SDK defaults (high-confidence, but a real tax on time):** must flip to Chat Completions
  and redirect/disable tracing for an OpenRouter-only build. Not a blocker, but it's why it's not the pick.
- **Judge familiarity with frameworks (low-medium, inherently subjective).** The legibility advantage of
  hand-rolled assumes the judge values reading plain code over recognizing a known framework. A judge who
  *prefers* seeing Pydantic AI's typed primitives might rate that higher. This is genuinely judge-dependent;
  the recommendation optimizes for the worst case (a judge who wants to see the mechanism itself).
- **Not independently benchmarked here:** exact latency numbers, and current library versions/APIs as of
  the build date — verify against the pinned versions in your `uv` lockfile, since agent-framework APIs move fast.

---

## Recommendation

**Build option (a)/(c): a hand-rolled minimal agent loop, with Pydantic models for all schemas and an
OpenTelemetry-shaped per-turn trace.** This maximizes the top-weighted criterion — every pillar is
enforced in code the judge reads directly, with nothing hidden behind a framework or a vendor dashboard:

1. **Chat loop:** a Pydantic `AgentState` (messages, W-2 fields, filing status, `questions_asked`,
   `trace`) carried server-side across turns; a plain `while` tool-dispatch loop over OpenRouter
   chat-completions. The ≤5-question budget is an integer gate.
2. **Tools:** a `TOOLS` registry (JSON Schema derived from Pydantic models) → python callables;
   **the 1040 computation runs deterministically in code and emits the filled official PDF** — the
   anchor "real tool, not talk."
3. **Guardrails (enforced + visible):** schema-validate the W-2; refuse off-task/advice requests via a
   checked condition + canned message; **validate the computed return before PDF fill (no fabricated
   numbers reach the form)**; redact SSN from logs/trace and keep it out of prompts.
4. **Observation:** append a structured trace record per turn (decision, tool, redacted args, result,
   guardrail verdict); expose it via logs + a small `/trace` endpoint (or trail panel) so it's visible
   in the *running* system, not only the repo. Emit as OTel spans to a local collector if you want the
   standards-based version cheaply.

**Fallback if you'd rather not own the loop:** **Pydantic AI** — native `OpenRouterProvider`, typed
`@agent.tool`, `@output_validator` + `ModelRetry` as code-enforced guardrails, and
`logfire.instrument_pydantic_ai()` over plain OTel (no vendor backend). Slightly less raw loop
legibility, materially less code to write. **Avoid the OpenAI Agents SDK** for this OpenRouter-only,
self-contained build (Responses-API + OpenAI-hosted-tracing defaults are friction), and **skip
LangGraph** (its orchestration power is unused here and its abstraction reduces pillar legibility).

**Smallest decision set for the orchestrator:**
1. **Hand-rolled loop (recommended) vs Pydantic AI (fast typed fallback)?** — both meet the rubric;
   choose on whether you value raw loop legibility (hand-rolled) over less code to own (Pydantic AI).
2. **Confirm: tax math is computed code-side and validated pre-PDF** (recommended yes — it is the
   strongest enforced-guardrail story and is approach-independent).
3. **Pick a tool-capable OpenRouter model and smoke-test one real W-2→1040 tool-call flow** before
   committing the loop.
4. **Commit to surfacing the trace in the running system** (`/trace` endpoint or UI panel), not just logs —
   it converts the highest-weighted pillar from "in the repo" to "visible at runtime."
