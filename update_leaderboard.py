#!/usr/bin/env python3
"""
AI Leaderboard for Vibe Coding — Fast Updater
Fetches real-time signals from LMArena Agent -> Code and pricing from OpenRouter,
computes the vibe score rankings, and surgically updates AI_Leaderboard_for_Vibe_Coding.html.

Execution time: ~2-3 seconds.
Zero external dependencies (uses Python standard library only).
"""

import sys
import os
import re
import json
import time
import urllib.request
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

# Canonical mapping from Arena model name to OpenRouter model identifier
OPENROUTER_MAP = {
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
    "Deepseek V4.1 Flash (Max)": "deepseek/deepseek-v4.1-flash",
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

# Predecessor mapping: when a new model lacks rolling-window token samples on Arena,
# inherit the measured mean token volume from its direct architectural predecessor
PREDECESSOR_MAP = {
    "Gemini 3.8 Flash (High)": "Gemini 3.6 Flash (High)",
    "GPT 5.6 Luna (xHigh)": "GPT 5.5 (xHigh)",
    "GPT 5.6 Terra (xHigh)": "GPT 5.5 (xHigh)",
    "GPT 5.6 Sol (xHigh)": "GPT 5.5 (xHigh)",
    "Claude Opus 5 (Max)": "Claude Opus 4.8 (High)",
    "Claude Fable 5.1 (Max)": "Claude Fable 5 (High)",
    "GLM 5.3 (Max)": "GLM 5.2 (Max)",
    "Qwen3.8 Max": "Qwen3.7 Max"
}

# Known verified historical baselines for models lacking sufficient rolling-window samples
KNOWN_BASELINES = {
    "Gemini 3.8 Flash (High)": {
        "meanUsd": 0.45,
        "meanMtok": 0.08,
        "inputPricePerMillion": 0.75,
        "outputPricePerMillion": 3.75
    }
}

# Known verified vendor list prices ($/M tokens: input, output) for models missing list pricing in Arena snapshot
KNOWN_LIST_PRICES = {
    "DeepSeek V4 Pro (High) (0813)": (0.44, 0.87),
    "Deepseek V4 Flash (High) (20260731)": (0.14, 0.28),
    "Grok 4.6 (xHigh)": (2.0, 6.0),
    "Qwen3.7 Max": (2.5, 7.5),
}

HTML_FILENAME = "AI_Leaderboard_for_Vibe_Coding.html"

def fetch_url(url, timeout=12):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")

def parse_arena_payload(arena_html):
    # Extract Next.js streaming chunks pushed via self.__next_f.push
    matches = re.findall(r"self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)", arena_html)
    raw_chunks = []
    for m in matches:
        try:
            raw_chunks.append(json.loads('"' + m + '"'))
        except Exception:
            raw_chunks.append(m)
    stream = "".join(raw_chunks)

    # Locate the snapshot JSON object
    pos_snap = stream.find('"snapshot":{')
    if pos_snap == -1:
        raise ValueError("Could not find 'snapshot' object in Arena HTML")
    start = pos_snap + len('"snapshot":')
    depth, end = 0, start
    for i in range(start, len(stream)):
        if stream[i] == "{":
            depth += 1
        elif stream[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    snapshot = json.loads(stream[start:end])

    # Locate the live rolling cost JSON object
    pos_cost = stream.find('"costWindowDays":')
    if pos_cost == -1:
        raise ValueError("Could not find 'costWindowDays' object in Arena HTML")
    start_c = stream.rfind("{", 0, pos_cost)
    depth, end_c = 0, start_c
    for i in range(start_c, len(stream)):
        if stream[i] == "{":
            depth += 1
        elif stream[i] == "}":
            depth -= 1
            if depth == 0:
                end_c = i + 1
                break
    costs = json.loads(stream[start_c:end_c])

    return snapshot, costs

def parse_openrouter_payload(or_raw_json):
    data = json.loads(or_raw_json)
    models = data.get("data", [])
    
    # Filter out batch routes and index by id
    or_by_id = {}
    for m in models:
        mid = m.get("id", "")
        if ":batch" in mid:
            continue
        or_by_id[mid] = m
    return or_by_id

def resolve_openrouter_pricing(model_name, or_by_id, perf_data=None):
    target_id = OPENROUTER_MAP.get(model_name)
    if not target_id:
        return None

    clean_id = target_id.split(":")[0]

    # Prioritize :free endpoint when explicitly specified or available with zero cost
    free_id = clean_id + ":free"
    if target_id.endswith(":free") or (free_id in or_by_id and free_id != target_id):
        free_cand = or_by_id.get(free_id) or or_by_id.get(target_id)
        if free_cand and float(free_cand["pricing"]["prompt"]) == 0 and float(free_cand["pricing"]["completion"]) == 0:
            return {
                "id": free_cand["id"],
                "prompt": 0.0,
                "completion": 0.0,
                "blended": 0.0
            }

    # Prioritize the hero box "IN / OUT PRICE" directly visible on OpenRouter page
    if perf_data and clean_id in perf_data:
        box_in = perf_data[clean_id].get("box_in")
        box_out = perf_data[clean_id].get("box_out")
        if box_in is not None and box_out is not None:
            blended_price = 0.25 * box_in + 0.75 * box_out
            return {
                "id": target_id,
                "prompt": box_in,
                "completion": box_out,
                "blended": blended_price
            }

    candidates = []
    if target_id in or_by_id:
        candidates.append(or_by_id[target_id])
    if free_id in or_by_id and free_id != target_id:
        candidates.append(or_by_id[free_id])
    
    if not candidates:
        return None

    # Select endpoint with the lowest blended price
    best = min(
        candidates,
        key=lambda c: 0.25 * float(c["pricing"]["prompt"]) + 0.75 * float(c["pricing"]["completion"])
    )
    prompt_price = float(best["pricing"]["prompt"]) * 1e6
    completion_price = float(best["pricing"]["completion"]) * 1e6
    blended_price = 0.25 * prompt_price + 0.75 * completion_price

    return {
        "id": best["id"],
        "prompt": prompt_price,
        "completion": completion_price,
        "blended": blended_price
    }

def format_price_dollars(v):
    if v is None:
        return "N/A"
    s = f"{v:.2f}"
    if s.endswith(".00"):
        return f"${int(v)}"
    elif s.endswith("0"):
        return f"${v:.1f}"
    return f"${v:.2f}"


def fetch_openrouter_performance(model_map):
    cache_file = "/tmp/or_perf_cache.json"
    now = time.time()
    cached_data = {}
    if os.path.isfile(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("_timestamp", 0) > now - 3600:
                raw_cached = cached.get("data", {})
                if any(v.get("provider_count", 0) > 0 for v in raw_cached.values()):
                    cached_data = raw_cached
        except Exception:
            cached_data = {}

    clean_ids = list(set([m_id.split(":")[0] for m_id in model_map.values()]))
    needed_ids = [
        cid for cid in clean_ids
        if cid not in cached_data
        or cached_data[cid].get("provider_count", 0) == 0
        or cached_data[cid].get("box_in") is None
    ]

    if not needed_ids:
        return cached_data

    def fetch_one(clean_id):
        url = f"https://openrouter.ai/{clean_id}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8")
            tps_matches = re.findall(r'p50_throughput\\\\?\":\s*([0-9.]+)', html)
            lat_matches = re.findall(r'p50_latency\\\\?\":\s*([0-9.]+)', html)
            box_match = re.search(r'In\s*/\s*Out\s*Price.*?\$([0-9.]+)\s*/\s*\$([0-9.]+)', html, re.DOTALL | re.I)
            box_in = float(box_match.group(1)) if box_match else None
            box_out = float(box_match.group(2)) if box_match else None
            tps_list = [float(x) for x in tps_matches if float(x) > 0]
            lat_list = [float(x) / 1000.0 for x in lat_matches if float(x) > 0]
            mean_tps = sum(tps_list) / len(tps_list) if tps_list else None
            mean_lat = sum(lat_list) / len(lat_list) if lat_list else None
            return clean_id, {
                "mean_tps": round(mean_tps, 1) if mean_tps else None,
                "mean_lat": round(mean_lat, 2) if mean_lat else None,
                "provider_count": len(tps_list),
                "box_in": box_in,
                "box_out": box_out
            }
        except Exception:
            return clean_id, {"mean_tps": None, "mean_lat": None, "provider_count": 0, "box_in": None, "box_out": None}

    results = dict(cached_data)
    with ThreadPoolExecutor(max_workers=12) as executor:
        for clean_id, data in executor.map(fetch_one, needed_ids):
            results[clean_id] = data

    if any(v.get("provider_count", 0) > 0 for v in results.values()):
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"_timestamp": now, "data": results}, f)
        except Exception:
            pass

    return results


def compute_leaderboard_data(snapshot, costs, or_by_id, perf_data=None):
    if perf_data is None:
        perf_data = {}
    cost_map = {e["contenderName"]: e for e in costs.get("entries", [])}
    raw_rows = snapshot.get("rows", [])
    
    processed = []
    for r in raw_rows:
        model_name = r["model"]
        contender = r["contenderName"]
        signals = r.get("signalScores", {})
        
        cs = signals.get("task_outcome_explicit", 0.0) * 100.0
        steer = signals.get("steerability", 0.0) * 100.0
        praise = signals.get("praise_complaint", 0.0) * 100.0
        bash = signals.get("bash_recovery_steps", 0.0) * 100.0
        score = 0.30 * cs + 0.30 * steer + 0.30 * praise + 0.10 * bash

        # Extract list prices
        list_in = r.get("inputPricePerMillion")
        list_out = r.get("outputPricePerMillion")
        if (list_in is None or list_out is None) and model_name in KNOWN_LIST_PRICES:
            list_in, list_out = KNOWN_LIST_PRICES[model_name]
        list_blended = 0.25 * list_in + 0.75 * list_out if list_in is not None and list_out is not None else None

        # Extract Arena live cost and output token volume
        cost_entry = cost_map.get(contender)
        arena_mtok = None
        fallback_source = None
        if cost_entry and cost_entry.get("pricedSampleCount", 0) >= 10:
            arena_cost = cost_entry.get("meanUsd")
            mtok_entry = cost_entry.get("outputMtokPerTask")
            if mtok_entry and mtok_entry.get("meanMtok") is not None:
                arena_mtok = mtok_entry.get("meanMtok")
        elif model_name in KNOWN_BASELINES:
            b = KNOWN_BASELINES[model_name]
            arena_cost = b.get("meanUsd", b.get("medianUsd"))
            if list_in is None:
                list_in = b["inputPricePerMillion"]
                list_out = b["outputPricePerMillion"]
                list_blended = 0.25 * list_in + 0.75 * list_out
        else:
            arena_cost = None

        # Predecessor token fallback: dynamically inherit from direct predecessor if model lacks live samples
        if arena_mtok is None and model_name in PREDECESSOR_MAP:
            pred_name = PREDECESSOR_MAP[model_name]
            pred_contender = next((x["contenderName"] for x in raw_rows if x["model"] == pred_name), None)
            if pred_contender and pred_contender in cost_map:
                pred_entry = cost_map[pred_contender]
                pred_mtok = pred_entry.get("outputMtokPerTask", {}).get("meanMtok")
                if pred_mtok is not None:
                    arena_mtok = pred_mtok
                    fallback_source = pred_name

        if arena_mtok is None and model_name in KNOWN_BASELINES:
            arena_mtok = KNOWN_BASELINES[model_name].get("meanMtok")
            if arena_mtok is not None and not fallback_source:
                fallback_source = "verified baseline"

        # Resolve OpenRouter real-time pricing
        or_info = resolve_openrouter_pricing(model_name, or_by_id, perf_data)
        or_cost = None
        ratio = 1.0
        if or_info and list_blended and list_blended > 0:
            ratio = or_info["blended"] / list_blended
            if arena_cost is not None:
                or_cost = arena_cost * ratio

        # Compute Time/Task (generation decode time + response latency overhead)
        sess = r.get("sessions", 0)
        obs = r.get("observations", 0)
        avg_turns = (obs / sess) if sess and sess > 0 else 100.0

        clean_id = OPENROUTER_MAP.get(model_name, "").split(":")[0]
        perf = perf_data.get(clean_id, {})
        mean_tps = perf.get("mean_tps")
        mean_lat = perf.get("mean_lat")
        provider_count = perf.get("provider_count", 0)

        tot_min = None
        dec_sec = None
        lat_sec = None
        output_tokens = None
        if arena_mtok is not None and mean_tps and mean_tps > 0 and mean_lat is not None:
            output_tokens = arena_mtok * 1_000_000.0
            dec_sec = output_tokens / mean_tps
            lat_sec = avg_turns * mean_lat
            tot_sec = dec_sec + lat_sec
            tot_min = tot_sec / 60.0

        processed.append({
            "model": model_name,
            "contender": contender,
            "score": score,
            "cs": cs,
            "steer": steer,
            "praise": praise,
            "bash": bash,
            "list_in": list_in,
            "list_out": list_out,
            "list_blended": list_blended,
            "arena_cost": arena_cost,
            "arena_mtok": arena_mtok,
            "fallback_source": fallback_source,
            "output_tokens": output_tokens,
            "avg_turns": avg_turns,
            "mean_tps": mean_tps,
            "mean_lat": mean_lat,
            "provider_count": provider_count,
            "dec_sec": dec_sec,
            "lat_sec": lat_sec,
            "tot_min": tot_min,
            "or_info": or_info,
            "or_cost": or_cost,
            "ratio": ratio
        })

    # Sort descending strictly by Score
    processed.sort(key=lambda x: x["score"], reverse=True)
    for idx, item in enumerate(processed, 1):
        item["rank"] = idx

    return processed

def compute_column_extrema(processed):
    extrema = {}
    for col in ["score", "cs", "steer", "praise", "bash"]:
        values = [p[col] for p in processed if p[col] is not None]
        pos = [v for v in values if v > 0]
        neg = [abs(v) for v in values if v < 0]
        extrema[col] = {
            "pos_max": max(pos) if pos else 1.0,
            "neg_max": max(neg) if neg else 1.0
        }
    return extrema

def render_cell_color(val, col, extrema):
    if val == 0:
        return ""
    if val > 0:
        alpha = max(0.05, min(1.0, val / extrema[col]["pos_max"]))
        return f' style="background-color:hsl(125 49% 50% / {alpha:.3f})"'
    else:
        alpha = max(0.05, min(1.0, abs(val) / extrema[col]["neg_max"]))
        return f' style="background-color:hsl(2 86% 63% / {alpha:.3f})"'

def render_table_rows(processed, extrema):
    rows_html = []

    for p in processed:
        rank = p["rank"]
        model = p["model"]
        score = p["score"]
        cs = p["cs"]
        steer = p["steer"]
        praise = p["praise"]
        bash = p["bash"]
        
        # Color styles
        s_style = render_cell_color(score, "score", extrema)
        cs_style = render_cell_color(cs, "cs", extrema)
        steer_style = render_cell_color(steer, "steer", extrema)
        praise_style = render_cell_color(praise, "praise", extrema)
        bash_style = render_cell_color(bash, "bash", extrema)

        # Numerical display strings
        s_sign = "+" if score > 0 else ""
        cs_sign = "+" if cs > 0 else ""
        steer_sign = "+" if steer > 0 else ""
        praise_sign = "+" if praise > 0 else ""
        bash_sign = "+" if bash > 0 else ""

        # Cost & Price cells
        arena_cost = p["arena_cost"]
        list_blended = p["list_blended"]
        list_in = p["list_in"]
        list_out = p["list_out"]
        or_cost = p["or_cost"]
        or_info = p["or_info"]
        ratio = p["ratio"]

        has_overlay = (
            or_info is not None
            and arena_cost is not None
            and or_cost is not None
            and round(ratio, 2) != 1.00
        )

        if has_overlay:
            direction = "down" if ratio < 1.0 else "up"
            cost_title = f'OpenRouter real-time &times; {ratio:.3f} via {or_info["id"]} (no batch)'
            cost_cell = (
                f'<td class="num" data-v="{or_cost:.2f}" title="{cost_title}">'
                f'<div class="main {direction}">OR ${or_cost:.2f}</div>'
                f'<div class="alt">Arena ${arena_cost:.2f}</div></td>'
            )
            
            or_in_str = format_price_dollars(or_info["prompt"])
            or_out_str = format_price_dollars(or_info["completion"])
            list_in_str = format_price_dollars(list_in)
            list_out_str = format_price_dollars(list_out)
            
            price_cell = (
                f'<td class="num" data-v="{or_info["blended"]:.2f}" title="{cost_title}">'
                f'<div class="main {direction}">OR {or_in_str} / {or_out_str}</div>'
                f'<div class="alt">list {list_in_str} / {list_out_str}</div></td>'
            )
        else:
            if arena_cost is not None:
                cost_cell = f'<td class="num" data-v="{arena_cost:.2f}"><div class="main">${arena_cost:.2f}</div></td>'
            else:
                cost_cell = '<td class="num"><div class="main">N/A</div></td>'
            
            if list_blended is not None:
                p_in_str = format_price_dollars(list_in)
                p_out_str = format_price_dollars(list_out)
                price_cell = f'<td class="num" data-v="{list_blended:.2f}"><div class="main">{p_in_str} / {p_out_str}</div></td>'
            else:
                price_cell = '<td class="num"><div class="main">N/A</div></td>'

        # Time cell (Generation Decode Time + Response Latency Overhead)
        tot_min = p.get("tot_min")
        output_tokens = p.get("output_tokens")
        mean_tps = p.get("mean_tps")
        mean_lat = p.get("mean_lat")
        dec_sec = p.get("dec_sec")
        lat_sec = p.get("lat_sec")
        avg_turns = p.get("avg_turns")
        provider_count = p.get("provider_count", 0)
        fallback_source = p.get("fallback_source")

        if tot_min is not None and dec_sec is not None and lat_sec is not None:
            mins = max(1, int(round(tot_min)))
            time_main = f"{mins}m"

            tok_k = int(round(output_tokens / 1000.0))
            tps_int = int(round(mean_tps))
            alt_ast = "*" if fallback_source else ""
            time_alt = f"{tok_k}k{alt_ast} &middot; {tps_int} t/s"
            source_note = f" (via predecessor {fallback_source})" if fallback_source else ""
            time_title = (
                f"Total: {time_main} | Decode: {dec_sec/60.0:.1f}m ({tok_k}k tok{source_note} @ {mean_tps:.1f} t/s) + "
                f"Latency: {lat_sec/60.0:.1f}m ({int(round(avg_turns))} turns &times; {mean_lat:.2f}s TTFT) "
                f"across {provider_count} OR providers"
            )
            time_cell = (
                f'<td class="num" data-v="{tot_min:.2f}" title="{time_title}">'
                f'<div class="main">{time_main}</div>'
                f'<div class="alt">{time_alt}</div></td>'
            )
        else:
            time_cell = '<td class="num"><div class="main">N/A</div></td>'

        row = (
            f'<tr>\n'
            f'<td class="num rank" data-v="{rank}">{rank}</td>\n'
            f'<td class="model" data-v="{model}">{model}</td>\n'
            f'<td class="num score-col" data-v="{score:.2f}"{s_style}><div class="main">{s_sign}{score:.2f}</div></td>\n'
            f'<td class="num" data-v="{cs:.2f}"{cs_style}><div class="main">{cs_sign}{cs:.2f}%</div></td>\n'
            f'<td class="num" data-v="{steer:.2f}"{steer_style}><div class="main">{steer_sign}{steer:.2f}%</div></td>\n'
            f'<td class="num" data-v="{praise:.2f}"{praise_style}><div class="main">{praise_sign}{praise:.2f}%</div></td>\n'
            f'<td class="num" data-v="{bash:.2f}"{bash_style}><div class="main">{bash_sign}{bash:.2f}%</div></td>\n'
            f'{cost_cell}\n'
            f'{time_cell}\n'
            f'{price_cell}\n'
            f'</tr>'
        )
        rows_html.append(row)

    return "\n".join(rows_html)

def update_html_file(html_path, snapshot, costs, rows_html):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    model_count = len(snapshot.get("rows", []))
    total_sessions = snapshot.get("totalSessions", 0)
    cost_window_days = costs.get("costWindowDays", 14)
    
    # Parse snapshot date (e.g. 2026-09-09T22:00:00.000Z -> Sep 9 2026)
    dt_iso = snapshot.get("lastUpdated", "2026-09-09T22:00:00.000Z")
    dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    month_name = dt.strftime("%b")
    day_num = dt.day
    year_num = dt.year
    snapshot_display = f"{month_name} {day_num}"
    snapshot_full = f"{month_name} {day_num}, {year_num}"
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Update hero statistics
    html = re.sub(
        r'(<div class="stat"><div class="v"><em>)\d+(</em></div><div class="k">Models tracked</div></div>)',
        r'\g<1>' + str(model_count) + r'\2',
        html
    )
    html = re.sub(
        r'(<div class="stat"><div class="v"><em>)[\d,]+(</em></div><div class="k">Sessions</div></div>)',
        r'\g<1>' + f"{total_sessions:,}" + r'\2',
        html
    )
    html = re.sub(
        r'(<div class="stat"><div class="v">)[^<]+<em>\d{4}</em>(</div><div class="k">Snapshot</div></div>)',
        f'<div class="stat"><div class="v">{snapshot_display} <em>{year_num}</em>\\2',
        html
    )
    html = re.sub(
        r'(<div class="stat"><div class="v"><em>)\d+(</em> days</div><div class="k">Cost window</div></div>)',
        r'\g<1>' + str(cost_window_days) + r'\2',
        html
    )

    # 2. Update search input placeholder
    html = re.sub(
        r'placeholder="Filter \d+ models…',
        f'placeholder="Filter {model_count} models…',
        html
    )

    # 3. Update table rows inside <div class="wrap"><table>
    pattern_table = r'(<div class="wrap">\s*<table>\s*<thead>.*?</thead>\s*<tbody>).*?(</tbody>\s*</table>\s*</div>)'
    replacement_table = r'\g<1>\n' + rows_html + r'\n\2'
    html, n_subs = re.subn(pattern_table, replacement_table, html, flags=re.DOTALL)
    if n_subs == 0:
        raise ValueError("Could not replace <tbody> in main table")

    # 4. Update footer snapshot & OpenRouter dates
    pattern_footer = r'Snapshot [^·]+· Signals: <a href="https://arena\.ai/leaderboard/agent/code">LMArena Agent → Code</a> · Prices: <a href="https://openrouter\.ai/models">OpenRouter</a> real-time \d{4}-\d{2}-\d{2} UTC'
    new_footer_text = f'Snapshot {snapshot_full} · Signals: <a href="https://arena.ai/leaderboard/agent/code">LMArena Agent → Code</a> · Prices: <a href="https://openrouter.ai/models">OpenRouter</a> real-time {today_utc} UTC'
    html = re.sub(pattern_footer, new_footer_text, html)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

def update_readme_example(readme_path, top_model):
    if not os.path.isfile(readme_path):
        return
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()

    name = top_model["model"]
    cs = top_model["cs"]
    steer = top_model["steer"]
    praise = top_model["praise"]
    bash = top_model["bash"]
    score = top_model["score"]

    cs_contrib = 0.30 * cs
    steer_contrib = 0.30 * steer
    praise_contrib = 0.30 * praise
    bash_contrib = 0.10 * bash

    line1 = (
        r"$$\text{Score} = 0.30 \times (" + f"{cs:+.2f}" + r") + 0.30 \times (" +
        f"{steer:+.2f}" + r") + 0.30 \times (" + f"{praise:+.2f}" + r") + 0.10 \times (" +
        f"{bash:+.2f}" + r")$$"
    )
    line2 = (
        r"$$\text{Score} = " + f"{cs_contrib:.2f} {steer_contrib:+.2f} {praise_contrib:+.2f} {bash_contrib:+.2f} = {score:+.2f}" + r"$$"
    )

    example_block = (
        f"### 3. Concrete Scoring Example\n\n"
        f"Taking the #1 ranked model, **{name}**, from the benchmark snapshot:\n\n"
        f"{line1}\n"
        f"{line2}"
    )

    pattern = r"### 3\. Concrete Scoring Example\s*\n\s*Taking .*?(?=\n\nSignal percentages)"
    readme, n = re.subn(pattern, lambda _: example_block, readme, flags=re.DOTALL)
    if n > 0:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme)

def main():
    t_start = time.time()
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(workspace_dir, HTML_FILENAME)

    if not os.path.isfile(html_path):
        print(f"Error: Could not locate {html_path}", file=sys.stderr)
        sys.exit(1)

    print("Fetching live payloads from Arena and OpenRouter...")
    arena_url = "https://arena.ai/leaderboard/agent/code"
    or_url = "https://openrouter.ai/api/v1/models"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_arena = executor.submit(fetch_url, arena_url)
            f_or = executor.submit(fetch_url, or_url)
            arena_html = f_arena.result()
            or_raw_json = f_or.result()
        try:
            with open("/tmp/arena.html", "w", encoding="utf-8") as f:
                f.write(arena_html)
            with open("/tmp/or.json", "w", encoding="utf-8") as f:
                f.write(or_raw_json)
        except Exception:
            pass
    except Exception as e:
        if os.path.isfile("/tmp/arena.html") and os.path.isfile("/tmp/or.json"):
            print(f"Live fetch failed ({e}); falling back to cached /tmp payloads...", file=sys.stderr)
            with open("/tmp/arena.html", "r", encoding="utf-8") as f:
                arena_html = f.read()
            with open("/tmp/or.json", "r", encoding="utf-8") as f:
                or_raw_json = f.read()
        else:
            raise

    t_fetch = time.time()
    print(f"Payloads ready in {t_fetch - t_start:.2f}s.")

    print("Parsing payloads and computing leaderboard scores...")
    snapshot, costs = parse_arena_payload(arena_html)
    or_by_id = parse_openrouter_payload(or_raw_json)
    
    print("Fetching OpenRouter real-time performance profiles...")
    perf_data = fetch_openrouter_performance(OPENROUTER_MAP)
    
    processed = compute_leaderboard_data(snapshot, costs, or_by_id, perf_data)
    extrema = compute_column_extrema(processed)
    rows_html = render_table_rows(processed, extrema)

    print("Updating " + HTML_FILENAME + "...")
    update_html_file(html_path, snapshot, costs, rows_html)

    if processed:
        print("Updating scoring example in README.md with #1 ranked model...")
        readme_path = os.path.join(workspace_dir, "README.md")
        update_readme_example(readme_path, processed[0])

    t_end = time.time()
    print(f"Successfully updated {len(processed)} models in {t_end - t_start:.2f}s!")

if __name__ == "__main__":
    main()
