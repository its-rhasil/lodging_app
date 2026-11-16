"""Folio ledger (DL-R07, DL-R08, DL-R10). folio_transactions is append-only (DL-P13)."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Integer, Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

TXN_TYPES = ("room_charge", "charge", "payment", "refund", "waiver", "reversal")
PAYMENT_METHODS = ("cash", "upi", "card", "bank_transfer", "other")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Folio(Base):
    __tablename__ = "folios"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_folios_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "stay_id"], ["stays.tenant_id", "stays.id"], name="fk_folios_stay"
        ),
        CheckConstraint("status IN ('open', 'closed')", name="ck_folio_status"),
        CheckConstraint("(status = 'closed') = (closed_at IS NOT NULL)", name="ck_folio_closed_at"),
        Index("ix_folios_tenant_status", "tenant_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False)
    stay_id = Column(Integer, nullable=False, unique=True)  # one folio per stay
    status = Column(String, nullable=False, default="open", server_default="open")
    opened_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    # NULL when the folio closed automatically (a later payment settled it).
    closed_by_user_id = Column(Integer, ForeignKey("users.id"))
    # Set on checkout with a balance owed (DL-P08); the folio then stays open under Pending balances.
    forced_checkout_reason = Column(String)

    stay = relationship("Stay", back_populates="folio", viewonly=True)
    transactions = relationship("FolioTransaction", viewonly=True, order_by="FolioTransaction.id")


class FolioTransaction(Base):
    __tablename__ = "folio_transactions"
    __table_args__ = (
        UniqueConstraint("folio_id", "id", name="uq_folio_transactions_folio_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "folio_id"], ["folios.tenant_id", "folios.id"],
            name="fk_folio_transactions_folio",
        ),
        # A waiver/reversal points at a row of the same folio.
        ForeignKeyConstraint(
            ["folio_id", "related_txn_id"],
            ["folio_transactions.folio_id", "folio_transactions.id"],
            name="fk_folio_transactions_related",
        ),
        UniqueConstraint("folio_id", "posting_key", name="uq_folio_posting_key"),
        CheckConstraint(f"txn_type IN ({_sql_list(TXN_TYPES)})", name="ck_txn_type"),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_txn_direction"),
        CheckConstraint("amount > 0", name="ck_txn_amount"),
        CheckConstraint(
            "(txn_type IN ('room_charge', 'charge', 'refund') AND direction = 'debit')"
            " OR (txn_type IN ('payment', 'waiver') AND direction = 'credit')"
            " OR txn_type = 'reversal'",
            name="ck_txn_dir_map",
        ),
        CheckConstraint(
            "(txn_type IN ('waiver', 'reversal')) = (related_txn_id IS NOT NULL)",
            name="ck_txn_related",
        ),
        # A waiver/reversal points at an earlier row: never itself, never a later one.
        # Relies on sequence-generated ids (later row = bigger id). If ids ever become
        # UUIDs, change this to "related_txn_id IS NULL OR related_txn_id <> id".
        CheckConstraint("related_txn_id IS NULL OR related_txn_id < id", name="ck_txn_related_earlier"),
        # Both columns are filled for room charges and both are empty for everything else.
        CheckConstraint(
            "(txn_type = 'room_charge' AND period_no IS NOT NULL AND period_start_at IS NOT NULL)"
            " OR (txn_type <> 'room_charge' AND period_no IS NULL AND period_start_at IS NULL)",
            name="ck_txn_period",
        ),
        CheckConstraint(
            f"payment_method IS NULL OR payment_method IN ({_sql_list(PAYMENT_METHODS)})",
            name="ck_txn_payment_method",
        ),
        CheckConstraint(
            "(txn_type IN ('payment', 'refund')) = (payment_method IS NOT NULL)",
            name="ck_txn_method_required",
        ),
        CheckConstraint(
            "txn_type NOT IN ('waiver', 'reversal', 'refund')"
            " OR (reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="ck_txn_reason_required",
        ),
        Index(
            "uq_one_reversal_per_txn", "related_txn_id",
            unique=True, postgresql_where=text("txn_type = 'reversal'"),
        ),
        Index("ix_folio_transactions_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(Integer, nullable=False)
    folio_id = Column(Integer, nullable=False)
    txn_type = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String)
    # 'room:<stay_plan_id>:<n>' or 'pay:<uuid>' — the idempotency key.
    posting_key = Column(String)
    period_no = Column(Integer)
    period_start_at = Column(DateTime(timezone=True))  # when the period accrued
    payment_method = Column(String)
    reference = Column(String)
    related_txn_id = Column(BigInteger)
    reason = Column(String)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))  # NULL = system (posting engine)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
