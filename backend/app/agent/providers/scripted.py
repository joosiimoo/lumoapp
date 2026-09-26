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
FACTUAL_SCOPE_TEXT = (
    "Puedo consultar hechos registrados en Lumo para hoy, ayer, una fecha ya transcurrida, "
    "el último cierre, o las diferencias de caja de los últimos días. "
    "No encuentro esa consulta entre esos hechos."
)
_FACTUAL_UNSUPPORTED = {
    "el trimestre pasado",
    "este ano",
    "el ano pasado",
    "que paso el trimestre pasado",
    "que paso este ano",
    "que vendi este ano",
    "que vendi el ano pasado",
}
_FACTUAL_DAY_SUMMARY = {"que paso hoy": "today", "que paso ayer": "yesterday"}
_FACTUAL_SALES = {
    "cuanto vendi hoy": "today",
    "cuantas ventas tuve hoy": "today",
    "cuanto vendi ayer": "yesterday",
    "cuantas ventas tuve ayer": "yesterday",
}
_FACTUAL_CLOSE = {"como cerre hoy": "today", "como cerre ayer": "yesterday"}
_FACTUAL_LATEST = {"cual fue mi ultimo cierre", "que paso en el ultimo cierre"}
_FACTUAL_CASH = {"hubo diferencia de caja", "hay diferencia de caja"}
_FACTUAL_RECENT = "he tenido diferencias de caja ultimamente"
_FACTUAL_EVENTS = {"que eventos hubo hoy": "today", "que eventos hubo ayer": "yesterday"}
_MONTH_MAX_DAY = {
    1: 31,
    2: 29,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}
_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_FACTUAL_ISO_DATE = re.compile(r"^que paso el (\d{4})-(\d{2})-(\d{2})$")
_FACTUAL_SPOKEN_DATE = re.compile(
    r"^que paso el (\d{1,2}) de ("
    + "|".join(_SPANISH_MONTHS)
    + r")(?: de (\d{4}))?$"
)
_NEXT_BEST_ACTION_PHRASES = {
    "que sigue",
    "que falta",
    "que tengo pendiente",
    "que sigue con el cierre",
    "que falta para cerrar",
    "que falta para el cierre",
    "que tengo pendiente para cerrar",
}
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


def _factual_decision(normalized: str) -> AgentDecision | None:
    if normalized in _FACTUAL_UNSUPPORTED:
        return AgentDecision(intent="factual_memory_unsupported", clarification_question=FACTUAL_SCOPE_TEXT)
    scope = _FACTUAL_DAY_SUMMARY.get(normalized)
    if scope is not None:
        return _factual("day_summary", scope)
    scope = _FACTUAL_SALES.get(normalized)
    if scope is not None:
        return _factual("sales_summary", scope)
    scope = _FACTUAL_CLOSE.get(normalized)
    if scope is not None:
        return _factual("close_summary", scope)
    if normalized in _FACTUAL_LATEST:
        return _factual("latest_close", "latest")
    if normalized in _FACTUAL_CASH:
        return _factual("cash_summary", "today")
    if normalized == _FACTUAL_RECENT:
        return AgentDecision(
            intent="factual_memory",
            candidate_tool="memory.business_facts@1",
            factual_query_type="recent_cash_differences",
            factual_scope="recent",
            factual_recent_days=7,
        )
    scope = _FACTUAL_EVENTS.get(normalized)
    if scope is not None:
        return _factual("day_events", scope)
    iso = _FACTUAL_ISO_DATE.fullmatch(normalized)
    if iso is not None:
        year, month, day = (int(part) for part in iso.groups())
        return _explicit_date(year, month, day, include_year=True)
    spoken = _FACTUAL_SPOKEN_DATE.fullmatch(normalized)
    if spoken is not None:
        day = int(spoken.group(1))
        month = _SPANISH_MONTHS[spoken.group(2)]
        if day < 1 or day > _MONTH_MAX_DAY[month]:
            return AgentDecision(intent="factual_memory_unsupported", clarification_question=FACTUAL_SCOPE_TEXT)
        year_text = spoken.group(3)
        if year_text is None:
            return AgentDecision(
                intent="factual_memory",
                candidate_tool="memory.business_facts@1",
                factual_query_type="day_summary",
                factual_scope="date",
                factual_month=month,
                factual_day=day,
            )
        return _explicit_date(int(year_text), month, day, include_year=True)
    if normalized.startswith("que paso el "):
        return AgentDecision(intent="factual_memory_unsupported", clarification_question=FACTUAL_SCOPE_TEXT)
    return None


def _factual(query_type: str, scope: str) -> AgentDecision:
    return AgentDecision(
        intent="factual_memory",
        candidate_tool="memory.business_facts@1",
        factual_query_type=query_type,  # type: ignore[arg-type]
        factual_scope=scope,  # type: ignore[arg-type]
    )


def _explicit_date(year: int, month: int, day: int, *, include_year: bool) -> AgentDecision:
    from datetime import date

    try:
        resolved = date(year, month, day)
    except ValueError:
        return AgentDecision(intent="factual_memory_unsupported", clarification_question=FACTUAL_SCOPE_TEXT)
    return AgentDecision(
        intent="factual_memory",
        candidate_tool="memory.business_facts@1",
        factual_query_type="day_summary",
        factual_scope="date",
        factual_business_date=resolved.isoformat() if include_year else None,
        factual_month=month,
        factual_day=day,
    )


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
        factual = _factual_decision(normalized)
        if factual is not None:
            return factual
        if normalized in _NEXT_BEST_ACTION_PHRASES:
            return AgentDecision(
                intent="next_best_action",
                candidate_tool="operational_day.next_best_action@1",
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
