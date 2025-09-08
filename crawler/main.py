import asyncio
import aiomysql
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from crawler.scrapers.saramin import crawl_saramin

load_dotenv()

SEARCH_START_DATE_STR = (datetime.now() - timedelta(weeks=3)).strftime('%Y-%m-%d')
BATCH_SIZE = 500  # DB 삽입 배치 단위
TOTAL_PAGE_LIMIT = 100 # 전체 페이지 제한
SEARCH_KEYWORDS = ['LLM', '데이터 분석', 'AI', 'rag', 'agent'] # 검색 키워드 리스트

async def get_existing_rec_idx(pool):
    """DB에서 기존 rec_idx 조회"""
    existing = set()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT link FROM job_raw")
            rows = await cur.fetchall()
            for row in rows:
                import re
                # link가 None인 경우를 대비한 방어 코드
                if row and row[0]:
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
    
    search_start_date = datetime.strptime(SEARCH_START_DATE_STR, "%Y-%m-%d")
    print(f"--- {search_start_date.strftime('%Y-%m-%d')} 이후 채용 공고 수집 시작 ---")

    for keyword in SEARCH_KEYWORDS:
        print(f"\n--- 키워드: '{keyword}' 크롤링 시작 ---")
        # crawl_saramin 함수가 DB 저장까지 모두 처리하도록 pool과 관련 인자들을 전달합니다.
        await crawl_saramin(
            pool=pool,
            search_start_date=search_start_date,
            existing_ids=existing_ids,
            total_page_limit=TOTAL_PAGE_LIMIT,
            search_keyword=keyword,
            batch_size=BATCH_SIZE,
            sql_cols=sql_cols
        )
    
    print(f"\n✨ 모든 키워드에 대한 크롤링 및 저장이 완료되었습니다.")

    pool.close()
    await pool.wait_closed()
    print(f"\n총 소요 시간: {datetime.now() - start_time}")

if __name__ == "__main__":
    asyncio.run(main())