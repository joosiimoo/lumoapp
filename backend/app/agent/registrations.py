from __future__ import annotations

from app.agent.generative_ui import GenerativeUIRegistration, GenerativeUIRegistry
from app.agent.tools import ToolRegistration, ToolRegistry


RESOLVE_PRODUCT = ToolRegistration(
    tool_id="catalog.resolve_product",
    version=1,
    input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
    output_schema={
        "type": "object",
        "required": ["match"],
        "properties": {
            "match": {"enum": ["unique", "ambiguous", "none"]},
            "product": {"type": ["object", "null"]},
            "candidates": {"type": "array"},
        },
    },
    permission="sale.create",
    policy_id="CAT-001",
    requires_idempotency=False,
    side_effect="read",
)

START_SALE = ToolRegistration(
    tool_id="sale.start",
    version=1,
    input_schema={
        "type": "object",
        "properties": {"conversation_id": {"type": ["string", "null"]}},
    },
    output_schema={
        "type": "object",
        "required": ["sale_session_id", "status", "created", "item_count"],
        "properties": {"status": {"enum": ["open", "ready_to_charge"]}},
    },
    permission="sale.create",
    policy_id="INT-001",
    requires_idempotency=True,
    side_effect="write",
)

TOTALIZE_SALE = ToolRegistration(
    tool_id="sale.totalize",
    version=1,
    input_schema={
        "type": "object",
        "properties": {"conversation_id": {"type": ["string", "null"]}},
    },
    output_schema={
        "type": "object",
        "required": ["sale_session_id", "status", "currency", "item_count", "subtotal", "total", "items"],
        "properties": {
            "status": {"enum": ["ready_to_charge"]},
        },
    },
    permission="sale.create",
    policy_id="SALE-003",
    requires_idempotency=True,
    side_effect="write",
)

ADD_ITEM = ToolRegistration(
    tool_id="sale.add_item",
    version=1,
    input_schema={
        "type": "object",
        "required": ["sale_session_id", "product_id", "quantity", "unit"],
        "properties": {
            "sale_session_id": {"type": "string"},
            "product_id": {"type": "string"},
            "quantity": {"type": "string"},
            "unit": {"enum": ["gram", "kilogram", "unit", "package"]},
        },
    },
    output_schema={"type": "object", "required": ["sale_item_id", "line_total"]},
    permission="sale.create",
    policy_id="SALE-001",
    requires_idempotency=True,
    side_effect="write",
)

SALE_SUMMARY = GenerativeUIRegistration(
    component="sale_summary",
    version=1,
    data_schema={
        "type": "object",
        "required": ["sale_session_id", "status", "item_count", "subtotal", "total", "items"],
    },
)

SALE_ITEM_ADDED = GenerativeUIRegistration(
    component="sale_item_added",
    version=1,
    data_schema={
        "type": "object",
        "required": [
            "sale_session_id",
            "sale_item_id",
            "product_name",
            "quantity_normalized",
            "line_total",
        ],
    },
)


def register_conversational_sale_tools(registry: ToolRegistry) -> None:
    for item in (RESOLVE_PRODUCT, START_SALE, ADD_ITEM, TOTALIZE_SALE):
        registry.register(item)


def register_sale_item_added_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(SALE_ITEM_ADDED)


def register_sale_summary_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(SALE_SUMMARY)
