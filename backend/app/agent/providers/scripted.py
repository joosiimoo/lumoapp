from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.agent.contracts import AgentDecision, AgentEntity, AgentResponse, LLMProvider, ProviderStatus
from app.domain.catalog import normalize_product_name

_UNIT_ALIASES = {
    "g": "gram",
    "gr": "gram",
    "gramo": "gram",
    "gramos": "gram",
    "kg": "kilogram",
    "kilo": "kilogram",
    "kilos": "kilogram",
    "kilogramo": "kilogram",
    "kilogramos": "kilogram",
}

_WITH_UNIT = re.compile(
    r"^\s*(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>gramos?|gr|g|kilogramos?|kilogramo|kilos?|kg)\s+(?:de\s+)?(?P<product>.+?)\s*$",
    re.IGNORECASE,
)
_WITHOUT_UNIT = re.compile(
    r"^\s*(?P<qty>\d+(?:[.,]\d+)?)\s+(?:de\s+)?(?P<product>[^\d].+?)\s*$",
    re.IGNORECASE,
)
_UNIT_ONLY = re.compile(
    r"^\s*(?P<unit>gramos?|gr|g|kilogramos?|kilogramo|kilos?|kg)\s*$",
    re.IGNORECASE,
)
_TOTALIZE_SYNONYMS = {"totalizar", "total", "el total"}
_PAYMENT_PHRASES = {
    "efectivo": "cash",
    "pagar en efectivo": "cash",
    "en efectivo": "cash",
    "tarjeta": "card",
    "pagar con tarjeta": "card",
    "con tarjeta": "card",
    "transferencia": "transfer",
    "pagar por transferencia": "transfer",
    "pagar con transferencia": "transfer",
    "por transferencia": "transfer",
}
_PAYMENT_METHOD_CLARIFY = {"pagar", "cheque"}
_PAYMENT_CLARIFICATION = "¿Cómo pagó? Puedo registrar *efectivo*, *tarjeta* o *transferencia*."
_DAY_SUMMARY_PHRASES = {"como vamos hoy", "ventas de hoy", "cuanto vendimos hoy"}


def normalize_closed_phrase(message: str) -> str:
    folded = unicodedata.normalize("NFKD", message)
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    folded = folded.lower()
    folded = re.sub(r"\s+", " ", folded).strip()
    if folded[:1] in "¿¡":
        folded = folded[1:].lstrip()
    if folded[-1:] in "?!":
        folded = folded[:-1].rstrip()
    return folded


@dataclass(frozen=True, slots=True)
class ParsedSaleUtterance:
    quantity: str | None
    unit: str | None
    product_query: str | None


def parse_sale_utterance(message: str) -> ParsedSaleUtterance | None:
    text = message.strip()
    matched = _WITH_UNIT.match(text)
    if matched:
        unit_raw = matched.group("unit").lower()
        return ParsedSaleUtterance(
            quantity=matched.group("qty").replace(",", "."),
            unit=_UNIT_ALIASES.get(unit_raw),
            product_query=normalize_product_name(matched.group("product")),
        )
    matched = _WITHOUT_UNIT.match(text)
    if matched:
        return ParsedSaleUtterance(
            quantity=matched.group("qty").replace(",", "."),
            unit=None,
            product_query=normalize_product_name(matched.group("product")),
        )
    matched = _UNIT_ONLY.match(text)
    if matched:
        unit_raw = matched.group("unit").lower()
        return ParsedSaleUtterance(
            quantity=None,
            unit=_UNIT_ALIASES.get(unit_raw),
            product_query=None,
        )
    return None


class ScriptedLLMProvider:
    """Deterministic local/test interpreter. No repository or database access."""

    def interpret(
        self,
        message: str,
        context: dict[str, Any],
        allowed_tools: list[str],
    ) -> AgentDecision:
        _ = (context, allowed_tools)
        normalized = normalize_closed_phrase(message)
        payment_method = _PAYMENT_PHRASES.get(normalized)
        if payment_method is not None:
            return AgentDecision(
                intent="commit_sale",
                payment_method=payment_method,  # type: ignore[arg-type]
                candidate_tool="sale.commit@1",
            )
        if normalized in _PAYMENT_METHOD_CLARIFY:
            return AgentDecision(
                intent="unsupported",
                clarification_question=_PAYMENT_CLARIFICATION,
            )
        if normalized in _TOTALIZE_SYNONYMS:
            return AgentDecision(
                intent="totalize_sale",
                candidate_tool="sale.totalize@1",
            )
        if normalized in _DAY_SUMMARY_PHRASES:
            return AgentDecision(
                intent="day_summary",
                candidate_tool="operational_day.summary@1",
            )
        parsed = parse_sale_utterance(message)
        if parsed is None:
            return AgentDecision(
                intent="unsupported",
                clarification_question="Puedo registrar un producto del catálogo con cantidad y unidad. Prueba con *900gr zanahoria*.",
            )
        if parsed.unit and not parsed.product_query and not parsed.quantity:
            return AgentDecision(
                intent="add_sale_item",
                unit=parsed.unit,  # type: ignore[arg-type]
                missing_fields=["product_query", "quantity"],
                clarification_question="¿Qué producto y cantidad vendiste?",
                entities=[AgentEntity(name="unit", value=parsed.unit, provenance="user")],
            )
        if parsed.unit is None:
            return AgentDecision(
                intent="add_sale_item",
                product_query=parsed.product_query,
                quantity=parsed.quantity,
                missing_fields=["unit"],
                clarification_question="¿En qué unidad está esa cantidad? Por ejemplo gramos o kilogramos.",
                entities=[
                    AgentEntity(name="product", value=parsed.product_query, provenance="user"),
                    AgentEntity(name="quantity", value=parsed.quantity, provenance="user"),
                ],
            )
        return AgentDecision(
            intent="add_sale_item",
            product_query=parsed.product_query,
            quantity=parsed.quantity,
            unit=parsed.unit,  # type: ignore[arg-type]
            candidate_tool="sale.add_item@1",
            response_hints=["99.00"],
            entities=[
                AgentEntity(name="product", value=parsed.product_query, provenance="user"),
                AgentEntity(name="quantity", value=parsed.quantity, provenance="user"),
                AgentEntity(name="unit", value=parsed.unit, provenance="user"),
                AgentEntity(name="line_total", value="99.00", provenance="model"),
            ],
        )

    def compose(self, result: dict[str, Any], ui_contracts: list[dict[str, Any]]) -> AgentResponse:
        text = str(result.get("text") or "Listo.")
        return AgentResponse(text=text, ui=list(ui_contracts))

    def health(self) -> ProviderStatus:
        return ProviderStatus(ready=False, provider="fake", detail="scripted interpreter; no vendor configured")


class FakeLLMProvider(ScriptedLLMProvider):
    """Backwards-compatible alias used by foundation tests."""
