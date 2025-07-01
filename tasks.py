import os
import pytesseract
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Document, DocumentText
from dotenv import load_dotenv
from celery_app import celery_app

load_dotenv()

# Настройка Tesseract
if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")

# Подключение к БД
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@celery_app.task(name='process_ocr_task')
def process_ocr_for_document(doc_id: int):
    """Основная функция обработки OCR для документа"""
    db = SessionLocal()
    try:
        # Получаем документ
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return {"status": "error", "message": f"Document {doc_id} not found"}

        # Проверяем существование файла
        if not os.path.exists(doc.path):
            return {"status": "error", "message": f"File not found: {doc.path}"}

        # Проверяем, не обработан ли уже документ
        existing_text = db.query(DocumentText).filter(DocumentText.id_doc == doc_id).first()
        if existing_text:
            return {"status": "skipped", "message": f"Document {doc_id} already processed"}

        # Выполняем OCR
        text = perform_ocr(doc.path)

        # Сохраняем результат в БД
        doc_text = DocumentText(id_doc=doc_id, text=text)
        db.add(doc_text)
        db.commit()

        return {"status": "success", "doc_id": doc_id, "text_length": len(text)}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def perform_ocr(image_path: str) -> str:
    """Выполняет OCR для изображения"""
    try:
        # Открываем изображение
        img = Image.open(image_path)

        # Применяем OCR (rus+eng)
        text = pytesseract.image_to_string(img, lang='rus+eng')

        return text
    except Exception as e:
        raise Exception(f"OCR processing failed: {str(e)}")