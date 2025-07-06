from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Date, Text
from datetime import date
from database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(255))
    date: Mapped[date] = mapped_column(Date)

    text: Mapped["DocumentText"] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False
    )


class DocumentText(Base):
    __tablename__ = "documents_text"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_doc: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    text: Mapped[str] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="text")