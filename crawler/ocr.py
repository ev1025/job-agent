import asyncio
import httpx
from google.cloud import vision

def ocr_sync_task(image_content):
    """(동기) 이미지 내용으로 OCR을 실행하는 작업"""
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        raise Exception(response.error.message)
    return response.full_text_annotation.text

async def get_ocr_text_from_image(image_uri):
    """이미지 URI에서 OCR 텍스트를 추출하는 비동기 함수"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(image_uri)
            response.raise_for_status()
            image_content = response.content
        
        loop = asyncio.get_running_loop()
        extracted_text = await loop.run_in_executor(None, ocr_sync_task, image_content)
        return extracted_text
    except Exception as e:
        print(f"❌ OCR 처리 중 오류: {e}")
        return ""
    

    