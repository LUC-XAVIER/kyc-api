"""Verification record and the per-stage pipeline result entities."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON as SAJSON,
)
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import EMBEDDING_DIM, Base, TimestampMixin, UUIDMixin
from app.db.types import EncryptedBytes, EncryptedDate, EncryptedString
from app.models.enums import (
    DuplicateResolution,
    ImageKind,
    Sex,
    SubmissionMethod,
    VerificationStatus,
)

if TYPE_CHECKING:
    from app.models.mfi import User


class Verification(UUIDMixin, TimestampMixin, Base):
    """Central record of a KYC verification request and its result."""

    __tablename__ = "verifications"

    client_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id")
    )
    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id"), index=True
    )
    submission_method: Mapped[SubmissionMethod] = mapped_column(
        Enum(SubmissionMethod, name="submission_method")
    )
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status")
    )
    reject_reason: Mapped[str | None] = mapped_column(String(64))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    processed_at: Mapped[datetime | None] = mapped_column()
    # Set when a manager approves/rejects a PENDING case: the free-text note
    # shown back to the agent, and when the decision was made.
    review_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    extracted_data: Mapped["ExtractedData | None"] = relationship(
        back_populates="verification", uselist=False
    )
    liveness_result: Mapped["LivenessResult | None"] = relationship(
        back_populates="verification", uselist=False
    )
    face_match_result: Mapped["FaceMatchResult | None"] = relationship(
        back_populates="verification", uselist=False
    )
    duplicate_flags: Mapped[list["DuplicateFlag"]] = relationship(
        back_populates="verification"
    )
    images: Mapped[list["VerificationImage"]] = relationship(
        back_populates="verification"
    )
    agent: Mapped["User | None"] = relationship("User")

    # --- Derived attributes surfaced on list/summary rows (read via
    #     Pydantic ``from_attributes``). ---
    @property
    def client_name(self) -> str | None:
        """The name read off the ID document, if OCR captured one."""
        return self.extracted_data.full_name if self.extracted_data else None

    @property
    def agent_name(self) -> str | None:
        """Full name of the agent who submitted this verification."""
        return self.agent.full_name if self.agent else None

    @property
    def branch_name(self) -> str | None:
        """Branch of the submitting agent."""
        return self.agent.branch_name if self.agent else None

    @property
    def flagged_duplicate(self) -> bool:
        """Whether the pipeline raised any duplicate-face flag."""
        return bool(self.duplicate_flags)

    @property
    def reviewed(self) -> bool:
        """Whether a manager has decided this (formerly PENDING) case."""
        return self.reviewed_at is not None

    @property
    def available_images(self) -> list["ImageKind"]:
        """Kinds of captured image stored for this verification.

        Reads only the rows' ``kind`` (the bytes are deferred), so the
        detail view can offer exactly the images that exist — e.g. no back
        for a passport.
        """
        return [image.kind for image in self.images]


class ExtractedData(UUIDMixin, Base):
    """OCR output extracted from the NIC card.

    The four directly identifying fields are encrypted at rest (NFR03/NFR04)
    via :mod:`app.db.types`, so a database dump or a leaked backup does not
    expose a client's identity. Encryption is transparent to callers.

    ``expiry_date``, ``sex`` and ``occupation`` are left readable: none of
    them identifies a person on its own, and keeping them queryable leaves
    room for aggregate reporting. ``field_confidences`` holds OCR scores,
    not the field values.
    """

    __tablename__ = "extracted_data"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id"), unique=True
    )
    full_name: Mapped[str | None] = mapped_column(EncryptedString)
    id_number: Mapped[str | None] = mapped_column(EncryptedString)
    date_of_birth: Mapped[date | None] = mapped_column(EncryptedDate)
    place_of_birth: Mapped[str | None] = mapped_column(EncryptedString)
    expiry_date: Mapped[date | None] = mapped_column()
    sex: Mapped[Sex | None] = mapped_column(Enum(Sex, name="sex"))
    occupation: Mapped[str | None] = mapped_column(String(255))
    field_confidences: Mapped[dict | None] = mapped_column(SAJSON)

    verification: Mapped["Verification"] = relationship(
        back_populates="extracted_data"
    )


class FaceEmbedding(UUIDMixin, TimestampMixin, Base):
    """Numerical face fingerprint stored for duplicate detection."""

    __tablename__ = "face_embeddings"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id")
    )
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    model_used: Mapped[str] = mapped_column(String(32), default="ArcFace")


class LivenessResult(UUIDMixin, TimestampMixin, Base):
    """Result of the liveness / anti-spoofing check."""

    __tablename__ = "liveness_results"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id"), unique=True
    )
    passed: Mapped[bool] = mapped_column(Boolean)
    method: Mapped[str] = mapped_column(String(64))
    anti_spoof_score: Mapped[float | None] = mapped_column(Float)
    landmarks_detected: Mapped[bool] = mapped_column(Boolean, default=False)

    verification: Mapped["Verification"] = relationship(
        back_populates="liveness_result"
    )


class FaceMatchResult(UUIDMixin, Base):
    """Face-matching score between the selfie and the NIC photo."""

    __tablename__ = "face_match_results"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id"), unique=True
    )
    match_score: Mapped[float] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean)
    threshold: Mapped[float] = mapped_column(Float)
    model_used: Mapped[str] = mapped_column(String(32), default="ArcFace")

    verification: Mapped["Verification"] = relationship(
        back_populates="face_match_result"
    )


class DuplicateFlag(UUIDMixin, TimestampMixin, Base):
    """Duplicate-detection result and its human review decision."""

    __tablename__ = "duplicate_flags"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id")
    )
    matched_client_id: Mapped[str | None] = mapped_column(String(64))
    similarity_score: Mapped[float] = mapped_column(Float)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column()
    resolution: Mapped[DuplicateResolution] = mapped_column(
        Enum(DuplicateResolution, name="duplicate_resolution"),
        default=DuplicateResolution.PENDING,
    )

    verification: Mapped["Verification"] = relationship(
        back_populates="duplicate_flags"
    )


class VerificationImage(UUIDMixin, TimestampMixin, Base):
    """A captured image (ID front/back or selfie) kept for manager review.

    The bytes are a re-compressed JPEG sealed with AES-GCM at rest — these
    are the most sensitive data in the system, so a database dump or leaked
    backup never exposes a client's face or document. Access is always
    MFI-scoped at the route layer.
    """

    __tablename__ = "verification_images"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verifications.id"), index=True
    )
    kind: Mapped[ImageKind] = mapped_column(Enum(ImageKind, name="image_kind"))
    content_type: Mapped[str] = mapped_column(String(32))
    # Deferred: the detail endpoint lists which images exist (by kind) without
    # dragging the encrypted bytes along; they load only when actually served.
    image: Mapped[bytes] = mapped_column(EncryptedBytes, deferred=True)

    verification: Mapped["Verification"] = relationship(
        back_populates="images"
    )
