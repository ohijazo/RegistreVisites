import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, Date, DateTime, Text, Time,
    ForeignKey, LargeBinary, Integer,
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Location(Base):
    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    qr_token = Column(String(64), unique=True, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    visits = relationship("Visit", back_populates="location")


class Department(Base):
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_ca = Column(String(200), nullable=False)
    name_es = Column(String(200), nullable=False)
    name_fr = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    order = Column(Integer, default=0)
    active = Column(Boolean, default=True)


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_hash = Column(String(64), nullable=False)
    content_ca = Column(Text, nullable=False)
    content_es = Column(Text, nullable=False)
    content_fr = Column(Text, nullable=False)
    content_en = Column(Text, nullable=False)
    active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    visits = relationship("Visit", back_populates="legal_document")


class Visit(Base):
    __tablename__ = "visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True)
    location = relationship("Location", back_populates="visits")

    # Dades personals
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(150), nullable=False)
    company = Column(String(200), nullable=False)
    id_document_enc = Column(LargeBinary, nullable=False)
    id_document_iv = Column(LargeBinary, nullable=False)
    id_document_hash = Column(String(64), nullable=True, index=True)
    phone = Column(String(30))

    # Visita
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"))
    department = relationship("Department")
    visit_reason = Column(Text, nullable=False)
    language = Column(String(2), nullable=False)

    # Consentiment RGPD
    legal_document_id = Column(UUID(as_uuid=True), ForeignKey("legal_documents.id"))
    legal_document = relationship("LegalDocument", back_populates="visits")
    accepted_at = Column(DateTime(timezone=True))
    signature = Column(LargeBinary)  # PNG de la signatura manuscrita

    # Metadades
    ip_address = Column(INET)
    user_agent = Column(Text)

    # Timestamps
    checked_in_at = Column(DateTime(timezone=True), default=utcnow)
    checked_out_at = Column(DateTime(timezone=True))
    checkout_method = Column(String(10))  # 'qr' | 'pin' | 'manual'

    # Sortida
    exit_token = Column(String(64), unique=True)
    exit_pin = Column(String(6))


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(200), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), default="receptionist")  # 'admin' | 'receptionist' | 'viewer'
    active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    last_logout_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ExpectedVisit(Base):
    """Visites planificades pel personal intern. Es consulten al dashboard
    i a la llista pròpia; no es vinculen automàticament amb Visit (text
    lliure de l'amfitrió). Un admin/recepcionista pot marcar-les com
    arribada / cancel·lada manualment."""
    __tablename__ = "expected_visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visitor_first_name = Column(String(100), nullable=False)
    visitor_last_name = Column(String(150))
    visitor_company = Column(String(200))
    visitor_phone = Column(String(30))

    host_name = Column(String(200), nullable=False)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    department = relationship("Department")

    expected_date = Column(Date, nullable=False, index=True)
    expected_time = Column(Time, nullable=True)
    visit_reason = Column(Text)
    notes = Column(Text)

    # 'pending' | 'arrived' | 'cancelled' | 'no_show'
    status = Column(String(20), default="pending", nullable=False, index=True)

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    created_by = relationship("AdminUser")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Notificació per email (enviament manual)
    last_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    last_email_recipients = Column(Text, nullable=True)

    # Vincle amb la visita real un cop el visitant arriba al quiosc
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.id"), nullable=True)
    visit = relationship("Visit", foreign_keys=[visit_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    admin = relationship("AdminUser")
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.id"), nullable=True)
    action = Column(String(50), nullable=False)  # 'view_id_document' | 'delete_visit' | 'manual_checkout'
    ip_address = Column(INET)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    detail = Column(Text)
