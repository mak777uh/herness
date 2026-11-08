/**
 * dsh-herness-room — клиентская часть: «Комната» как отдельная панель DSH.
 *
 * Где живёт: кнопка — в левом меню (`sidebar.panellist`, рядом с «Плагинами»),
 * содержимое — в центральной панели (root-слот `main` под своим ключом).
 * Открытие — `ctx.layout.selectPanel(id)`; `conversation` в `main` зарезервирован
 * за разговором, поэтому ключ свой.
 *
 * Почему не вкладка правой панели: владелец попросил место в левом меню под
 * «Плагинами» — там глобальные панели, а не вкладки разговора.
 *
 * Комната — часть харнесса, а не DSH; плагин только показывает её.
 */

window.__ModuleLoader__.load({
  id: "dsh-herness-room",
  factory(require) {
    const React = require("react");
    const h = React.createElement;
    const { useState, useEffect, useRef, useCallback } = React;

    const ID = "dsh-herness-room";
    const API = "/api/dsh-herness-room";

    const CSS = `
      /* Окно занимает панель целиком и не может уехать за экран.
         Родитель — .mainPanel из ui-layout: display:flex; flex:1; min-height:0,
         БЕЗ position:relative. Поэтому absolute привязался бы к frame, а не к
         панели; берём flex-элемент с flex:1 и min-height:0 — тогда высоту
         задаёт панель, а не содержимое, и «съезда» вниз не будет. */
      .hsr-wrap{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;
        overflow:hidden;font-family:inherit;color:var(--dsw-alias-label-primary,#1d1d1f);
        background:var(--dsw-alias-bg-base,transparent)}
      /* Короткий экран: запас снизу уменьшается, чтобы лента не схлопнулась. */
      @media (max-height:700px){.hsr-form{padding-bottom:calc(12px + var(--hsr-bottom-gap,24px))}}
      .hsr-head{display:flex;align-items:center;gap:10px;padding:10px 16px;
        border-bottom:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.18));
        flex:0 0 auto}
      .hsr-title{font-size:14px;font-weight:600;margin:0}
      .hsr-sub{font-size:12px;opacity:.6;margin-left:auto}
      .hsr-chat{flex:1 1 auto;min-height:0;overflow-y:auto;padding:16px;
        display:flex;flex-direction:column;gap:12px;scroll-behavior:smooth}
      .hsr-msg{max-width:min(760px,88%);padding:10px 14px;border-radius:14px;
        white-space:pre-wrap;word-wrap:break-word;font-size:14px;line-height:1.55}
      .hsr-user{align-self:flex-end;background:var(--dsw-alias-accent-primary,#4c8dff);
        color:#fff;border-bottom-right-radius:5px}
      .hsr-bot{align-self:flex-start;
        background:var(--dsw-alias-fill-secondary,rgba(127,127,127,.12));
        border:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.18));
        border-bottom-left-radius:5px}
      .hsr-meta{font-size:11px;opacity:.7;margin-bottom:6px;display:flex;gap:8px;
        align-items:center;flex-wrap:wrap}
      .hsr-badge{font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px}
      .hsr-PASS{background:rgba(63,185,80,.18);color:#3fb950}
      .hsr-FAIL{background:rgba(248,81,73,.18);color:#f85149}
      .hsr-UNKNOWN{background:rgba(210,153,34,.18);color:#d29922}
      /* Ввод прибит к низу панели, но с запасом снизу.
         Замер по скриншоту 08.11.2026: нижние 58 px экрана (y 1021..1078)
         накрыты сплошной светлой полосой #efefef на всю ширину, и вердикты
         PASS/FAIL оказывались под ней. Запас отодвигает ввод в видимую зону.
         Значение задаётся переменной --hsr-bottom-gap (по умолчанию 64 px). */
      .hsr-form{flex:0 0 auto;display:flex;gap:10px;align-items:flex-end;
        padding:12px 16px 16px;
        padding-bottom:calc(16px + var(--hsr-bottom-gap,64px));
        border-top:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.18));
        background:var(--dsw-alias-bg-primary,transparent)}
      .hsr-input{flex:1;resize:none;min-height:46px;max-height:160px;padding:12px 14px;
        border-radius:12px;border:1px solid var(--dsw-alias-border-secondary,rgba(127,127,127,.28));
        background:var(--dsw-alias-bg-secondary,transparent);color:inherit;font:inherit;
        line-height:1.4;outline:none;box-sizing:border-box}
      .hsr-input:focus{border-color:var(--dsw-alias-accent-primary,#4c8dff)}
      .hsr-send{flex:0 0 auto;height:46px;padding:0 20px;border:0;border-radius:12px;
        background:var(--dsw-alias-accent-primary,#4c8dff);color:#fff;font:inherit;
        font-weight:600;cursor:pointer}
      .hsr-send:disabled{opacity:.5;cursor:default}
      .hsr-empty{opacity:.6;text-align:center;margin:auto;font-size:14px;max-width:420px}
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

    /**
     * Сколько пикселей внизу окна недоступно.
     *
     * Замер 08.11.2026: экран 1536x864 при масштабе 125 %, рабочая область
     * 1536x816 — 48 логических px снизу заняты панелью задач. Окно DSH
     * развёрнуто и достаёт до 823, то есть его низ уходит ПОД панель.
     * Приложение при этом рисует полную высоту, и последние ~48 px
     * оказываются вне экрана — вместе с полем ввода.
     *
     * Берём visualViewport: он знает реально видимую высоту, а не
     * запрошенную. Разница и есть недоступная полоса.
     */
    function measureBottomGap(el) {
      if (!el || typeof el.getBoundingClientRect !== "function") return 0;
      const rect = el.getBoundingClientRect();
      const vv = window.visualViewport;
      const visibleBottom = vv
        ? vv.offsetTop + vv.height
        : (window.innerHeight || document.documentElement.clientHeight || 0);
      if (!visibleBottom || !rect.height) return 0;
      const gap = Math.round(visibleBottom - rect.bottom);
      // Разумный предел: больше 200 px — это уже не «полоса», а ошибка замера.
      return gap > 0 && gap <= 200 ? gap : 0;
    }

    function Room() {
      const [messages, setMessages] = useState([]);
      const [busy, setBusy] = useState(false);
      const [text, setText] = useState("");
      const [bottomGap, setBottomGap] = useState(0);
      const chatRef = useRef(null);
      const wrapRef = useRef(null);

      // Запас снизу меряется по фактическому положению панели и
      // пересчитывается при изменении размера окна.
      useEffect(() => {
        const apply = () => setBottomGap(measureBottomGap(wrapRef.current));
        apply();
        const timer = window.setTimeout(apply, 250);
        window.addEventListener("resize", apply);
        // visualViewport меняется, когда панель задач или масштаб меняют
        // реально видимую высоту, и resize окна при этом может не прийти.
        const vv = window.visualViewport;
        if (vv) {
          vv.addEventListener("resize", apply);
          vv.addEventListener("scroll", apply);
        }
        return () => {
          window.clearTimeout(timer);
          window.removeEventListener("resize", apply);
          if (vv) {
            vv.removeEventListener("resize", apply);
            vv.removeEventListener("scroll", apply);
          }
        };
      }, []);

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

      // Поле ввода растёт вместе с текстом, но не выше max-height из CSS.
      const inputRef = useRef(null);
      useEffect(() => {
        const el = inputRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 160) + "px";
      }, [text]);

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

      return h("div", {
        className: "hsr-wrap",
        ref: wrapRef,
        style: bottomGap ? { "--hsr-bottom-gap": bottomGap + "px" } : undefined,
      }, [
        h("div", { className: "hsr-head", key: "head" }, [
          h("h2", { className: "hsr-title", key: "t" }, "Комната herness"),
          h("span", { className: "hsr-sub", key: "s" },
            busy ? "выполняется…" : "изолированная комната · PASS / FAIL / UNKNOWN"),
        ]),
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
            ref: inputRef,
            className: "hsr-input",
            rows: 1,
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

    /**
     * Иконка кнопки в левом меню.
     *
     * Кнопку рисует сам сайдбар (`sidebar.panellist` — «Global panel icons»),
     * а сюда приходят только size и active. Поэтому возвращаем глиф, а не
     * свою кнопку: иначе получилась бы кнопка внутри кнопки.
     */
    function PanelIcon({ size = 18, active = false } = {}) {
      return h("svg", {
        viewBox: "0 0 24 24",
        width: size,
        height: size,
        "aria-hidden": "true",
        focusable: "false",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: active ? 2 : 1.8,
        strokeLinecap: "round",
        strokeLinejoin: "round",
      }, [
        h("rect", { key: "r", x: 3, y: 4, width: 18, height: 13, rx: 3 }),
        h("path", { key: "p", d: "M8 21h8M9 12l2 2 4-4" }),
      ]);
    }

    return {
      inject: ["slots"],
      apply(ctx) {
        const styles = ctx.get("styles");
        const disposeStyles = styles && typeof styles.insert === "function"
          ? styles.insert(CSS)
          : () => {};

        const slots = ctx.get("slots");
        if (!slots || typeof slots.inject !== "function") return disposeStyles;

        // Тело панели: глобальные панели занимают root-слот `main` под своим
        // ключом (`conversation` зарезервирован за разговором).
        const disposeBody = slots.inject("main", () =>
          slots.register({ name: "main", key: ID }, Room));

        // Кнопка в левом меню. id обязан совпадать с ключом панели в `main`:
        // каталог слота говорит прямо — «each list id addresses the matching
        // main panel». order 60 — после «Плагинов» (0) и «Расписаний» (10).
        const disposeButton = slots.inject("sidebar.panellist", () =>
          slots.register({ name: "sidebar.panellist", id: ID, order: 60,
                           label: "Комната" }, PanelIcon));

        return () => {
          disposeButton();
          disposeBody();
          disposeStyles();
        };
      },
    };
  },
});
