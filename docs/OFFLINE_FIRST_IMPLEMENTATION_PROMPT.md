# Akinfolu Foods: offline-first launch implementation prompt

You are implementing the launch-critical offline-first sales workflow for Akinfolu Foods. The primary user is a non-technical shop operator working on a phone or small tablet with unreliable internet. The product's single most important promise is: a real sale can always be recorded quickly, safely, and exactly once, whether or not the server is reachable.

## Operating rules

1. Work in small, reviewable stages. After every stage, run the relevant tests, inspect the diff for regressions, review failure and concurrency paths, and assess whether the design will remain maintainable when more devices, sellers, products, and reports are added.
2. Never call a stage complete because it compiles. A stage is complete only when its acceptance tests pass and its error paths preserve the user's data.
3. Preserve existing behaviour unless this brief intentionally replaces it. Do not delete unrelated user changes.
4. Prefer explicit domain types, versioned local schemas, database constraints, transactional server operations, and idempotent APIs. Avoid abstractions that obscure the sale lifecycle.
5. A completed sale is business truth. Never silently discard one because connectivity, authentication, stale stock, a retry, or navigation failed.
6. Keep the interface calm and minimal. Detailed tracking belongs underneath; the seller sees only what helps complete the next action.

## Required architecture

### Durable local-first sale capture

- Make the frontend installable and usable as a PWA. Cache the application shell and essential assets.
- Use IndexedDB, with an explicit schema version and upgrade path, for products, customers, settings, cart drafts, queued sales, sync attempts, and sync metadata.
- Cache the latest usable product/customer catalogue and the shared walk-in customer. The POS must open from cached data after a restart with no connection.
- Save a completed sale locally before any network request. Generate a UUID `client_sale_id` on the device and retain it permanently.
- Persist the cart while it is being built. Navigation, refresh, closing, or a crash must not lose it.
- Store price/name snapshots, quantities, payment details, seller/device identity, `sold_at`, `queued_at`, local reference, retry count, last error, and sync state.
- Use explicit `pending`, `syncing`, `synced`, and `needs_attention` states. Never leave a record stuck in `syncing` after restart.

### Idempotent synchronization

- Add a server-side unique `client_sale_id`. Replaying the request returns the existing sale and never deducts stock or records payment twice.
- Accept a sale and its initial payment atomically.
- Automatically sync on app start, focus, an online event, and bounded exponential backoff with jitter. Provide manual retry.
- Check actual API reachability rather than trusting only `navigator.onLine`.
- Process records independently so one conflict never blocks later sales.
- Preserve queued records across expired sessions. Reauthenticate when connected without erasing the queue.
- Distinguish retryable failures from permanent validation conflicts and retain actionable details.
- Handle a lost response after server commit: retry must resolve to the original server sale.

### Offline stock policy and inventory tracking

- Add an append-only inventory movement ledger for opening stock, restock, sale, return, damage/expiry, correction, and deletion reversal.
- Each movement stores product, signed quantity, reason, actor, device/client reference, event time, sync time, related sale, and note.
- Keep current stock consistent transactionally with the ledger.
- Never discard an already completed offline sale because cached stock is stale. Record it and flag an inventory exception for admin attention.
- Prevent ordinary online overselling while providing an explicit trusted offline-sync path.
- Add constraints and concurrency tests so retries cannot duplicate movements.

### Sales, payment, price, tax, and audit integrity

- Store `sold_at` separately from `created_at` and `synced_at`; use Lagos-local business time correctly.
- Capture Cash, Transfer, POS, or Pay later at checkout. Default immediate payment to the full total and support valid partial payment.
- Reject zero/negative payments and unintended overpayments, while leaving an extension point for refunds.
- Do not blindly trust client prices. Preserve the applied price snapshot, compare with the current server price, and require/record authorized overrides.
- Move tax to configurable business settings and preserve its snapshot per sale.
- Record structured audit changes. Audit failures must be observable rather than swallowed.
- Restrict production CORS to configured origins and add a health endpoint.

### Minimal seller experience

- Default to Walk-in Customer; named customer selection is optional.
- Create customers inline without losing the cart.
- Put frequent/recent products first while retaining fast search.
- Add a persistent mobile cart bar with item count and total; open the cart as a sheet. Checkout remains reachable without scrolling.
- Use at least 44x44px touch targets for critical controls.
- Use the concrete action `Record sale · ₦…`.
- After local save, immediately clear the active cart and say the sale is safe on the device.
- Add one quiet sync-confidence strip: `All sales synced · time`, `Offline · N sales safely saved`, or `Syncing X of Y`.
- Use plain language, visible focus, keyboard and screen-reader support, responsive layouts, and reduced-motion support.

### Minimal operational tracking

- Show today's sales, Cash/Transfer/POS totals, pending sync count, low/out-of-stock products, and customer balances due.
- Add configurable reorder thresholds; keep advanced reports out of the seller flow.
- Preserve seller, device, actual sale time, sync time, payment method, inventory movement, and client reference for future reporting.
- Allow cost price/profit tracking to be added later without rewriting historic sale items, but never invent profit before cost data exists.

## Required failure tests

Automate tests for fully offline sale/restart/sync; lost response and retry; concurrent duplicate submissions; independent queue processing; expired auth with retained queue; stale price override rules; two devices selling final stock offline; sale/payment rollback; movement balance across sale/return/reversal/correction; offline PWA shell and catalogue; cart persistence; mobile checkout reachability; touch sizes; production CORS/timezone; and all existing permissions, customer, product, sale, payment, and return behaviour.

## Completion gate

Before completion:

1. Run backend tests, frontend tests, type checking, linting, and production builds.
2. Verify migrations on both clean and existing databases.
3. Review persistent-field and IndexedDB schema upgrades.
4. Review transaction boundaries, constraints, races, retries, stale state, auth expiry, and service-worker updates.
5. Inspect mobile/desktop loading, empty, error, offline, syncing, and success states plus accessibility.
6. Confirm no secrets, databases, generated output, or unrelated files are committed.
7. Read the final diff as a bug reviewer and resolve every credible launch blocker.
8. Report deliberately deferred work; never call deferred or untested work complete.

The implementation is complete only when the seller can record a sale without internet, close and reopen the app, see that it is safe, reconnect, and observe exactly one server sale, one correct payment, and one correct set of inventory movements without manual intervention.
