"""MFI branch (office) management — manager only.

A manager lists the MFI's branches and creates new ones, capped by the
subscription plan's ``max_branches``.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.models import Branch
from app.schemas.branch import BranchCreate, BranchSummary

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("", response_model=list[BranchSummary])
def list_branches(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[Branch]:
    """List the MFI's branches, ordered by name."""
    return (
        db.query(Branch)
        .filter_by(mfi_account_id=principal.mfi_account.id)
        .order_by(Branch.name)
        .all()
    )


@router.post(
    "", response_model=BranchSummary, status_code=status.HTTP_201_CREATED
)
def create_branch(
    payload: BranchCreate,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> Branch:
    """Create a branch, enforcing the plan's branch limit + unique name."""
    mfi = principal.mfi_account
    name = payload.name.strip()
    if not name:
        raise ValidationError("Branch name is required.")

    plan = mfi.plan
    if plan is not None and plan.max_branches is not None:
        existing = (
            db.query(Branch).filter_by(mfi_account_id=mfi.id).count()
        )
        if existing >= plan.max_branches:
            raise ValidationError(
                "Your plan's branch limit has been reached."
            )

    if (
        db.query(Branch)
        .filter_by(mfi_account_id=mfi.id, name=name)
        .first()
        is not None
    ):
        raise ValidationError("A branch with that name already exists.")

    branch = Branch(mfi_account_id=mfi.id, name=name)
    db.add(branch)
    db.flush()
    return branch
