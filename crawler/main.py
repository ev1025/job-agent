import asyncio
import pandas as pd
import aiomysql
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from crawler.scrapers.saramin import crawl_saramin

load_dotenv()

SEARCH_START_DATE_STR = (datetime.now() - timedelta(weeks=3)).strftime('%Y-%m-%d')
BATCH_SIZE = 500  # DB 삽입 배치 단위
TOTAL_PAGE_LIMIT = 100 # 전체 페이지 제한 (예시 값, 원하는대로 변경 가능)
SEARCH_KEYWORDS = ['LLM', '데이터 분석', 'AI','rag', 'agent'] # 검색 키워드 리스트

async def save_final_jobs(pool, df: pd.DataFrame):
    """DataFrame을 job_raw 테이블에 배치 저장"""
    sql = """
        INSERT INTO job_raw (
            platform, title, company, description, location, experience,
            employment_type, posted_date, deadline_date, crawled_at, link, rec_idx
        ) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new
        ON DUPLICATE KEY UPDATE crawled_at = new.crawled_at
    """
    df = df.where(pd.notnull(df), None)
    # INSERT 순서에 맞춰 열 정렬
    df = df[['platform', 'title', 'company', 'description', 'location', 
             'experience', 'employment_type', 'posted_date', 'deadline_date',
             'crawled_at', 'link', 'rec_idx']]
    data = df.to_records(index=False).tolist()

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, data)
            await conn.commit()
    print(f"✅ {len(df)}개의 데이터를 job_raw에 저장 완료")

async def get_existing_rec_idx(pool):
    """DB에서 기존 rec_idx 조회"""
    existing = set()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT link FROM job_raw")
            rows = await cur.fetchall()
            for row in rows:
                import re
                match = re.search(r'rec_idx=(\d+)', row[0])
                if match:
                    existing.add(match.group(1))
    return existing

async def delete_expired_jobs(pool):
    """
    마감일이 지난 채용 공고와 등록일이 30일 이상 지난 채용 공고를 DB에서 삭제
    """
    today_date = datetime.now()
    today_str_for_sql = today_date.strftime('%Y-%m-%d')
    cutoff_date = (today_date - timedelta(days=30)).strftime('%Y-%m-%d')

    
    # SQL 쿼리에서 Python의 문자열 포맷팅 문자를 제거
    sql = """
        DELETE FROM job_raw
        WHERE 
            STR_TO_DATE(posted_date, '%%Y-%%m-%%d') < %s
            OR 
        (
            deadline_date REGEXP '[0-9]{4}-[0-9]{2}-[0-9]{2}' AND
            STR_TO_DATE(deadline_date, '%%Y-%%m-%%d') < %s
        )
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # aiomysql의 `execute` 메서드에 튜플로 인자를 전달
            await cur.execute(sql, (cutoff_date, today_str_for_sql))
            deleted_count = cur.rowcount
            await conn.commit()
    print(f"✅ {deleted_count}개의 만료된 채용 공고를 삭제 완료")

async def main():
    start_time = datetime.now()
    pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db="jobdb",
        autocommit=False
    )

    await delete_expired_jobs(pool)

    existing_ids = await get_existing_rec_idx(pool)

    sql_cols = {
        '플랫폼': 'platform', '제목': 'title', '회사명': 'company', '상세내용': 'description',
        '지역': 'location', '경력': 'experience', '고용형태': 'employment_type',
        '등록일': 'posted_date', '마감일': 'deadline_date',
        '크롤링 시간': 'crawled_at', '상세링크': 'link', 'rec_idx': 'rec_idx'
    }

    all_jobs = []
    
    search_start_date = datetime.strptime(SEARCH_START_DATE_STR, "%Y-%m-%d")
    print(f"--- {search_start_date.strftime('%Y-%m-%d')} 이후 채용 공고 수집 시작 ---")

    for keyword in SEARCH_KEYWORDS:
        print(f"\n--- 키워드: '{keyword}' 크롤링 시작 ---")
        jobs = await crawl_saramin(search_start_date, existing_ids, TOTAL_PAGE_LIMIT, keyword)
        if jobs:
            all_jobs.extend(jobs)
    
    print(f"\n총 {len(all_jobs)}개의 데이터 수집 완료. DB에 저장 시작.")

    while len(all_jobs) >= BATCH_SIZE:
        batch = all_jobs[:BATCH_SIZE]
        df = pd.DataFrame(batch)
        df.rename(columns=sql_cols, inplace=True)
        df['platform'] = 0
        df = df[['platform', 'title', 'company', 'description', 'location', 
                 'experience', 'employment_type', 'posted_date', 'deadline_date',
                 'crawled_at', 'link', 'rec_idx']]
        await save_final_jobs(pool, df)
        all_jobs = all_jobs[BATCH_SIZE:]

    if all_jobs:
        df = pd.DataFrame(all_jobs)
        df.rename(columns=sql_cols, inplace=True)
        df['platform'] = 0
        df = df[['platform', 'title', 'company', 'description', 'location', 
                 'experience', 'employment_type', 'posted_date', 'deadline_date',
                 'crawled_at', 'link', 'rec_idx']]
        await save_final_jobs(pool, df)

    pool.close()
    await pool.wait_closed()
    print(f"\n총 소요 시간: {datetime.now() - start_time}")

if __name__ == "__main__":
    asyncio.run(main())