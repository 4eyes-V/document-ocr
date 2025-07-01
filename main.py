import os
from datetime import date
import base64
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Form, Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
from celery_app import celery_app

# Загрузка переменных окружения
load_dotenv()

# Инициализация FastAPI
app = FastAPI(
    title="Document OCR Service",
    description="API для загрузки, обработки и управления документами с использованием OCR",
    version="1.0.0",
    contact={
        "name": "Support Team",
        "email": "support@document-ocr.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Настройки
DOCUMENTS_DIR = "documents"
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

# Подключение к БД
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создание таблиц в БД
Base.metadata.create_all(bind=engine)


@app.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Проверка состояния сервиса",
    description="Проверяет работоспособность сервиса и подключенные компоненты",
    response_description="Статус сервиса и подключенные сервисы",
    tags=["System"]
)
async def health_check():
    return {
        "status": "OK",
        "services": {
            "database": "PostgreSQL",
            "queue": "Redis",
            "ocr": "Tesseract"
        }
    }


@app.post(
    "/upload_doc",
    status_code=status.HTTP_201_CREATED,
    summary="Загрузка документа",
    description="Загружает документ (изображение) в систему в формате base64 и сохраняет метаданные в БД",
    response_description="Информация о загруженном документе",
    tags=["Documents"]
)
async def upload_document(
        file_content: str = Form(
            ...,
            description="Содержимое файла в формате base64. Может включать префикс (data:image/...;base64,)",
            example="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        ),
        filename: str = Form(
            ...,
            description="Имя файла с расширением (например: document.jpg)",
            example="invoice.png"
        ),
        doc_date: date = Form(
            ...,
            description="Дата документа в формате ГГГГ-ММ-ДД",
            example="2023-10-15"
        )
):
    try:
        # Декодируем base64
        if "," in file_content:
            file_content = file_content.split(",")[1]

        file_data = base64.b64decode(file_content)

        # Генерируем уникальное имя файла
        file_path = os.path.join(DOCUMENTS_DIR, filename)
        counter = 1
        while os.path.exists(file_path):
            name, ext = os.path.splitext(filename)
            file_path = os.path.join(DOCUMENTS_DIR, f"{name}_{counter}{ext}")
            counter += 1

        # Сохраняем файл
        with open(file_path, "wb") as f:
            f.write(file_data)

        # Сохраняем в базу данных
        db = SessionLocal()
        try:
            from models import Document
            doc = Document(path=file_path, date=doc_date)
            db.add(doc)
            db.commit()
            db.refresh(doc)

            return {
                "status": "success",
                "message": "Document uploaded successfully",
                "document_id": doc.id,
                "path": file_path,
                "date": doc_date
            }
        finally:
            db.close()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing document: {str(e)}"
        )


@app.delete(
    "/doc_delete/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Удаление документа",
    description="Удаляет документ из базы данных и соответствующий файл с диска",
    response_description="Результат операции удаления",
    tags=["Documents"]
)
async def delete_document(
        doc_id: int = Path(
            ...,
            description="ID документа для удаления",
            gt=0,
            example=1
        )
):
    db = SessionLocal()
    try:
        from models import Document
        # Находим документ в базе
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {doc_id} not found"
            )

        # Получаем путь к файлу перед удалением
        file_path = doc.path

        # Удаляем документ и связанные тексты
        db.delete(doc)
        db.commit()

        # Удаляем файл с диска
        if os.path.exists(file_path):
            os.remove(file_path)
            file_deleted = True
        else:
            file_deleted = False

        return {
            "status": "success",
            "message": "Document deleted successfully",
            "document_id": doc_id,
            "file_deleted": file_deleted,
            "path": file_path
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting document: {str(e)}"
        )
    finally:
        db.close()


@app.post(
    "/doc_analyse/{doc_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запуск анализа документа",
    description="Запускает фоновую задачу OCR для распознавания текста в документе",
    response_description="Информация о запущенной задаче",
    tags=["OCR Processing"]
)
async def analyse_document(
        doc_id: int = Path(
            ...,
            description="ID документа для анализа",
            gt=0,
            example=1
        )
):
    db = SessionLocal()
    try:
        from models import Document
        # Проверяем существование документа
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {doc_id} not found"
            )

        # Отправляем задачу в Celery
        task = celery_app.send_task(
            'tasks.process_ocr_task',
            args=[doc_id],
            queue='ocr_queue'
        )

        return {
            "status": "processing",
            "message": "Document submitted for OCR processing",
            "task_id": task.id,
            "doc_id": doc_id,
            "queue": "ocr_queue"
        }
    finally:
        db.close()


@app.get(
    "/task_status/{task_id}",
    status_code=status.HTTP_200_OK,
    summary="Проверка статуса задачи",
    description="Возвращает текущий статус и результат выполнения фоновой задачи",
    response_description="Статус и результат задачи",
    tags=["OCR Processing"]
)
async def get_task_status(
        task_id: str = Path(
            ...,
            description="ID задачи Celery",
            example="d8e9f0a1-b2c3-4d5e-6f7a-8b9c0d1e2f3g"
        )
):
    task = celery_app.AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "status": task.status,
    }

    if task.status == 'SUCCESS':
        response['result'] = task.result
    elif task.status == 'FAILURE':
        response['error'] = str(task.result)

    return response


@app.get(
    "/get_text/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Получение текста документа",
    description="Возвращает распознанный текст документа из базы данных",
    response_description="Текст документа и метаданные",
    tags=["Documents"]
)
async def get_document_text(
        doc_id: int = Path(
            ...,
            description="ID документа для получения текста",
            gt=0,
            example=1
        )
):
    db = SessionLocal()
    try:
        from models import Document, DocumentText

        # Проверяем существование документа
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {doc_id} not found"
            )

        # Получаем текст документа
        doc_text = db.query(DocumentText).filter(DocumentText.id_doc == doc_id).first()

        if not doc_text:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Text for document ID {doc_id} not found. Please run analysis first."
            )

        return {
            "doc_id": doc_id,
            "text": doc_text.text,
            "path": doc.path,
            "date": doc.date.isoformat()
        }
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)