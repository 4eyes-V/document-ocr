import os
import pytesseract
from PIL import Image
from celery_app import celery_app
from models import Document, DocumentText
from database import SyncSessionLocal
from sqlalchemy import select

if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


@celery_app.task(name='process_ocr_task')
def process_ocr_for_document(doc_id: int):
    db = next(get_sync_db())
    try:
        doc = db.execute(select(Document).filter(Document.id == doc_id)).scalar_one_or_none()
        if not doc:
            return {"status": "error", "message": f"Document {doc_id} not found"}

        if not os.path.exists(doc.path):
            return {"status": "error", "message": f"File not found: {doc.path}"}

        if doc.text:
            return {"status": "skipped", "message": f"Document {doc_id} already processed"}

        text = perform_ocr(doc.path)

        doc_text = DocumentText(id_doc=doc_id, text=text)
        doc.text = doc_text
        db.add(doc_text)
        db.commit()

        return {"status": "success", "doc_id": doc_id, "text_length": len(text)}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def perform_ocr(image_path: str) -> str:
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang='rus+eng')
    except Exception as e:
        return f"OCR processing failed: {str(e)}"