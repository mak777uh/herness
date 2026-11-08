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
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export const name = "dsh-herness-room";

export const inject = ["http"];

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
 * Достать ответ агента из журнала приёмки.
 *
 * Берётся ПОСЛЕДНЕЕ событие `run/end` (журнал дописывается прогонами),
 * а не первое: несколько прогонов в одном журнале иначе отдали бы ответ
 * предыдущей задачи.
 */
export function answerFromJournal(journalPath) {
  if (!existsSync(journalPath)) return "";
  let raw;
  try {
    raw = readFileSync(journalPath, "latin1");
  } catch {
    return "";
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

  const answer = answerFromJournal(join(root, "runs", "accept", "journal.bin"));
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

export function apply(ctx, config = {}) {
  const settings = { ...DEFAULTS, ...config };
  const root = settings.hernessRoot;

  // HTTP-мост: клиент зовёт /api/dsh-herness-room/ask и /history.
  ctx.inject(["http"], (hctx) => {
    const http = hctx.get("http");
    if (!http || typeof http.route !== "function") return;
    http.route("POST", "/api/dsh-herness-room/ask", async (request, reply) => {
      const task = String(request.body?.task ?? "").trim();
      if (!task) {
        reply.code(400).send({ error: "пустая задача" });
        return;
      }
      const row = await runTask(root, settings.kernel, settings.timeoutSec, task);
      reply.send(row);
    });
    http.route("GET", "/api/dsh-herness-room/history", async (_request, reply) => {
      reply.send(readHistory(root));
    });
  });
}
