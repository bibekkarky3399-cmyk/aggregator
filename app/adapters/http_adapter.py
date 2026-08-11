"""Config-driven HTTP adapter — default for all admin-configured providers.

Supports JSON REST (default) and SOAP/XML when ``auth_config.soap`` is set,
so agencies like United Solutions can be onboarded from Admin without custom
Python adapter modules.
"""

from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin
from xml.sax.saxutils import escape as xml_escape

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.adapters.auth_strategies import get_auth_strategy
from app.adapters.base import AdapterRequest, AdapterResponse, ProviderAdapter
from app.adapters.mapping import apply_request_mapping, normalize_response
from app.core.logging import get_logger
from app.models.provider import HttpMethod, Provider
from app.schemas.aggregation import NormalizedOffer

logger = get_logger(__name__)


class GenericHttpAdapter(ProviderAdapter):
    """
    Fully configuration-driven adapter.

    New providers can be onboarded via the admin API without writing code,
    as long as request/response mappings and auth config are provided.

    SOAP: set ``auth_config.soap`` with operation + field templates (see bootstrap
    United Solutions seeds). Credentials stay in auth_config; sync from ``US_*`` env.
    """

    def __init__(self, provider: Provider, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(provider)
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.provider.timeout_seconds),
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_url(self, path: str | None = None) -> str:
        base = self.provider.base_url.rstrip("/") + "/"
        relative = (path or self.provider.endpoint_path or "/").lstrip("/")
        # SOAP often posts to the base endpoint with empty path
        if path is None and not (self.provider.endpoint_path or "").strip():
            return self.provider.base_url.rstrip("/")
        return urljoin(base, relative)

    def _soap_config(self) -> dict[str, Any] | None:
        cfg = self.provider.auth_config or {}
        soap = cfg.get("soap")
        return soap if isinstance(soap, dict) else None

    async def _prepare(
        self,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, str], dict[str, Any], dict[str, Any] | None]:
        headers = {"Accept": "application/json", **(self.provider.default_headers or {})}
        query_params: dict[str, Any] = {}
        body = apply_request_mapping(
            payload,
            self.provider.request_mapping or {},
            self.provider.default_params or {},
        )

        auth = get_auth_strategy(self.provider.auth_type)
        await auth.apply(headers, query_params, self.provider.auth_config or {}, client)

        method = self.provider.http_method
        if method == HttpMethod.GET:
            query_params = {**body, **query_params}
            return headers, query_params, None

        return headers, query_params, body

    async def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any],
        json_body: dict[str, Any] | None,
        *,
        content: bytes | None = None,
        raise_server_error: bool = True,
    ) -> httpx.Response:
        client = await self._get_client()
        attempts = max(int(self.provider.max_retries) + 1, 1)

        async for attempt in AsyncRetrying(
            stop_after_attempt(attempts),
            wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            reraise=True,
        ):
            with attempt:
                logger.debug(
                    "Calling provider=%s method=%s url=%s attempt=%s",
                    self.provider.slug,
                    method,
                    url,
                    attempt.retry_state.attempt_number,
                )
                kwargs: dict[str, Any] = {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "params": params or None,
                    "timeout": self.provider.timeout_seconds,
                }
                if content is not None:
                    kwargs["content"] = content
                else:
                    kwargs["json"] = json_body
                response = await client.request(**kwargs)
                if raise_server_error and response.status_code >= 500:
                    response.raise_for_status()
                return response

        raise RuntimeError("Retry loop exited unexpectedly")

    async def execute(self, request: AdapterRequest) -> AdapterResponse:
        started = time.perf_counter()
        soap = self._soap_config()
        if soap:
            return await self._execute_soap(request, soap, started)
        try:
            client = await self._get_client()
            headers, params, body = await self._prepare(request.payload, client)
            url = self._build_url()
            method = self.provider.http_method.value

            response = await self._send(method, url, headers, params, body)
            latency_ms = (time.perf_counter() - started) * 1000

            if response.status_code >= 400:
                return AdapterResponse(
                    success=False,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=f"HTTP {response.status_code}: {response.text[:300]}",
                    raw={"status_code": response.status_code, "body": _safe_json(response)},
                )

            raw = _safe_json(response)
            normalized = normalize_response(
                raw,
                self.provider.response_mapping or {},
                self.provider.slug,
            )
            offers = [NormalizedOffer.model_validate(item) for item in normalized]

            return AdapterResponse(
                success=True,
                offers=offers,
                data=raw if not offers else {"flights": [o.model_dump() for o in offers]},
                latency_ms=latency_ms,
                status_code=response.status_code,
                raw=raw,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.exception("Provider %s failed: %s", self.provider.slug, exc)
            return AdapterResponse(
                success=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    async def _execute_soap(
        self,
        request: AdapterRequest,
        soap: dict[str, Any],
        started: float,
    ) -> AdapterResponse:
        try:
            auth = self.provider.auth_config or {}
            payload = dict(request.payload or {})
            operation = str(soap.get("operation") or "").strip()
            if not operation:
                raise ValueError("auth_config.soap.operation is required")

            ns = str(soap.get("namespace") or "http://booking.us.org/").strip()
            fields_tpl = soap.get("fields") if isinstance(soap.get("fields"), dict) else {}
            fields = {
                key: _resolve_soap_value(expr, auth=auth, payload=payload)
                for key, expr in fields_tpl.items()
            }

            # Optional CDATA raw fields (e.g. IssueTicket passenger XML)
            raw_fields: dict[str, str] = {}
            for key, expr in (soap.get("raw_fields") or {}).items():
                raw_fields[key] = _resolve_soap_value(expr, auth=auth, payload=payload)

            envelope = _build_soap_envelope(ns, operation, fields, raw_fields)
            endpoint = (
                str(auth.get("endpoint") or "").strip()
                or self.provider.base_url.rstrip("/")
            )
            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{ns}{operation}"',
                **(self.provider.default_headers or {}),
            }

            response = await self._send(
                "POST",
                endpoint,
                headers,
                {},
                None,
                content=envelope.encode("utf-8"),
                raise_server_error=False,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            payload_xml = _unwrap_soap_return(response.text)
            err = _soap_error_message(payload_xml)
            if response.status_code >= 400:
                return AdapterResponse(
                    success=False,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=err or f"SOAP HTTP {response.status_code}: {response.text[:300]}",
                    raw={"body": response.text[:2000], "payload": payload_xml[:2000]},
                )
            if err:
                return AdapterResponse(
                    success=False,
                    latency_ms=latency_ms,
                    status_code=200,
                    error=err,
                    raw={"payload": payload_xml[:2000]},
                )

            mode = str(soap.get("response_mode") or "data").lower()
            if mode == "offers":
                items = _soap_items(
                    payload_xml,
                    item_tag=str(soap.get("items_tag") or "Availability"),
                    wrap_tags=tuple(soap.get("wrap_tags") or ("Outbound", "Inbound")),
                )
                # Flatten tag→text dicts then apply response_mapping
                mapping = self.provider.response_mapping or soap.get("item_map") or {}
                if isinstance(mapping, dict) and "items" not in mapping:
                    # Treat mapping as field map; items already extracted
                    normalized = [
                        _map_soap_item(item, mapping, self.provider.slug) for item in items
                    ]
                else:
                    normalized = normalize_response(
                        {"items": items},
                        {**(mapping if isinstance(mapping, dict) else {}), "items": "items"},
                        self.provider.slug,
                    )
                offers = [NormalizedOffer.model_validate(item) for item in normalized]
                return AdapterResponse(
                    success=True,
                    offers=offers,
                    data={"flights": [o.model_dump() for o in offers]},
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    raw={"fare_count": len(offers)},
                )

            # data mode — extract named tags into a dict
            result_map = soap.get("result_map") if isinstance(soap.get("result_map"), dict) else {}
            data: dict[str, Any] = {"payload": payload_xml[:8000], "source": "soap"}
            for dest, tag in result_map.items():
                values = _find_tag_texts(payload_xml, str(tag))
                if not values:
                    continue
                if dest.endswith("s") and dest not in {"status", "reservation_status"}:
                    data[dest] = values
                else:
                    data[dest] = values[0]
            # sectors convenience
            if soap.get("items_tag") == "Sector":
                sectors = _soap_items(payload_xml, item_tag="Sector", wrap_tags=())
                data["sectors"] = [
                    {
                        "sector_code": (s.get("SectorCode") or "").upper(),
                        "sector_name": s.get("SectorName") or s.get("SectorCode") or "",
                    }
                    for s in sectors
                    if s.get("SectorCode")
                ]
            return AdapterResponse(
                success=True,
                data=data,
                latency_ms=latency_ms,
                status_code=response.status_code,
                raw=data,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.exception("SOAP provider %s failed: %s", self.provider.slug, exc)
            return AdapterResponse(
                success=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    async def test_connectivity(self, sample_payload: dict[str, Any] | None = None) -> AdapterResponse:
        started = time.perf_counter()
        try:
            soap = self._soap_config()
            if soap:
                return await self._test_soap_connectivity(sample_payload, started)

            client = await self._get_client()
            path = self.provider.health_check_path
            if path:
                headers = {"Accept": "application/json", **(self.provider.default_headers or {})}
                params: dict[str, Any] = {}
                auth = get_auth_strategy(self.provider.auth_type)
                await auth.apply(headers, params, self.provider.auth_config or {}, client)
                url = self._build_url(path)
                response = await client.get(
                    url,
                    headers=headers,
                    params=params or None,
                    timeout=min(self.provider.timeout_seconds, 15.0),
                )
                latency_ms = (time.perf_counter() - started) * 1000
                ok = response.status_code < 400
                return AdapterResponse(
                    success=ok,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=None if ok else f"HTTP {response.status_code}",
                    raw=_safe_json(response),
                )

            payload = sample_payload or {
                "origin": "KTM",
                "destination": "PKR",
                "departure_date": "2026-09-15",
                "adults": 1,
                "currency": "NPR",
            }
            return await self.execute(AdapterRequest(payload=payload, operation="connectivity"))
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return AdapterResponse(success=False, latency_ms=latency_ms, error=str(exc))

    async def _test_soap_connectivity(
        self,
        sample_payload: dict[str, Any] | None,
        started: float,
    ) -> AdapterResponse:
        """
        Probe SOAP agencies without requiring booking IDs.

        Reservation / IssueTicket / GetFlightDetail / GetItinerary need a live
        flight_id or PNR. Admin "Test connection" usually has none — verify
        credentials with CheckBalance (or soap.connectivity) instead.
        """
        soap = self._soap_config() or {}
        payload = dict(sample_payload or {})
        operation = str(soap.get("operation") or "")

        if operation == "FlightAvailability":
            payload.setdefault("origin", "KTM")
            payload.setdefault("destination", "PKR")
            payload.setdefault("departure_date", "2026-09-15")
            payload.setdefault("adults", 1)
            payload.setdefault("currency", "NPR")
        elif operation == "SalesReport":
            today = date.today()
            payload.setdefault("from_date", (today.replace(day=1)).isoformat())
            payload.setdefault("to_date", today.isoformat())
        elif operation == "CheckBalance":
            payload.setdefault("airline_id", "")

        fields_tpl = soap.get("fields") if isinstance(soap.get("fields"), dict) else {}
        required = _soap_required_payload_keys(fields_tpl)
        missing = [k for k in sorted(required) if not str(payload.get(k) or "").strip()]
        conn = soap.get("connectivity") if isinstance(soap.get("connectivity"), dict) else None

        # GetItinerary marks pnr/ticket optional, but empty calls crash the US host (NPE).
        resource_ops = {"Reservation", "IssueTicket", "GetFlightDetail", "GetItinerary"}
        resource_keys = _soap_payload_keys(fields_tpl)
        lacks_resource = (
            operation in resource_ops
            and resource_keys
            and not any(str(payload.get(k) or "").strip() for k in resource_keys)
        )

        if conn or missing or lacks_resource:
            if lacks_resource and not missing:
                missing = sorted(resource_keys)
            probe_op = str((conn or {}).get("operation") or "CheckBalance").strip()
            probe_fields = (conn or {}).get("fields") if isinstance((conn or {}).get("fields"), dict) else None
            if not probe_fields:
                probe_fields = {
                    "strUserId": "$auth.user_id",
                    "strPassword": "$auth.password",
                    "strAgencyId": "$auth.agency_id",
                    "strAirlineId": "$payload.airline_id|optional",
                    "strClientIP": "$auth.client_ip",
                }
            probe_soap = {
                "namespace": soap.get("namespace") or "http://booking.us.org/",
                "operation": probe_op,
                "response_mode": "data",
                "fields": probe_fields,
            }
            result = await self._execute_soap(
                AdapterRequest(payload=payload, operation="connectivity"),
                probe_soap,
                started,
            )
            if not result.success:
                return result
            note = f"Authenticated via {probe_op}"
            if missing and operation:
                note += f"; full {operation} needs: {', '.join(missing)}"
            raw = dict(result.raw) if isinstance(result.raw, dict) else {"raw": result.raw}
            raw.update({"connectivity_probe": probe_op, "note": note})
            return AdapterResponse(
                success=True,
                latency_ms=result.latency_ms,
                status_code=result.status_code,
                data=result.data,
                raw=raw,
            )

        return await self._execute_soap(
            AdapterRequest(payload=payload, operation="connectivity"),
            soap,
            started,
        )


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"text": response.text[:1000]}


def _to_api_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if re.match(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$", text):
        return text.upper()
    try:
        return date.fromisoformat(text).strftime("%d-%b-%Y").upper()
    except ValueError:
        pass
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().strftime("%d-%b-%Y").upper()
        except ValueError:
            continue
    return text


def _soap_payload_keys(fields: dict[str, Any], *, required_only: bool = False) -> set[str]:
    """Return $payload.* keys referenced by SOAP field templates."""
    keys: set[str] = set()
    for expr in fields.values():
        if not isinstance(expr, str):
            continue
        text = expr.strip()
        if not text.startswith("$payload."):
            continue
        if required_only and "|optional" in text:
            continue
        name = text[len("$payload.") :].split("|", 1)[0].strip()
        if name:
            keys.add(name)
    return keys


def _soap_required_payload_keys(fields: dict[str, Any]) -> set[str]:
    return _soap_payload_keys(fields, required_only=True)


def _resolve_soap_value(expr: Any, *, auth: dict[str, Any], payload: dict[str, Any]) -> str:
    """
    Resolve field template expressions.

    Examples:
      "$auth.user_id"
      "$payload.origin"
      "$payload.departure_date|api_date"
      "$payload.return_date|api_date|optional"
      "O"  (literal)
    """
    if expr is None:
        return ""
    if not isinstance(expr, str):
        return str(expr)
    text = expr
    if not text.startswith("$"):
        return text

    parts = text[1:].split("|")
    path = parts[0]
    transforms = parts[1:]
    root, _, rest = path.partition(".")
    if root == "auth":
        value = auth.get(rest) if rest else None
        # nested auth.soap ignored — credentials are top-level
        if rest and "." in rest:
            cur: Any = auth
            for bit in rest.split("."):
                cur = cur.get(bit) if isinstance(cur, dict) else None
            value = cur
    elif root == "payload":
        cur = payload
        for bit in rest.split("."):
            if not bit:
                continue
            if isinstance(cur, dict):
                cur = cur.get(bit)
            else:
                cur = None
                break
        value = cur
        # common aliases
        if value is None and rest == "flight_id":
            value = payload.get("offer_id") or payload.get("strFlightId")
        if value is None and rest == "return_date":
            extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
            value = extras.get("return_date")
    else:
        value = None

    if value is None or value == "":
        if "optional" in transforms:
            return ""
        return ""

    out = str(value)
    if "api_date" in transforms:
        out = _to_api_date(out)
    if "upper" in transforms:
        out = out.upper()
    if "str" in transforms:
        out = str(out)
    return out


def _build_soap_envelope(
    ns: str,
    operation: str,
    fields: dict[str, str],
    raw_fields: dict[str, str] | None = None,
) -> str:
    body_parts = [f"         <{k}>{xml_escape(v)}</{k}>" for k, v in fields.items()]
    for k, v in (raw_fields or {}).items():
        body_parts.append(f"         <{k}>{v}</{k}>")
    body = "\n".join(body_parts)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:book="{ns}">
   <soapenv:Header/>
   <soapenv:Body>
      <book:{operation}>
{body}
      </book:{operation}>
   </soapenv:Body>
</soapenv:Envelope>"""


def _unwrap_soap_return(raw: str) -> str:
    text = raw or ""
    m = re.search(r"<return\b[^>]*>(.*?)</return>", text, flags=re.I | re.S)
    if m:
        inner = html.unescape(m.group(1)).strip()
        if "&lt;" in inner and "<" not in inner[:30]:
            inner = html.unescape(inner)
        return inner
    return html.unescape(text)


def _soap_error_message(payload: str) -> str | None:
    m = re.search(r"<Error\b[^>]*>(.*?)</Error>", payload or "", flags=re.I | re.S)
    if not m:
        return None
    msg = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return html.unescape(msg).strip() or None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _soap_items(
    payload: str,
    *,
    item_tag: str,
    wrap_tags: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    if not (payload or "").strip():
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []

    rows: list[dict[str, str]] = []

    def row_from(el: ET.Element, direction: str = "") -> dict[str, str]:
        row: dict[str, str] = {}
        for child in el:
            row[_local(child.tag)] = (child.text or "").strip()
        if direction:
            row["Direction"] = direction
        return row

    if wrap_tags:
        for wrap in root.iter():
            wname = _local(wrap.tag)
            if wname not in wrap_tags:
                continue
            for el in wrap:
                if _local(el.tag) == item_tag:
                    row = row_from(el, wname)
                    if any(row.values()):
                        rows.append(row)
    if not rows:
        for el in root.iter():
            if _local(el.tag) != item_tag:
                continue
            row = row_from(el)
            if any(row.values()):
                rows.append(row)
    return rows


def _find_tag_texts(blob: str, name: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(rf"<{name}\b[^>]*>(.*?)</{name}>", blob or "", flags=re.I | re.S):
        val = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        val = html.unescape(val).strip()
        if val:
            out.append(val)
    return out


def _money(raw: str) -> float | None:
    text = re.sub(r"[^\d.]", "", str(raw or "").replace(",", ""))
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _map_soap_item(item: dict[str, str], mapping: dict[str, str], provider_slug: str) -> dict[str, Any]:
    """Map SOAP Availability row → NormalizedOffer fields using config mapping."""
    # Built-in fare total if adult+taxes present and price not mapped from a single field
    adult = _money(item.get("AdultFare") or "")
    fuel = _money(item.get("FuelSurcharge") or "") or 0.0
    tax = _money(item.get("Tax") or "") or 0.0
    vat = _money(item.get("AdultVAT") or "") or 0.0
    computed_total = None if adult is None else adult + fuel + tax + vat

    out: dict[str, Any] = {"provider": provider_slug, "raw": item, "stops": 0}
    if mapping:
        for unified, src in mapping.items():
            if unified == "items":
                continue
            if src == "__total__":
                out[unified] = computed_total
            else:
                out[unified] = item.get(src)
    else:
        out.update(
            {
                "offer_id": item.get("FlightId"),
                "origin": item.get("Departure"),
                "destination": item.get("Arrival"),
                "airline": item.get("Airline"),
                "flight_number": item.get("FlightNo"),
                "cabin_class": item.get("FlightClassCode"),
                "price": computed_total,
                "currency": item.get("Currency") or "NPR",
            }
        )
    if out.get("price") is not None:
        try:
            out["price"] = float(out["price"])
        except (TypeError, ValueError):
            pass
    return out
