"""Masterdata / reference data (ADR-010) -- slow-changing, enterprise-wide
reference data, a DIFFERENT category from the transactional business objects
elsewhere in this package (ADR-002 governs those; this doesn't). Every
code_field below is what CodeListStore keys on."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

PartyKind = Literal["customer", "carrier", "forwarder", "consignee"]


class Party(BaseModel):
    party_id: str
    name: str
    kind: PartyKind
    country: str | None = None
    active: bool = True


class Location(BaseModel):
    """Real UN/LOCODE reference (systems/tms/fixtures/locations.yaml)."""

    locode: str
    name: str
    type: Literal["seaport", "airport", "inland_terminal", "rail_terminal"]
    country: str
    timezone: str
    lat: float | None = None
    lon: float | None = None


class Currency(BaseModel):
    """ISO 4217."""

    code: str
    name: str
    minor_unit: int  # decimal places, e.g. 2 for EUR/USD, 0 for JPY
    symbol: str | None = None
    active: bool = True


class Incoterm(BaseModel):
    """Incoterms(R) 2020."""

    code: str
    name: str
    responsibility_transfer: str
    version: str = "2020"


class Commodity(BaseModel):
    hs_code: str
    description: str
    dangerous_goods: bool = False
    dg_class: str | None = None  # -> DangerousGoodsClass.class_code, if applicable


class Equipment(BaseModel):
    code: str
    name: str
    type: Literal["container", "vehicle"]
    capacity: str | None = None


class UnitOfMeasure(BaseModel):
    code: str
    name: str
    quantity_kind: Literal["weight", "volume", "count"]


class DangerousGoodsClass(BaseModel):
    """IMDG classes 1-9."""

    class_code: str
    name: str
    description: str


class PaymentTerm(BaseModel):
    code: str
    name: str
    description: str | None = None
