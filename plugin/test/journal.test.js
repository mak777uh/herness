/**
 * Тест проверки кадров HSJ2 в плагине: битый кадр не даёт ответа.
 *
 * Запуск: node plugin/test/journal.test.js
 */

import { createHash } from "node:crypto";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { answerFromJournal, lastJournalError } from "../lib/index.js";
import { RECORD_HEADER, verifyJournal } from "../lib/journal.js";

const RESULTS = [];
const check = (ok, message) => RESULTS.push([ok, message]);

const MAGIC = Buffer.from("HSJ2", "latin1");

function frame(seq, kind, payloadText) {
  const payload = Buffer.from(payloadText, "utf8");
  const head = Buffer.alloc(12);
  head.writeUInt32LE(payload.length, 0);
  head.writeBigUInt64LE(BigInt(seq), 4);
  const digest = createHash("sha256")
    .update(head)
    .update(Buffer.from([kind]))
    .update(payload)
    .digest();
  const crc = Buffer.alloc(4);
  digest.copy(crc, 0, 0, 4);
  const kindByte = Buffer.from([kind]);
  return Buffer.concat([head, crc, kindByte, payload]);
}

function journalFile(frames) {
  const version = Buffer.alloc(4);
  version.writeUInt32LE(2, 0);
  return Buffer.concat([MAGIC, version, ...frames]);
}

const valid = journalFile([
  frame(1, 1, "run/start task: найди все текстовые файлы"),
  frame(2, 1, "tool/call search"),
  frame(3, 2, "run/end 42"),
]);

// 1. Целый журнал разбирается и ответ читается.
const checked = verifyJournal(valid);
check(checked.ok && checked.records.length === 3, "целый журнал: три кадра, ok");

// 2. Подмена одного байта в payload ломает CRC.
const corrupted = Buffer.from(valid);
corrupted[corrupted.length - 2] ^= 0x01;
const broken = verifyJournal(corrupted);
check(!broken.ok && broken.reason.includes("CRC"), `битый payload: ${broken.reason}`);

// 3. Подмена magic (HSJ2 → HSJ1) отвергается.
const wrongMagic = Buffer.from(valid);
wrongMagic.write("HSJ1", 0, "latin1");
const magic = verifyJournal(wrongMagic);
check(!magic.ok && magic.reason.includes("HSJ2"), `чужая версия файла: ${magic.reason}`);

// 4. Оборванный хвост отвергается, а не читается как «последний кадр».
const torn = Buffer.concat([valid, Buffer.from([0, 0, 0])]);
const tornReport = verifyJournal(torn);
check(!tornReport.ok && tornReport.reason.includes("оборван"), `оборванный хвост: ${tornReport.reason}`);

// 5. Разрыв последовательности (seq 1 → 3).
const gap = journalFile([frame(1, 1, "run/start task: x"), frame(3, 2, "run/end 7")]);
const gapReport = verifyJournal(gap);
check(!gapReport.ok && gapReport.reason.includes("разрыв"), `разрыв seq: ${gapReport.reason}`);

// 6. answerFromJournal: целый журнал отдаёт ответ, битый — пустой ответ и причину.
const dir = mkdtempSync(join(tmpdir(), "hsj-"));
try {
  const good = join(dir, "good.bin");
  writeFileSync(good, valid);
  const answer = answerFromJournal(good, "найди все текстовые файлы", 0);
  check(answer === "42", `answerFromJournal на целом журнале: ${JSON.stringify(answer)}`);

  const bad = join(dir, "bad.bin");
  const forged = Buffer.from(valid);
  forged[forged.length - 2] ^= 0x01;
  writeFileSync(bad, forged);
  const none = answerFromJournal(bad, "найди все текстовые файлы", 0);
  check(none === "", "подделанный журнал не даёт ответа");
  check(String(lastJournalError).includes("CRC"), `причина отказа сохранена: ${lastJournalError}`);

  // 7. Чужая задача не принимается даже на целом журнале.
  const foreign = answerFromJournal(good, "сложи два числа", 0);
  check(foreign === "", "чужая задача не принимает ответ");
} finally {
  rmSync(dir, { recursive: true, force: true });
}

let failed = 0;
for (const [ok, message] of RESULTS) {
  console.log(`[${ok ? "ok" : "FAIL"}] ${message}`);
  if (!ok) failed += 1;
}
console.log(`провалов: ${failed}`);
process.exit(failed === 0 ? 0 : 1);
