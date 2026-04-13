from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def summarize_reconciliation(results: list[TradeResult]) -> ReconciliationResult:
    attempted_reports = sum(1 for result in results if result.report_attempted)
    successful_reports = sum(1 for result in results if result.report_succeeded)
    duplicate_reports = sum(
        1
        for result in results
        for item in result.bridgewood_results
        if item.status == "duplicate"
    )
    failed_reports = sum(
        1 for result in results if result.report_attempted and not result.report_succeeded
    )
    return ReconciliationResult(
        checked_orders=len(results),
        attempted_reports=attempted_reports,
        successful_reports=successful_reports,
        duplicate_reports=duplicate_reports,
        failed_reports=failed_reports,
        results=results,
    )

