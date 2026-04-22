from crawler.crawler import crawl_kotech
from rag.chunk import split_text
from rag.embedding import get_embedding
from rag.vector_db import add_vector, save_index
from crawler.crawler import get_index_links

from playwright.async_api import async_playwright
import asyncio


async def crawl_and_store():

	print("VectorDB 초기화 완료", flush=True)

	print("===== 테스트용 단일 페이지 크롤링 =====", flush=True)

	# ⭐ 전체 사이트 링크 수집 (임시 중지)
	urlList = await get_index_links()

	# ⭐ 테스트용 페이지 직접 지정
	# urlList = [
	#	"https://www.kotech.co.kr/k15.html"
	#]

	print("실제 크롤링 페이지 개수:", len(urlList), flush=True)

	async with async_playwright() as p:

		browser = await p.chromium.launch(headless=True)

		page = await browser.new_page()

		for urlStr in urlList:

			print("===== 크롤링 실행 =====", flush=True)
			print("URL:", urlStr, flush=True)

			try:

				titleStr, textStr = await crawl_kotech(page, urlStr)

				fullText = titleStr + "\n" + textStr

			except Exception as err:

				print("크롤링 실패 → skip", err, flush=True)
				continue

			# ⭐ Cafe24 트래픽 초과 페이지 검사
			if (
				"허용 접속량을 초과" in textStr
				or "503 Service Unavailable" in textStr
				or "Service Unavailable" in textStr
			):
				print("Cafe24 트래픽 초과 페이지 감지 → skip", flush=True)
				continue

			# ⭐ 빈 페이지 방지
			if textStr is None or len(textStr.strip()) == 0:
				print("텍스트 없음 → skip", flush=True)
				continue			

			chunkList = split_text(fullText)

			print("chunk 개수:", len(chunkList), flush=True)

			for idxNum, chunkStr in enumerate(chunkList):

				print("----- chunk", idxNum, "-----", flush=True)
				print(chunkStr[:300], flush=True)

			for chunkStr in chunkList:

				embedText = f"""
				제목: {titleStr}
				내용:
				{chunkStr}
				"""

				vectorArr = get_embedding(embedText, "passage")

				add_vector(
					vectorArr,
					chunkStr,
					urlStr,
					titleStr
				)

			await asyncio.sleep(2)

		await browser.close()

	save_index()

	print("VectorDB 저장 완료", flush=True)