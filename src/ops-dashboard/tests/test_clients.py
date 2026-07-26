import httpx
import pytest

from ops_dashboard.clients import GeoClient, GeoUnavailableError, RateClient, TmsClient, TmsUnavailableError


class _FakeTransport(httpx.MockTransport):
    pass


def _client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tms_client_get_route(monkeypatch):
    def handler(request):
        assert request.url.path == "/routes/SHA-HAM-MUC"
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(200, json={"id": "SHA-HAM-MUC"})

    monkeypatch.setattr(httpx, "get", lambda url, headers, timeout: _client_with(handler).get(url, headers=headers))
    client = TmsClient(base_url="http://tms", api_key="k")
    assert client.get_route("SHA-HAM-MUC") == {"id": "SHA-HAM-MUC"}


def test_tms_client_404_returns_none(monkeypatch):
    def handler(request):
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "get", lambda url, headers, timeout: _client_with(handler).get(url, headers=headers))
    client = TmsClient(base_url="http://tms", api_key="k")
    assert client.get_route("NOPE") is None


def test_tms_client_unreachable_raises(monkeypatch):
    def raise_connect_error(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", raise_connect_error)
    client = TmsClient(base_url="http://tms", api_key="k")
    with pytest.raises(TmsUnavailableError):
        client.get_route("SHA-HAM-MUC")


def test_rate_client_get_rate(monkeypatch):
    def handler(request):
        assert request.url.path == "/rates/SHA-HAM-MUC"
        return httpx.Response(200, json={"route_id": "SHA-HAM-MUC", "carrier_id": "COSCO"})

    monkeypatch.setattr(httpx, "get", lambda url, headers, timeout: _client_with(handler).get(url, headers=headers))
    client = RateClient(base_url="http://rate", api_key="k")
    assert client.get_rate("SHA-HAM-MUC")["carrier_id"] == "COSCO"


def test_geo_client_sends_a_bearer_token_not_an_api_key(monkeypatch):
    """M10 D4: the ONE client authenticating with Authorization: Bearer,
    not X-API-Key -- geo-api is OIDC-protected, not API-key-protected."""
    def handler(request):
        assert request.url.path == "/v1/legs/geometry"
        assert dict(request.url.params) == {"from": "CNSHA", "to": "DEHAM", "mode": "ocean"}
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"distance_km": 20568.7, "geometry": {"type": "LineString", "coordinates": []}})

    monkeypatch.setattr(
        httpx, "get",
        lambda url, params, headers, timeout: _client_with(handler).get(url, params=params, headers=headers),
    )
    client = GeoClient(base_url="http://geo", token_provider=lambda: "test-token")
    result = client.get_leg_geometry(from_locode="CNSHA", to_locode="DEHAM", mode="ocean")
    assert result["distance_km"] == 20568.7


def test_geo_client_unreachable_raises(monkeypatch):
    def raise_connect_error(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", raise_connect_error)
    client = GeoClient(base_url="http://geo", token_provider=lambda: "test-token")
    with pytest.raises(GeoUnavailableError):
        client.get_leg_geometry(from_locode="CNSHA", to_locode="DEHAM", mode="ocean")
