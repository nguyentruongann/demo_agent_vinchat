from __future__ import annotations

import json
from typing import Any

from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import normalize_text


_ALLOWED_TASK_TYPES = {
    "place_structure_clarification",
    "detailed_review",
    "property_detail",
    "brand_detail",
    "comparison",
    "price_estimate",
    "price_lookup",
    "hotel_recommendation",
    "destination_recommendation",
    "policy_qa",
    "memory_recall",
    "amenity_check",
    "availability_check",
    "itinerary",
    "support_action",
    "general_qa",
}

_ALLOWED_RETRIEVAL_INTENTS = {
    "hotel",
    "booking_product",
    "attraction",
    "dining",
    "service",
    "promotion",
    "event",
    "golf",
    "mice",
    "policy",
    "payment",
}


def _bounded_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _normalize_task(raw: dict[str, Any], index: int) -> dict[str, Any] | None:
    goal = str(raw.get("goal") or raw.get("question") or "").strip()
    if not goal:
        return None

    task_type = str(raw.get("task_type") or "general_qa").strip().lower()
    if task_type not in _ALLOWED_TASK_TYPES:
        task_type = "general_qa"

    retrieval_intents: list[str] = []
    for value in raw.get("retrieval_intents") or []:
        intent = str(value or "").strip().lower()
        if intent in _ALLOWED_RETRIEVAL_INTENTS and intent not in retrieval_intents:
            retrieval_intents.append(intent)

    references: list[str] = []
    for value in raw.get("reference_phrases") or []:
        text = str(value or "").strip()
        if text and text not in references:
            references.append(text[:160])

    depends_on: list[str] = []
    for value in raw.get("depends_on") or []:
        ref = str(value or "").strip()
        if ref and ref not in depends_on:
            depends_on.append(ref[:40])

    return {
        "task_id": f"t{index}",
        "task_type": task_type,
        "goal": goal[:500],
        "must_answer": True,
        "needs_memory": _bool(raw.get("needs_memory")),
        "memory_reason": str(raw.get("memory_reason") or "").strip()[:300],
        "reference_phrases": references,
        "retrieval_intents": retrieval_intents,
        "needs_retrieval": _bool(raw.get("needs_retrieval", True)),
        "depends_on": depends_on,
    }


def _audit_missing_tasks(llm: LLMService, message: str, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Second-pass semantic audit so the planner cannot quietly drop clause 3+."""
    audit_schema = """{
  \"missing_tasks\": [
    {
      \"task_type\": \"general_qa\",
      \"goal\": \"missing customer-visible outcome only\",
      \"needs_memory\": false,
      \"memory_reason\": \"\",
      \"reference_phrases\": [],
      \"retrieval_intents\": [],
      \"needs_retrieval\": true,
      \"depends_on\": []
    }
  ]
}"""
    result = llm.json(
        system_prompt=(
            "You are a completeness auditor for a customer request task plan. Compare CURRENT_REQUEST with EXISTING_TASK_PLAN. "
            "Find every customer-visible question/requested outcome that is present in CURRENT_REQUEST but not represented by any existing task. "
            "This includes third, fourth, fifth, or later clauses; there is no two-clause limit. Do not add paraphrase duplicates and do not invent wishes the customer did not express. "
            "If nothing is missing, return missing_tasks=[]. Use the same closed task_type and retrieval_intents vocabularies as the planner. Return JSON only."
        ),
        user_prompt=(
            "CURRENT_REQUEST:\n" + str(message or "")
            + "\n\nEXISTING_TASK_PLAN:\n" + json.dumps(tasks, ensure_ascii=False)
            + "\n\nReturn exactly:\n" + audit_schema
        ),
    )
    output: list[dict[str, Any]] = []
    for raw in result.get("missing_tasks") or []:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_task(raw, len(tasks) + len(output) + 1)
        if not normalized:
            continue
        goal_norm = normalize_text(normalized.get("goal"))
        if any(goal_norm and goal_norm == normalize_text(item.get("goal")) for item in tasks + output):
            continue
        output.append(normalized)
    return output


def _deterministic_fallback_tasks(message: str) -> list[dict[str, Any]]:
    """Small safe fallback; the LLM remains the main semantic decomposer.

    This fallback deliberately recognizes only high-value shapes. It never tries to
    fully replace semantic decomposition, but it preserves the UX-critical case where
    a customer both questions an assumption and asks for a detailed review.
    """
    text = normalize_text(message)
    tasks: list[dict[str, Any]] = []

    place_markers = (
        "2 noi", "hai noi", "may noi", "tung noi", "co 2 noi", "co hai noi",
        "2 cho", "hai cho", "may cho", "tung cho", "co 2 cho", "co hai cho",
        "2 dia diem", "hai dia diem", "co phai 2",
    )
    review_markers = (
        "review", "chi tiet", "danh gia", "gioi thieu", "tung noi", "tung cho",
        "details", "detail", "tell me about",
    )
    if any(marker in text for marker in place_markers):
        tasks.append({
            "task_id": "t1",
            "task_type": "place_structure_clarification",
            "goal": "Determine whether the places/items the customer refers to are actually separate places.",
            "must_answer": True,
            "needs_memory": True,
            "memory_reason": "The assumed count/identity refers to information previously shown or discussed.",
            "reference_phrases": [],
            "retrieval_intents": ["hotel", "attraction", "service"],
            "needs_retrieval": True,
            "depends_on": [],
        })
    if any(marker in text for marker in review_markers):
        tasks.append({
            "task_id": f"t{len(tasks) + 1}",
            "task_type": "detailed_review",
            "goal": "Provide the detailed review requested by the customer for the correctly resolved place(s) or components.",
            "must_answer": True,
            "needs_memory": bool(tasks),
            "memory_reason": "The review target may depend on the preceding clarification/reference.",
            "reference_phrases": [],
            "retrieval_intents": ["hotel", "attraction", "dining", "service"],
            "needs_retrieval": True,
            "depends_on": ["t1"] if tasks else [],
        })

    if not tasks:
        tasks.append({
            "task_id": "t1",
            "task_type": "general_qa",
            "goal": str(message or "").strip()[:500] or "Answer the current customer request.",
            "must_answer": True,
            "needs_memory": False,
            "memory_reason": "",
            "reference_phrases": [],
            "retrieval_intents": [],
            "needs_retrieval": True,
            "depends_on": [],
        })
    return tasks


def understand_current_request(state: AgentState) -> AgentState:
    """Decompose the current request into every customer-visible task.

    The guardrail has already approved the raw current turn. This node therefore
    focuses only on *what the customer wants done now*. It does not resolve memory,
    retrieve facts, or answer. Most importantly, the number of tasks is data-driven:
    a request may contain one, two, five, or more independent clauses.
    """
    route = str(state.get("route") or "").strip()
    if route not in {"rag", "conversation_context"}:
        return {
            "request_tasks": [],
            "request_task_count": 0,
            "request_requires_memory": False,
            "request_understanding_summary": "Request understanding skipped for a non-factual route.",
            "request_understanding_confidence": 1.0,
            "request_understanding_source": "route_skip",
        }

    message = effective_user_message(state)
    llm = LLMService()
    prompt = (
        "You are the CURRENT-REQUEST task planner for a Vinpearl/VinWonders customer assistant. "
        "The input guardrail has already approved this turn. Your only job is to identify EVERY customer-visible outcome requested in the CURRENT message. "
        "Do not answer, do not retrieve facts, and do not assume the customer's wording is factually correct. "
        "Decompose the message into atomic tasks: each semantically independent question, requested action, comparison, clarification, review, price calculation, policy check, recommendation, or follow-up outcome is a separate task. "
        "There is no special two-clause limit: preserve all requested clauses in their original order. Do not collapse later clauses into the first one merely because they concern the same place. "
        "A task may depend on an earlier task. Example: 'ở đây có 2 nơi hả, review chi tiết từng nơi' MUST become (1) verify whether they are actually two places, and (2) provide the requested detailed review using the corrected structure from task 1. "
        "If the customer states an assumption as a question ('có 2 nơi hả?', 'phòng này ở 5 người được hả?'), represent the task as VERIFY/CLARIFY that assumption, not as a confirmed fact. "
        "Set needs_memory=true only when that task contains an omitted/relative reference whose target requires prior conversation, such as 'ở đây', 'cái đó', 'gói trên', 'từng nơi' after previously discussed items, or when the user explicitly asks to reuse/review earlier information. "
        "Memory need is task-specific: one clause may need memory while another is fully explicit. "
        "Use task_type only from this closed set: place_structure_clarification, detailed_review, property_detail, brand_detail, comparison, price_estimate, price_lookup, hotel_recommendation, destination_recommendation, policy_qa, memory_recall, amenity_check, availability_check, itinerary, support_action, general_qa. "
        "retrieval_intents may contain only: hotel, booking_product, attraction, dining, service, promotion, event, golf, mice, policy, payment. "
        "Return JSON only."
    )
    payload = {
        "current_message_original": state.get("user_message", ""),
        "current_message_sanitized": message,
        "has_prior_conversation": bool(state.get("conversation_turns")),
        "page_context_present": bool(state.get("page_context")),
    }
    schema = '''{
  "tasks": [
    {
      "task_type": "general_qa",
      "goal": "one complete customer-visible outcome",
      "needs_memory": false,
      "memory_reason": "why prior turns are required, or empty",
      "reference_phrases": ["that package"],
      "retrieval_intents": ["hotel"],
      "needs_retrieval": true,
      "depends_on": []
    }
  ],
  "overall_goal": "one sentence covering ALL requested outcomes",
  "confidence": 0.0
}'''

    try:
        result = llm.json(
            system_prompt=prompt,
            user_prompt=(
                "UNTRUSTED_CURRENT_REQUEST_JSON:\n"
                + json.dumps(payload, ensure_ascii=False)
                + "\n\nReturn exactly:\n"
                + schema
            ),
        )
        tasks: list[dict[str, Any]] = []
        for raw in result.get("tasks") or []:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_task(raw, len(tasks) + 1)
            if normalized:
                tasks.append(normalized)
        if not tasks:
            raise ValueError("task planner returned no valid tasks")

        try:
            missing_tasks = _audit_missing_tasks(llm, message, tasks)
        except Exception as audit_exc:
            missing_tasks = []
            print(f"[REQUEST PLAN AUDIT] skipped after error: {type(audit_exc).__name__}: {audit_exc}")
        if missing_tasks:
            tasks.extend(missing_tasks)
            for index, task in enumerate(tasks, start=1):
                task["task_id"] = f"t{index}"

        summary = str(result.get("overall_goal") or "").strip()[:800]
        if missing_tasks or not summary:
            summary = " | ".join(task["goal"] for task in tasks)
        confidence = _bounded_confidence(result.get("confidence"))
        source = "llm_task_decomposition"
    except Exception as exc:
        tasks = _deterministic_fallback_tasks(message)
        summary = " | ".join(task["goal"] for task in tasks)
        confidence = 0.0
        source = f"deterministic_fallback:{type(exc).__name__}"

    requires_memory = any(bool(task.get("needs_memory")) for task in tasks)
    print("\n===== CURRENT REQUEST UNDERSTANDING =====")
    print(f"Question: {message}")
    print(f"Task count: {len(tasks)}")
    for task in tasks:
        print(
            f"  {task.get('task_id')} type={task.get('task_type')} "
            f"memory={task.get('needs_memory')} retrieval={task.get('retrieval_intents')} "
            f"goal={task.get('goal')}"
        )
    print(f"Requires memory: {requires_memory}")
    print(f"Summary: {summary}")
    print("=========================================\n")

    return {
        "request_tasks": tasks,
        "request_task_count": len(tasks),
        "request_requires_memory": requires_memory,
        "request_understanding_summary": summary,
        "request_understanding_confidence": confidence,
        "request_understanding_source": source,
    }
