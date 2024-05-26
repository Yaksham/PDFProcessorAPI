import logging
import os
from uuid import uuid4
from celery import Celery
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
import fitz  # PyMuPDF
import redis
from slowapi import Limiter, _rate_limit_exceeded_handler # slowapi for rate limiting
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn

logger = logging.getLogger("uvicorn")

# Defining API key 
API_KEY = os.getenv('API_KEY')
api_key_header = APIKeyHeader(name="api_key")

celery_app = Celery(
    __name__,
    broker='redis://localhost:6379',
    backend='redis://localhost:6379'
)
    
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

redisdb = redis.Redis(host='localhost', port=6379, db=1)

UPLOAD_DIR = "./tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Dependency to check API key
def api_key_auth(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.post("/webhook",
          responses={
                200: {"description": "PDF file successfully processed", "content": {"application/json": {"example": {"file_id": "unique_id"}}}},
                400: {"description": "Bad Request", "content": {
                    "application/json": {
                        "examples": {
                            "invalid_file_type": {"summary": "Invalid File Type", "value": {"detail": "The uploaded file is not a valid PDF file."}},
                            "invalid_file_extension": {"summary": "Invalid File Extension", "value": {"detail": "The uploaded file does not have a .pdf extension."}},
                            "file_too_large": {"summary": "File Too Large", "value": {"detail": "The uploaded file exceeds the size limit."}}
                        }
                    },
                }},
                401: {"description": "Unauthorized", "content": {"application/json": {"example": {"detail": "Invalid API Key"}}}},
                500: {"description": "Internal Server Error", "content": {"application/json": {"example": {"detail": "Failed to process the uploaded file."}}}}
            }
          )
@limiter.limit("5/minute")
async def receive_pdf(request: Request, file: UploadFile = File(...), api_key: str = Depends(api_key_auth)):
    """
    Webhook API, this will take in a pdf file, store it in a temporary location, and return a unique id.
    """
    logger.info("Entering webhook API")
    
    # File Sanitization
    if file.content_type != "application/pdf":
        logger.warning("Uploaded file is not a PDF")
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF file.")
    
    if not file.filename.endswith(".pdf"):
        logger.warning("File does not have a .pdf extension")
        raise HTTPException(status_code=400, detail="The uploaded file does not have a .pdf extension.")
    
    # Limit file size
    max_file_size = 10 * 1024 * 1024  # 10 MB limit
    file_content = await file.read()
    if len(file_content) > max_file_size:
        logger.warning("Uploaded file exceeds size limit")
        raise HTTPException(status_code=400, detail="The uploaded file exceeds the size limit.")
    
    try:
        file_id = str(uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)  # store file temporarily in OS
        
        redisdb.set(file_id, file_path)
        convert_pdf.delay(file_id) # celery task to convert pdf
        logger.info("File %s stored and processing started", file_id)
        return JSONResponse(content={"file_id": file_id})
    except Exception as e:
        logger.error("Failed to process the uploaded file: %s", e)
        raise HTTPException(status_code=500, detail="Failed to process the uploaded file.") from e

@app.get("/polling/{file_id}",
        responses={
                200: {"description": "file_id validated", "content": {
                    "application/json": {
                        "examples": {
                            "converted_contents": {"summary": "Converted Contents", "value": {"data": "result_data"}},
                            "processing": {"summary": "File still processing", "value": {"status": "processing"}}
                        }
                    },
                    
                }},
                400: {"description": "Bad Request", "content": {"application/json": {"example": {"detail": "Invalid file ID"}}}},
                401: {"description": "Unauthorized", "content": {"application/json": {"example": {"detail": "Invalid API Key"}}}},
                404: {"description": "Not Found", "content": {"application/json": {"example": {"detail": "File not found"}}}},
                500: {"description": "Internal Server Error", "content": {"application/json": {"example": {"detail": "Failed to fetch file data."}}}}
            } 
         )
@limiter.limit("10/minute")
async def get_pdf_data(request: Request, file_id: str, api_key: str = Depends(api_key_auth)):
    """
    Polling API, this will take in a file id and return the status along with the contents if the file has finished processing.
    """
    logger.info("Entering polling API")
    
    if redisdb.get(file_id) is None:
        logger.warning("File ID %s not found", file_id)
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        result = redisdb.get(file_id)
        result_data = result.decode('utf-8')
        if os.path.exists(result_data):
            logger.info("File ID %s is still processing", file_id)
            return JSONResponse(content={"status": "processing"})
        else:
            logger.info("File ID %s has been processed", file_id)
            return JSONResponse(content={"data": result_data})
    except Exception as e:
        logger.error("Failed to fetch data for file ID %s: %s", file_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch file data.") from e
    
@celery_app.task(name="convert_pdf")
def convert_pdf(file_id: str):
    file_path = redisdb.get(file_id)
    if not file_path:
        return {"error": "File not found"}
    
    file_path = file_path.decode('utf-8')
    try:
        doc = fitz.open(file_path)
        text_data = ""
        for page in doc:
            text_data += page.get_text()
        redisdb.set(file_id, text_data)
        os.remove(file_path)
    except Exception as e:
        redisdb.set(file_id, f"Error processing file: {str(e)}")
        return {"error": str(e)}

    return {"success": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
