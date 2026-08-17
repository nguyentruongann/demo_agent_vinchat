"""Single source of truth for Vinpearl/VinWonders assistant scope.

The guardrail is the authoritative scope gate. Downstream nodes reuse this policy
instead of maintaining keyword deny-lists that can contradict the knowledge base.
"""

from __future__ import annotations


VINPEARL_SCOPE_POLICY = (
    "SCOPE POLICY (semantic, relationship-based): Decide scope from the requested deliverable and its "
    "relationship to Vinpearl/VinWonders/VinClub or a product/service documented in the Vinpearl knowledge "
    "base. OFFICIAL-FAQ PRIORITY: if a request is semantically equivalent to an item in the official Vinpearl "
    "FAQ knowledge base, it is IN SCOPE (unless independently blocked by the safety policy), even when the FAQ "
    "topic would normally look external in isolation. NEVER classify a turn as out of scope merely because it "
    "contains a word that can also describe an external service. "
    "\n\nIN SCOPE: Vinpearl/VinWonders destinations, hotels/resorts/rooms, dining, attractions, Safari, Grand World, "
    "golf, meetings/events/MICE, promotions/vouchers, VinClub, policies/regulations/FAQs, booking/payment/refund "
    "guidance, and support for those services. Also in scope are cross-domain components that Vinpearl itself "
    "documents or supports in its knowledge base, including ALL official FAQ categories: General, Hotels, "
    "Bundle (Hotels + Flights), Tours & Experiences, Flights, VinClub, and VinWonders & Safari. This includes all "
    "Vinpearl flight-ticket FAQ rules such as ticketing/payment/rescheduling, identity documents, baggage, liquids/items "
    "carried onboard, pets, pregnancy, and lost baggage; Hotel + Flight bundles; airport pickup/transfer and "
    "Vinpearl/VinWonders shuttle-bus questions; and weather-related operating "
    "or visit-policy questions about a Vinpearl/VinWonders venue (for example whether Safari can be visited during "
    "heavy rain). "
    "\n\nRELATION RULE: words such as flight, airline, airport, transfer, shuttle, bus, transport, weather, rain, passport, "
    "document, bank, payment, refund, cancellation, or passenger are NOT out-of-scope keywords. If they are part "
    "of a Vinpearl-supported product, package, venue, FAQ, policy, booking, or support question, keep the turn in "
    "scope. Do not require the user to repeat the word Vinpearl in every turn: a question can be in scope because "
    "its service/FAQ pattern is one that the Vinpearl knowledge base explicitly supports or because conversation "
    "context clearly binds it to a Vinpearl service. Judge the semantic object and requested answer, not isolated nouns. "
    "SUPPORTED-DESTINATION DISCOVERY: broad travel/discovery requests such as 'what can I do in Hanoi?', "
    "'có gì chơi ở Hà Nội?', or 'tư vấn du lịch Hà Nội' are IN SCOPE when the named destination resolves to the "
    "official Vinpearl destination catalog. In that case, interpret the deliverable as Vinpearl-KB-bounded discovery: "
    "answer only with grounded Vinpearl/VinWonders/partnered content available in the knowledge base, not as an "
    "unrestricted general-city guide. The user does not need to repeat the Vinpearl brand in that request. "
    "Conversation-memory meta questions are also IN SCOPE when they ask to recall, repeat, or summarize the user's "
    "own immediately preceding in-scope Vinpearl conversation (for example 'what did I just ask?', 'do you remember "
    "what we were discussing?', or 'summarize what we just discussed?'). These are conversation-context requests, "
    "not unrelated external deliverables. "
    "\n\nOUT OF SCOPE: a distinct external deliverable unrelated to Vinpearl-supported knowledge/services, such as live "
    "weather forecasts, independent airline fare/schedule/status search or booking, visa/passport application advice, "
    "general city taxi/public-transport route planning, unrelated news, coding, finance, or other non-Vinpearl work. "
    "A request can mention an external company or airline and still be in scope when the user is asking about a "
    "Vinpearl-documented flight-ticket/package rule. "
    "\n\nMIXED-SCOPE RULE (strict): block the whole turn only when the user actually requests a SEPARATE out-of-scope "
    "deliverable in addition to an in-scope Vinpearl deliverable. Do NOT treat an ancillary fact, comparison term, "
    "service component, or contextual noun inside one Vinpearl question as a separate deliverable. "
    "\n\nCAPABILITY RULE: the assistant may explain policies and self-service steps, but it cannot execute payments, "
    "change/cancel/refund a user's personal booking, inspect private records, or claim that an operational action "
    "was completed. Those case-specific actions may require human support; they are not out of scope merely because "
    "the chatbot cannot perform them."
)


SCOPE_DECISION_EXAMPLES = (
    "Examples that MUST be treated consistently: "
    "(1) 'May I change my confirmed hotel + flight booking after payment?' => in scope/RAG; "
    "(2) 'Can I reschedule my flight date and time?' when asking the Vinpearl flight-ticket FAQ => in scope/RAG; "
    "(3) 'What documents do I need onboard for the flight ticket sold/supported by Vinpearl?' => in scope/RAG; "
    "(4) 'Does VinWonders provide a shuttle bus?' => in scope/RAG; "
    "(5) 'Can I visit Vinpearl Safari when it rains heavily?' => in scope/RAG; "
    "(6) 'What is the weather in Phu Quoc tomorrow?' => out of scope because it asks for a live external forecast; "
    "(7) 'Find the cheapest Vietjet flight tomorrow' => out of scope because it asks for independent live flight search; "
    "(8) 'Explain Vinpearl's hotel policy and also write Python code' => block the whole turn under strict mixed scope; "
    "(9) after an in-scope Vinpearl discussion, 'What was my last question?' => in scope as conversation memory."
)


def scope_policy_prompt(*, include_examples: bool = True) -> str:
    """Return the canonical scope policy used by every semantic classifier."""
    if include_examples:
        return f"{VINPEARL_SCOPE_POLICY}\n\n{SCOPE_DECISION_EXAMPLES}"
    return VINPEARL_SCOPE_POLICY
