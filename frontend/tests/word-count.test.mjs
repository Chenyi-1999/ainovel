import test from 'node:test';
import assert from 'node:assert/strict';
import { allowedWordRange, countNonWhitespaceCodePoints, writingCallLimit } from '../src/wordCount.ts';

test('counts Python-compatible non-whitespace Unicode code points, not UTF-16 units', () => {
  assert.equal(countNonWhitespaceCodePoints('  汉字，A1😀\t\n'), 6);
  assert.equal(countNonWhitespaceCodePoints('\u0085\u001c\u3000'), 0);
  assert.equal(countNonWhitespaceCodePoints('\ufeff'), 1);
  assert.equal(countNonWhitespaceCodePoints(''), 0);
});

test('computes the inclusive ten percent target range', () => {
  assert.deepEqual(allowedWordRange(4800), { min: 4320, max: 5280 });
  assert.deepEqual(allowedWordRange(301), { min: 271, max: 331 });
});

test('estimates bounded writing calls from target length and batch size', () => {
  assert.deepEqual(writingCallLimit(4800, 2), { perChapter: 7, batchTotal: 14 });
  assert.deepEqual(writingCallLimit(6000, 20), { perChapter: 9, batchTotal: 180 });
  assert.deepEqual(writingCallLimit(300, 1), { perChapter: 2, batchTotal: 2 });
});
