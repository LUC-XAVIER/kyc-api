"""Unit tests for the verify request -> PipelineInput mapping.

Pure validation/mapping; no database or ML, so it runs anywhere.
"""

import uuid

import pytest

from app.api.v1.routes.verify import build_pipeline_input
from app.core.exceptions import ValidationError
from app.models.enums import DocumentType


def _kwargs(**overrides):
    base = {
        "client_id": "CL-1",
        "mfi_account_id": uuid.uuid4(),
        "document_type": DocumentType.NIC,
        "id_front": b"front",
        "selfie": b"selfie",
        "id_back": b"back",
    }
    base.update(overrides)
    return base


def test_nic_with_back_builds_input() -> None:
    """A complete NIC request maps to a populated PipelineInput."""
    result = build_pipeline_input(**_kwargs())

    assert result.document_type is DocumentType.NIC
    assert result.id_front_image == b"front"
    assert result.id_back_image == b"back"
    assert result.selfie_image == b"selfie"


def test_nic_without_back_is_rejected() -> None:
    """A NIC missing its back image is a validation error."""
    with pytest.raises(ValidationError, match="back"):
        build_pipeline_input(**_kwargs(id_back=None))


def test_passport_without_back_is_allowed() -> None:
    """A single-page passport needs no back image."""
    result = build_pipeline_input(
        **_kwargs(document_type=DocumentType.PASSPORT, id_back=None)
    )

    assert result.document_type is DocumentType.PASSPORT
    assert result.id_back_image is None


@pytest.mark.parametrize("missing", ["id_front", "selfie"])
def test_missing_required_image_is_rejected(missing: str) -> None:
    """An empty front or selfie is rejected before the pipeline runs."""
    with pytest.raises(ValidationError, match="required"):
        build_pipeline_input(**_kwargs(**{missing: b""}))
