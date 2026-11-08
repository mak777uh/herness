/**
 * dsh-herness-room — клиентская часть: вкладка «Комната» в правой панели DSH.
 *
 * Почему правая панель, а не отдельное окно: задача должна стоять рядом с
 * разговором, не уводя с него. Комната — часть харнесса, а не DSH; плагин
 * только показывает её.
 *
 * Регистрация типа вкладки — два шага (см. README @deepseek-ai/dsh-client-ui-sidebar-right):
 *   1. ctx.sidebarRightTabs.register({ id, kind, title, guide }) — объявление типа;
 *   2. ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name, key: id }, Body)).
 * Тело вкладки без объявления типа не делает вкладку: её нечем открыть.
 */

window.__ModuleLoader__.load({
  id: "dsh-herness-room",
  factory(require) {
    const React = require("react");
    const h = React.createElement;
    const { useState, useEffect, useRef, useCallback } = React;

    const KIND = "herness-room";
    const ID = "dsh-herness-room";
    const API = "/api/dsh-herness-room";

    const CSS = `
      .hsr-wrap{display:flex;flex-direction:column;height:100%;min-height:320px;
        font-family:inherit;color:var(--dsw-alias-label-primary,#1d1d1f)}
      .hsr-chat{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
      .hsr-msg{max-width:92%;padding:9px 12px;border-radius:12px;white-space:pre-wrap;
        word-wrap:break-word;font-size:13px;line-height:1.5}
      .hsr-user{align-self:flex-end;background:var(--dsw-alias-accent-primary,#4c8dff);color:#fff;
        border-bottom-right-radius:4px}
      .hsr-bot{align-self:flex-start;background:var(--dsw-alias-fill-secondary,rgba(127,127,127,.12));
        border:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.18));
        border-bottom-left-radius:4px}
      .hsr-meta{font-size:11px;opacity:.7;margin-bottom:5px;display:flex;gap:8px;align-items:center;
        flex-wrap:wrap}
      .hsr-badge{font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px}
      .hsr-PASS{background:rgba(63,185,80,.18);color:#3fb950}
      .hsr-FAIL{background:rgba(248,81,73,.18);color:#f85149}
      .hsr-UNKNOWN{background:rgba(210,153,34,.18);color:#d29922}
      .hsr-form{display:flex;gap:8px;padding:10px 12px;
        border-top:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.18))}
      .hsr-input{flex:1;resize:none;height:44px;padding:10px 12px;border-radius:10px;
        border:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.28));
        background:transparent;color:inherit;font:inherit;outline:none}
      .hsr-input:focus{border-color:var(--dsw-alias-accent-primary,#4c8dff)}
      .hsr-send{padding:0 16px;border:0;border-radius:10px;
        background:var(--dsw-alias-accent-primary,#4c8dff);color:#fff;font:inherit;
        font-weight:600;cursor:pointer}
      .hsr-send:disabled{opacity:.5;cursor:default}
      .hsr-empty{opacity:.6;text-align:center;margin-top:28px;font-size:13px}
      .hsr-wait{opacity:.75;font-style:italic}
      .hsr-retry{margin-top:6px;font-size:12px;background:none;border:0;padding:0;
        color:var(--dsw-alias-accent-primary,#4c8dff);cursor:pointer;text-decoration:underline}
    `;

    /** Задача в комнату. Пустой ответ всегда UNKNOWN — даже если сервер промолчал. */
    async function ask(task) {
      const response = await fetch(API + "/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task }),
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const row = await response.json();
      const answer = String(row.answer ?? "").trim();
      const verdict = answer ? (row.verdict || "UNKNOWN") : "UNKNOWN";
      return { ...row, answer, verdict };
    }

    function Room() {
      const [messages, setMessages] = useState([]);
      const [busy, setBusy] = useState(false);
      const [text, setText] = useState("");
      const chatRef = useRef(null);

      useEffect(() => {
        fetch(API + "/history")
          .then((r) => r.json())
          .then((rows) => {
            if (!Array.isArray(rows) || !rows.length) return;
            setMessages(rows.flatMap((row) => ([
              { role: "user", text: row.task },
              { role: "bot", text: row.answer || "(пусто)", verdict: row.verdict, seconds: row.seconds },
            ])));
          })
          .catch(() => { /* история не критична */ });
      }, []);

      useEffect(() => {
        if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
      }, [messages]);

      const send = useCallback(async () => {
        const task = text.trim();
        if (!task || busy) return;
        setText("");
        setBusy(true);
        setMessages((prev) => [...prev, { role: "user", text: task },
                                      { role: "bot", text: "выполняю в комнате…", waiting: true }]);
        try {
          const row = await ask(task);
          setMessages((prev) => [...prev.filter((m) => !m.waiting),
            { role: "bot", text: row.answer || "(пусто)", verdict: row.verdict, seconds: row.seconds }]);
        } catch (error) {
          setMessages((prev) => [...prev.filter((m) => !m.waiting),
            { role: "bot", text: "ошибка связи: " + error.message, verdict: "UNKNOWN" }]);
        } finally {
          setBusy(false);
        }
      }, [text, busy]);

      return h("div", { className: "hsr-wrap" }, [
        h("div", { className: "hsr-chat", ref: chatRef, key: "chat" },
          messages.length === 0
            ? [h("div", { className: "hsr-empty", key: "empty" },
                "Задайте задачу — она выполнится в изолированной комнате herness.")]
            : messages.map((m, i) => h("div", {
                key: i,
                className: "hsr-msg " + (m.role === "user" ? "hsr-user" : "hsr-bot") +
                           (m.waiting ? " hsr-wait" : ""),
              }, [
                m.role === "bot" && m.verdict
                  ? h("div", { className: "hsr-meta", key: "meta" }, [
                      h("span", { key: "t" }, "комната" + (m.seconds ? " · " + m.seconds + " с" : "")),
                      h("span", { key: "v", className: "hsr-badge hsr-" + m.verdict }, m.verdict),
                    ])
                  : null,
                h("div", { key: "body" }, m.text),
              ]))),
        h("div", { className: "hsr-form", key: "form" }, [
          h("textarea", {
            key: "input",
            className: "hsr-input",
            value: text,
            placeholder: "Например: сколько строк в NOT-CLAIMED.md? Ответь только числом.",
            onChange: (event) => setText(event.target.value),
            onKeyDown: (event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            },
          }),
          h("button", {
            key: "send",
            className: "hsr-send",
            disabled: busy,
            onClick: send,
          }, busy ? "…" : "Отправить"),
        ]),
      ]);
    }

    return {
      inject: ["slots", "sidebarRightTabs"],
      apply(ctx) {
        const styles = ctx.get("styles");
        const disposeStyles = styles && typeof styles.insert === "function"
          ? styles.insert(CSS)
          : () => {};

        const tabs = ctx.get("sidebarRightTabs");
        const slots = ctx.get("slots");
        const sidebarRight = ctx.get("sidebarRight");

        // Шаг 1: объявление типа вкладки. Без него тело вкладки некуда открыть.
        const disposeType = tabs && typeof tabs.register === "function"
          ? tabs.register({
              id: ID,
              kind: KIND,
              title: () => "Комната",
              guide: [{ id: KIND, title: "Комната herness",
                        description: "Задачи в изолированной комнате с вердиктом" }],
            })
          : () => {};

        // Шаг 2: тело вкладки, ключ — id типа.
        const disposeBody = slots && typeof slots.inject === "function"
          ? slots.inject("sidebar.right.pane.tab", () =>
              slots.register({ name: "sidebar.right.pane.tab", key: ID }, Room))
          : () => {};

        // Открытие: только когда есть сеанс на экране и вкладки ещё нет,
        // иначе вкладка плодилась бы на каждый рендер.
        const open = () => {
          if (!sidebarRight || typeof sidebarRight.openTab !== "function") return;
          const openTabs = sidebarRight.openTabs;
          const current = openTabs && typeof openTabs.getSnapshot === "function"
            ? openTabs.getSnapshot()
            : [];
          const exists = Array.isArray(current) && current.some((t) => t && t.kind === KIND);
          if (exists) return;
          try { sidebarRight.openTab(KIND); } catch { /* нет сеанса на экране */ }
        };

        const disposeAuto = sidebarRight && typeof sidebarRight.mounted === "object" &&
                            typeof sidebarRight.mounted.subscribe === "function"
          ? sidebarRight.mounted.subscribe(() => open())
          : () => {};

        return () => {
          disposeAuto();
          disposeBody();
          disposeType();
          disposeStyles();
        };
      },
    };
  },
});
