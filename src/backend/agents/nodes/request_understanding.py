from __future__ import annotations

import json
import re
from typing import Any

from src.backend.agents.nodes.guardrail import effective_user_message
from src.backend.agents.state import AgentState
from src.backend.services.llm import LLMService
from src.backend.services.query_parser import (
    detect_intents,
    detect_retrieval_facets,
    normalize_text,
)


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

_ALLOWED_RESULT_SCOPES = {"normal", "exhaustive"}


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


_BOOKING_PURCHASE_MARKERS = (
    "mua ve", "dat ve", "nen mua ve", "goi ve", "combo ve",
    "buy ticket", "book ticket", "purchase ticket", "ticket purchase",
    "ticket package", "booking package",
)

_BOOKING_PROCEDURE_MARKERS = (
    "bat dau", "the nao", "cach ", "huong dan", "o dau", "nen ",
    "how ", "where ", "start", "guide", "which ", "should ",
)

_RELATIVE_AREA_MARKERS = (
    "nhung khu do", "cac khu do", "may khu do", "nhung khu nay", "cac khu nay",
    "nhung khu vua noi", "cac khu vua noi", "those zones", "those areas",
    "these zones", "these areas", "the zones above", "the areas above",
)

_LODGING_MARKERS = (
    "hotel", "resort", "room", "villa", "khach san", "phong", "biet thu",
)


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


def _repair_task_contract(task: dict[str, Any]) -> dict[str, Any]:
    """Repair purchase guidance and deictic zone-price planner mistakes.

    The verbatim customer clause is authoritative. Buying/booking guidance is
    demoted only when it has procedural purchase semantics and the deterministic
    facet detector finds no explicit numeric money question.
    """
    output = dict(task)
    source_text = str(output.get("source_text") or output.get("goal") or "").strip()
    padded = f" {normalize_text(source_text)} "
    purchase_guidance = (
        any(marker in padded for marker in _BOOKING_PURCHASE_MARKERS)
        and any(marker in padded for marker in _BOOKING_PROCEDURE_MARKERS)
    )
    explicit_price = bool(
        detect_retrieval_facets(source_text, "").get("price_requested")
    )
    task_type = str(output.get("task_type") or "general_qa")

    intents = list(output.get("retrieval_intents") or [])
    if purchase_guidance and "booking_product" not in intents:
        intents.append("booking_product")
    if (
        task_type in {"price_lookup", "price_estimate"}
        and purchase_guidance
        and not explicit_price
    ):
        output["task_type_repaired_from"] = task_type
        output["task_type"] = "general_qa"

    relative_area_price = bool(
        explicit_price
        and any(marker in normalize_text(source_text) for marker in _RELATIVE_AREA_MARKERS)
    )
    if relative_area_price:
        output["needs_memory"] = True
        output["memory_reason"] = (
            "The plural area/zone reference must be resolved from the immediately preceding turn."
        )
        if not any(marker in normalize_text(source_text) for marker in _LODGING_MARKERS):
            intents = [intent for intent in intents if intent != "hotel"]
        for intent in ("attraction", "booking_product"):
            if intent not in intents:
                intents.append(intent)
        output["result_scope"] = "normal"
        output["retrieval_queries"] = [
            "VinWonders admission ticket prices and whether the zones mentioned in the immediately preceding turn are separately priced or included",
            source_text[:500],
        ]
    if explicit_price and str(output.get("task_type") or "") == "general_qa":
        output["task_type"] = "price_lookup"
    output["retrieval_intents"] = intents

    output["price_requested"] = bool(
        output.get("task_type") in {"price_lookup", "price_estimate"}
    )
    return output


def _normalize_task(raw: dict[str, Any], index: int) -> dict[str, Any] | None:
    goal = str(raw.get("goal") or raw.get("question") or "").strip()
    if not goal:
        return None

    task_type = str(raw.get("task_type") or "general_qa").strip().lower()
    if task_type not in _ALLOWED_TASK_TYPES:
        task_type = "general_qa"

    result_scope = str(raw.get("result_scope") or "normal").strip().lower()
    if result_scope not in _ALLOWED_RESULT_SCOPES:
        result_scope = "normal"

    retrieval_intents: list[str] = []
    for value in raw.get("retrieval_intents") or []:
        intent = str(value or "").strip().lower()
        if intent in _ALLOWED_RETRIEVAL_INTENTS and intent not in retrieval_intents:
            retrieval_intents.append(intent)

    retrieval_queries: list[str] = []
    seen_retrieval_queries: set[str] = set()
    for value in raw.get("retrieval_queries") or []:
        text = str(value or "").strip()
        normalized = normalize_text(text)
        if not normalized or normalized in seen_retrieval_queries:
            continue
        seen_retrieval_queries.add(normalized)
        retrieval_queries.append(text[:500])
        if len(retrieval_queries) >= 3:
            break

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

    return _repair_task_contract({
        "task_id": f"t{index}",
        "task_type": task_type,
        "result_scope": result_scope,
        "goal": goal[:500],
        # Preserve the exact customer clause as a separate field.  ``goal`` is an
        # English retrieval rewrite, while ``source_text`` is required for exact FAQ
        # matching, Vietnamese predicate preservation, and auditability.
        "source_text": str(
            raw.get("source_text")
            or raw.get("original_text")
            or raw.get("question")
            or ""
        ).strip()[:500],
        "must_answer": True,
        "needs_memory": _bool(raw.get("needs_memory")),
        "memory_reason": str(raw.get("memory_reason") or "").strip()[:300],
        "reference_phrases": references,
        "retrieval_intents": retrieval_intents,
        "retrieval_queries": retrieval_queries,
        "needs_retrieval": _bool(raw.get("needs_retrieval", True)),
        "depends_on": depends_on,
    })


_REQUEST_MARKERS = (
    "cho toi biet", "cho minh biet", "tu van", "goi y", "so sanh", "review",
    "liet ke", "huong dan", "can lam gi", "nen chon", "nen mua", "nen o",
    "tell me", "recommend", "compare", "list", "show me", "how do i",
    "what should", "which should",
)

_MEMORY_REFERENCE_MARKERS = (
    "cai do", "cho do", "goi do", "noi do", "o do", "ben do", "cai kia",
    "cho kia", "goi kia", "vua noi", "luc nay", "o tren", "phia tren",
    "nhung khu do", "cac khu do", "may khu do", "nhung khu nay", "cac khu nay",
    "that one", "that place", "there", "the above", "mentioned earlier",
    "those zones", "those areas", "these zones", "these areas",
)


def _atomic_clause_candidates(message: str) -> list[str]:
    """Extract explicit question/request clauses without pretending to be an LLM.

    This is a deterministic *coverage guard*, not the main semantic planner.  It is
    intentionally conservative: question marks, semicolons/newlines, and numbered or
    bulleted requests are boundaries; ordinary descriptive sentences remain attached
    to the semantic LLM plan instead of becoming fake tasks.
    """
    raw = str(message or "").strip()
    if not raw:
        return []

    # Make numbered/bulleted lists visible as boundaries while preserving their text.
    prepared = re.sub(r"\s+(?=(?:[-*•]|\d+[.)])\s+)", "\n", raw)
    pieces = re.split(r"(?<=[?？;；])\s*|\n+", prepared)

    def split_compound_question(piece: str) -> list[str]:
        """Split comma-joined predicates only when every side is interrogative."""
        if "?" not in piece and "？" not in piece:
            return [piece]
        body = piece.rstrip().rstrip("?？").strip()
        parts = [value.strip() for value in re.split(r"\s*,\s*", body) if value.strip()]
        if len(parts) <= 1:
            return [piece]

        question_markers = (
            "khong", "sao", "nao", "may gio", "bao nhieu", "the nao",
            "khi nao", "luc nao", "duoc chu", "right", "how", "what",
            "when", "where", "which", "can ", "does ", "do ", "is ", "are ",
        )
        if not all(
            any(marker in f" {normalize_text(part)} " for marker in question_markers)
            for part in parts
        ):
            return [piece]
        return [f"{part}?" for part in parts]

    expanded_pieces = [
        clause
        for piece in pieces
        for clause in split_compound_question(piece)
    ]
    output: list[str] = []
    seen: set[str] = set()
    for piece in expanded_pieces:
        clause = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", piece).strip()
        if not clause:
            continue
        normalized = normalize_text(clause)
        is_explicit_question = "?" in clause or "？" in clause
        is_explicit_request = any(marker in normalized for marker in _REQUEST_MARKERS)
        if not (is_explicit_question or is_explicit_request):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(clause[:500])
    return output


def _fallback_task_for_clause(clause: str, index: int) -> dict[str, Any]:
    """Create one safe retrieval task when an explicit clause escaped the LLM plan."""
    normalized = normalize_text(clause)
    padded = f" {normalized} "

    def has_any(markers: tuple[str, ...]) -> bool:
        return any(f" {normalize_text(marker)} " in padded for marker in markers)

    intents = list(detect_intents(clause))
    facets = detect_retrieval_facets(clause, clause)

    payment_markers = (
        "thanh toan", "chuyen khoan", "ngan hang", "the ngan hang", "the tin dung",
        "bank transfer", "bank account", "payment", "credit card", "debit card",
    )
    policy_markers = (
        "chinh sach", "quy dinh", "nhan phong", "tra phong", "check in", "check out",
        "hotline", "lien he", "tong dai", "contact", "bring food", "mang do an",
        "tre em", "child policy", "hoan huy", "doi lich", "refund", "cancel",
    )
    booking_markers = (
        # Do not add accent-stripped single tokens ``ve``/``goi`` here: Vietnamese
        # "vé/về" and "gói/gọi" collapse to the same forms. detect_intents() keeps
        # accents and already handles the unambiguous ticket/package meanings.
        "combo", "pass", "ticket", "package", "voucher", "dat phong",
        "book room", "booking",
    )
    if has_any(payment_markers):
        for intent in ("payment", "policy"):
            if intent not in intents:
                intents.append(intent)
    elif has_any(policy_markers) and "policy" not in intents:
        intents.append("policy")
    if has_any(booking_markers) and "booking_product" not in intents:
        intents.append("booking_product")

    if facets.get("cost_estimate_requested"):
        task_type = "price_estimate"
    elif facets.get("price_requested"):
        task_type = "price_lookup"
    elif {"policy", "payment"} & set(intents):
        task_type = "policy_qa"
    else:
        task_type = "general_qa"

    needs_memory = has_any(_MEMORY_REFERENCE_MARKERS)
    return _repair_task_contract({
        "task_id": f"t{index}",
        "task_type": task_type,
        "result_scope": "normal",
        "goal": clause[:500],
        "source_text": clause[:500],
        "must_answer": True,
        "needs_memory": needs_memory,
        "memory_reason": (
            "The atomic clause contains a relative reference to earlier conversation context."
            if needs_memory else ""
        ),
        "reference_phrases": [],
        "retrieval_intents": intents,
        "retrieval_queries": [clause[:500]],
        "needs_retrieval": True,
        "depends_on": [],
    })


def _ensure_explicit_clause_coverage(
    message: str,
    tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Guarantee one task per explicit question/list item.

    The semantic planner remains authoritative for meaning.  This guard only repairs
    the observable failure mode where it returns fewer tasks than the number of
    explicit customer questions.  Existing tasks are aligned in order and missing
    clauses receive bounded multilingual retrieval tasks.
    """
    clauses = _atomic_clause_candidates(message)
    if len(clauses) <= 1:
        return tasks, 0

    def align_task_to_clause(task: dict[str, Any], clause: str) -> dict[str, Any]:
        """Force one-to-one verbatim provenance and keep it as the first query."""
        aligned = dict(task)
        aligned["source_text"] = clause
        queries = [clause, *(aligned.get("retrieval_queries") or [])]
        deduped: list[str] = []
        seen: set[str] = set()
        for value in queries:
            text = str(value or "").strip()
            key = normalize_text(text)
            if key and key not in seen:
                seen.add(key)
                deduped.append(text[:500])
        aligned["retrieval_queries"] = deduped[:3]
        return aligned

    if len(tasks) >= len(clauses):
        # A superficially valid plan may still put the whole compound message into
        # every source_text.  When the counts match, ordered one-to-one alignment is
        # deterministic and prevents those tasks from collapsing again at FAQ/RAG.
        if len(tasks) == len(clauses):
            tasks = [
                align_task_to_clause(task, clause)
                for task, clause in zip(tasks, clauses)
            ]
        return tasks, 0

    repaired: list[dict[str, Any]] = []
    for index, clause in enumerate(clauses):
        if index < len(tasks):
            repaired.append(align_task_to_clause(tasks[index], clause))
        else:
            repaired.append(_fallback_task_for_clause(clause, index + 1))

    # Keep semantic tasks that go beyond punctuation-level clauses (for example a
    # planner may split a comparison into verification + recommendation).
    repaired.extend(dict(task) for task in tasks[len(clauses):])
    for index, task in enumerate(repaired, start=1):
        task["task_id"] = f"t{index}"
    return repaired, max(0, len(repaired) - len(tasks))


_FACET_LABELS = {
    "hotel": "hotels and rooms",
    "booking_product": "bookable products and numeric prices",
    "attraction": "attractions and entertainment",
    "dining": "dining and restaurants",
    "service": "services and amenities",
    "promotion": "promotions and offers",
    "event": "events and shows",
    "golf": "golf",
    "mice": "meetings and events facilities",
    "policy": "policies and rules",
    "payment": "payment guidance",
}


def _ensure_requested_facet_coverage(
    message: str,
    tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Split implicit multi-facet requests even if both LLM passes collapse them."""
    explicit_intents = [
        intent for intent in detect_intents(message)
        if intent in _ALLOWED_RETRIEVAL_INTENTS and intent != "booking_product"
    ]
    facets = detect_retrieval_facets(message, message)
    price_requested = bool(facets.get("price_requested"))
    cost_estimate_requested = bool(facets.get("cost_estimate_requested"))
    if not (len(explicit_intents) >= 3 or (len(explicit_intents) >= 2 and price_requested)):
        return tasks, 0

    full_message_key = normalize_text(message)

    def is_atomic_for(task: dict[str, Any], intent: str) -> bool:
        task_intents = list(task.get("retrieval_intents") or [])
        source_key = normalize_text(task.get("source_text") or "")
        return intent in task_intents and (
            len(task_intents) == 1 or (source_key and source_key != full_message_key)
        )

    repaired = [dict(task) for task in tasks]
    if len(repaired) == 1 and len(repaired[0].get("retrieval_intents") or []) > 1:
        repaired = []

    additions = 0
    for intent in explicit_intents:
        if any(is_atomic_for(task, intent) for task in repaired):
            continue
        label = _FACET_LABELS[intent]
        repaired.append({
            "task_id": "",
            "task_type": "policy_qa" if intent in {"policy", "payment"} else "general_qa",
            "result_scope": "normal",
            "goal": f"Answer the requested part about {label}.",
            "source_text": str(message or "").strip()[:500],
            "must_answer": True,
            "needs_memory": False,
            "memory_reason": "",
            "reference_phrases": [],
            "retrieval_intents": [intent],
            "retrieval_queries": [f"{message} | Focus only on {label}"[:500]],
            "needs_retrieval": True,
            "depends_on": [],
        })
        additions += 1

    price_covered = any(
        str(task.get("task_type") or "") in {"price_lookup", "price_estimate"}
        for task in repaired
    )
    if price_requested and not price_covered:
        price_intents = [
            intent for intent in explicit_intents
            if intent in {"hotel", "attraction", "dining", "service", "promotion"}
        ]
        price_intents.append("booking_product")
        repaired.append({
            "task_id": "",
            "task_type": "price_estimate" if cost_estimate_requested else "price_lookup",
            "result_scope": "normal",
            "goal": "Provide the requested grounded cost or price information.",
            "source_text": str(message or "").strip()[:500],
            "must_answer": True,
            "needs_memory": False,
            "memory_reason": "",
            "reference_phrases": [],
            "retrieval_intents": price_intents,
            "retrieval_queries": [f"{message} | Focus on numeric prices and cost"[:500]],
            "needs_retrieval": True,
            "depends_on": [],
            "price_requested": True,
        })
        additions += 1

    for index, task in enumerate(repaired, start=1):
        task["task_id"] = f"t{index}"
    return repaired, additions


def _audit_missing_tasks(
    llm: LLMService,
    message: str,
    tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, list[str]]]:
    """Second-pass semantic audit for task coverage, result scope, and evidence type."""
    audit_schema = """{
  \"missing_tasks\": [],
  \"scope_updates\": [],
  \"retrieval_updates\": []
}"""
    result = llm.json(
        system_prompt=(
            "You are a completeness auditor for a customer request task plan. Compare CURRENT_REQUEST with EXISTING_TASK_PLAN. "
            "Find every customer-visible question/requested outcome that is present in CURRENT_REQUEST but not represented by any existing task. "
            "Also audit each existing task's result_scope semantically. result_scope=exhaustive means the customer wants the COMPLETE SET of matching items/records/options, regardless of the exact vocabulary or language used; result_scope=normal means a representative/single/non-complete result is acceptable. "
            "If a task's scope is wrong, put only that task_id and the corrected result_scope in scope_updates. Do not use a keyword checklist; infer coverage from meaning. "
            "Also audit retrieval_intents by evidence type. If the task asks for purchasable/bookable tickets, passes, packages, combos, vouchers, memberships, or equivalent catalog products, booking_product should be present; promotion is only for actual discounts/offers/deals, hotel is for properties/rooms. Only emit retrieval_updates when the existing evidence types are materially wrong or incomplete. "
            "When an update is needed, each scope_updates item must be exactly {task_id, result_scope}; each retrieval_updates item must be exactly {task_id, retrieval_intents}. Missing tasks use the same task object shape as the planner, including result_scope and a verbatim source_text clause copied from CURRENT_REQUEST. "
            "This includes third, fourth, fifth, or later clauses; there is no two-clause limit. Do not add paraphrase duplicates and do not invent wishes the customer did not express. "
            "If nothing is missing and no scope/evidence-type correction is needed, return missing_tasks=[], scope_updates=[], retrieval_updates=[]. Use the same closed task_type and retrieval_intents vocabularies as the planner. Return JSON only."
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

    valid_task_ids = {str(item.get("task_id") or "") for item in tasks}
    scope_updates: dict[str, str] = {}
    for raw in result.get("scope_updates") or []:
        if not isinstance(raw, dict):
            continue
        task_id = str(raw.get("task_id") or "").strip()
        result_scope = str(raw.get("result_scope") or "").strip().lower()
        if task_id in valid_task_ids and result_scope in _ALLOWED_RESULT_SCOPES:
            scope_updates[task_id] = result_scope

    retrieval_updates: dict[str, list[str]] = {}
    for raw in result.get("retrieval_updates") or []:
        if not isinstance(raw, dict):
            continue
        task_id = str(raw.get("task_id") or "").strip()
        if task_id not in valid_task_ids:
            continue
        values: list[str] = []
        for value in raw.get("retrieval_intents") or []:
            intent = str(value or "").strip().lower()
            if intent in _ALLOWED_RETRIEVAL_INTENTS and intent not in values:
                values.append(intent)
        if values:
            retrieval_updates[task_id] = values
    return output, scope_updates, retrieval_updates


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
            "result_scope": "normal",
            "goal": "Determine whether the places/items the customer refers to are actually separate places.",
            "source_text": str(message or "").strip()[:500],
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
            "result_scope": "normal",
            "goal": "Provide the detailed review requested by the customer for the correctly resolved place(s) or components.",
            "source_text": str(message or "").strip()[:500],
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
            "result_scope": "normal",
            "goal": str(message or "").strip()[:500] or "Answer the current customer request.",
            "source_text": str(message or "").strip()[:500],
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
        "When a customer gives multiple independent requirements or preferences and also asks how, where, or to whom they should communicate them, create one task for each independently answerable requirement plus a separate informational contact/communication-guidance task. Do not collapse the communication channel into the requirements themselves. "
        "A task may depend on an earlier task. Example: 'ở đây có 2 nơi hả, review chi tiết từng nơi' MUST become (1) verify whether they are actually two places, and (2) provide the requested detailed review using the corrected structure from task 1. "
        "If the customer states an assumption as a question ('có 2 nơi hả?', 'phòng này ở 5 người được hả?'), represent the task as VERIFY/CLARIFY that assumption, not as a confirmed fact. "
        "Set needs_memory=true only when that task contains an omitted/relative reference whose target requires prior conversation, such as 'ở đây', 'cái đó', 'gói trên', 'từng nơi' after previously discussed items, or when the user explicitly asks to reuse/review earlier information. "
        "Memory need is task-specific: one clause may need memory while another is fully explicit. "
        "Use task_type only from this closed set: place_structure_clarification, detailed_review, property_detail, brand_detail, comparison, price_estimate, price_lookup, hotel_recommendation, destination_recommendation, policy_qa, memory_recall, amenity_check, availability_check, itinerary, support_action, general_qa. "
        "retrieval_intents may contain only: hotel, booking_product, attraction, dining, service, promotion, event, golf, mice, policy, payment. "
        "Write every goal as a standalone faithful English retrieval query, even when the current request is in another language. A request that only asks for a contact channel or how to notify the company is informational guidance, not an operation on a customer record; represent it as policy_qa or general_qa and include policy evidence when appropriate. "
        "For each task, also return retrieval_queries with one or two concise English search variants. The first must preserve the concrete request; the second should express the broader source-style concept that an official FAQ or policy is likely to use, without adding facts. For example, concrete guest preferences may be abstracted as a special requirement, while still preserving the requested contact/procedure relation. "
        "For each task, source_text MUST be the smallest faithful verbatim clause copied from current_message_sanitized that expresses that task. Never put the whole compound message into every source_text. "
        "Choose retrieval_intents by evidence type, not by broad brand words: a task asking for prices/listing of bookable tickets, passes, packages, combos, vouchers, memberships, or similar purchasable catalog items should include booking_product; promotion is for discounts/offers/deals, and hotel is for properties/rooms. Infer this semantically rather than requiring literal English labels. "
        "Use price_lookup only when the customer explicitly asks for a numeric price, cost, fare, fee, budget, total, estimate, or how much. Asking how/where to buy or book, how to start, which purchase channel to use, or requesting ticket-purchase guidance WITHOUT a money question is general_qa with booking_product evidence; the mere presence of ticket/package/booking words never makes it price_lookup. "
        "For every task also set result_scope to exactly normal or exhaustive. Use exhaustive when the customer semantically requests the COMPLETE SET of matching records/items/options (for example all/every/complete/full list, list everything, what are all available types/packages, show the whole catalog), regardless of the exact vocabulary or language used. Do not require any particular keyword; infer the requested coverage from meaning. Use normal when representative, best, nearest, a few, one, or otherwise non-complete evidence is enough. "
        "Return JSON only."
    )
    payload = {
        "current_message_sanitized": message,
        "has_prior_conversation": bool(state.get("conversation_turns")),
        "page_context_present": bool(state.get("page_context")),
    }
    schema = '''{
  "tasks": [
    {
      "task_type": "general_qa",
      "result_scope": "normal",
      "goal": "one complete customer-visible outcome",
      "source_text": "verbatim clause from the customer's current message",
      "needs_memory": false,
      "memory_reason": "why prior turns are required, or empty",
      "reference_phrases": ["that package"],
      "retrieval_intents": ["hotel"],
      "retrieval_queries": ["concrete faithful search query", "broader source-style paraphrase"],
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
            missing_tasks, scope_updates, retrieval_updates = _audit_missing_tasks(llm, message, tasks)
        except Exception as audit_exc:
            missing_tasks, scope_updates, retrieval_updates = [], {}, {}
            print(f"[REQUEST PLAN AUDIT] skipped after error: {type(audit_exc).__name__}: {audit_exc}")
        if scope_updates or retrieval_updates:
            for task in tasks:
                task_id = str(task.get("task_id") or "")
                if task_id in scope_updates:
                    task["result_scope"] = scope_updates[task_id]
                if task_id in retrieval_updates:
                    merged_intents = list(task.get("retrieval_intents") or [])
                    for intent in retrieval_updates[task_id]:
                        if intent not in merged_intents:
                            merged_intents.append(intent)
                    task["retrieval_intents"] = merged_intents
        if missing_tasks:
            tasks.extend(missing_tasks)
            for index, task in enumerate(tasks, start=1):
                task["task_id"] = f"t{index}"

        tasks, clause_additions = _ensure_explicit_clause_coverage(message, tasks)
        tasks, facet_additions = _ensure_requested_facet_coverage(message, tasks)
        deterministic_additions = clause_additions + facet_additions

        summary = str(result.get("overall_goal") or "").strip()[:800]
        if missing_tasks or deterministic_additions or not summary:
            summary = " | ".join(task["goal"] for task in tasks)
        confidence = _bounded_confidence(result.get("confidence"))
        source = "llm_task_decomposition"
    except Exception as exc:
        tasks = _deterministic_fallback_tasks(message)
        tasks, clause_additions = _ensure_explicit_clause_coverage(message, tasks)
        tasks, facet_additions = _ensure_requested_facet_coverage(message, tasks)
        deterministic_additions = clause_additions + facet_additions
        summary = " | ".join(task["goal"] for task in tasks)
        confidence = 0.0
        source = f"deterministic_fallback:{type(exc).__name__}"

    tasks = [_repair_task_contract(task) for task in tasks]
    requires_memory = any(bool(task.get("needs_memory")) for task in tasks)
    print("\n===== CURRENT REQUEST UNDERSTANDING =====")
    print(f"Question: {message}")
    print(f"Task count: {len(tasks)}")
    for task in tasks:
        print(
            f"  {task.get('task_id')} type={task.get('task_type')} scope={task.get('result_scope', 'normal')} "
            f"memory={task.get('needs_memory')} retrieval={task.get('retrieval_intents')} "
            f"source_text={task.get('source_text')} goal={task.get('goal')}"
        )
        if task.get("retrieval_queries"):
            print(f"    retrieval_queries={task.get('retrieval_queries')}")
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
