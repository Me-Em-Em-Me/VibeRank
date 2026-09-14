# AI Leaderboard for Vibe Coding

A standalone, self-contained web application providing an empirical, actionable ranking of LLMs tailored specifically for agentic coding ("vibe coding"). It combines evaluation signals from LMArena's Agent → Code benchmark with real-time inference pricing from OpenRouter.

## Overview

Traditional benchmarks often measure one-shot snippet completion or synthetic puzzles. In contrast, this leaderboard captures real multi-turn developer interaction dynamics inside live environments (accepted tasks, course corrections, user sentiment, and error recovery) while tracking true execution costs.

The core deliverable is [`AI_Leaderboard_for_Vibe_Coding.html`](file:///Volumes/SSDMarco/VibeCoding/AI-Leaderboard/AI_Leaderboard_for_Vibe_Coding.html), a single-file zero-dependency dashboard that can be opened directly in any modern web browser.

---

## Methodology & Scoring

### 1. Vibe Score Formula

The ranking is sorted strictly descending by **Score**:

$$\text{Score} = 0.30 \times \text{CS} + 0.30 \times \text{Steer} + 0.30 \times \text{Praise} + 0.10 \times \text{Bash}$$

| Signal | Weight | Source Field | What It Measures |
| :--- | :---: | :--- | :--- |
| **Confirmed Success (CS)** | **30%** | `task_outcome_explicit` | Frequency at which tasks are explicitly marked as completed and accepted. |
| **Steerability (Steer)** | **30%** | `steerability` | Ability to adopt user course-corrections, changing approach without regression. |
| **Praise / Complaint (Praise)** | **30%** | `praise_complaint` | Ratio of positive developer sentiment versus reported frustrations. |
| **Bash Recovery (Bash)** | **10%** | `bash_recovery_steps` | Resilience in autonomously fixing broken commands and syntax/runtime errors. |

> **Crucial Rule:** Cost is purely informational (for budgeting and tie-breaking). **Cost never enters the Score formula.**

### 2. Cost & Pricing Metrics

- **Cost/Task**: Mean USD cost per task (session) on Arena measured across a rolling 14-day window (`costWindowDays = 14`). Set to `N/A` if `pricedSampleCount < 10` (or `< 30` for sparse models).
- **Score / $**: `max(Score, 0) / Cost/Task`, using the OpenRouter cost when that overlay is shown, otherwise the Arena mean. Negative Scores become `0`; a positive Score with zero cost is `+∞`; unavailable costs are `N/A`.
- **Price $/M**: Vendor list price per million tokens (input / output) reported on Arena.
- **OpenRouter Real-Time Overlay**: Where an active OpenRouter route exists, the effective cost is calculated and shown **first**:
  $$\text{OR \$/task} = \text{Cost/Task} \times \frac{\text{OR}_{\text{blended}}}{\text{list}_{\text{blended}}}$$
  $$\text{blended} = 0.25 \times \text{input \$/M} + 0.75 \times \text{output \$/M}$$
  - **Green (`.main.down`)**: OpenRouter is cheaper than vendor list price.
  - **Red (`.main.up`)**: OpenRouter is more expensive than vendor list price.
  - **Plain single line**: When OpenRouter matches vendor list price (to 2 decimals) or when OpenRouter data is unavailable.
- **General Rounding Rule**: ALL price and currency metrics (including Cost/Task, Price $/M, blended prices, and internal numerical `data-v` sorting attributes) MUST be rounded to at most 2 decimal places. No price or cost metric may expose 3 or more decimal places.

---

## Interactive Features

1. **Three-State Column Sorting**: Click any header to cycle: Descending → Ascending → Default Rank order. Handled via inline JavaScript reading `data-v` attributes. `Score` is sorted descending on initial load.
2. **★ Pin & Compare Layer**:
   - Select individual models using the star icon, or use the header star to select/deselect all.
   - Click **Compare** to isolate selected models directly in the table (no secondary dialog or detached window).
   - Star selections persist across sessions using `localStorage["vibe-lb-pins"]`.
3. **Boxed Score Column (`.score-col`)**: The primary Vibe Score is highlighted with a persistent 2px accent outline framing the header down to the last visible row.
4. **Per-Column Dynamic Tinting**: Score and signal cells use pure linear green/red scales, normalized separately for each column and sign; Score / $ uses the same non-negative linear scale relative to the actual largest finite ratio, with no tint for zero.

---

## Fast Update Guide

The repository includes a dedicated, zero-dependency updater script [`update_leaderboard.py`](file:///Volumes/SSDMarco/VibeCoding/AI-Leaderboard/update_leaderboard.py) that completes the full data refresh in **under 2 seconds**.

```bash
python3 update_leaderboard.py
```

> **INSTRUCTION FOR AI ASSISTANTS & AUTOMATIONS:**
> Whenever asked to refresh, modify, or update the leaderboard, run `python3 update_leaderboard.py`.
> Maintain [`AI_Leaderboard_for_Vibe_Coding.html`](file:///Volumes/SSDMarco/VibeCoding/AI-Leaderboard/AI_Leaderboard_for_Vibe_Coding.html) as a single self-contained file in English. Do not regenerate HTML manually token-by-token.

### How It Works

1. **Concurrent Fetching**: Downloads live payloads in parallel from:
   - `https://arena.ai/leaderboard/agent/code`
   - `https://openrouter.ai/api/v1/models`
2. **Payload Parsing**:
   - Reassembles Arena Next.js `self.__next_f` stream chunks to extract snapshot scores and 14-day rolling cost statistics.
   - Extracts OpenRouter pricing, filtering out `:batch` routes and prioritizing `:free` endpoints for each model.
3. **Deterministic Scoring**:
   - Computes Vibe Score: `0.30 * CS + 0.30 * Steer + 0.30 * Praise + 0.10 * Bash`.
   - Normalizes per-column min/max bounds and calculates dynamic HSL tint alphas.
   - Renders OpenRouter price overlay badges (green for cheaper, red for more expensive).
4. **Surgical DOM Update**:
   - Updates hero counters (models tracked, total sessions, snapshot date, cost window).
   - Injects fresh `<tbody>` rows with numerical `data-v` sorting keys into [`AI_Leaderboard_for_Vibe_Coding.html`](file:///Volumes/SSDMarco/VibeCoding/AI-Leaderboard/AI_Leaderboard_for_Vibe_Coding.html).
   - Refreshes methodology notes and footer timestamp.

### Technical Specifications & Formulas

- **Score**: Compute `0.30 * CS + 0.30 * Steer + 0.30 * Praise + 0.10 * Bash` using the frozen percentage points from `signalScores`.
- **Cell Attributes (`data-v`)**: Maintain numerical sort keys on every `<td>`:
  - Rank: integer.
  - Model: string.
  - Score and Signals: floating point numbers.
  - Score / $: non-negative `max(Score, 0) / Cost/Task`; use `data-v="Infinity"` for positive Score with zero cost and omit `data-v` when the cost is unavailable so `N/A` sorts last.
  - Cost/Task: primary numerical value (OR cost if available, else Arena mean).
  - Price $/M: blended price `0.25 * input + 0.75 * output` of the primary pair.
- **Dynamic Alphas**:
  - For positive values: `alpha = value / column_max`
  - For negative values: `alpha = abs(value) / abs(column_min)`
  - Clamp alpha between `0.05` and `1.0`. A value of exactly `0` receives no inline background color.

### 3. OpenRouter Model Identifier Mapping

Use this canonical mapping for real-time model resolution:

```json
{
  "Claude Fable 5 (High)": "anthropic/claude-fable-5",
  "Claude Fable 5.1 (Max)": "anthropic/claude-fable-5.1",
  "Claude Opus 4.8 (High)": "anthropic/claude-opus-4.8",
  "Claude Opus 5 (High)": "anthropic/claude-opus-5",
  "Claude Opus 5 (Max)": "anthropic/claude-opus-5",
  "Claude Sonnet 4.6": "anthropic/claude-sonnet-4.6",
  "Claude Sonnet 5 (High)": "anthropic/claude-sonnet-5",
  "DeepSeek V4 Pro": "deepseek/deepseek-v4-pro",
  "DeepSeek V4 Pro (High) (0813)": "deepseek/deepseek-v4-pro-0813",
  "Deepseek V4 Flash (High) (20260731)": "deepseek/deepseek-v4-flash-0731",
  "GLM 5.2 (Max)": "z-ai/glm-5.2",
  "GLM 5.3 (Max)": "z-ai/glm-5.3",
  "GLM 5.3 Flash": "z-ai/glm-5.3-flash",
  "GPT 5.4 (High)": "openai/gpt-5.4",
  "GPT 5.5": "openai/gpt-5.5",
  "GPT 5.5 (xHigh)": "openai/gpt-5.5",
  "GPT 5.6 Luna (xHigh)": "openai/gpt-5.6-luna",
  "GPT 5.6 Sol (xHigh)": "openai/gpt-5.6-sol",
  "GPT 5.6 Terra (xHigh)": "openai/gpt-5.6-terra",
  "GPT 6 Astra (Max)": "openai/gpt-6-astra",
  "Gemini 3.1 Pro Preview": "google/gemini-3.1-pro-preview",
  "Gemini 3.5 Flash Lite": "google/gemini-3.5-flash-lite",
  "Gemini 3.6 Flash (High)": "google/gemini-3.6-flash",
  "Gemini 3.8 Flash (High)": "google/gemini-3.8-flash",
  "Grok 4.5": "x-ai/grok-4.5",
  "Grok 4.6 (xHigh)": "x-ai/grok-4.6",
  "Hy3": "tencent/hy3",
  "Hy4 preview": "tencent/hy4-preview",
  "Inkling": "thinkingmachines/inkling:free",
  "Inkling Small": "thinkingmachines/inkling-small:free",
  "Kimi K3 (Max)": "moonshotai/kimi-k3",
  "Mimo V2.5 Pro": "xiaomi/mimo-v2.5-pro",
  "Minimax M2.7": "minimax/minimax-m2.7",
  "Minimax M3": "minimax/minimax-m3",
  "Mistral Medium 3.5": "mistralai/mistral-medium-3-5",
  "Muse Spark 1.1": "meta/muse-spark-1.1",
  "Muse Spark 1.2 (xHigh)": "meta/muse-spark-1.2-contributor",
  "Muse Spark 1.3 (Max)": "meta/muse-spark-1.3-contributor",
  "Qwen 3.8 27B": "qwen/qwen3.8-27b",
  "Qwen3.7 Max": "qwen/qwen3.7-max",
  "Qwen3.7 Plus": "qwen/qwen3.7-plus",
  "Qwen3.8 Flash Next": "qwen/qwen3.8-flash",
  "Qwen3.8 Max": "qwen/qwen3.8-max-0902",
  "Solar Pro 4": "upstage/solar-pro4"
}
```

*When a new model enters the leaderboard, look up its real-time endpoint in `/tmp/or.json`, always check if a `:free` version exists for the model, select the lowest In/Out Price among active providers/endpoints (excluding `:batch`), and append it to this dictionary.*

### 4. Verified List Prices & Historical Baselines

When Arena live payloads omit vendor list pricing or lack sufficient 14-day rolling cost samples, `update_leaderboard.py` applies verified fallbacks:
- **`KNOWN_LIST_PRICES`**: Fallback vendor list prices ($/M tokens: input, output) used when Arena snapshot values are `null`:
  - `DeepSeek V4 Pro (High) (0813)`: `$0.44 / $0.87` (from $0.435 rounded to 2 decimals)
  - `Deepseek V4 Flash (High) (20260731)`: `$0.14 / $0.28`
  - `Grok 4.6 (xHigh)`: `$2 / $6`
  - `Qwen3.7 Max`: `$2.5 / $7.5`
- **`KNOWN_BASELINES`**: Verified historical mean cost baseline for models with insufficient rolling samples (`pricedSampleCount < 10`):
  - `Gemini 3.8 Flash (High)`: `$0.45` mean USD.

### 5. Acceptance Checklist

Before completing an update, verify each item:
- [ ] Header metadata matches Arena live values (snapshot date, total model count, total session count, OpenRouter timestamp).
- [ ] Models are sorted by `Score` descending, numbered $1 \dots N$.
- [ ] Formula is computed accurately row by row: `0.30*CS + 0.30*Steer + 0.30*Praise + 0.10*Bash`.
- [ ] OpenRouter price overlays are properly color-coded (green if cheaper, red if more expensive, neutral if identical or unmapped).
- [ ] General rule: ALL currency and price values without exception (Cost/Task, Price $/M, blended rates, and `data-v` attributes) are rounded to at most 2 decimal places.
- [ ] Sorting functionality works across all columns; ties break on initial rank.
- [ ] `score-col` styling is active and properly framed.
- [ ] The framed Score / $ column immediately precedes Cost/Task, uses the displayed cost value, clamps negative Scores to zero, and displays positive zero-cost ratios as `+∞`.
- [ ] Pin & Compare functionality is preserved and persists via `localStorage`.
- [ ] No third-party tracking or injected challenge scripts remain in the HTML.
