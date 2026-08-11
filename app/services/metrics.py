"""In-memory API metrics (no search/booking payloads stored)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderStats:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    offers: int = 0

    def record(self, *, success: bool, latency_ms: float | None, offer_count: int = 0) -> None:
        self.calls += 1
        if success:
            self.successes += 1
            self.offers += offer_count
        else:
            self.failures += 1
        if latency_ms is not None:
            self.total_latency_ms += latency_ms

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.calls if self.calls else 0.0

    @property
    def success_rate(self) -> float:
        return (self.successes / self.calls * 100.0) if self.calls else 0.0


@dataclass
class MetricsStore:
    started_at: float = field(default_factory=time.time)
    aggregate_requests: int = 0
    aggregate_offers: int = 0
    provider_stats: dict[str, ProviderStats] = field(default_factory=lambda: defaultdict(ProviderStats))
    # Minute buckets: {minute_epoch: {calls, successes, failures, latency_sum, latency_n}}
    timeline: dict[int, dict[str, float]] = field(default_factory=dict)
    recent_events: deque = field(default_factory=lambda: deque(maxlen=40))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_aggregation(
        self,
        *,
        providers_queried: int,
        providers_succeeded: int,
        providers_failed: int,
        total_offers: int,
        results: list[dict[str, Any]],
    ) -> None:
        now = time.time()
        minute = int(now // 60) * 60

        with self._lock:
            self.aggregate_requests += 1
            self.aggregate_offers += total_offers

            bucket = self.timeline.setdefault(
                minute,
                {"calls": 0, "successes": 0, "failures": 0, "latency_sum": 0.0, "latency_n": 0},
            )
            bucket["calls"] += 1

            for row in results:
                slug = str(row.get("provider") or "unknown")
                success = bool(row.get("success"))
                latency = row.get("latency_ms")
                offers = int(row.get("offer_count") or 0)
                self.provider_stats[slug].record(
                    success=success,
                    latency_ms=float(latency) if latency is not None else None,
                    offer_count=offers,
                )
                if success:
                    bucket["successes"] += 1
                else:
                    bucket["failures"] += 1
                if latency is not None:
                    bucket["latency_sum"] += float(latency)
                    bucket["latency_n"] += 1

            self.recent_events.appendleft(
                {
                    "ts": now,
                    "providers_queried": providers_queried,
                    "providers_succeeded": providers_succeeded,
                    "providers_failed": providers_failed,
                    "total_offers": total_offers,
                }
            )

            # Keep ~2 hours of minute buckets
            cutoff = minute - 120 * 60
            stale = [k for k in self.timeline if k < cutoff]
            for k in stale:
                del self.timeline[k]

    def snapshot(self, hours: int = 2) -> dict[str, Any]:
        now = time.time()
        cutoff = int((now - hours * 3600) // 60) * 60

        with self._lock:
            providers = []
            for slug, stats in sorted(
                self.provider_stats.items(),
                key=lambda item: item[1].calls,
                reverse=True,
            ):
                providers.append(
                    {
                        "provider": slug,
                        "calls": stats.calls,
                        "successes": stats.successes,
                        "failures": stats.failures,
                        "success_rate": round(stats.success_rate, 1),
                        "avg_latency_ms": round(stats.avg_latency_ms, 1),
                        "offers": stats.offers,
                    }
                )

            labels: list[str] = []
            calls_series: list[int] = []
            success_series: list[int] = []
            failure_series: list[int] = []
            latency_series: list[float | None] = []

            # Build contiguous minute series for charting
            start = cutoff
            end = int(now // 60) * 60
            minute = start
            while minute <= end:
                bucket = self.timeline.get(minute)
                labels.append(time.strftime("%H:%M", time.localtime(minute)))
                if bucket:
                    calls_series.append(int(bucket["calls"]))
                    success_series.append(int(bucket["successes"]))
                    failure_series.append(int(bucket["failures"]))
                    if bucket["latency_n"]:
                        latency_series.append(round(bucket["latency_sum"] / bucket["latency_n"], 1))
                    else:
                        latency_series.append(None)
                else:
                    calls_series.append(0)
                    success_series.append(0)
                    failure_series.append(0)
                    latency_series.append(None)
                minute += 60

            total_provider_calls = sum(p["calls"] for p in providers)
            total_successes = sum(p["successes"] for p in providers)
            overall_success = (
                round(total_successes / total_provider_calls * 100.0, 1)
                if total_provider_calls
                else 0.0
            )
            avg_latency = 0.0
            if providers:
                weighted = sum(p["avg_latency_ms"] * p["calls"] for p in providers)
                avg_latency = round(weighted / total_provider_calls, 1) if total_provider_calls else 0.0

            return {
                "uptime_seconds": int(now - self.started_at),
                "aggregate_requests": self.aggregate_requests,
                "aggregate_offers": self.aggregate_offers,
                "provider_calls": total_provider_calls,
                "overall_success_rate": overall_success,
                "avg_latency_ms": avg_latency,
                "providers": providers,
                "timeline": {
                    "labels": labels,
                    "calls": calls_series,
                    "provider_successes": success_series,
                    "provider_failures": failure_series,
                    "avg_latency_ms": latency_series,
                },
                "recent": list(self.recent_events)[:20],
            }


metrics_store = MetricsStore()
