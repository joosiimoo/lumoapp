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
        "required": ["sale_session_id", "quantity", "unit", "source_type"],
        "properties": {
            "sale_session_id": {"type": "string"},
            "quantity": {"type": "string"},
            "unit": {"enum": ["gram", "kilogram", "unit", "package"]},
            "source_type": {"enum": ["catalog", "free_concept"]},
            "product_id": {"type": ["string", "null"]},
            "concept_name": {"type": "string"},
            "unit_price": {
                "type": "object",
                "required": ["amount", "currency"],
                "properties": {"amount": {"type": "string"}, "currency": {"type": "string"}},
            },
            "price_override": {
                "type": "object",
                "required": ["unit_price", "reason"],
                "properties": {
                    "unit_price": {
                        "type": "object",
                        "required": ["amount", "currency"],
                        "properties": {"amount": {"type": "string"}, "currency": {"type": "string"}},
                    },
                    "reason": {"type": "string"},
                },
            },
        },
    },
    output_schema={
        "type": "object",
        "required": ["sale_item_id", "line_total", "source_type", "product_name"],
        "properties": {
            "source_type": {"enum": ["catalog", "free_concept"]},
            "product_id": {"type": ["string", "null"]},
        },
    },
    permission="sale.create",
    policy_id="SALE-001",
    requires_idempotency=True,
    side_effect="write",
)

COMMIT_SALE = ToolRegistration(
    tool_id="sale.commit",
    version=1,
    input_schema={
        "type": "object",
        "required": ["payment_method"],
        "properties": {
            "conversation_id": {"type": ["string", "null"]},
            "payment_method": {"enum": ["cash", "card", "transfer"]},
        },
    },
    output_schema={
        "type": "object",
        "required": [
            "sale_session_id",
            "payment_id",
            "status",
            "currency",
            "item_count",
            "total",
            "payment",
            "items",
        ],
        "properties": {
            "status": {"enum": ["confirmed"]},
            "payment": {
                "type": "object",
                "required": ["method", "amount", "status"],
                "properties": {
                    "method": {"enum": ["cash", "card", "transfer"]},
                    "status": {"enum": ["recorded"]},
                },
            },
        },
    },
    permission="sale.create",
    policy_id="SALE-004",
    requires_idempotency=True,
    side_effect="write",
)

OPERATIONAL_DAY_SUMMARY = ToolRegistration(
    tool_id="operational_day.summary",
    version=1,
    input_schema={"type": "object", "properties": {}},
    output_schema={
        "type": "object",
        "required": [
            "business_date",
            "currency",
            "sale_count",
            "gross_sales_total",
            "cash_total",
            "card_total",
            "transfer_total",
        ],
    },
    permission="sale.create",
    policy_id="DAY-001",
    requires_idempotency=False,
    side_effect="read",
)

NEXT_BEST_ACTION = ToolRegistration(
    tool_id="operational_day.next_best_action",
    version=1,
    input_schema={"type": "object", "additionalProperties": False, "properties": {}},
    output_schema={
        "type": "object",
        "required": ["operational_day_id", "day_status", "pending_count", "next_best_action"],
    },
    permission="sale.create",
    policy_id="NBA-001",
    requires_idempotency=False,
    side_effect="read",
)

_PREPARATION_OUTPUT_REQUIRED = [
    "operational_day_id",
    "business_date",
    "day_status",
    "currency",
    "sale_count",
    "expected_cash",
    "counted_cash",
    "cash_difference",
    "cash_status",
    "counted_at",
    "cash_count_id",
]

SUBMIT_CASH_COUNT = ToolRegistration(
    tool_id="closing.submit_cash_count",
    version=1,
    input_schema={
        "type": "object",
        "required": ["amount"],
        "additionalProperties": False,
        "properties": {"amount": {"type": "string"}},
    },
    output_schema={
        "type": "object",
        "required": [*_PREPARATION_OUTPUT_REQUIRED, "supersedes_cash_count_id"],
        "properties": {
            "cash_status": {"enum": ["not_counted", "balanced", "over", "short"]},
        },
    },
    permission="closing.submit_cash_count",
    policy_id="CLOSE-001",
    requires_idempotency=True,
    side_effect="write",
)

CLOSING_CONFIRM = ToolRegistration(
    tool_id="closing.confirm",
    version=1,
    input_schema={
        "type": "object",
        "required": ["confirmation_token"],
        "additionalProperties": False,
        "properties": {"confirmation_token": {"type": "string"}},
    },
    output_schema={
        "type": "object",
        "required": [
            "operational_day_id",
            "closing_snapshot_id",
            "business_date",
            "day_status",
            "closed_at",
            "currency",
            "sale_count",
            "gross_sales_total",
            "expected_cash",
            "counted_cash",
            "cash_difference",
            "cash_status",
        ],
        "properties": {
            "day_status": {"enum": ["closed"]},
            "cash_status": {"enum": ["balanced", "over", "short"]},
        },
    },
    permission="closing.confirm",
    policy_id="CLOSE-003",
    requires_idempotency=True,
    side_effect="write",
)

CLOSING_PREPARE = ToolRegistration(
    tool_id="closing.prepare",
    version=1,
    input_schema={"type": "object", "additionalProperties": False, "properties": {}},
    output_schema={
        "type": "object",
        "required": _PREPARATION_OUTPUT_REQUIRED,
        "properties": {
            "cash_status": {"enum": ["not_counted", "balanced", "over", "short"]},
        },
    },
    permission="closing.submit_cash_count",
    policy_id="CLOSE-002",
    requires_idempotency=False,
    side_effect="read",
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

SALE_CONFIRMED = GenerativeUIRegistration(
    component="sale_confirmed",
    version=1,
    data_schema={
        "type": "object",
        "required": ["sale_session_id", "payment_id", "status", "item_count", "total", "payment", "items"],
    },
)

OPERATIONAL_DAY_SUMMARY_UI = GenerativeUIRegistration(
    component="operational_day_summary",
    version=1,
    data_schema={
        "type": "object",
        "required": [
            "business_date",
            "currency",
            "sale_count",
            "gross_sales_total",
            "cash_total",
            "card_total",
            "transfer_total",
        ],
    },
)


DAILY_CLOSE_PREPARATION_UI = GenerativeUIRegistration(
    component="daily_close_preparation",
    version=1,
    data_schema={
        "type": "object",
        "required": _PREPARATION_OUTPUT_REQUIRED,
        "properties": {
            "cash_status": {"enum": ["not_counted", "balanced", "over", "short"]},
            "confirmation_token": {"type": ["string", "null"]},
        },
    },
)

DAILY_CLOSE_CONFIRMED_UI = GenerativeUIRegistration(
    component="daily_close_confirmed",
    version=1,
    data_schema={
        "type": "object",
        "required": [
            "operational_day_id",
            "closing_snapshot_id",
            "business_date",
            "day_status",
            "closed_at",
            "currency",
            "sale_count",
            "gross_sales_total",
            "expected_cash",
            "counted_cash",
            "cash_difference",
            "cash_status",
        ],
        "properties": {
            "day_status": {"enum": ["closed"]},
            "cash_status": {"enum": ["balanced", "over", "short"]},
        },
    },
)

NEXT_BEST_ACTION_UI = GenerativeUIRegistration(
    component="next_best_action",
    version=1,
    data_schema={
        "type": "object",
        "required": ["work_item_id", "type", "title", "reason", "priority", "status"],
        "properties": {
            "outcome_type": {"enum": ["daily_close_ready"]},
            "type": {
                "enum": [
                    "cash_count_required",
                    "cash_difference_review",
                    "close_confirmation_required",
                ]
            },
            "status": {"enum": ["open"]},
            "expires_at": {"type": "null"},
        },
    },
)


def register_conversational_sale_tools(registry: ToolRegistry) -> None:
    for item in (
        RESOLVE_PRODUCT,
        START_SALE,
        ADD_ITEM,
        TOTALIZE_SALE,
        COMMIT_SALE,
        OPERATIONAL_DAY_SUMMARY,
        NEXT_BEST_ACTION,
        SUBMIT_CASH_COUNT,
        CLOSING_PREPARE,
        CLOSING_CONFIRM,
    ):
        registry.register(item)


def register_sale_item_added_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(SALE_ITEM_ADDED)


def register_sale_summary_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(SALE_SUMMARY)


def register_sale_confirmed_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(SALE_CONFIRMED)


def register_operational_day_summary_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(OPERATIONAL_DAY_SUMMARY_UI)


def register_daily_close_preparation_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(DAILY_CLOSE_PREPARATION_UI)


def register_daily_close_confirmed_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(DAILY_CLOSE_CONFIRMED_UI)


def register_next_best_action_ui(registry: GenerativeUIRegistry) -> None:
    registry.register(NEXT_BEST_ACTION_UI)
