window.__ModuleLoader__.load({
  id: "dsh-herness-room",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;

    let react = require("react");
    let react_jsx_runtime = require("react/jsx-runtime");
    const h = react_jsx_runtime.jsx;
    const { useState, useEffect, useRef } = react;

    // ---- стили ----
    const css = `
      .hsr-wrap{display:flex;flex-direction:column;height:100%;min-height:420px;
        font-family:-apple-system,"Segoe UI",system-ui,sans-serif;color:var(--dsw-alias-label-primary,#1d1d1f)}
      .hsr-chat{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
      .hsr-msg{max-width:min(760px,88%);padding:10px 14px;border-radius:12px;white-space:pre-wrap;
        word-wrap:break-word;font-size:14px;line-height:1.5}
      .hsr-user{align-self:flex-end;background:#4c8dff;color:#fff;border-bottom-right-radius:4px}
      .hsr-bot{align-self:flex-start;background:rgba(127,127,127,.12);
        border:1px solid rgba(127,127,127,.18);border-bottom-left-radius:4px}
      .hsr-meta{font-size:11px;opacity:.65;margin-bottom:5px;display:flex;gap:8px;align-items:center}
      .hsr-badge{font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px}
      .hsr-PASS{background:rgba(63,185,80,.18);color:#3fb950}
      .hsr-FAIL{background:rgba(248,81,73,.18);color:#f85149}
      .hsr-UNKNOWN{background:rgba(210,153,34,.18);color:#d29922}
      .hsr-form{display:flex;gap:8px;padding:12px 16px;border-top:1px solid rgba(127,127,127,.18)}
      .hsr-input{flex:1;resize:none;height:46px;padding:11px 13px;border-radius:10px;
        border:1px solid rgba(127,127,127,.28);background:transparent;color:inherit;font:inherit;outline:none}
      .hsr-input:focus{border-color:#4c8dff}
      .hsr-send{padding:0 20px;border:0;border-radius:10px;background:#4c8dff;color:#fff;
        font:inherit;font-weight:600;cursor:pointer}
      .hsr-send:disabled{opacity:.5;cursor:default}
      .hsr-empty{opacity:.6;text-align:center;margin-top:36px;font-size:14px}
      .hsr-wait{opacity:.7;font-style:italic}
    `;
    if (!document.getElementById("dsh-herness-room-css")) {
      const style = document.createElement("style");
      style.id = "dsh-herness-room-css";
      style.textContent = css;
      document.head.appendChild(style);
    }

    // ---- компонент ----
    function Room() {
      const [messages, setMessages] = useState([]);
      const [busy, setBusy] = useState(false);
      const [text, setText] = useState("");
      const chatRef = useRef(null);

      useEffect(() => {
        fetch("/api/dsh-herness-room/history")
          .then((r) => r.json())
          .then((rows) => {
            if (!Array.isArray(rows) || !rows.length) return;
            setMessages(rows.flatMap((row) => ([
              { role: "user", text: row.task },
              { role: "bot", text: row.answer || "(пусто)", verdict: row.verdict, seconds: row.seconds },
            ])));
          })
          .catch(() => {});
      }, []);

      useEffect(() => {
        if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
      }, [messages]);

      async function send() {
        const task = text.trim();
        if (!task || busy) return;
        setText("");
        setBusy(true);
        setMessages((prev) => [...prev, { role: "user", text: task },
                                      { role: "bot", text: "выполняю в комнате…", waiting: true }]);
        try {
          const response = await fetch("/api/dsh-herness-room/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task }),
          });
          const row = await response.json();
          setMessages((prev) => [...prev.filter((m) => !m.waiting),
            { role: "bot", text: row.answer || "(пусто)", verdict: row.verdict, seconds: row.seconds }]);
        } catch (error) {
          setMessages((prev) => [...prev.filter((m) => !m.waiting),
            { role: "bot", text: "ошибка связи: " + error, verdict: "UNKNOWN" }]);
        } finally {
          setBusy(false);
        }
      }

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

    exports.Room = Room;
    exports.apply = (ctx) => {
      if (!ctx || !ctx.slots) return;
      ctx.slots.register({ name: "herness.room", key: "dsh-herness-room#room" }, () => Room);
    };
    return module.exports;
  },
});
