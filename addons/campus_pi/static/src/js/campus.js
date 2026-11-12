/* InnobaTech Lab · Campus PI — JS ligero sin dependencias */
(function () {
    "use strict";

    function esc(s) {
        return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    // Markdown mínimo para las respuestas del tutor IA (seguro: se escapa primero)
    function md(text) {
        var lines = esc(text || "").split(/\n/);
        var html = "", inList = false;
        lines.forEach(function (l) {
            var li = l.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
            if (li) {
                if (!inList) { html += "<ul>"; inList = true; }
                html += "<li>" + li[1] + "</li>";
                return;
            }
            if (inList) { html += "</ul>"; inList = false; }
            if (/^#{1,6}\s/.test(l)) { html += "<p><b>" + l.replace(/^#+\s/, "") + "</b></p>"; }
            else if (l.trim()) { html += "<p>" + l + "</p>"; }
        });
        if (inList) { html += "</ul>"; }
        return html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
    }

    function overlay(msg) {
        var o = document.createElement("div");
        o.className = "cp-overlay";
        o.innerHTML = '<div><div class="cp-spinner"></div>' + esc(msg) + "</div>";
        document.body.appendChild(o);
    }

    document.addEventListener("DOMContentLoaded", function () {
        // Formularios largos (agente IA)
        document.querySelectorAll(".cp-loading-form").forEach(function (f) {
            f.addEventListener("submit", function () {
                overlay("El agente IA está trabajando… esto puede tardar un par de minutos.");
            });
        });

        // Cronómetro del simulador
        var timer = document.getElementById("cp-timer");
        if (timer) {
            var deadline = parseInt(timer.dataset.deadline, 10);
            var form = document.getElementById("cp-sim-form");
            var tick = function () {
                var left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
                var m = Math.floor(left / 60), s = left % 60;
                timer.textContent = (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                if (left < 120) { timer.classList.add("low"); }
                if (left <= 0) {
                    clearInterval(iv);
                    form.querySelector("button").removeAttribute("onclick");
                    form.submit();
                }
            };
            var iv = setInterval(tick, 1000);
            tick();
        }

        // Chat del tutor IA
        var chat = document.getElementById("cp-chat");
        if (chat) {
            chat.querySelectorAll("[data-md]").forEach(function (n) { n.innerHTML = md(n.textContent); });
            chat.scrollTop = chat.scrollHeight;
            var input = document.getElementById("cp-chat-input");
            var send = function (text) {
                if (!text.trim()) { return; }
                var me = document.createElement("div");
                me.className = "cp-msg cp-msg-me";
                me.textContent = text;
                chat.appendChild(me);
                var wait = document.createElement("div");
                wait.className = "cp-msg cp-msg-ai cp-typing";
                wait.textContent = "El tutor está pensando…";
                chat.appendChild(wait);
                chat.scrollTop = chat.scrollHeight;
                input.value = "";
                fetch(chat.dataset.url, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { message: text } }),
                }).then(function (r) { return r.json(); }).then(function (data) {
                    wait.classList.remove("cp-typing");
                    if (data.error) {
                        wait.textContent = "Error: " + ((data.error.data && data.error.data.message) || data.error.message);
                    } else {
                        wait.innerHTML = md(data.result.answer);
                    }
                    chat.scrollTop = chat.scrollHeight;
                }).catch(function () { wait.textContent = "No fue posible contactar al tutor."; });
            };
            document.getElementById("cp-chat-form").addEventListener("submit", function (e) {
                e.preventDefault();
                send(input.value);
            });
            input.addEventListener("keydown", function (e) {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); }
            });
            document.querySelectorAll(".cp-suggest").forEach(function (b) {
                b.addEventListener("click", function () { send(b.textContent); });
            });
        }
    });
})();
