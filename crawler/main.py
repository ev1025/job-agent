import asyncio
import pandas as pd
import aiomysql
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from crawler.scrapers.saramin import crawl_saramin

# --- CONFIGURATION ---
load_dotenv()

SEARCH_START_DATE_STR = (datetime.now() - timedelta(weeks=3)).strftime('%Y-%m-%d')
BATCH_SIZE = 500  # DB 삽입 배치 단위
TOTAL_PAGE_LIMIT = 100 # 전체 페이지 제한
SEARCH_KEYWORDS = ['LLM', '데이터 분석', 'AI','rag', 'agent'] # 검색 키워드 리스트

# --- DATABASE FUNCTIONS ---
async def save_final_jobs(pool, df: pd.DataFrame):
    """DataFrame을 job_raw 테이블에 배치 저장"""
    if df.empty:
        return
        
    sql = """
        INSERT INTO job_raw (
            platform, title, company, description, location, experience,
            employment_type, posted_date, deadline_date, crawled_at, link, rec_idx
        ) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new
        ON DUPLICATE KEY UPDATE crawled_at = new.crawled_at
    """
    df = df.where(pd.notnull(df), None)
    df = df[['platform', 'title', 'company', 'description', 'location', 
             'experience', 'employment_type', 'posted_date', 'deadline_date',
             'crawled_at', 'link', 'rec_idx']]
    data = df.to_records(index=False).tolist()

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.executemany(sql, data)
                await conn.commit()
                print(f"✅ {len(df)}개의 데이터를 job_raw에 저장 완료")
            except Exception as e:
                print(f"🚨 DB 저장 중 오류 발생: {e}")
                await conn.rollback()

async def get_existing_rec_idx(pool):
    """DB에서 기존 rec_idx 조회"""
    existing = set()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT rec_idx FROM job_raw WHERE platform = 0") # 사람인(0) 공고만
            rows = await cur.fetchall()
            for row in rows:
                if row[0]: existing.add(str(row[0]))
    print(f"✅ DB에서 {len(existing)}개의 기존 사람인 rec_idx를 불러왔습니다.")
    return existing

async def delete_expired_jobs(pool):
    """마감일이 지난 채용 공고와 등록일이 30일 이상 지난 채용 공고를 DB에서 삭제"""
    today_date = datetime.now()
    cutoff_date = (today_date - timedelta(days=30)).strftime('%Y-%m-%d')
    today_str_for_sql = today_date.strftime('%Y-%m-%d')

    sql = """
        DELETE FROM job_raw
        WHERE 
            STR_TO_DATE(posted_date, '%%Y-%%m-%%d') < %s
            OR 
            (
                deadline_date REGEXP '^[0-9]{4}/[0-9]{2}/[0-9]{2}$' AND
                STR_TO_DATE(REPLACE(deadline_date, '/', '-'), '%%Y-%%m-%%d') < %s
            )
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (cutoff_date, today_str_for_sql))
            deleted_count = cur.rowcount
            await conn.commit()
    print(f"✅ {deleted_count}개의 만료된 채용 공고를 삭제 완료")
    
# --- MAIN EXECUTION ---
async def main():
    start_time = datetime.now()
    pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME", "jobdb"), autocommit=False
    )

    sql_cols = {
        '플랫폼': 'platform', '제목': 'title', '회사명': 'company', '상세내용': 'description',
        '지역': 'location', '경력': 'experience', '고용형태': 'employment_type',
        '등록일': 'posted_date', '마감일': 'deadline_date',
        '크롤링 시간': 'crawled_at', '상세링크': 'link', 'rec_idx': 'rec_idx'
    }

    await delete_expired_jobs(pool)
    existing_ids = await get_existing_rec_idx(pool)

    all_jobs_buffer = []
    total_new_jobs_count = 0
    
    search_start_date = datetime.strptime(SEARCH_START_DATE_STR, "%Y-%m-%d")
    print(f"--- {search_start_date.strftime('%Y-%m-%d')} 이후 채용 공고 수집 시작 ---")

    for keyword in SEARCH_KEYWORDS:
        print(f"\n--- 키워드: '{keyword}' 크롤링 시작 ---")
        
        async for jobs_from_page in crawl_saramin(search_start_date, existing_ids, TOTAL_PAGE_LIMIT, keyword):
            all_jobs_buffer.extend(jobs_from_page)
            
            if len(all_jobs_buffer) >= BATCH_SIZE:
                batch_to_save = all_jobs_buffer[:BATCH_SIZE]
                all_jobs_buffer = all_jobs_buffer[BATCH_SIZE:]

                df = pd.DataFrame(batch_to_save)
                df.rename(columns=sql_cols, inplace=True)
                df['platform'] = 0 # 사람인 플랫폼 번호
                await save_final_jobs(pool, df)
                total_new_jobs_count += len(batch_to_save)

    if all_jobs_buffer:
        df = pd.DataFrame(all_jobs_buffer)
        df.rename(columns=sql_cols, inplace=True)
        df['platform'] = 0
        await save_final_jobs(pool, df)
        total_new_jobs_count += len(all_jobs_buffer)

    print(f"\n총 {total_new_jobs_count}개의 새로운 데이터를 수집 및 저장 완료.")
    
    pool.close()
    await pool.wait_closed()
    print(f"총 소요 시간: {datetime.now() - start_time}")

if __name__ == "__main__":
    asyncio.run(main())