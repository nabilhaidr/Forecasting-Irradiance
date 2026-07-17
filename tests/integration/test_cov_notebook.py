from __future__ import annotations

import asyncio
import csv
import re
import sys
import zipfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


NOTEBOOK = Path("notebooks/S0_2_COV_Characterisation.ipynb")
TAGS = (
    "PLTS IKN / STS09 / WB09_EMI01 / MEAS / GLOBAL HORIZONTAL IRRADIANCE (GHI)",
    "PLTS IKN / STS09 / WB09_EMI01 / MEAS / DIFFUSE HORIZONTAL IRRADIANCE (DHI)",
    "PLTS IKN / STS09 / WB09_EMI01 / MEAS / DIRECT HORIZONTAL IRRADIANCE (DNI*cosZ)",
    "PLTS IKN / STS09 / WB09_EMI01 / MEAS / GLOBAL INCLINED IRRADIANCE (POA)",
    "PLTS IKN / STS09 / WB09_EMI01 / MEAS / IN-PLANE REAR-SIDE IRRADIANCE (RSI) 01",
)


def _create_notebook_inputs(root: Path) -> tuple[Path, Path, Path]:
    raw_dir = root / "mounted-raw"
    raw_dir.mkdir()
    archive_path = raw_dir / "generic.zip"
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for tag_index, tag in enumerate(TAGS):
            lines = [f'date_time;"{tag}";object_caeid']
            for index in range(25):
                total_seconds = index * 10
                lines.append(
                    "2026-06-01 08:"
                    f"{total_seconds // 60:02d}:{total_seconds % 60:02d}.000;"
                    f"{10 + tag_index + index * 0.1:.6f};0"
                )
            archive.writestr(
                f"data-{tag_index}.csv",
                ("\n".join(lines) + "\n").encode("utf-8"),
            )
    reference = root / "drive_inventory.csv"
    with reference.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["drive_file_id", "zip_name", "byte_size"])
        writer.writerow(["drive-fixture", archive_path.name, archive_path.stat().st_size])
    site_config = root / "site.yaml"
    site_config.write_text(
        "site:\n  site_id: PLTS-IKN\n  timezone: Asia/Makassar\n",
        encoding="utf-8",
    )
    return raw_dir, reference, site_config


def test_notebook_is_a_thin_editable_runner() -> None:
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    sources = "\n".join(cell.source for cell in notebook.cells)
    parameter_cells = [
        cell for cell in notebook.cells if "parameters" in cell.metadata.get("tags", [])
    ]

    assert len(parameter_cells) == 1
    for name in (
        "DRIVE_RAW_DATA_DIR",
        "LOCAL_STAGE_DIR",
        "OUTPUT_DIR",
        "STRICT_MODE",
        "SKIP_DRIVE_MOUNT",
    ):
        assert name in parameter_cells[0].source
    assert "from src.characterisation.cov_cli import run_cov_characterisation" in sources
    assert "shutil.copy2" in sources
    assert not re.search(r"def\s+(estimate_|characterise_|parse_scada_)", sources)
    for forbidden in ("client_secret", "refresh_token", "oauth_json", "rclone.conf"):
        assert forbidden not in sources.lower()


def test_notebook_executes_locally_and_writes_pipeline_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_dir, reference, site_config = _create_notebook_inputs(tmp_path)
    output_dir = tmp_path / "notebook-output"
    stage_dir = tmp_path / "vm-stage"
    repo_root = Path.cwd().resolve()
    overrides = {
        "COV_REPO_ROOT": str(repo_root),
        "COV_DRIVE_RAW_DATA_DIR": str(raw_dir),
        "COV_LOCAL_STAGE_DIR": str(stage_dir),
        "COV_OUTPUT_DIR": str(output_dir),
        "COV_REFERENCE_INVENTORY": str(reference),
        "COV_SITE_CONFIG": str(site_config),
        "COV_STRICT_MODE": "true",
        "COV_SKIP_DRIVE_MOUNT": "true",
        "COV_DRIVE_OUTPUT_DIR": "",
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)

    notebook = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    )
    executed = client.execute()

    assert (output_dir / "run_manifest.json").is_file()
    assert (output_dir / "tag_characterisation.csv").is_file()
    assert (output_dir / "phase0_cov_characterisation.md").is_file()
    assert len(list(stage_dir.glob("*.zip"))) == 1
    outputs = "\n".join(
        str(output)
        for cell in executed.cells
        for output in cell.get("outputs", [])
    )
    assert "canonical_freq" in outputs
