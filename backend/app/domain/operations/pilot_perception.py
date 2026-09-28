from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

QUESTION_SET_VERSION = "anti_pos@1"
CLASSIFICATION_VERSION = "anti_pos_classification@1"

REQUIRED_QUESTIONS = frozenset(
    {
        "close_organizer",
        "information_delivery",
        "product_category",
        "workflow_ownership",
    }
)


class CloseOrganizerResponse(StrEnum):
    MERCHANT = "merchant"
    LUMO = "lumo"
    SHARED = "shared"
    UNSURE = "unsure"


class InformationDeliveryResponse(StrEnum):
    LUMO_BRINGS = "lumo_brings"
    MERCHANT_SEARCHES = "merchant_searches"
    MIXED = "mixed"
    UNSURE = "unsure"


class ProductCategoryResponse(StrEnum):
    OPERATOR_HELP = "operator_help"
    ANOTHER_SYSTEM = "another_system"
    MIXED = "mixed"
    UNSURE = "unsure"


class WorkflowOwnershipResponse(StrEnum):
    YES = "yes"
    PARTIALLY = "partially"
    NO = "no"
    UNSURE = "unsure"


class CaptureSource(StrEnum):
    INTERNAL_INTERVIEW = "internal_interview"
    INTERNAL_IMPORT = "internal_import"


class AntiPosClassification(StrEnum):
    OPERATOR_PERCEIVED = "operator_perceived"
    MIXED = "mixed"
    POS_LIKE = "pos_like"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


_RESPONSES_BY_QUESTION: dict[str, frozenset[str]] = {
    "close_organizer": frozenset(m.value for m in CloseOrganizerResponse),
    "information_delivery": frozenset(m.value for m in InformationDeliveryResponse),
    "product_category": frozenset(m.value for m in ProductCategoryResponse),
    "workflow_ownership": frozenset(m.value for m in WorkflowOwnershipResponse),
}


def validate_question_code(question_code: str) -> None:
    if question_code not in REQUIRED_QUESTIONS:
        raise ValueError(f"unknown question_code: {question_code}")


def validate_response_code(question_code: str, response_code: str) -> None:
    validate_question_code(question_code)
    allowed = _RESPONSES_BY_QUESTION[question_code]
    if response_code not in allowed:
        raise ValueError(f"unknown response_code for {question_code}: {response_code}")


def validate_capture_source(capture_source: str) -> None:
    if capture_source not in {m.value for m in CaptureSource}:
        raise ValueError(f"unknown capture_source: {capture_source}")


@dataclass(frozen=True, slots=True)
class PerceptionAnswer:
    question_code: str
    response_code: str


def is_sufficient_capture(answers: Mapping[str, str]) -> bool:
    if set(answers.keys()) != REQUIRED_QUESTIONS:
        return False
    return all(answers[q] != "unsure" for q in REQUIRED_QUESTIONS)


def classify_anti_pos(answers: Mapping[str, str]) -> AntiPosClassification:
    non_unsure = [code for code in answers.values() if code != "unsure"]
    if len(non_unsure) < 3 or len(non_unsure) == 0 and all(v == "unsure" for v in answers.values()):
        return AntiPosClassification.INSUFFICIENT_EVIDENCE
    if all(answers.get(q) == "unsure" for q in REQUIRED_QUESTIONS):
        return AntiPosClassification.INSUFFICIENT_EVIDENCE

    organizer = answers.get("close_organizer", "unsure")
    delivery = answers.get("information_delivery", "unsure")
    category = answers.get("product_category", "unsure")
    ownership = answers.get("workflow_ownership", "unsure")

    if category == ProductCategoryResponse.ANOTHER_SYSTEM.value:
        return AntiPosClassification.POS_LIKE
    if (
        organizer == CloseOrganizerResponse.MERCHANT.value
        and delivery == InformationDeliveryResponse.MERCHANT_SEARCHES.value
        and ownership in {WorkflowOwnershipResponse.NO.value, WorkflowOwnershipResponse.UNSURE.value}
    ):
        return AntiPosClassification.POS_LIKE

    if (
        category == ProductCategoryResponse.OPERATOR_HELP.value
        and organizer in {CloseOrganizerResponse.LUMO.value, CloseOrganizerResponse.SHARED.value}
        and ownership in {WorkflowOwnershipResponse.YES.value, WorkflowOwnershipResponse.PARTIALLY.value}
    ):
        return AntiPosClassification.OPERATOR_PERCEIVED

    answered = sum(1 for q in REQUIRED_QUESTIONS if answers.get(q, "unsure") != "unsure")
    if answered >= 2:
        return AntiPosClassification.MIXED
    return AntiPosClassification.INSUFFICIENT_EVIDENCE


def is_delegation_positive(answers: Mapping[str, str]) -> bool:
    organizer = answers.get("close_organizer")
    ownership = answers.get("workflow_ownership")
    return organizer in {CloseOrganizerResponse.LUMO.value, CloseOrganizerResponse.SHARED.value} and ownership in {
        WorkflowOwnershipResponse.YES.value,
        WorkflowOwnershipResponse.PARTIALLY.value,
    }


def is_proactive_information_positive(answers: Mapping[str, str]) -> bool:
    return answers.get("information_delivery") == InformationDeliveryResponse.LUMO_BRINGS.value


def select_latest_sufficient_capture(
    captures: list[tuple[datetime, Mapping[str, str]]],
    *,
    evidence_cutoff_at: datetime,
) -> Mapping[str, str] | None:
    eligible = [
        (captured_at, answers)
        for captured_at, answers in captures
        if captured_at <= evidence_cutoff_at and is_sufficient_capture(answers)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda item: item[0], reverse=True)
    return eligible[0][1]
