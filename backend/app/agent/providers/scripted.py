from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.agent.contracts import AgentDecision, AgentEntity, AgentResponse, LLMProvider, ProviderStatus
from app.domain.sales.concept import (
    UNSUPPORTED_UNIT_TEXT,
    parse_sale_utterance,
    price_problem_text,
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
_EXPORT_PHRASES = {
    "exporta las ventas de hoy",
    "exportar ventas",
    "descargar excel",
    "descargar csv",
}
_UNSUPPORTED_TEXT = (
    "Puedo registrar un producto del catálogo con cantidad y unidad. Prueba con *900gr zanahoria*."
)

_AMOUNT_SLOT = r"\$?\d+(?:[.,]\d{1,2})?"
_CASH_COUNT_PATTERNS = (
    re.compile(rf"^tengo (?P<amount>{_AMOUNT_SLOT}) en caja$"),
    re.compile(rf"^hay (?P<amount>{_AMOUNT_SLOT}) en caja$"),
    re.compile(rf"^conte (?P<amount>{_AMOUNT_SLOT})$"),
    re.compile(rf"^caja (?P<amount>{_AMOUNT_SLOT})$"),
)
_CLOSE_PREPARATION_PHRASES = {
    "preparar el cierre",
    "preparar cierre",
    "cuanto deberia haber en caja",
    "efectivo esperado",
}
_REQUEST_CLOSE_PHRASES = {
    "cerrar el dia",
    "cerrar la jornada",
    "cerrar caja",
}
_CONFIRM_CLOSE_PHRASES = {
    "confirmar cierre",
    "si, cerrar",
    "confirmar",
}


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


def _claims_sale(parsed) -> bool:
    """Sale grammar only. Other closed-domain misses stay unsupported."""
    if parsed.kind in {"basis", "unit_only", "bare_number", "price", "unsupported"}:
        return True
    if parsed.kind != "utterance":
        return False
    if parsed.quantity:
        return True
    span = (parsed.display_span or "").strip()
    if not span or " " in span:
        return False
    return re.fullmatch(r"(?:cajas?|litros?|ml|manojos?|docenas?)", span, re.IGNORECASE) is None


def parse_counted_phrase(normalized: str) -> str | None:
    """Closed cash-count grammar. One numeric slot, no thousands separators, no bare amount."""
    for pattern in _CASH_COUNT_PATTERNS:
        matched = pattern.match(normalized)
        if matched is not None:
            return matched.group("amount").lstrip("$").replace(",", ".")
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
        if normalized in _EXPORT_PHRASES:
            return AgentDecision(
                intent="unsupported",
                clarification_question=_UNSUPPORTED_TEXT,
            )
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
        counted_amount = parse_counted_phrase(normalized)
        if counted_amount is not None:
            return AgentDecision(
                intent="record_cash_count",
                counted_amount=counted_amount,
                candidate_tool="closing.submit_cash_count@1",
                entities=[AgentEntity(name="counted_amount", value=counted_amount, provenance="user")],
            )
        if normalized in _CLOSE_PREPARATION_PHRASES:
            return AgentDecision(
                intent="close_preparation",
                candidate_tool="closing.prepare@1",
            )
        if normalized in _REQUEST_CLOSE_PHRASES:
            return AgentDecision(
                intent="request_close",
                candidate_tool="closing.prepare@1",
            )
        if normalized in _CONFIRM_CLOSE_PHRASES:
            return AgentDecision(
                intent="confirm_close",
                candidate_tool="closing.confirm@1",
            )
        parsed = parse_sale_utterance(message)
        if parsed is None or not _claims_sale(parsed):
            return AgentDecision(
                intent="unsupported",
                clarification_question=_UNSUPPORTED_TEXT,
            )
        if parsed.kind == "unsupported":
            return AgentDecision(
                intent="add_sale_item",
                missing_fields=["unit"],
                clarification_question=UNSUPPORTED_UNIT_TEXT,
            )
        if parsed.kind == "basis":
            return AgentDecision(
                intent="add_sale_item",
                price_basis="per_kilogram",
                missing_fields=["product_query", "quantity"],
            )
        if parsed.kind == "unit_only":
            return AgentDecision(
                intent="add_sale_item",
                unit=parsed.unit,  # type: ignore[arg-type]
                missing_fields=["product_query", "quantity"],
                clarification_question="¿Qué producto y cantidad vendiste?",
                entities=[AgentEntity(name="unit", value=parsed.unit, provenance="user")],
            )
        if parsed.kind == "bare_number":
            return AgentDecision(
                intent="add_sale_item",
                quantity=parsed.bare_number,
                unit_price=parsed.bare_number,
                missing_fields=["product_query"],
            )
        if parsed.kind == "price":
            return AgentDecision(
                intent="add_sale_item",
                unit_price=parsed.unit_price,
                price_basis="per_kilogram" if parsed.per_kilogram else None,
                missing_fields=["product_query", "quantity"],
                clarification_question=None if parsed.price_problem is None else price_problem_text(parsed.price_problem),
            )
        if parsed.price_problem:
            return AgentDecision(
                intent="add_sale_item",
                product_query=parsed.display_span,
                quantity=parsed.quantity,
                unit=parsed.unit,  # type: ignore[arg-type]
                missing_fields=["unit_price"],
                clarification_question=price_problem_text(parsed.price_problem),
            )
        missing: list[str] = []
        if parsed.unit is None:
            missing.append("unit")
        if parsed.quantity is None:
            missing.append("quantity")
        basis = "per_kilogram" if parsed.per_kilogram else ("per_each" if parsed.unit_price and parsed.unit in {None, "unit", "package"} else None)
        if parsed.unit is None and parsed.quantity and parsed.display_span:
            return AgentDecision(
                intent="add_sale_item",
                product_query=parsed.display_span,
                quantity=parsed.quantity,
                unit_price=parsed.unit_price,
                price_basis=basis,
                package_word=parsed.package_word,  # type: ignore[arg-type]
                missing_fields=["unit"],
                clarification_question="¿En qué unidad está esa cantidad? Por ejemplo gramos o kilogramos.",
                candidate_tool="sale.add_item@1" if parsed.unit_price else None,
                entities=[
                    AgentEntity(name="product", value=parsed.display_span, provenance="user"),
                    AgentEntity(name="quantity", value=parsed.quantity, provenance="user"),
                ],
            )
        if missing:
            return AgentDecision(
                intent="add_sale_item",
                product_query=parsed.display_span,
                quantity=parsed.quantity,
                unit=parsed.unit,  # type: ignore[arg-type]
                unit_price=parsed.unit_price,
                price_basis=basis,
                package_word=parsed.package_word,  # type: ignore[arg-type]
                missing_fields=missing,
                entities=[
                    AgentEntity(name="product", value=parsed.display_span, provenance="user"),
                ],
            )
        return AgentDecision(
            intent="add_sale_item",
            product_query=parsed.display_span,
            quantity=parsed.quantity,
            unit=parsed.unit,  # type: ignore[arg-type]
            unit_price=parsed.unit_price,
            price_basis="per_kilogram" if parsed.per_kilogram else ("per_each" if parsed.unit in {"unit", "package"} and parsed.unit_price else None),
            package_word=parsed.package_word,  # type: ignore[arg-type]
            candidate_tool="sale.add_item@1",
            response_hints=["99.00"],
            entities=[
                AgentEntity(name="product", value=parsed.display_span, provenance="user"),
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
