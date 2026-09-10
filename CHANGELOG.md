# Changelog

## 0.2.0 — unreleased

- **The bus now carries `ra_common.Envelope`** instead of a bespoke minimal
  envelope, matching `seda-bus-java` (which depends on `ra-common-java`).
  - New dependency: `ra-common`.
  - Routing follows the envelope's `DynamicRoutingSlip` (LIFO, keyed by
    `route.service`) rather than a `slip: list[str]` of channel names.
  - `make_envelope(to, payload, slip=[...])` and `target_service(env)` keep the
    earlier ergonomic API on top of the richer type.
  - Per-hop retry counts moved from `env.attempts` onto the channel (keyed by
    envelope id), mirroring `SEDAMessageChannel.attempts`.
- Public API otherwise unchanged: `SEDABus`, `Channel`, `Consumer`, `Delivery`,
  `Backpressure`, and the `channel` / `subscribe` / `publish` / `stats` /
  `set_dead_letter_channel` methods.

## 0.1.0

Initial release — static-configuration SEDA core (stages, bounded queues, one
shared worker pool, per-stage concurrency, back-pressure, routing slips,
retry/dead-letter).
