import os
from datetime import date
import base64
from fastapi import FastAPI, HTTPException, status, Form, Path, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import lifespan, get_async_db, Base
from models import Document, DocumentText

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
    lifespan=lifespan
)

DOCUMENTS_DIR = "documents"
os.makedirs(DOCUMENTS_DIR, exist_ok=True)


@app.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Проверка состояния сервиса",
    tags=["System"]
)
async def health_check():
    return JSONResponse(content={
        "status": "OK",
        "services": ["PostgreSQL", "Redis", "Tesseract"]
    })


@app.post(
    "/upload_doc",
    status_code=status.HTTP_201_CREATED,
    summary="Загрузка документа",
    tags=["Documents"]
)
async def upload_document(
        file_content: str = Form(...),
        filename: str = Form(...),
        doc_date: date = Form(...),
        db: AsyncSession = Depends(get_async_db)
):
    try:
        if "," in file_content:
            file_content = file_content.split(",")[1]

        file_data = base64.b64decode(file_content)

        base_name, ext = os.path.splitext(filename)
        counter = 1
        file_path = os.path.join(DOCUMENTS_DIR, filename)
        while os.path.exists(file_path):
            file_path = os.path.join(DOCUMENTS_DIR, f"{base_name}_{counter}{ext}")
            counter += 1

        with open(file_path, "wb") as f:
            f.write(file_data)

        doc = Document(path=file_path, date=doc_date)
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        return JSONResponse(content={
            "status": "success",
            "document_id": doc.id,
            "path": file_path,
            "date": doc_date.isoformat()
        }, status_code=status.HTTP_201_CREATED)

    except Exception as e:
        if db.is_active:
            await db.rollback()
        return JSONResponse(
            content={"error": f"Error processing document: {str(e)}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@app.delete(
    "/doc_delete/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Удаление документа",
    tags=["Documents"]
)
async def delete_document(
        doc_id: int = Path(..., gt=0),
        db: AsyncSession = Depends(get_async_db)
):
    try:
        result = await db.execute(select(Document).filter(Document.id == doc_id))
        doc = result.scalars().first()
        if not doc:
            return JSONResponse(
                content={"error": f"Document with ID {doc_id} not found"},
                status_code=status.HTTP_404_NOT_FOUND
            )

        file_path = doc.path
        await db.delete(doc)
        await db.commit()

        file_deleted = False
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                file_deleted = True
            except:
                pass

        return JSONResponse(content={
            "status": "success",
            "document_id": doc_id,
            "file_deleted": file_deleted,
            "path": file_path
        })

    except Exception as e:
        if db.is_active:
            await db.rollback()
        return JSONResponse(
            content={"error": f"Error deleting document: {str(e)}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@app.post(
    "/doc_analyse/{doc_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запуск анализа документа",
    tags=["OCR Processing"]
)
async def analyse_document(
        doc_id: int = Path(..., gt=0),
        db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(Document).filter(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        return JSONResponse(
            content={"error": f"Document with ID {doc_id} not found"},
            status_code=status.HTTP_404_NOT_FOUND
        )

    from celery_app import celery_app
    task = celery_app.send_task('process_ocr_task', args=[doc_id], queue='ocr_queue')

    return JSONResponse(content={
        "status": "processing",
        "task_id": task.id,
        "doc_id": doc_id
    }, status_code=status.HTTP_202_ACCEPTED)


@app.get(
    "/task_status/{task_id}",
    status_code=status.HTTP_200_OK,
    summary="Проверка статуса задачи",
    tags=["OCR Processing"]
)
async def get_task_status(task_id: str):
    from celery_app import celery_app
    task = celery_app.AsyncResult(task_id)

    response = {"task_id": task_id, "status": task.status}

    if task.status == 'SUCCESS':
        response['result'] = task.result
    elif task.status == 'FAILURE':
        response['error'] = str(task.result)

    return JSONResponse(content=response)


@app.get(
    "/get_text/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Получение текста документа",
    tags=["Documents"]
)
async def get_document_text(
        doc_id: int = Path(..., gt=0),
        db: AsyncSession = Depends(get_async_db)
):
    doc_result = await db.execute(
        select(Document, DocumentText)
        .outerjoin(DocumentText, Document.id == DocumentText.id_doc)
        .filter(Document.id == doc_id)
    )
    result = doc_result.first()

    if not result:
        return JSONResponse(
            content={"error": f"Document with ID {doc_id} not found"},
            status_code=status.HTTP_404_NOT_FOUND
        )

    doc, doc_text = result

    if not doc_text:
        return JSONResponse(
            content={"error": f"Text for document ID {doc_id} not found"},
            status_code=status.HTTP_404_NOT_FOUND
        )

    return JSONResponse(content={
        "doc_id": doc_id,
        "text": doc_text.text,
        "path": doc.path,
        "date": doc.date.isoformat()
    })