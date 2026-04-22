from collections import Counter
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def crawl_kotech(pageObj, urlStr):

	print("크롤링 URL:", urlStr, flush=True)

	await pageObj.goto(urlStr)

	await pageObj.wait_for_timeout(2000)

	print("최종 URL:", pageObj.url, flush=True)

	if "overTraffic" in pageObj.url:
		print("트래픽 초과 페이지 감지 → 크롤링 중단", flush=True)
		return "", ""

	htmlStr = await pageObj.content()

	soupObj = BeautifulSoup(htmlStr, "html.parser")

	for tagObj in soupObj(["script","style","nav","header","footer"]):
		tagObj.decompose()

	# ⭐ 페이지 제목 추출
	titleStr = ""

	# ----------------------------------------------------
	# 1️⃣ 현재 URL에서 파일명 추출 (예: k12.html)
	# ----------------------------------------------------
	fileNameStr = urlStr.split("/")[-1]

	print("현재 파일명:", fileNameStr, flush=True)

	# ----------------------------------------------------
	# 2️⃣ 메뉴에서 해당 href를 가진 a 태그 찾기
	# 예: <a href="k12.html">회사개요</a>
	# ----------------------------------------------------

	menuTitleList = soupObj.select(f'a[href="{fileNameStr}"]')

	parentTitle = ""
	childTitle = ""

	# ⭐ 상위 메뉴 목록
	parentMenuList = [
		"사업영역",
		"인공지능 AI",
		"OCR 솔루션",
		"DB 구축",
		"시스템 구축"
	]

	for menuTitleObj in menuTitleList:

		tmpTitle = menuTitleObj.get_text().strip()

		print("메뉴 발견:", tmpTitle, flush=True)

		# ------------------------------
		# 상위 메뉴
		# ------------------------------
		if tmpTitle in parentMenuList:

			parentTitle = tmpTitle

			print("상위 메뉴:", parentTitle, flush=True)

			continue

		# ------------------------------
		# 하위 메뉴
		# ------------------------------
		childTitle = tmpTitle

		print("하위 메뉴:", childTitle, flush=True)

		break

	# ------------------------------
	# 제목 생성
	# ------------------------------
	if parentTitle and childTitle:

		titleStr = parentTitle + " " + childTitle

	elif childTitle:

		titleStr = childTitle

	elif parentTitle:

		titleStr = parentTitle

	# ----------------------------------------------------
	# 3️⃣ 혹시 못 찾았을 경우 기존 방식 fallback
	# ----------------------------------------------------
	if not titleStr:

		titleObj = soupObj.select_one("h2")

		if titleObj:
			titleStr = titleObj.get_text().strip()

	print("페이지 제목:", titleStr, flush=True)

	# ⭐ 본문 영역 선택 (다양한 구조 대응)
	mainObj = soupObj.select_one(".txtarea .txts")

	if not mainObj:
		mainObj = soupObj.select_one(".page.m13_2")

	if not mainObj:
		mainObj = soupObj.select_one(".page.m14_1")

	if not mainObj:
		mainObj = soupObj.select_one(".sub_contents")

	if not mainObj:
		mainObj = soupObj.select_one(".contents")

	if not mainObj:
		mainObj = soupObj.select_one(".container")

	if not mainObj:
		mainObj = soupObj.select_one(".page")

	if mainObj:
		textStr = mainObj.get_text(separator="\n")
	else:
		textStr = soupObj.get_text(separator="\n")

	lines = []

	ignoreList = [
		"icon",
		"home",
		"menu",
		"login",
		"top",
		"ALL MENU",
		"PR CENTER",
		"Copyright",
		"ADD :",
		"TEL :",
		"FAX :"
	]

	for lineStr in textStr.split("\n"):

		lineStr = lineStr.strip()

		if len(lineStr) < 5:
			continue

		if lineStr.lower() in ignoreList:
			continue

		lines.append(lineStr)

	# 중복 제거
	lines = list(dict.fromkeys(lines))

	textStr = "\n".join(lines)

	print("텍스트 길이:", len(textStr), flush=True)
	print("텍스트 시작:", textStr[:500], flush=True)
	print("텍스트 중간:", textStr[1000:1500], flush=True)
	print("텍스트 끝:", textStr[-500:], flush=True)

	return titleStr, textStr


async def get_index_links():

	baseUrl = "https://www.kotech.co.kr/"
	indexUrl = baseUrl + "index.html"

	print("===== index.html 크롤링 시작 =====", flush=True)
	print("index URL:", indexUrl, flush=True)

	async with async_playwright() as p:

		browser = await p.chromium.launch(headless=True)

		page = await browser.new_page()

		await page.goto(indexUrl)

		await page.wait_for_timeout(2000)

		htmlStr = await page.content()

		await browser.close()

	print("index HTML 길이:", len(htmlStr), flush=True)

	soupObj = BeautifulSoup(htmlStr, "html.parser")

	urlList = []
	fileNameList = []

	print("===== 링크 분석 시작 =====", flush=True)

	for tagObj in soupObj.find_all("a", href=True):

		hrefStr = tagObj["href"].strip()

		print("href 발견:", hrefStr, flush=True)

		if re.match(r"^k\d+.*\.html$", hrefStr):

			fullUrl = baseUrl + hrefStr
			
			print("크롤링 대상 추가:", fullUrl, flush=True)

			urlList.append(fullUrl)

			fileNameList.append(hrefStr)

	print("===== 링크 수집 완료 =====", flush=True)

	# ⭐ 전체 발견 개수
	totalCount = len(fileNameList)

	# ⭐ 파일명별 개수
	counterObj = Counter(fileNameList)

	# ⭐ 중복 제거 개수
	uniqueCount = len(counterObj)

	# ⭐ 중복 개수
	duplicateCount = totalCount - uniqueCount

	print("===== 링크 통계 =====", flush=True)
	print("전체 발견:", totalCount, flush=True)
	print("중복 제거:", uniqueCount, flush=True)
	print("중복 개수:", duplicateCount, flush=True)

	print("===== 파일별 중복 개수 =====", flush=True)

	for fileNameStr, countNum in counterObj.items():

		if countNum > 1:

			print(fileNameStr, ":", countNum, flush=True)

	return list(set(urlList))