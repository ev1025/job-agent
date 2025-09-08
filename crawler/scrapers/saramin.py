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

async def get_existing_rec_idx(pool):
    """job_raw 테이블의 link 컬럼에서 rec_idx 값을 추출"""
    rec_idx_set = set()
    sql = "SELECT link FROM job_raw"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                link = row[0]
                if not link:
                    continue
                match = re.search(r"rec_idx=(\d+)", link)
                if match:
                    rec_idx_set.add(match.group(1))
    print(f"✅ DB에서 {len(rec_idx_set)}개의 기존 rec_idx를 불러왔습니다.")
    return rec_idx_set

async def get_job_detail(client, rec_idx):
    detail_url = DETAIL_URL_TEMPLATE.format(rec_idx)
    image_url = None
    cleaned_text = ""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': f'{BASE_URL}/zf_user/search'
        }
        response = await client.get(detail_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        content_area = soup.select_one('.wrap_jv_cont') or soup.body
        if content_area:
            raw_text = content_area.get_text('\n', strip=True)
            cleaned_text = preprocess_text(raw_text)

            images = []
            for img_tag in content_area.find_all('img'):
                src = img_tag.get('src')
                if "drive.google.com" in src:
                    continue
                if not src or src.startswith('data:image') or 'logo' in src or 'icon' in src:
                    continue
                if not src.startswith('http'):
                    if src.startswith('//'):
                        src = 'https:' + src
                    else:
                        src = BASE_URL + src
                images.append(src)
        
        return cleaned_text, images
    except Exception as e:
        print(f"상세 내용 수집 중 오류: {detail_url}, {e}")
        return f"오류 발생: {e}", None

async def get_job_postings_on_page(client, page, semaphore, search_start_date, existing_rec_idx=None):
    search_url = f"{BASE_URL}/zf_user/search"
    params = {'search_area': 'main','page':1,'recruitPage': page,'recruitSort':'reg_dt','recruitPageCount':100,'loc_mcd' : 101000}
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
            link_href = title_element.get('href', '') if title_element else ''
            rec_idx_match = re.search(r'rec_idx=(\d+)', link_href)
            if not rec_idx_match:
                continue
            rec_idx = rec_idx_match.group(1)

            if rec_idx in existing_rec_idx:
                continue

            content_element = job.select_one('.job_sector')
            content_text = content_element.text.strip() if content_element else ''
            date_match = re.search(r'(\d{2}/\d{2}/\d{2})', content_text)
            if not date_match:
                continue
            posted_date_str = "20" + date_match.group(1).replace('/', '-')
            posted_date_obj = datetime.strptime(posted_date_str, '%Y-%m-%d')
            if posted_date_obj < search_start_date:
                should_stop = True
                continue

            conditions_list = [cond.text.strip() for cond in job.select('.job_condition span')]
            region = conditions_list[0] if len(conditions_list) > 0 else ''
            experience = conditions_list[1] if len(conditions_list) > 1 else ''
            job_type = conditions_list[3] if len(conditions_list) > 3 else ''
            deadline_element = job.select_one('.job_date .date')
            deadline_raw = deadline_element.text.strip() if deadline_element else '상시채용'
            deadline = deadline_raw
            if "채용시" not in deadline_raw and "상시" not in deadline_raw:
                match_md = re.search(r'(\d{2})/(\d{2})', deadline_raw)
                if match_md:
                    today = datetime.now()
                    month_str, day_str = match_md.groups()
                    deadline_month = int(month_str)
                    year_to_use = today.year
                    if deadline_month < today.month:
                        year_to_use += 1
                    deadline = f"{year_to_use}/{month_str}/{day_str}"
                elif "오늘마감" in deadline_raw:
                    deadline = datetime.now().strftime('%Y/%m/%d')
            
            jobs_on_page.append({
                'rec_idx': rec_idx,
                '제목': title_element.get('title', '제목 없음') if title_element else '제목 없음',
                '회사명': job.select_one('.corp_name a').text.strip() if job.select_one('.corp_name a') else '회사명 없음',
                '등록일': posted_date_str,
                '상세링크': BASE_URL + link_href,
                '크롤링 시간': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                '지역': region,
                '경력': experience,
                '고용형태': job_type,
                '마감일': deadline,
            })
        
        async def fetch_detail_with_semaphore(job_info):
            async with semaphore:
                detail_text, image_urls = await get_job_detail(client, job_info['rec_idx'])
                
                if len(detail_text) < 100 and image_urls:
                    if isinstance(image_urls, str):
                        image_urls = [image_urls]
                    
                    print(f"✅ [{job_info['제목']}] 상세 내용이 짧아 OCR 시도")
                    
                    ocr_texts = await asyncio.gather(*[get_ocr_text_from_image(url) for url in image_urls])
                    ocr_texts = [preprocess_text(text) for text in ocr_texts if text]
                    
                    if ocr_texts:
                        detail_text += "\n\n--- OCR 결과 ---\n" + "\n\n".join(ocr_texts)
                
                job_info['상세내용'] = detail_text
                return job_info

        tasks = [fetch_detail_with_semaphore(job_info) for job_info in jobs_on_page]
        processed_jobs = await asyncio.gather(*tasks)
        return processed_jobs, should_stop
    except Exception as e:
        print(f"페이지 {page} 처리 중 오류: {e}")
        return [], True

async def crawl_saramin(search_start_date: datetime, existing_ids: set, total_page_limit: int):
    """사람인 스크레이퍼: 특정 날짜 이후 데이터를 전체 페이지 제한에 맞춰 수집"""
    all_jobs = []
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 1
        while True:
            print(f"--- 페이지 {page} ---")
            jobs_from_page, stop_now = await get_job_postings_on_page(client, page, semaphore, search_start_date, existing_ids)

            # 중복 제거
            jobs_from_page = [job for job in jobs_from_page if job['rec_idx'] not in existing_ids]
            for job in jobs_from_page:
                existing_ids.add(job['rec_idx'])

            if jobs_from_page:
                all_jobs.extend(jobs_from_page)
            
            # 페이지 제한 or 종료 조건 확인
            if stop_now or page >= total_page_limit:
                break
            
            page += 1
            await asyncio.sleep(0.5)

    return all_jobs