/**
 * dsh-herness-room — серверная часть.
 *
 * Принимает задачу от клиента, кладёт её в очередь herness, запускает прогон
 * в комнате и возвращает ответ с вердиктом.
 *
 * Почему через accept-run.ps1, а не напрямую: прогон в комнате — это QEMU,
 * собственное ядро и initramfs. Дублировать эту логику в плагине значило бы
 * иметь две реализации одного механизма.
 *
 * ДЕФЕКТ, ИСПРАВЛЕННЫЙ В 0.2.0 (F-ROOM-1). Ответ агента лежит в журнале
 * событием `run/end`. accept-run.ps1 УДАЛЯЕТ журнал перед каждым прогоном
 * (строка `Remove-Item $journal`), а прежняя версия читала ответ ПОСЛЕ
 * прогона. Если прогон падал раньше записи журнала, журнал оставался
 * отсутствующим, ответ получался пустым, а вердикт брался из строки
 * «итог:» и оставался PASS. Так в intake/history.jsonl появилась строка
 * `verdict: PASS, answer: ""` — PASS без ответа.
 *
 * Правило (AGENTS.md §2, R-0008): пустой ответ — это UNKNOWN, никогда не
 * PASS. Здесь вердикт понижается до UNKNOWN, если ответа нет.
 */

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export const name = "dsh-herness-room";

// Обязательных зависимостей нет: без webServer плагин просто не регистрирует
// маршруты, но не висит в pending. Раньше здесь стоял `["http"]` — сервиса с
// таким именем в профиле нет, и строка не активировалась НИКОГДА (F-ROOM-2).
export const inject = [];

/** Настройки по умолчанию: их можно переопределить в cordis.patch.yml. */
const DEFAULTS = {
  hernessRoot: "C:/111/herness",
  kernel: "vmlinuz-own-hardened2",
  timeoutSec: 420,
};

/** Критерий приёмки для задач из окна: агент должен закончить сам. */
const CRITERIA = {
  require_status: "done",
  max_steps: 24,
  max_allowance: 0.1,
  must_not_call: ["write"],
  tools: ["search", "list", "read"],
};

const VERDICTS = new Set(["PASS", "FAIL", "UNKNOWN"]);

function now() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

/**
 * Достать ответ агента из журнала приёмки — но только если журнал
 * принадлежит ЭТОЙ задаче.
 *
 * Дефект F-ROOM-3 (найден 08.11.2026 по истории окна). accept-run.ps1 удаляет
 * журнал перед прогоном, но если прогон падает раньше записи, журнала нет
 * вовсе или он остаётся от ПРЕДЫДУЩЕГО прогона. Прежняя версия брала из него
 * последний `run/end` и отдавала ЧУЖОЙ ответ: на «найди все текстовые файлы»
 * приходил ответ на «привет».
 *
 * Теперь ответ принимается, только если:
 *   — файл журнала изменён после старта прогона (mtime >= startedAt), и
 *   — событие `run/start` в журнале несёт ровно эту задачу.
 * Иначе ответ пуст, и вердикт понижается до UNKNOWN.
 */
export function answerFromJournal(journalPath, task = "", startedAt = 0) {
  if (!existsSync(journalPath)) return "";
  let stat;
  try {
    stat = statSync(journalPath);
  } catch {
    return "";
  }
  // Журнал старше прогона — это журнал другого прогона.
  if (startedAt && stat.mtimeMs < startedAt) return "";

  let raw;
  try {
    raw = readFileSync(journalPath, "latin1");
  } catch {
    return "";
  }
  // Задача должна совпасть с той, что записана в run/start этого журнала.
  // Сравниваем по вхождению, а не по равенству: запись журнала приписывает
  // к тексту служебный байт (в замере 08.11.2026 — «…числом.5»), и строгое
  // равенство отвергало бы СВОЙ журнал. Задача длинная, случайного
  // совпадения с чужой не будет.
  if (task) {
    const starts = [...raw.matchAll(/run\/start task: ([^\x00\x06\n]+)/g)];
    if (!starts.length) return "";
    const needle = task.trim();
    const recorded = starts.map((m) =>
      Buffer.from(m[1], "latin1").toString("utf8"));
    if (!recorded.some((text) => text.includes(needle))) return "";
  }

  const matches = [...raw.matchAll(/run\/end ([^\x00\x06\n]+)/g)];
  if (!matches.length) return "";
  const bytes = Buffer.from(matches[matches.length - 1][1], "latin1");
  return bytes.toString("utf8").trim();
}

/**
 * Вердикт с защитой от ложного PASS.
 *
 * `итог:` — вердикт приёмки над журналом. Он ничего не говорит о том, что
 * ответ доехал до окна. Ответ без текста — это UNKNOWN (R-0008).
 */
export function settleVerdict(reported, answer) {
  const verdict = VERDICTS.has(reported) ? reported : "UNKNOWN";
  if (verdict === "PASS" && !String(answer ?? "").trim()) return "UNKNOWN";
  return verdict;
}

/**
 * Прогон задачи в комнате.
 * Возвращает { answer, verdict, seconds, task }.
 */
async function runTask(root, kernel, timeoutSec, task) {
  const intake = join(root, "intake");
  const done = join(intake, "done");
  mkdirSync(intake, { recursive: true });
  mkdirSync(done, { recursive: true });

  // Метка с миллисекундами и случайным хвостом: две задачи в одну секунду
  // иначе получили бы один файл критерия.
  const id = `T-${now()}-${randomUUID().slice(0, 8)}`;
  const criteriaPath = join(intake, `${id}.json`);
  writeFileSync(criteriaPath, JSON.stringify({ ...CRITERIA, task }, null, 1) + "\n", "utf8");

  const started = Date.now();
  const args = [
    "-NoProfile", "-File", join(root, "core-rs", "accept-run.ps1"),
    "-Mode", "loop-bridge", "-Kernel", kernel, "-Net",
    "-TimeoutSec", String(timeoutSec),
    "-Criteria", `intake/${id}.json`,
    "-Task", task,
  ];

  const output = await new Promise((resolve) => {
    let text = "";
    const child = spawn("pwsh", args, { cwd: root, windowsHide: true });
    child.stdout.on("data", (chunk) => { text += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk) => { text += chunk.toString("utf8"); });
    child.on("close", () => resolve(text));
    child.on("error", () => resolve(text));
  });

  let reported = "";
  for (const line of output.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed.startsWith("итог:")) {
      reported = trimmed.slice(trimmed.indexOf(":") + 1).trim();
    }
  }

  // Ответ принимается только из журнала ЭТОГО прогона: файл должен быть
  // записан после старта и нести ту же задачу. Иначе журнал чужой, и ответ
  // пуст — вердикт понизится до UNKNOWN (F-ROOM-3).
  const answer = answerFromJournal(
    join(root, "runs", "accept", "journal.bin"), task, started);
  const verdict = settleVerdict(reported, answer);

  const seconds = Number(((Date.now() - started) / 1000).toFixed(1));
  writeFileSync(join(done, `${id}.json`),
    JSON.stringify({ ...CRITERIA, task, verdict, reported, answer }, null, 1) + "\n", "utf8");
  try { unlinkSync(criteriaPath); } catch { /* уже нет */ }

  // История для клиента: одна строка JSON на задачу.
  const history = join(intake, "history.jsonl");
  const row = { task, answer, verdict, reported, seconds, at: new Date().toISOString() };
  const previous = existsSync(history) ? readFileSync(history, "utf8") : "";
  writeFileSync(history, previous + JSON.stringify(row) + "\n", "utf8");

  return row;
}

function readHistory(root, limit = 50) {
  const history = join(root, "intake", "history.jsonl");
  if (!existsSync(history)) return [];
  const lines = readFileSync(history, "utf8").split(/\r?\n/).filter(Boolean);
  return lines.slice(-limit).map((line) => {
    try { return JSON.parse(line); } catch { return null; }
  }).filter(Boolean);
}

/**
 * Прочитать тело запроса целиком (node:http, без фреймворка).
 * Потолок 64 КиБ: задача — это текст, а не файл; всё сверх — отказ, а не OOM.
 */
function readBody(req, limit = 64 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new Error("тело запроса больше 64 КиБ"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function sendJson(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
  });
  res.end(body);
}

export function apply(ctx, config = {}) {
  const settings = { ...DEFAULTS, ...config };
  const root = settings.hernessRoot;

  // Маршруты регистрируются в webServer — это и есть HTTP-носитель DSH.
  // Раньше здесь стоял сервис `http`, которого в профиле нет: строка висела
  // в ожидании, маршруты не появлялись, и окно получало 404 (F-ROOM-2).
  // Обработчик — обычный node:http (req, res), а не (request, reply).
  ctx.inject(["webServer"], (sctx) => {
    const server = sctx.get("webServer");
    if (!server || typeof server.register !== "function") return;

    const history = server.register({
      kind: "exact",
      path: "/api/dsh-herness-room/history",
      handler: (req, res) => {
        if (req.method !== "GET") {
          res.writeHead(405, { allow: "GET" });
          res.end();
          return;
        }
        sendJson(res, 200, readHistory(root));
      },
    });

    const ask = server.register({
      kind: "exact",
      path: "/api/dsh-herness-room/ask",
      handler: async (req, res) => {
        if (req.method !== "POST") {
          res.writeHead(405, { allow: "POST" });
          res.end();
          return;
        }
        let task = "";
        try {
          const raw = await readBody(req);
          task = String(JSON.parse(raw || "{}").task ?? "").trim();
        } catch (error) {
          sendJson(res, 400, { error: String(error && error.message ? error.message : error) });
          return;
        }
        if (!task) {
          sendJson(res, 400, { error: "пустая задача" });
          return;
        }
        try {
          const row = await runTask(root, settings.kernel, settings.timeoutSec, task);
          sendJson(res, 200, row);
        } catch (error) {
          // Прогон не состоялся — это UNKNOWN, а не PASS и не пустой ответ.
          sendJson(res, 200, {
            task, answer: "", verdict: "UNKNOWN", seconds: 0,
            error: String(error && error.message ? error.message : error),
          });
        }
      },
    });

    return () => {
      ask();
      history();
    };
  });
}
