/**
 * dsh-herness-room — серверная часть.
 *
 * Принимает задачу от клиента, кладёт её в очередь herness, запускает прогон
 * в комнате и возвращает ответ с вердиктом.
 *
 * Почему через accept-run.ps1, а не напрямую: прогон в комнате — это QEMU,
 * собственное ядро и initramfs. Дублировать эту логику в плагине значило бы
 * иметь две реализации одного механизма.
 */

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const name = "dsh-herness-room";

export const inject = ["http", "slots"];

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

function now() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
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

  const id = `T-${now()}`;
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

  let verdict = "UNKNOWN";
  for (const line of output.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed.startsWith("итог:")) {
      verdict = trimmed.slice(trimmed.indexOf(":") + 1).trim();
    }
  }

  // Ответ агента лежит в журнале событием run/end: accept-run печатает вердикт,
  // но не текст ответа.
  let answer = "";
  const journal = join(root, "runs", "accept", "journal.bin");
  if (existsSync(journal)) {
    const raw = readFileSync(journal, "utf8");
    const found = raw.match(/run\/end ([^\x00\x06\n]+)/);
    if (found) answer = found[1].trim();
  }

  const seconds = Number(((Date.now() - started) / 1000).toFixed(1));
  writeFileSync(join(done, `${id}.json`),
    JSON.stringify({ ...CRITERIA, task, verdict, answer }, null, 1) + "\n", "utf8");
  try { (await import("node:fs")).unlinkSync(criteriaPath); } catch { /* уже нет */ }

  // История для клиента: одна строка JSON на задачу.
  const history = join(intake, "history.jsonl");
  const row = { task, answer, verdict, seconds, at: new Date().toISOString() };
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

  // Слот интерфейса: вкладка «Комната».
  ctx.inject(["slots"], (sctx) => {
    const slots = sctx.get("slots");
    if (!slots || typeof slots.register !== "function") return;
    slots.register({ name: "herness.room", key: "dsh-herness-room#room" }, () => null);
  });
}
