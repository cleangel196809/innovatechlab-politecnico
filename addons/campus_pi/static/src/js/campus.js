/* InnovaTech Lab · Campus PI — JS ligero sin dependencias */
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

        // Presentaciones generadas (y video narrado con la voz del navegador)
        document.querySelectorAll(".cp-deck").forEach(function (deck) {
            var slides = deck.querySelectorAll(".cp-slide");
            var dots = deck.querySelector(".cp-deck-dots");
            var playBtn = deck.querySelector("[data-deck=play]");
            var i = 0, playing = false, timer = null;
            var synth = window.speechSynthesis;
            if (!slides.length) { return; }
            slides.forEach(function (_s, k) {
                var b = document.createElement("button");
                b.type = "button";
                b.setAttribute("aria-label", "Diapositiva " + (k + 1));
                b.addEventListener("click", function () { stop(); show(k); });
                dots.appendChild(b);
            });
            function show(k) {
                i = Math.max(0, Math.min(slides.length - 1, k));
                slides.forEach(function (s, n) { s.classList.toggle("active", n === i); });
                dots.querySelectorAll("button").forEach(function (b, n) { b.classList.toggle("on", n === i); });
            }
            function voice() {
                if (!synth) { return null; }
                var vs = synth.getVoices().filter(function (v) { return /^es/i.test(v.lang); });
                return vs.filter(function (v) { return /CO|419|MX|US/.test(v.lang); })[0] || vs[0] || null;
            }
            function say() {
                if (!playing) { return; }
                var text = slides[i].dataset.say || "";
                var next = function () {
                    if (!playing) { return; }
                    if (i < slides.length - 1) { show(i + 1); say(); } else { stop(); }
                };
                if (synth && window.SpeechSynthesisUtterance) {
                    var u = new SpeechSynthesisUtterance(text);
                    u.lang = "es-CO";
                    var v = voice();
                    if (v) { u.voice = v; }
                    u.rate = 1;
                    u.onend = next;
                    u.onerror = function () { timer = setTimeout(next, 6000); };
                    synth.speak(u);
                } else {
                    timer = setTimeout(next, Math.max(5000, text.length * 60));
                }
            }
            function stop() {
                playing = false;
                clearTimeout(timer);
                if (synth) { synth.cancel(); }
                if (playBtn) { playBtn.textContent = "▶ Reproducir con narración"; }
            }
            if (playBtn) {
                playBtn.addEventListener("click", function () {
                    if (playing) { stop(); return; }
                    playing = true;
                    playBtn.textContent = "⏸ Pausar";
                    say();
                });
            }
            deck.querySelector("[data-deck=prev]").addEventListener("click", function () { stop(); show(i - 1); });
            deck.querySelector("[data-deck=next]").addEventListener("click", function () { stop(); show(i + 1); });
            document.addEventListener("keydown", function (e) {
                if (/INPUT|TEXTAREA|SELECT/.test((e.target.tagName || ""))) { return; }
                if (e.key === "ArrowRight") { stop(); show(i + 1); }
                if (e.key === "ArrowLeft") { stop(); show(i - 1); }
            });
            window.addEventListener("pagehide", stop);
            show(0);
        });

        // Práctica rápida de los cuestionarios (corrección en el servidor)
        document.querySelectorAll(".cp-practice").forEach(function (box) {
            box.querySelectorAll(".cp-practice-q").forEach(function (q) {
                var fb = q.querySelector(".cp-practice-fb");
                q.querySelectorAll(".cp-practice-opt").forEach(function (b) {
                    b.addEventListener("click", function () {
                        q.querySelectorAll(".cp-practice-opt").forEach(function (x) { x.disabled = true; });
                        fetch(box.dataset.url, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ jsonrpc: "2.0", method: "call",
                                params: { question_id: parseInt(q.dataset.q, 10), option_id: parseInt(b.dataset.o, 10) } }),
                        }).then(function (r) { return r.json(); }).then(function (data) {
                            var res = data.result || {};
                            if (data.error || res.error) {
                                fb.textContent = "No se pudo verificar la respuesta. Intenta de nuevo.";
                                q.querySelectorAll(".cp-practice-opt").forEach(function (x) { x.disabled = false; });
                                return;
                            }
                            b.classList.add(res.ok ? "ok" : "bad");
                            var good = q.querySelector('[data-o="' + res.correct_id + '"]');
                            if (good) { good.classList.add("ok"); }
                            fb.innerHTML = "<b>" + (res.ok ? "✔ ¡Correcto!" : "✘ No es correcta.") + "</b> " +
                                esc(res.feedback || "") + (res.explanation ? "<br/><span class='cp-muted'>" + esc(res.explanation) + "</span>" : "");
                        }).catch(function () {
                            fb.textContent = "No se pudo verificar la respuesta. Intenta de nuevo.";
                            q.querySelectorAll(".cp-practice-opt").forEach(function (x) { x.disabled = false; });
                        });
                    });
                });
            });
        });

        // Avance del agente de diseño instruccional
        var job = document.getElementById("cp-job");
        if (job) {
            var order = Array.prototype.map.call(job.querySelectorAll(".cp-job-steps li"), function (li) { return li.dataset.stage; });
            var poll = function () {
                fetch(job.dataset.url, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} }),
                }).then(function (r) { return r.json(); }).then(function (data) {
                    var r = data.result || {};
                    document.getElementById("cp-job-pct").textContent = (r.progress || 0) + " %";
                    document.getElementById("cp-job-bar").style.width = (r.progress || 0) + "%";
                    var log = document.getElementById("cp-job-log");
                    if (log.textContent !== r.log) { log.textContent = r.log || ""; log.scrollTop = log.scrollHeight; }
                    var idx = order.indexOf(r.stage);
                    job.querySelectorAll(".cp-job-steps li").forEach(function (li, i) {
                        li.classList.toggle("ok", i < idx || r.state === "done");
                        li.classList.toggle("on", i === idx && r.state !== "done");
                    });
                    var li = job.querySelector('.cp-job-steps li[data-stage="' + r.stage + '"]');
                    document.getElementById("cp-job-stage").textContent = r.state === "done" ? "Terminado" :
                        (r.state === "error" ? "Con error" : (li ? li.textContent : "En cola"));
                    if (r.state === "done") {
                        document.getElementById("cp-job-link").href = r.course_url;
                        document.getElementById("cp-job-done").hidden = false;
                        return;
                    }
                    if (r.state === "error" || r.stale) {
                        document.getElementById("cp-job-error-msg").textContent = r.error ||
                            "El agente dejó de responder (el servidor pudo reiniciarse). Puedes reintentar.";
                        document.getElementById("cp-job-error").hidden = false;
                        if (r.state === "error") { return; }
                    }
                    setTimeout(poll, 2500);
                }).catch(function () { setTimeout(poll, 5000); });
            };
            poll();
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
