from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import AppConfig
from .provider_resilience import ProviderFailure, provider_request_json

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
AI_SUMMARY_CACHE_VERSION = "v2"
SUMMARY_ROLE = "explanation_only"
SELECTION_SOURCE = "deterministic_scoring"
SELECTION_METHOD = (
    "Deterministic scoring and portfolio constraints select research candidates; "
    "the summary layer only explains the scoring result."
)


def build_ai_summary(config: AppConfig, analysis: dict[str, Any]) -> dict[str, Any]:
    template = build_template_summary(analysis)
    if config.ai_summary_provider != "openai":
        return template
    if not config.openai_api_key:
        template["provider"] = "template-fallback"
        template["provider_label"] = "template summary fallback"
        template["limitations"].append("OpenAI explanation-summary provider is configured, but no API key is available.")
        return template
    cached = _read_cached_summary(config, analysis)
    if cached:
        return cached
    generated = _openai_summary(config, analysis)
    if not generated:
        template["provider"] = "template-fallback"
        template["provider_label"] = "template summary fallback"
        template["limitations"].append("OpenAI explanation-summary generation failed; deterministic local template summary is shown.")
        return template
    _write_cached_summary(config, analysis, generated)
    return generated


def build_template_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    evaluation = analysis.get("evaluation", {})
    metrics = analysis.get("metrics", {})
    profile = analysis.get("profile", {})
    history = analysis.get("history", {})
    rationale = list(evaluation.get("rationale", []))[:3]
    coverage = evaluation.get("data_coverage_label", "unknown")
    data_note = history.get("realtime_note", "Data freshness depends on the configured providers.")
    positives = _positive_points(evaluation, metrics)
    risks = _risk_points(evaluation, metrics)
    return {
        "provider": "template",
        "provider_label": "template summary",
        "model": "deterministic-vcb-alt-v1",
        "role": SUMMARY_ROLE,
        "selection_source": SELECTION_SOURCE,
        "selection_method": SELECTION_METHOD,
        "language": "en",
        "headline": f"{analysis.get('ticker', '')} is a {evaluation.get('public_label', 'review')} setup.",
        "summary": (
            f"{analysis.get('ticker', '')} is classified as {evaluation.get('primary_archetype_label', 'unknown')} "
            f"with score {evaluation.get('combined_score', '-')}. The current industry context is "
            f"{profile.get('sector', 'Unknown')} / {profile.get('industry', 'Unknown')}. "
            "This text explains deterministic scoring output; it is not the selection engine."
        ),
        "why_selected": rationale or ["No selection rationale is available for this ticker."],
        "positive_factors": positives,
        "risk_flags": risks,
        "data_quality": {
            "coverage_score": evaluation.get("data_coverage_score", 0),
            "coverage_label": coverage,
            "coverage_detail": evaluation.get("data_coverage_detail", ""),
            "source": evaluation.get("source", ""),
            "as_of": evaluation.get("data_as_of", ""),
            "note": data_note,
        },
        "limitations": [
            "The summary provider explains deterministic scoring output and does not select stocks.",
            "Decision support only; not a trading instruction or personalized portfolio action.",
            "A human operator must verify filings, news, options, and analyst data before publication.",
        ],
    }


def _positive_points(evaluation: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    points: list[str] = []
    if int(evaluation.get("combined_score", 0)) >= 55:
        points.append("Composite score is above the internal review threshold.")
    if float(metrics.get("return_12w_pct") or 0) > 0:
        points.append(f"12-week momentum is positive at {metrics.get('return_12w_pct')}%.")
    if float(metrics.get("analyst_revision_score") or 0) > 0:
        points.append(f"Analyst/revision score is positive at {metrics.get('analyst_revision_score')}.")
    if float(metrics.get("call_open_interest") or 0) > float(metrics.get("put_open_interest") or 0) > 0:
        points.append("Options positioning shows more call open interest than put open interest.")
    return points or ["No strong positive non-price factor is available yet."]


def _risk_points(evaluation: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    risks = list(evaluation.get("warnings", []))[:2]
    if int(evaluation.get("data_coverage_score", 0)) < 60:
        risks.append("Data coverage is below the final-selection gate.")
    if float(metrics.get("short_interest_pct") or 0) >= 20:
        risks.append(f"Short interest is elevated at {metrics.get('short_interest_pct')}%.")
    if not metrics.get("intraday_source"):
        error = metrics.get("intraday_error")
        if error:
            risks.append(f"Near-real-time quote provider did not return data: {error}")
        else:
            risks.append("No real-time or near-real-time quote provider is currently active.")
    return risks


def _openai_summary(config: AppConfig, analysis: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": config.openai_model,
        "store": False,
        "max_output_tokens": 700,
        "text": {"format": {"type": "json_object"}},
        "input": (
            "Return strict JSON for a stock-screening explanation with keys: headline, summary, "
            "why_selected, positive_factors, risk_flags, limitations. Do not give trading instructions "
            "or personalized portfolio guidance. "
            "The explanation layer does not select stocks; it only explains deterministic scoring results. "
            f"Use only this data: {json.dumps(_compact_analysis(analysis), ensure_ascii=False)}"
        ),
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        response_payload = provider_request_json(config, "openai", request)
    except (ProviderFailure, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    text = _response_text(response_payload)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    template = build_template_summary(analysis)
    parsed["provider"] = "openai"
    parsed["provider_label"] = "OpenAI explanation summary"
    parsed["model"] = config.openai_model
    parsed["role"] = SUMMARY_ROLE
    parsed["selection_source"] = SELECTION_SOURCE
    parsed["selection_method"] = SELECTION_METHOD
    parsed["data_quality"] = template["data_quality"]
    for key in ("why_selected", "positive_factors", "risk_flags"):
        if not isinstance(parsed.get(key), list):
            parsed[key] = template[key]
    limitations = parsed.get("limitations", [])
    if isinstance(limitations, str):
        limitations = [limitations]
    elif not isinstance(limitations, list):
        limitations = []
    parsed["limitations"] = [
        "The summary provider explains deterministic scoring output and does not select stocks.",
        *limitations,
    ]
    return parsed


def _compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    evaluation = analysis.get("evaluation", {})
    metrics = analysis.get("metrics", {})
    profile = analysis.get("profile", {})
    return {
        "ticker": analysis.get("ticker"),
        "profile": profile,
        "evaluation": {
            key: evaluation.get(key)
            for key in [
                "primary_archetype_label",
                "combined_score",
                "public_label",
                "can_enter",
                "rationale",
                "warnings",
                "precision_notes",
                "data_coverage_score",
                "data_coverage_label",
                "data_coverage_detail",
                "source",
                "data_as_of",
            ]
        },
        "metrics": metrics,
    }


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return str(payload["output_text"])
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return str(content["text"])
    return ""


def _summary_cache_path(config: AppConfig, analysis: dict[str, Any]) -> Path:
    ticker = str(analysis.get("ticker", "unknown")).lower()
    source = str(analysis.get("evaluation", {}).get("source", "source")).replace("/", "_")
    version = str(analysis.get("evaluation", {}).get("scoring_version", "version")).replace("/", "_")
    return config.data_dir / "ai_summary_cache" / AI_SUMMARY_CACHE_VERSION / f"{ticker}_{source}_{version}.json"


def _read_cached_summary(config: AppConfig, analysis: dict[str, Any]) -> dict[str, Any]:
    path = _summary_cache_path(config, analysis)
    if not path.exists():
        return {}
    if time.time() - path.stat().st_mtime > config.ai_summary_cache_ttl_hours * 3600:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return {}


def _write_cached_summary(config: AppConfig, analysis: dict[str, Any], summary: dict[str, Any]) -> None:
    path = _summary_cache_path(config, analysis)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True), encoding="utf-8")
