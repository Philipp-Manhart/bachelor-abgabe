from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ScaleProfile:
    name: str
    customers: int
    dealers: int
    vehicles: int
    leasing_contracts: int
    loan_contracts: int
    account_seeds: int


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    scale: ScaleProfile
    seed: int
    date_start: date
    date_end: date
    banking_snapshot_start: date


DEV_SCALE = ScaleProfile(
    name="dev",
    customers=300,
    dealers=25,
    vehicles=220,
    leasing_contracts=150,
    loan_contracts=120,
    account_seeds=80,
)

BENCHMARK_SCALE = ScaleProfile(
    name="benchmark",
    customers=2500,
    dealers=120,
    vehicles=2800,
    leasing_contracts=2000,
    loan_contracts=1500,
    account_seeds=500,
)

SCALE_PROFILES: dict[str, ScaleProfile] = {
    DEV_SCALE.name: DEV_SCALE,
    BENCHMARK_SCALE.name: BENCHMARK_SCALE,
}

DATE_START = date(2018, 1, 1)
DATE_END = date(2026, 12, 31)
BANKING_SNAPSHOT_START = date(2023, 1, 1)
DEFAULT_SEED = 42


def build_config(scale_name: str, seed: int = DEFAULT_SEED) -> GeneratorConfig:
    try:
        scale = SCALE_PROFILES[scale_name]
    except KeyError as exc:
        supported = ", ".join(sorted(SCALE_PROFILES))
        msg = f"Unsupported scale profile {scale_name!r}. Expected one of: {supported}"
        raise ValueError(msg) from exc

    return GeneratorConfig(
        scale=scale,
        seed=seed,
        date_start=DATE_START,
        date_end=DATE_END,
        banking_snapshot_start=BANKING_SNAPSHOT_START,
    )
