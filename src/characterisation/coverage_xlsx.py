"""Generalised raw-column ingest for every instantaneous irradiance XLSX family.

The S0-3 closure reader (`dni_cosz_xlsx`) is intentionally frozen to the
GHI/DHI/DNIcosZ audit scope; this module extends the same raw-column contract
(`date_time`, one value column, `object_caeid`) to POA, RSI heads, and the
WS-5 `Total_Irradiance` spelling for the S0-5 coverage audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .cov_contract import ParameterClass
from .cov_ingest import sha256_file
from .dni_cosz_xlsx import WS_TO_LOCATION


STANDARDIZED_FILE = re.compile(
    r"^(GHI|DHI|DNIcosZ|POA|RSI_0[123]|Total_Irradiance)"
    r"_PLTS-IKN_WS-([1-5])_(\d{4})-(.+)\.xlsx$",
    re.IGNORECASE,
)
LEGACY_FILE = re.compile(
    r"^(GHI|DHI|DNI\s*cosZ|POA|RSI\s*0[123]|Total\s+Irradiance)"
    r"\s+WS-([1-5])\s+PLTS\s+IKN(?:\s+.+)?\.xlsx$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CoverageFileIdentity:
    """Channel identity recovered from an instantaneous workbook filename."""

    channel_group: str
    subchannel: str | None
    ws: str
    filename_schema: str


@dataclass(frozen=True)
class CoverageXlsxIngestion:
    """Instantaneous events and file-level provenance for the coverage audit."""

    events: pd.DataFrame
    source_manifest: pd.DataFrame
    strict_errors: tuple[str, ...]


def _normalise_channel_token(token: str) -> tuple[str, str | None]:
    compact = re.sub(r"[\s_]+", "", token).upper()
    if compact == "GHI" or compact == "TOTALIRRADIANCE":
        return "GHI", None
    if compact == "DHI":
        return "DHI", None
    if compact == "DNICOSZ":
        return "DNIcosZ", None
    if compact == "POA":
        return "POA", None
    if compact.startswith("RSI"):
        return "RSI", f"RSI_{compact[-2:]}"
    raise ValueError(f"unrecognised channel token: {token!r}")


def parse_coverage_filename(name: str) -> CoverageFileIdentity | None:
    """Identify channel, WS number, and schema; reject accumulation families."""

    if "accum" in name.lower():
        return None
    standard = STANDARDIZED_FILE.fullmatch(name)
    if standard is not None:
        channel_group, subchannel = _normalise_channel_token(standard.group(1))
        return CoverageFileIdentity(
            channel_group, subchannel, standard.group(2), "standardized"
        )
    legacy = LEGACY_FILE.fullmatch(name)
    if legacy is not None:
        channel_group, subchannel = _normalise_channel_token(legacy.group(1))
        return CoverageFileIdentity(
            channel_group, subchannel, legacy.group(2), "legacy"
        )
    return None


EVENT_COLUMNS = (
    "emi",
    "sts",
    "wb",
    "channel_group",
    "channel_key",
    "subchannel",
    "parameter_class",
    "event_time_raw",
    "event_time",
    "event_time_ns",
    "value",
    "object_caeid_raw",
    "source_xlsx",
    "source_xlsx_relative_path",
)


def ingest_coverage_xlsx(root: Path) -> CoverageXlsxIngestion:
    """Read only raw date/value/object columns from every instantaneous file."""

    root = Path(root)
    event_frames: list[pd.DataFrame] = []
    manifest_rows: list[dict[str, object]] = []
    errors: list[str] = []
    matches: list[tuple[Path, CoverageFileIdentity]] = []
    for path in sorted(root.rglob("*.xlsx"), key=lambda item: item.as_posix()):
        identity = parse_coverage_filename(path.name)
        if identity is not None:
            matches.append((path, identity))
    for path, identity in matches:
        emi, sts, wb = WS_TO_LOCATION[identity.ws]
        channel_key = identity.subchannel or identity.channel_group
        try:
            try:
                raw = pd.read_excel(path, usecols="A:E", engine="openpyxl")
            except ValueError:
                # pandas rejects out-of-bounds usecols on narrow malformed files;
                # fall back to a plain read so layout errors stay diagnosable.
                raw = pd.read_excel(path, engine="openpyxl").iloc[:, :5]
        except Exception as exc:  # pandas/openpyxl expose several workbook errors
            errors.append(f"{path.name}: cannot read workbook: {exc}")
            continue
        if "date_time" not in raw.columns or "object_caeid" not in raw.columns:
            errors.append(f"{path.name}: missing raw date_time/object_caeid columns")
            continue
        columns = list(raw.columns)
        date_position = columns.index("date_time")
        object_position = columns.index("object_caeid")
        value_candidates = columns[date_position + 1 : object_position]
        if len(value_candidates) != 1:
            errors.append(
                f"{path.name}: expected one raw value column between date_time and "
                f"object_caeid, found {len(value_candidates)}"
            )
            continue
        value_column = value_candidates[0]
        parsed_time = pd.to_datetime(raw["date_time"], errors="coerce")
        parsed_value = pd.to_numeric(raw[value_column], errors="coerce")
        valid = parsed_time.notna() & parsed_value.notna()
        events = pd.DataFrame(
            {
                "emi": emi,
                "sts": sts,
                "wb": wb,
                "channel_group": identity.channel_group,
                "channel_key": channel_key,
                "subchannel": identity.subchannel,
                "parameter_class": ParameterClass.INSTANTANEOUS_IRRADIANCE.value,
                "event_time_raw": raw.loc[valid, "date_time"].astype(str),
                "event_time": parsed_time.loc[valid],
                "event_time_ns": parsed_time.loc[valid].astype("int64"),
                "value": parsed_value.loc[valid].astype("float64"),
                "object_caeid_raw": raw.loc[valid, "object_caeid"].astype("string"),
                "source_xlsx": path.name,
                "source_xlsx_relative_path": path.relative_to(root).as_posix(),
            }
        ).reset_index(drop=True)
        event_frames.append(events)
        manifest_rows.append(
            {
                "xlsx_name": path.name,
                "relative_path": path.relative_to(root).as_posix(),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
                "ws": f"WS-{identity.ws}",
                "emi": emi,
                "channel_group": identity.channel_group,
                "subchannel": identity.subchannel,
                "filename_schema": identity.filename_schema,
                "raw_row_count": int(len(events)),
                "coverage_start_raw": (
                    None if events.empty else str(events["event_time_raw"].iloc[0])
                ),
                "coverage_end_raw": (
                    None if events.empty else str(events["event_time_raw"].iloc[-1])
                ),
            }
        )

    events = (
        pd.concat(event_frames, ignore_index=True)
        if event_frames
        else pd.DataFrame(columns=list(EVENT_COLUMNS))
    )
    if not events.empty:
        events = events.sort_values(
            ["emi", "channel_key", "event_time_ns", "source_xlsx_relative_path"],
            kind="stable",
            ignore_index=True,
        ).drop_duplicates(
            ["emi", "channel_key", "event_time_ns", "value", "object_caeid_raw"],
            keep="first",
            ignore_index=True,
        )
    manifest = pd.DataFrame(manifest_rows)
    if not manifest.empty:
        manifest = manifest.sort_values(
            "relative_path", kind="stable", ignore_index=True
        )
        subchannel = manifest["subchannel"].astype(object)
        manifest["subchannel"] = subchannel.where(subchannel.notna(), None)
    return CoverageXlsxIngestion(events, manifest, tuple(errors))
