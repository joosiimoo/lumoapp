"""Display span and grounded price for a sale utterance.

The display span keeps the merchant's spelling. Catalog lookup uses
normalize_product_name on that span and is not stored on the sale line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.domain.catalog.product import SaleUnit
from app.domain.shared.money import Money

_BASIS_PHRASES = ("el kilo", "por kilo", "por kg", "por kilogramo", "el kilogramo")
_AMOUNT = r"-?\$?\d+(?:[.,]\d+)?"
_BASIS = r"(?:el kilo|por kilo|por kg|por kilogramo|el kilogramo)"
_PRICE_WITH_A = re.compile(
    rf"^(?P<body>.*?)\s+a\s+(?P<amount>{_AMOUNT})(?:\s+cada\s+un[oa])?(?:\s+(?P<basis>{_BASIS}))?\s*$",
    re.IGNORECASE,
)
_PRICE_TRAILING = re.compile(
    rf"^(?P<body>.*\D)\s+(?P<amount>{_AMOUNT})\s*$",
)
_PRICE_ONLY = re.compile(
    rf"^(?:a\s+)?(?P<amount>{_AMOUNT})(?:\s+cada\s+un[oa])?(?:\s+(?P<basis>{_BASIS}))?\s*$",
    re.IGNORECASE,
)
_BASIS_ONLY = re.compile(rf"^(?:{_BASIS})\s*$", re.IGNORECASE)
_LEADING_QTY = re.compile(r"^(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$")
_MASS = re.compile(
    r"^(?P<unit>gramos?|gr|g|kilogramos?|kilogramo|kilos?|kg)(?:\s+de)?\s+(?P<rest>.*)$",
    re.IGNORECASE,
)
_COUNT = re.compile(
    r"^(?P<unit>unidades?|piezas?)(?:\s+de)?\s+(?P<rest>.*)$",
    re.IGNORECASE,
)
_PACKAGE = re.compile(
    r"^(?P<unit>bolsas?|paquetes?)\b(?P<rest>.*)$",
    re.IGNORECASE,
)
_UNSUPPORTED = re.compile(
    r"(?<![\wáéíóúñ])(cajas?|litros?|ml|manojos?|docenas?)(?![\wáéíóúñ])",
    re.IGNORECASE,
)
_FOREIGN = re.compile(r"(?<![\w])(usd|dolares|dolar|eur)(?![\w])", re.IGNORECASE)
_UNIT_ONLY = re.compile(
    r"^(?P<unit>gramos?|gr|g|kilogramos?|kilogramo|kilos?|kg)\s*$",
    re.IGNORECASE,
)
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
    "unidad": "unit",
    "unidades": "unit",
    "pieza": "unit",
    "piezas": "unit",
    "bolsa": "package",
    "bolsas": "package",
    "paquete": "package",
    "paquetes": "package",
}
_PACKAGE_WORD = {
    "bolsa": "bolsa",
    "bolsas": "bolsa",
    "paquete": "paquete",
    "paquetes": "paquete",
}

UNSUPPORTED_UNIT_TEXT = "No reconozco esa unidad. Puedo registrar unidad, paquete, gramos o kilogramos."
FOREIGN_CURRENCY_TEXT = "Solo puedo registrar precios en pesos."
INVALID_PRICE_TEXT = "El precio tiene que ser mayor que cero."
SCALE_PRICE_TEXT = "El precio solo puede tener dos decimales."
EMPTY_CONCEPT_TEXT = "¿Qué vendiste?"
LONG_CONCEPT_TEXT = "Ese nombre es demasiado largo."
MAX_DISPLAY_SPAN = 200


@dataclass(frozen=True, slots=True)
class GroundedPrice:
    amount: Decimal | None
    per_kilogram: bool
    problem: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedSaleUtterance:
    kind: str
    quantity: str | None = None
    unit: str | None = None
    display_span: str | None = None
    unit_price: str | None = None
    per_kilogram: bool = False
    package_word: str | None = None
    price_problem: str | None = None
    bare_number: str | None = None


def collapse_display_span(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def ground_user_price(raw_message: str) -> GroundedPrice:
    text = raw_message.strip()
    if not text:
        return GroundedPrice(amount=None, per_kilogram=False)
    if _FOREIGN.search(text):
        return GroundedPrice(amount=None, per_kilogram=False, problem="foreign")
    basis = _basis_present(text)
    amount_text = _amount_in_message(text)
    if amount_text is None:
        return GroundedPrice(amount=None, per_kilogram=basis)
    parsed, problem = _parse_amount(amount_text)
    return GroundedPrice(amount=parsed, per_kilogram=basis, problem=problem)


def parse_sale_utterance(message: str) -> ParsedSaleUtterance | None:
    text = message.strip()
    if not text:
        return None
    if _BASIS_ONLY.match(text):
        return ParsedSaleUtterance(kind="basis", per_kilogram=True)
    unit_only = _UNIT_ONLY.match(text)
    if unit_only:
        return ParsedSaleUtterance(kind="unit_only", unit=_UNIT_ALIASES.get(unit_only.group("unit").lower()))
    if re.fullmatch(r"-?\$?\d+(?:[.,]\d+)?", text):
        return ParsedSaleUtterance(kind="bare_number", bare_number=text.lstrip("$").replace(",", "."))
    price_only = _PRICE_ONLY.match(text)
    if price_only:
        parsed, problem = _parse_amount(price_only.group("amount"))
        return ParsedSaleUtterance(
            kind="price",
            unit_price=None if parsed is None else _format_price(parsed),
            per_kilogram=bool(price_only.group("basis")),
            price_problem=problem,
        )
    grounded = ground_user_price(text)
    body = _body_without_price(text, grounded)
    leading = _LEADING_QTY.match(body.strip())
    price_text = None if grounded.amount is None else _format_price(grounded.amount)
    if leading is None:
        span = collapse_display_span(body)
        if not span:
            return None
        return ParsedSaleUtterance(
            kind="utterance",
            display_span=span,
            unit_price=price_text,
            per_kilogram=grounded.per_kilogram,
            price_problem=grounded.problem,
        )
    rest = leading.group("rest")
    if _UNSUPPORTED.match(rest.strip()):
        return ParsedSaleUtterance(kind="unsupported")
    unit, package_word, span = _split_unit(rest)
    return ParsedSaleUtterance(
        kind="utterance",
        quantity=leading.group("qty").replace(",", "."),
        unit=unit,
        display_span=span,
        unit_price=price_text,
        per_kilogram=grounded.per_kilogram,
        package_word=package_word,
        price_problem=grounded.problem,
    )


def _body_without_price(text: str, grounded: GroundedPrice) -> str:
    priced = _PRICE_WITH_A.match(text)
    if priced:
        return priced.group("body")
    if grounded.amount is None:
        return text
    trailing = _PRICE_TRAILING.match(text)
    if trailing:
        return trailing.group("body")
    return text


def price_problem_text(problem: str | None) -> str:
    if problem == "foreign":
        return FOREIGN_CURRENCY_TEXT
    if problem == "scale":
        return SCALE_PRICE_TEXT
    return INVALID_PRICE_TEXT


def missing_price_text(*, unit: str | None, package_word: str | None) -> str:
    if package_word == "bolsa":
        return "¿A qué precio vendiste cada bolsa?"
    if package_word == "paquete":
        return "¿A qué precio vendiste cada paquete?"
    if unit in {"gram", "kilogram"}:
        return "¿A qué precio vendiste cada kilogramo?"
    return "¿A qué precio vendiste cada uno?"


def basis_question(amount: Decimal) -> str:
    rendered = f"{amount.quantize(Decimal('0.01')):.2f}"
    return f"¿Los ${rendered} son por kilogramo? Responde por kilo."


MAX_OVERRIDE_REASON = 200
BLANK_OVERRIDE_REASON_TEXT = "Necesito un motivo para registrar ese precio."
LONG_OVERRIDE_REASON_TEXT = "Ese motivo es demasiado largo."


def normalize_override_reason(value: str) -> str:
    return collapse_display_span(value)


def catalog_override_question(
    name: str,
    catalog_price: Money,
    override_price: Decimal,
    sale_unit: SaleUnit,
    *,
    changed: bool = False,
) -> str:
    label = {"kilogram": "kg", "unit": "unidad", "package": "paquete"}[sale_unit.value]
    registered = catalog_price.to_json()["amount"]
    proposed = f"{override_price.quantize(Decimal('0.01')):.2f}"
    verb = "ahora está" if changed else "está"
    return (
        f"{name} {verb} registrado a ${registered} por {label}. "
        f"¿Por qué lo vendiste a ${proposed}?"
    )


def _basis_present(text: str) -> bool:
    folded = text.lower()
    return any(phrase in folded for phrase in _BASIS_PHRASES)


def _amount_in_message(text: str) -> str | None:
    stripped = text.strip()
    if re.fullmatch(r"-?\$?\d+(?:[.,]\d+)?", stripped):
        return stripped
    priced = _PRICE_WITH_A.match(stripped)
    if priced:
        return priced.group("amount")
    price_only = _PRICE_ONLY.match(stripped)
    if price_only and _LEADING_QTY.match(stripped) is None:
        return price_only.group("amount")
    trailing = _PRICE_TRAILING.match(stripped)
    if trailing:
        return trailing.group("amount")
    return None


def _parse_amount(raw: str) -> tuple[Decimal | None, str | None]:
    text = raw.lstrip("$").replace(",", ".")
    if text.startswith("-"):
        return None, "non_positive"
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None, "non_positive"
    if "." in text and len(text.split(".", 1)[1]) > 2:
        return None, "scale"
    value = Decimal(text)
    if value <= 0:
        return None, "non_positive"
    return value, None


def _format_price(amount: Decimal) -> str:
    if amount == amount.to_integral_value():
        return f"{amount:.2f}"
    return format(amount, "f")


def _split_unit(rest: str) -> tuple[str | None, str | None, str | None]:
    mass = _MASS.match(rest)
    if mass:
        unit = _UNIT_ALIASES[mass.group("unit").lower()]
        return unit, None, collapse_display_span(mass.group("rest")) or None
    count = _COUNT.match(rest)
    if count:
        return "unit", None, collapse_display_span(count.group("rest")) or None
    package = _PACKAGE.match(rest)
    if package:
        word = package.group("unit").lower()
        span = collapse_display_span(package.group("unit") + package.group("rest"))
        return "package", _PACKAGE_WORD[word], span or None
    span = collapse_display_span(rest)
    return None, None, span or None
