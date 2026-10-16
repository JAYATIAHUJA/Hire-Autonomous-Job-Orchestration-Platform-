"""DPDP right to erasure: DELETE /v1/me removes the account and every row it owns.

Order matters. Stored files go first (a storage failure then leaves the rows in
place to retry, instead of orphaning files nobody can find), then each module's
rows, then the login identities, sessions and the account itself.
"""

from typing import Optional

from sqlalchemy.orm import Session as DbSession

from .. import models as pow_profile_models
from ..applications.models import Application, ConsentLog, PipelineEvent, ProcessedMessage
from ..facts import repository as facts_repository
from ..facts.storage import ObjectStore
from ..services import pow_service
from .models import Account, OtpCode


def erase_account(db: DbSession, account: Account, store: Optional[ObjectStore]) -> None:
    account_id = account.id
    email = account.email

    # Resume files and the fact vault (raises before deleting anything if files exist
    # but storage is not configured).
    facts_repository.erase_account_data(db, account_id, store)
    db.flush()
    # PoW runs, evidence and the profiles they built (commits).
    pow_service.erase(db, account_id)

    # Profiles analysed directly through /api/profile/analyze.
    for user in db.query(pow_profile_models.User).filter(pow_profile_models.User.account_id == account_id).all():
        db.delete(user)  # cascades to projects, contributions, skills

    # Swipes, consent receipts, the pipeline trail and the mail ledger.
    app_ids = [a.id for a in db.query(Application.id).filter(Application.account_id == account_id).all()]
    if app_ids:
        db.query(PipelineEvent).filter(PipelineEvent.application_db_id.in_(app_ids)).delete(synchronize_session=False)
    db.query(ConsentLog).filter(ConsentLog.account_id == account_id).delete(synchronize_session=False)
    db.query(Application).filter(Application.account_id == account_id).delete(synchronize_session=False)
    db.query(ProcessedMessage).filter(ProcessedMessage.account_id == account_id).delete(synchronize_session=False)

    if email:
        db.query(OtpCode).filter(OtpCode.email == email).delete(synchronize_session=False)
    # Identities, sessions and privacy consents cascade from the account.
    db.delete(db.merge(account))
    db.commit()
