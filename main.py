from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import ollama
import tempfile
import os
import fitz  # PyMuPDF
import pdfplumber
import base64
from io import BytesIO
from PIL import Image
import asyncio
import uuid
import time

app = FastAPI(title="PDF Analysis API", version="1.0.0", description="Complete PDF analysis with multimodal AI")

# CORS 설정 - Next.js와 모든 Origin 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Next.js 개발 서버 및 프로덕션 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# 진행 중인 작업 추적
processing_tasks: Dict[str, Dict] = {}


class Item(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    price: float


class PDFAnalysisResponse(BaseModel):
    filename: str
    text_content: str
    analysis: str
    model_used: str  # 분석에 사용된 ollama 모델  
    page_count: int
    task_id: Optional[str] = None


class TaskStatus(BaseModel):
    task_id: str
    status: str  # "processing", "completed", "failed", "cancelled"
    progress: int  # 0-100
    current_step: str
    result: Optional[PDFAnalysisResponse] = None
    error: Optional[str] = None


items_db = []


@app.get("/")
async def root():
    return {"message": "Hello World!"}


@app.get("/test", response_class=HTMLResponse)
async def test_page():
    with open("static/test.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/pdf-test", response_class=HTMLResponse)
async def pdf_test_page():
    with open("static/pdf-test.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api-docs", response_class=HTMLResponse)
async def api_docs():
    with open("static/api-docs.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/ollama/models")
async def get_ollama_models():
    try:
        models = ollama.list()
        return {"models": [model["name"] for model in models["models"]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Ollama models: {str(e)}")




async def extract_text_from_pdf_with_pymupdf(pdf_file: UploadFile) -> tuple[str, int]:
    try:
        # PDF 내용을 메모리에서 직접 처리
        content = await pdf_file.read()
        pdf_document = fitz.open(stream=content, filetype="pdf")
        
        text = ""
        page_count = pdf_document.page_count
        
        # 각 페이지에서 텍스트 추출
        for page_num in range(page_count):
            page = pdf_document[page_num]
            page_text = page.get_text()
            text += f"--- 페이지 {page_num + 1} ---\n{page_text}\n\n"
        
        pdf_document.close()
        return text.strip(), page_count
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")


async def extract_images_from_pdf_and_analyze(pdf_file: UploadFile, model: str = "gemma3:4b", task_id: str = None) -> tuple[str, int]:
    try:
        # PDF 내용을 메모리에서 직접 처리
        content = await pdf_file.read()
        all_text = ""
        
        # PyMuPDF로 이미지 추출 및 텍스트 추출
        pdf_document = fitz.open(stream=content, filetype="pdf")
        page_count = pdf_document.page_count
        
        if task_id:
            processing_tasks[task_id]["current_step"] = f"PDF 문서 로드 완료 ({page_count}페이지)"
            processing_tasks[task_id]["progress"] = 10
        
        # pdfplumber로 텍스트와 테이블 추출
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page_num, (fitz_page, plumber_page) in enumerate(zip(pdf_document, pdf.pages), 1):
                # 취소 확인
                if task_id and processing_tasks.get(task_id, {}).get("status") == "cancelled":
                    raise Exception("Task was cancelled")
                
                if task_id:
                    progress = 10 + (page_num / page_count) * 60  # 10-70% for text extraction
                    processing_tasks[task_id]["progress"] = int(progress)
                    processing_tasks[task_id]["current_step"] = f"페이지 {page_num}/{page_count} 텍스트 추출 중"
                
                all_text += f"--- 페이지 {page_num} ---\n"
                
                # pdfplumber로 텍스트 추출
                page_text = plumber_page.extract_text()
                if page_text:
                    all_text += page_text + "\n"
                
                # 테이블 추출
                tables = plumber_page.extract_tables()
                for table_num, table in enumerate(tables, 1):
                    all_text += f"\n[표 {table_num}]\n"
                    for row in table:
                        if row:
                            row_text = " | ".join([str(cell) if cell else "" for cell in row])
                            all_text += row_text + "\n"
                    all_text += "\n"
                
                # PyMuPDF로 이미지 추출 및 분석
                image_list = fitz_page.get_images()
                if image_list:
                    all_text += f"\n[이미지 {len(image_list)}개 분석 결과]\n"
                    
                    for img_index, img in enumerate(image_list):
                        # 취소 확인
                        if task_id and processing_tasks.get(task_id, {}).get("status") == "cancelled":
                            raise Exception("Task was cancelled")
                        
                        if task_id:
                            img_progress = 70 + ((page_num - 1) / page_count + (img_index + 1) / len(image_list) / page_count) * 20
                            processing_tasks[task_id]["progress"] = int(img_progress)
                            processing_tasks[task_id]["current_step"] = f"페이지 {page_num} 이미지 {img_index + 1}/{len(image_list)} 분석 중"
                        
                        try:
                            # 이미지 데이터 추출
                            xref = img[0]
                            pix = fitz.Pixmap(pdf_document, xref)
                            
                            if pix.n - pix.alpha < 4:  # RGB 또는 그레이스케일
                                # 이미지를 base64로 인코딩
                                img_data = pix.tobytes("png")
                                img_base64 = base64.b64encode(img_data).decode()
                                
                                # gemma3:4b 멀티모달로 이미지 분석
                                image_analysis = await analyze_image_with_ollama(img_base64, model)
                                all_text += f"이미지 {img_index + 1} 분석:\n{image_analysis}\n\n"
                            
                            pix = None  # 메모리 정리
                            
                        except Exception as e:
                            all_text += f"이미지 {img_index + 1}: 분석 실패 - {str(e)}\n"
                
                all_text += "\n"
        
        pdf_document.close()
        
        if task_id:
            processing_tasks[task_id]["current_step"] = "PDF 분석 완료"
            processing_tasks[task_id]["progress"] = 90
        
        return all_text.strip(), page_count
        
    except Exception as e:
        if "cancelled" in str(e):
            raise e
        raise HTTPException(status_code=400, detail=f"Failed to extract and analyze PDF: {str(e)}")


async def analyze_image_with_ollama(image_base64: str, model: str) -> str:
    try:
        # gemma3:4b 멀티모달로 이미지 분석
        response = ollama.generate(
            model=model,
            prompt="이 이미지에 있는 모든 텍스트를 추출하고, 이미지의 내용을 상세히 설명해주세요. 텍스트가 있다면 정확히 추출해주세요.",
            images=[image_base64]
        )
        return response["response"]
    except Exception as e:
        return f"이미지 분석 실패: {str(e)}"


async def extract_text_from_pdf_with_pdfplumber(pdf_file: UploadFile) -> tuple[str, int]:
    try:
        # PDF 내용을 메모리에서 직접 처리
        content = await pdf_file.read()
        
        with pdfplumber.open(BytesIO(content)) as pdf:
            text = ""
            page_count = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, 1):
                text += f"--- 페이지 {page_num} ---\n"
                
                # 텍스트 추출
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                
                # 테이블 추출
                tables = page.extract_tables()
                for table_num, table in enumerate(tables, 1):
                    text += f"\n[표 {table_num}]\n"
                    for row in table:
                        if row:  # None이 아닌 행만 처리
                            row_text = " | ".join([str(cell) if cell else "" for cell in row])
                            text += row_text + "\n"
                    text += "\n"
                
                # 이미지 정보 추출
                images = page.images
                if images:
                    text += f"\n[이미지 {len(images)}개 발견]\n"
                    for img_num, img in enumerate(images, 1):
                        bbox = img.get('bbox', [0, 0, 0, 0])
                        text += f"이미지 {img_num}: 위치 x={bbox[0]:.1f}, y={bbox[1]:.1f}, 크기 {bbox[2]-bbox[0]:.1f}x{bbox[3]-bbox[1]:.1f}\n"
                
                text += "\n"
            
            return text.strip(), page_count
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF with pdfplumber: {str(e)}")


async def extract_text_from_pdf_with_pymupdf_from_path(file_path: str) -> tuple[str, int]:
    try:
        pdf_document = fitz.open(file_path)
        
        text = ""
        page_count = pdf_document.page_count
        
        # 각 페이지에서 텍스트 추출
        for page_num in range(page_count):
            page = pdf_document[page_num]
            page_text = page.get_text()
            text += f"--- 페이지 {page_num + 1} ---\n{page_text}\n\n"
        
        pdf_document.close()
        return text.strip(), page_count
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")


async def analyze_text_with_ollama(text: str, model_name: str, prompt: str = None) -> str:
    try:
        if not prompt:
            prompt = f"""다음 텍스트를 분석하고 요약해주세요. 주요 내용, 핵심 포인트, 그리고 중요한 정보들을 한국어로 정리해주세요:

{text}"""
        
        response = ollama.generate(model=model_name, prompt=prompt)
        return response["response"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze text with Ollama: {str(e)}")


@app.post("/pdf/analyze", response_model=PDFAnalysisResponse)
async def analyze_pdf(
    file: UploadFile = File(...),
    model: str = Form(default="gemma3:4b"),
    custom_prompt: Optional[str] = Form(default=None)
):
    try:
        print(f"Received file: {file.filename}")
        print(f"Model: {model}")
        
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # 완전한 PDF 분석 (pdfplumber + PyMuPDF + gemma3:4b 멀티모달)
        text_content, page_count = await extract_images_from_pdf_and_analyze(file, model)
        
        if not text_content.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the PDF")
        
        # gemma3:4b로 최종 통합 분석
        analysis = await analyze_text_with_ollama(text_content, model, custom_prompt)
        
        return PDFAnalysisResponse(
            filename=file.filename,
            text_content=text_content,
            analysis=analysis,
            model_used=model,
            page_count=page_count
        )
    except Exception as e:
        print(f"Error in analyze_pdf: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/pdf/analyze-async")
async def analyze_pdf_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form(default="gemma3:4b"),
    custom_prompt: Optional[str] = Form(default=None)
):
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # 태스크 ID 생성
        task_id = str(uuid.uuid4())
        
        # 태스크 상태 초기화
        processing_tasks[task_id] = {
            "task_id": task_id,
            "status": "processing",
            "progress": 0,
            "current_step": "PDF 분석 시작",
            "result": None,
            "error": None,
            "filename": file.filename,
            "model": model
        }
        
        # 백그라운드에서 PDF 분석 실행
        background_tasks.add_task(process_pdf_async, task_id, file, model, custom_prompt)
        
        return {"task_id": task_id, "status": "processing", "message": "PDF 분석이 시작되었습니다"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def process_pdf_async(task_id: str, file: UploadFile, model: str, custom_prompt: Optional[str]):
    try:
        # PDF 분석 실행
        text_content, page_count = await extract_images_from_pdf_and_analyze(file, model, task_id)
        
        # 취소 확인
        if processing_tasks.get(task_id, {}).get("status") == "cancelled":
            return
        
        processing_tasks[task_id]["current_step"] = "AI 분석 중"
        processing_tasks[task_id]["progress"] = 90
        
        # 최종 AI 분석
        analysis = await analyze_text_with_ollama(text_content, model, custom_prompt)
        
        # 결과 저장
        result = PDFAnalysisResponse(
            filename=file.filename,
            text_content=text_content,
            analysis=analysis,
            model_used=model,
            page_count=page_count,
            task_id=task_id
        )
        
        processing_tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "current_step": "분석 완료",
            "result": result
        })
        
    except Exception as e:
        processing_tasks[task_id].update({
            "status": "failed",
            "progress": 0,
            "current_step": "분석 실패",
            "error": str(e)
        })


@app.get("/tasks/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatus(**processing_tasks[task_id])


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if processing_tasks[task_id]["status"] in ["completed", "failed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    
    processing_tasks[task_id]["status"] = "cancelled"
    processing_tasks[task_id]["current_step"] = "사용자에 의해 취소됨"
    
    return {"message": "Task cancelled successfully"}


@app.get("/tasks")
async def get_all_tasks():
    return {"tasks": list(processing_tasks.values())}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    del processing_tasks[task_id]
    return {"message": "Task deleted successfully"}


@app.get("/items", response_model=List[Item])
async def get_items():
    return items_db


@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    for item in items_db:
        if item["id"] == item_id:
            return item
    return {"error": "Item not found"}


@app.post("/items", response_model=Item)
async def create_item(item: Item):
    item_dict = item.dict()
    item_dict["id"] = len(items_db) + 1
    items_db.append(item_dict)
    return item_dict


@app.put("/items/{item_id}", response_model=Item)
async def update_item(item_id: int, item: Item):
    for i, existing_item in enumerate(items_db):
        if existing_item["id"] == item_id:
            item_dict = item.dict()
            item_dict["id"] = item_id
            items_db[i] = item_dict
            return item_dict
    return {"error": "Item not found"}


@app.delete("/items/{item_id}")
async def delete_item(item_id: int):
    for i, item in enumerate(items_db):
        if item["id"] == item_id:
            deleted_item = items_db.pop(i)
            return {"message": f"Item {item_id} deleted", "item": deleted_item}
    return {"error": "Item not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)