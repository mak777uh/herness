/**
 * journal.js — проверка кадров HSJ2 в плагине.
 *
 * Зачем. До этого плагин читал журнал как текст (latin1) и искал в нём `run/end`.
 * Такой журнал можно испортить или подделать одной правкой байтов, и ответ всё равно
 * прошёл бы: CRC кадра никто не сверял. Здесь кадр проверяется по той же раскладке,
 * что в `core-rs/src/journal.rs`:
 *
 *   файл:   "HSJ2" (4) + version u32 LE (4)
 *   кадр:   len u32 | seq u64 | crc u32 | kind u8 | payload[len]
 *   crc  = первые 4 байта SHA-256 от len || seq || kind || payload (u32 LE)
 *   kind = 1 (Data) | 2 (Commit)
 *
 * Правило: сомнение трактуется как «журнала нет». Пустой ответ даёт UNKNOWN
 * (R-0008), а не PASS.
 */

import { createHash } from "node:crypto";

export const MAGIC = "HSJ2";
export const VERSION = 2;
export const FILE_HEADER = 8;
export const RECORD_HEADER = 17;
const KINDS = new Set([1, 2]);

function crcOf(len, seqBig, kind, payload) {
  const head = Buffer.alloc(12);
  head.writeUInt32LE(len, 0);
  head.writeBigUInt64LE(seqBig, 4);
  const digest = createHash("sha256")
    .update(head)
    .update(Buffer.from([kind]))
    .update(payload)
    .digest();
  return digest.readUInt32LE(0);
}

/**
 * Разобрать и проверить журнал.
 * @returns {{ok: boolean, records: Array<{seq: number, kind: number, payload: Buffer}>, reason: string}}
 */
export function verifyJournal(buffer) {
  const empty = { ok: false, records: [], reason: "пустой файл" };
  if (!Buffer.isBuffer(buffer) || buffer.length < FILE_HEADER) return empty;

  const magic = buffer.subarray(0, 4).toString("latin1");
  if (magic !== MAGIC) {
    return { ok: false, records: [], reason: `заголовок ${JSON.stringify(magic)} вместо ${MAGIC}` };
  }
  const version = buffer.readUInt32LE(4);
  if (version !== VERSION) {
    return { ok: false, records: [], reason: `версия ${version} вместо ${VERSION}` };
  }

  const records = [];
  let pos = FILE_HEADER;
  let expected = 1;
  while (pos < buffer.length) {
    if (buffer.length - pos < RECORD_HEADER) {
      return { ok: false, records, reason: `оборванный кадр: ${buffer.length - pos} байт вместо ${RECORD_HEADER}` };
    }
    const len = buffer.readUInt32LE(pos);
    const seqBig = buffer.readBigUInt64LE(pos + 4);
    const seq = Number(seqBig);
    const crc = buffer.readUInt32LE(pos + 12);
    const kind = buffer[pos + 16];
    if (!KINDS.has(kind)) {
      return { ok: false, records, reason: `неизвестный kind ${kind}` };
    }
    if (buffer.length - pos < RECORD_HEADER + len) {
      return { ok: false, records, reason: "оборванный хвост: payload короче len" };
    }
    const payload = buffer.subarray(pos + RECORD_HEADER, pos + RECORD_HEADER + len);
    if (seq !== expected) {
      return { ok: false, records, reason: `разрыв последовательности: ждали ${expected}, в кадре ${seq}` };
    }
    const actual = crcOf(len, seqBig, kind, payload);
    if (actual !== crc) {
      return {
        ok: false,
        records,
        reason: `CRC кадра ${seq} не сходится: ${actual.toString(16)} против ${crc.toString(16)}`,
      };
    }
    records.push({ seq, kind, payload });
    expected += 1;
    pos += RECORD_HEADER + len;
  }
  return { ok: true, records, reason: "" };
}

/** Текст события из проверенных кадров (UTF-8). */
export function eventText(record) {
  return record.payload.toString("utf8");
}
