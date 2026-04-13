from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..bridgewood.client import BridgewoodClient
from ..types.results import ReconciliationResult, TradeResult


def resolve_after_timestamp(
    after: datetime | timedelta | None,
) -> datetime | None:
    if after is None:
        return None
    if isinstance(after, timedelta):
        return datetime.now(timezone.utc) - after
    if after.tzinfo is None:
        return after.replace(tzinfo=timezone.utc)
    return after.astimezone(timezone.utc)


def fetch_recorded_external_ids(
    reporter: BridgewoodClient,
    *,
    expected_external_ids: set[str],
    after: datetime | None,
    page_limit: int = 100,
) -> set[str]:
    if not expected_external_ids:
        return set()

    matched_external_ids: set[str] = set()
    cursor: str | None = None

    while True:
        page = reporter.list_executions(limit=page_limit, cursor=cursor)
        if not page.items:
            break

        matched_external_ids.update(
            item.external_order_id
            for item in page.items
            if item.external_order_id in expected_external_ids
        )
        if matched_external_ids == expected_external_ids:
            break

        if after is not None:
            oldest_execution = min(item.executed_at for item in page.items)
            if oldest_execution < after:
                break

        cursor = page.next_cursor
        if cursor is None:
            break

    return matched_external_ids


def summarize_reconciliation(
    results: list[TradeResult],
    *,
    checked_orders: int | None = None,
) -> ReconciliationResult:
    attempted_reports = sum(1 for result in results if result.report_attempted)
    successful_reports = sum(
        1 for result in results if result.report_attempted and result.report_succeeded
    )
    duplicate_reports = sum(
        1
        for result in results
        for item in result.bridgewood_results
        if item.status == "duplicate"
    )
    failed_reports = sum(
        1
        for result in results
        if result.report_attempted and not result.report_succeeded
    )
    return ReconciliationResult(
        checked_orders=checked_orders if checked_orders is not None else len(results),
        attempted_reports=attempted_reports,
        successful_reports=successful_reports,
        duplicate_reports=duplicate_reports,
        failed_reports=failed_reports,
        results=results,
    )
