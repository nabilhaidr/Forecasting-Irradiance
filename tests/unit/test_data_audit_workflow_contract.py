from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/s0-5-data-audit.yml")


def test_audit_workflow_is_manual_read_only_and_pinned() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "contents: read" in text
    assert "persist-credentials: false" in text
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0" in text
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in text
    assert "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f" in text


def test_audit_workflow_stages_all_instantaneous_channels() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "EXPECTED_RAW_ZIP_COUNT: \"145\"" in text
    assert "EXPECTED_RAW_BYTES: \"23776109\"" in text
    # every instantaneous channel family must be staged, accumulation excluded
    for pattern in (
        "GHI_PLTS-IKN",
        "DHI_PLTS-IKN",
        "DNIcosZ_PLTS-IKN",
        "POA_PLTS-IKN",
        "RSI_0",
        "Total_Irradiance_PLTS-IKN",
    ):
        assert pattern in text, pattern
    assert "*Accum*.xlsx" in text


def test_audit_workflow_runs_irradiance_scope_and_excludes_raw_uploads() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "requirements-nwp.txt" in text
    assert "requirements-cov.txt" in text
    assert "python -m src.characterisation.data_audit_cli" in text
    assert "--scope irradiance" in text
    upload_start = text.index("actions/upload-artifact@")
    upload_block = text[upload_start:]
    assert "raw_cov" not in upload_block
    assert "historical" not in upload_block
    assert "if: always()" in text
