"""Canonical daily-sales export columns. CSV and XLSX share this order."""

EXPORT_COLUMNS: tuple[str, ...] = (
    "business_date",
    "sale_session_id",
    "sale_transaction_number",
    "void_transaction_number",
    "sale_status",
    "sale_confirmed_at",
    "sale_item_id",
    "product_name",
    "source_type",
    "product_id",
    "quantity",
    "unit",
    "catalog_unit_price",
    "unit_price",
    "price_override_reason",
    "line_total",
    "currency",
    "payment_id",
    "payment_method",
    "payment_amount",
)

COLUMN_WIDTHS: tuple[int, ...] = (
    14,  # business_date
    38,  # sale_session_id
    18,  # sale_transaction_number
    18,  # void_transaction_number
    22,  # sale_status
    38,  # sale_confirmed_at
    38,  # sale_item_id
    28,  # product_name
    16,  # source_type
    38,  # product_id
    12,  # quantity
    14,  # unit
    20,  # catalog_unit_price
    14,  # unit_price
    36,  # price_override_reason
    14,  # line_total
    12,  # currency
    38,  # payment_id
    16,  # payment_method
    16,  # payment_amount
)
