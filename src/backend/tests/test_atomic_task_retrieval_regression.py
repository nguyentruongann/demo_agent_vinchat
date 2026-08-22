from __future__ import annotations

from types import SimpleNamespace

from src.backend.agents.nodes import request_understanding
from src.backend.agents.nodes import retrieval as retrieval_node


def test_explicit_questions_repair_a_collapsed_task_plan() -> None:
    message = "Hotline đó hỗ trợ đặt phòng luôn à? Còn nhận phòng bên đó mấy giờ vậy?"
    collapsed = [
        {
            "task_id": "t1",
            "task_type": "policy_qa",
            "result_scope": "normal",
            "goal": "Explain booking hotline support and hotel check-in time.",
            "source_text": message,
            "retrieval_intents": ["policy"],
            "retrieval_queries": ["booking hotline and hotel check-in policy"],
            "needs_retrieval": True,
        }
    ]

    tasks, added = request_understanding._ensure_explicit_clause_coverage(message, collapsed)

    assert added == 1
    assert [task["task_id"] for task in tasks] == ["t1", "t2"]
    assert tasks[0]["source_text"] == "Hotline đó hỗ trợ đặt phòng luôn à?"
    assert tasks[1]["source_text"] == "Còn nhận phòng bên đó mấy giờ vậy?"


def test_matching_task_count_still_gets_exact_clause_provenance() -> None:
    message = "Có Grand Deluxe không? Villa ở được mấy người?"
    tasks = [
        {
            "task_id": "t1",
            "goal": "Check whether Grand Deluxe exists.",
            "source_text": message,
            "retrieval_queries": ["Grand Deluxe room"],
        },
        {
            "task_id": "t2",
            "goal": "Check villa capacity.",
            "source_text": message,
            "retrieval_queries": ["villa guest capacity"],
        },
    ]

    repaired, added = request_understanding._ensure_explicit_clause_coverage(message, tasks)

    assert added == 0
    assert repaired[0]["source_text"] == "Có Grand Deluxe không?"
    assert repaired[1]["source_text"] == "Villa ở được mấy người?"
    assert repaired[0]["retrieval_queries"][0] == "Có Grand Deluxe không?"
    assert repaired[1]["retrieval_queries"][0] == "Villa ở được mấy người?"


def test_comma_joined_independent_predicates_are_atomic() -> None:
    clauses = request_understanding._atomic_clause_candidates(
        "Sân đó có driving range không, buổi tối đánh được không?"
    )

    assert clauses == [
        "Sân đó có driving range không?",
        "buổi tối đánh được không?",
    ]


def test_compound_testcase_shapes_keep_every_customer_question() -> None:
    cases = {
        "Vậy chỗ đó nên chọn phòng thường hay villa? Có Grand Deluxe không?": 2,
        "Hotline đó hỗ trợ đặt phòng luôn à? Còn nhận phòng bên đó mấy giờ vậy?": 2,
        "Cái pass đó có vào được công viên nước không? Cuối tuần thì giá có khác không?": 2,
        "Sân nào? Còn Family Room ở được mấy người?": 2,
        "Nhà hàng hải sản nhìn hoàng hôn, đúng không? Ở đó có gần VinWonders không?": 2,
        "Đèn đêm cho 27 hố thì không đánh tối được à? Nhà hàng chứa được bao nhiêu người?": 2,
    }

    for message, expected_count in cases.items():
        assert len(request_understanding._atomic_clause_candidates(message)) == expected_count


def test_comma_inside_one_question_is_not_over_split() -> None:
    clauses = request_understanding._atomic_clause_candidates(
        "Nhà hàng có món Việt, món Nhật không?"
    )

    assert clauses == ["Nhà hàng có món Việt, món Nhật không?"]


def test_same_intent_questions_are_retrieved_and_assessed_per_task(monkeypatch) -> None:
    calls: list[str] = []

    class FakeRag:
        def hybrid_search(self, **kwargs):
            source_text = kwargs["user_message"]
            calls.append(source_text)
            if source_text.startswith("Hotline"):
                return (
                    [
                        {
                            "id": "faq-hotline",
                            "text": "Official booking hotline guidance.",
                            "score": 0.91,
                            "metadata": {
                                "entity_type": "faq",
                                "entity_id": "faq-hotline",
                                "entity_name": "Can the hotline help book a room?",
                            },
                            "matched_intent": "policy",
                        }
                    ],
                    {
                        "mode": "faq_exact",
                        "intent": "policy",
                        "intents": ["policy"],
                        "explicit_intents": ["policy"],
                        "constraint_derived_intents": [],
                        "intent_results": {
                            "policy": {
                                "status": "found",
                                "document_count": 1,
                                "candidate_count": 1,
                                "best_score": 0.91,
                                "faq_match": True,
                                "missing_destination_ids": [],
                            }
                        },
                        "faq_match": {"accepted": True},
                        "destinations": [],
                        "destination_ids": [],
                        "destination_names": [],
                        "keyword_candidate_count": 1,
                        "missing_destination_ids": [],
                    },
                )
            return (
                [],
                {
                    "mode": "semantic_fallback",
                    "intent": "policy",
                    "intents": ["policy"],
                    "explicit_intents": ["policy"],
                    "constraint_derived_intents": [],
                    "intent_results": {
                        "policy": {
                            "status": "not_found",
                            "document_count": 0,
                            "candidate_count": 0,
                            "best_score": 0.0,
                            "missing_destination_ids": [],
                        }
                    },
                    "faq_match": {"accepted": False},
                    "destinations": [],
                    "destination_ids": [],
                    "destination_names": [],
                    "keyword_candidate_count": 0,
                    "missing_destination_ids": [],
                },
            )

        @staticmethod
        def build_context_with_diagnostics(documents, exhaustive=False, task_aware=False):
            assert task_aware is True
            task_counts: dict[str, int] = {}
            for item in documents:
                for task_id in item.get("matched_task_ids") or []:
                    task_counts[task_id] = task_counts.get(task_id, 0) + 1
            return (
                "\n".join(item.get("text", "") for item in documents),
                {
                    "document_count": len(documents),
                    "branch_counts": {"policy": len(documents)},
                    "intents": ["policy"] if documents else [],
                    "entity_keys": [item.get("id") for item in documents],
                    "task_counts": task_counts,
                    "task_ids": list(task_counts),
                },
            )

    def fake_enrich(documents, **_kwargs):
        return documents, {
            "structured_price_document_count": 0,
            "structured_enrichment_count": 0,
            "price_estimate_packet": {},
            "price_estimate_destination_ids": [],
            "preferred_output_currency": "VND",
            "currency_conversion_guidance": "",
        }

    monkeypatch.setattr(retrieval_node, "get_rag_service", lambda: FakeRag())
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(top_k=4, min_relevance_score=0.35),
    )
    monkeypatch.setattr(retrieval_node, "enrich_retrieved_documents", fake_enrich)

    state = {
        "rag_query": "booking hotline and hotel check-in time",
        "user_message": "Hotline đó hỗ trợ đặt phòng luôn à? Còn nhận phòng bên đó mấy giờ vậy?",
        "original_language": "vi",
        "original_language_name": "Vietnamese",
        "resolved_destinations": [],
        "request_task_count": 2,
        "request_tasks": [
            {
                "task_id": "t1",
                "task_type": "policy_qa",
                "goal": "Can the hotline help book a room?",
                "source_text": "Hotline đó hỗ trợ đặt phòng luôn à?",
                "retrieval_intents": ["policy"],
                "retrieval_queries": ["official booking hotline assistance"],
                "needs_retrieval": True,
            },
            {
                "task_id": "t2",
                "task_type": "policy_qa",
                "goal": "What is the hotel check-in time?",
                "source_text": "Còn nhận phòng bên đó mấy giờ vậy?",
                "retrieval_intents": ["policy"],
                "retrieval_queries": ["official hotel check-in time"],
                "needs_retrieval": True,
            },
        ],
    }

    retrieved = retrieval_node.retrieve_context(state)

    assert calls == [
        "Hotline đó hỗ trợ đặt phòng luôn à?",
        "Còn nhận phòng bên đó mấy giờ vậy?",
    ]
    assert retrieved["task_retrieval_results"]["t1"]["status"] == "found"
    assert retrieved["task_retrieval_results"]["t2"]["status"] == "not_found"
    assert retrieved["context_task_ids"] == ["t1"]

    assessment = retrieval_node.assess_information({
        **state,
        **retrieved,
        "request_mode": "information",
        "resolution_mode": "information_only",
    })
    assert assessment["enough_information"] is True
    assert "t1" in assessment["assessment_reason"]
    assert "t2" in assessment["assessment_reason"]


def test_no_atomic_task_evidence_keeps_no_data_route(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_node,
        "get_settings",
        lambda: SimpleNamespace(top_k=4, min_relevance_score=0.35),
    )
    state = {
        "request_mode": "information",
        "resolution_mode": "information_only",
        "retrieved_documents": [],
        "task_retrieval_results": {
            "t1": {"status": "not_found", "best_score": 0.0, "serialized_document_count": 0},
            "t2": {"status": "not_found", "best_score": 0.0, "serialized_document_count": 0},
        },
    }

    result = retrieval_node.assess_information(state)
    assert result["enough_information"] is False
    assert result["insufficiency_action"] == "no_data"
