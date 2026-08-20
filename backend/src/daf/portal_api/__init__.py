"""Portal-facing Lambda handlers (Task 17.1) — API-Gateway-proxy entry points
that adapt HTTP requests to the existing `Supervisor` / `HitlApprovalBroker`
domain APIs. No new framework dependency: plain `(event, context) -> dict`
classic AWS Lambda proxy-integration handlers.
"""
