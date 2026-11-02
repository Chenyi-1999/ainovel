// Match Python's str.isspace() behavior while counting Unicode code points.
const PYTHON_WHITESPACE = /[\p{White_Space}\u001c-\u001f]/u;

export function countNonWhitespaceCodePoints(text: string): number {
  let count = 0;
  for (const codePoint of text) {
    if (!PYTHON_WHITESPACE.test(codePoint)) count += 1;
  }
  return count;
}

export function allowedWordRange(target: number): { min: number; max: number } {
  return { min: Math.floor((target * 9 + 9) / 10), max: Math.floor(target * 11 / 10) };
}

export function writingCallLimit(targetWords: number, chapterCount = 1): { perChapter: number; batchTotal: number } {
  const perChapter = Math.ceil(targetWords / 800) + 1;
  return { perChapter, batchTotal: perChapter * chapterCount };
}
