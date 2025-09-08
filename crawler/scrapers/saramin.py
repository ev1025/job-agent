import asyncio
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import re

from crawler.ocr import get_ocr_text_from_image

BASE_URL = "https://www.saramin.co.kr"
DETAIL_URL_TEMPLATE = "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={}"
CONCURRENT_REQUESTS_LIMIT = 10

def preprocess_text(text):
    if not text:
        return ""
    text = re.sub(r'\n\s*\n+', '\n', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    lines = [re.sub(r'^\s*[■▶*]\s*', '', line) for line in lines]
    return '\n'.join(lines)

async def get_job_detail(client, rec_idx):
    detail_url = DETAIL_URL_TEMPLATE.format(rec_idx)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': f'{BASE_URL}/zf_user/search'
        }
        response = await client.get(detail_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        content_area = soup.select_one('.wrap_jv_cont') or soup.body
        
        cleaned_text = ""
        images = []
        if content_area:
            raw_text = content_area.get_text('\n', strip=True)
            cleaned_text = preprocess_text(raw_text)

            for img_tag in content_area.find_all('img'):
                src = img_tag.get('src')
                if "drive.google.com" in src or not src or src.startswith('data:image') or 'logo' in src or 'icon' in src:
                    continue
                if not src.startswith('http'):
                    src = 'https:' + src if src.startswith('//') else BASE_URL + src
                images.append(src)
        
        return cleaned_text, images
    except Exception as e:
        print(f"상세 내용 수집 중 오류: {detail_url}, {e}")
        return f"오류 발생: {e}", None

async def get_job_postings_on_page(client, page, semaphore, search_start_date, existing_rec_idx, search_keyword):
    search_url = f"{BASE_URL}/zf_user/search"
    params = {
        'search_area': 'main', 'page': 1, 'recruitPage': page,
        'recruitSort': 'reg_dt', 'recruitPageCount': 100, 'searchword': search_keyword
    }
    jobs_on_page = []
    should_stop = False
    try:
        response = await client.get(search_url, params=params)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        job_listings = soup.select('.item_recruit')
        if not job_listings:
            return [], True

        for job in job_listings:
            title_element = job.select_one('.job_tit a')
            link_href = title_element['href'] if title_element else ''
            rec_idx_match = re.search(r'rec_idx=(\d+)', link_href)
            if not rec_idx_match: continue
            
            rec_idx = rec_idx_match.group(1)
            if rec_idx in existing_rec_idx: continue

            content_element = job.select_one('.job_sector')
            date_match = re.search(r'(\d{2}/\d{2}/\d{2})', content_element.text if content_element else '')
            if not date_match: continue
            
            posted_date_str = "20" + date_match.group(1).replace('/', '-')
            posted_date_obj = datetime.strptime(posted_date_str, '%Y-%m-%d')
            if posted_date_obj < search_start_date:
                should_stop = True
                continue

            conditions = [cond.text.strip() for cond in job.select('.job_condition span')]
            deadline_raw = (job.select_one('.job_date .date') or BeautifulSoup("<span>상시채용</span>", "html.parser")).text.strip()
            deadline = deadline_raw
            if "채용시" not in deadline_raw and "상시" not in deadline_raw:
                match_md = re.search(r'~(\d{2})/(\d{2})', deadline_raw)
                if match_md:
                    today = datetime.now()
                    m, d = map(int, match_md.groups())
                    year = today.year + 1 if m < today.month else today.year
                    deadline = f"{year}/{m:02d}/{d:02d}"
                elif "오늘마감" in deadline_raw:
                    deadline = datetime.now().strftime('%Y/%m/%d')
            
            jobs_on_page.append({
                'rec_idx': rec_idx, '제목': title_element.get('title', '제목 없음'),
                '회사명': (job.select_one('.corp_name a') or BeautifulSoup("<a>회사명 없음</a>", "html.parser")).text.strip(),
                '등록일': posted_date_str, '상세링크': BASE_URL + link_href,
                '크롤링 시간': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                '지역': conditions[0] if len(conditions) > 0 else '',
                '경력': conditions[1] if len(conditions) > 1 else '',
                '고용형태': conditions[3] if len(conditions) > 3 else '',
                '마감일': deadline,
            })
        
        async def fetch_detail_with_semaphore(job_info):
            async with semaphore:
                detail_text, image_urls = await get_job_detail(client, job_info['rec_idx'])
                if len(detail_text) < 100 and image_urls:
                    print(f"✅ [{job_info['제목']}] 상세 내용이 짧아 OCR 시도")
                    ocr_tasks = [get_ocr_text_from_image(url) for url in image_urls]
                    ocr_results = await asyncio.gather(*ocr_tasks)
                    ocr_texts = [preprocess_text(text) for text in ocr_results if text]
                    if ocr_texts:
                        detail_text += "\n\n--- OCR 결과 ---\n" + "\n\n".join(ocr_texts)
                job_info['상세내용'] = detail_text
                return job_info

        tasks = [fetch_detail_with_semaphore(job) for job in jobs_on_page]
        return [job for job in await asyncio.gather(*tasks) if job], should_stop
    except Exception as e:
        print(f"페이지 {page} 처리 중 오류: {e}")
        return [], True


async def crawl_saramin(search_start_date: datetime, existing_ids: set, total_page_limit: int, search_keyword: str):
    """사람인 스크레이퍼: 특정 날짜 이후 데이터를 페이지별로 `yield`하는 비동기 제너레이터"""
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(1, total_page_limit + 1):
            print(f"--- 키워드 '{search_keyword}'에 대한 페이지 {page} ---")
            jobs_from_page, stop_now = await get_job_postings_on_page(client, page, semaphore, search_start_date, existing_ids, search_keyword)

            new_jobs = []
            for job in jobs_from_page:
                if job and job.get('rec_idx') not in existing_ids:
                    new_jobs.append(job)
                    existing_ids.add(job['rec_idx']) # 중복 수집 방지를 위해 세트에 바로 추가

            if new_jobs:
                yield new_jobs

            if stop_now:
                print("설정한 날짜 이전의 공고에 도달하여 중단합니다.")
                break
            
            await asyncio.sleep(0.5)