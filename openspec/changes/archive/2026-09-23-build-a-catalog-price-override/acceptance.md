# Acceptance notes

Manual acceptance passed for a higher override, reason capture, the adjusted-price caption on the added card, the summary caption, the confirmed caption, an equal catalog price on the normal path, a lower override, cancellation, a new sale replacing a pending override, a closed intent clearing the pending override, free-concept regression, and a mixed normal/override/free-concept session.

The final mixed session contained two free-concept bolsas-de-hielo lines because one was already present before the final mixed sequence. The confirmed session lines were bolsas de hielo 36.00, Zanahoria 22.50, Tomate override 27.00, and bolsas de hielo 36.00, totaling 121.50 MXN.

Final read-only PostgreSQL acceptance passed for snapshot, charged price, and reason persistence, an unchanged Product.current_price, audit, outbox, idempotency, zero invalid invariants, RLS, the catalog-only downgrade predicate, and the composite tenant foreign key.
