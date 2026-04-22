import re


def split_text(textStr):

	chunkSize = 800
	overlapSize = 150

	chunkList = []

	textLen = len(textStr)

	startNum = 0

	while startNum < textLen:

		endNum = startNum + chunkSize

		chunkStr = textStr[startNum:endNum]

		chunkStr = chunkStr.strip()

		if len(chunkStr) > 0:
			chunkList.append(chunkStr)

		startNum += (chunkSize - overlapSize)

	return chunkList