from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, nullable=False)
    date = Column(Date, nullable=False)

    texts = relationship("DocumentText", back_populates="document", cascade="all, delete")


class DocumentText(Base):
    __tablename__ = "documents_text"

    id = Column(Integer, primary_key=True, index=True)
    id_doc = Column(Integer, ForeignKey("documents.id"), nullable=False)
    text = Column(String, nullable=False)

    document = relationship("Document", back_populates="texts")