/* InnovaTech Lab · Campus PI — JS ligero sin dependencias */
(function () {
    "use strict";

    function b64text(text) {
        var bytes = new TextEncoder().encode(text), bin = "";
        for (var i = 0; i < bytes.length; i++) { bin += String.fromCharCode(bytes[i]); }
        return btoa(bin);
    }

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

        // Presentaciones y videos generados: voz neuronal del servidor (respaldo: voz del navegador),
        // puntos que aparecen al ritmo de la narración, subtítulos y pantalla completa.
        document.querySelectorAll(".cp-deck").forEach(function (deck) {
            var slides = deck.querySelectorAll(".cp-slide");
            var dots = deck.querySelector(".cp-deck-dots");
            var playBtn = deck.querySelector("[data-deck=play]");
            var ccBtn = deck.querySelector("[data-deck=cc]");
            var cap = deck.querySelector(".cp-deck-caption");
            var voiceUrl = deck.dataset.voice;
            var playLabel = playBtn ? playBtn.innerHTML : "";
            var i = 0, playing = false, timer = null, audio = null, token = 0, serverOk = !!voiceUrl;
            var synth = window.speechSynthesis;
            var cache = {};
            if (!slides.length) { return; }
            slides.forEach(function (_s, k) {
                var b = document.createElement("button");
                b.type = "button";
                b.setAttribute("aria-label", "Diapositiva " + (k + 1));
                b.addEventListener("click", function () { stop(); show(k); });
                dots.appendChild(b);
            });
            function steps(sl) {
                return sl.querySelectorAll(".cp-sl-cards li, .cp-sl-steps li, .cp-sl-table tr + tr");
            }
            function reveal(frac) {
                var st = steps(slides[i]);
                var n = Math.min(st.length, Math.floor(frac * (st.length + 0.6)) + 1);
                st.forEach(function (li, k) { li.classList.toggle("cp-hidden", k >= n); });
            }
            function show(k) {
                i = Math.max(0, Math.min(slides.length - 1, k));
                slides.forEach(function (s, n) { s.classList.toggle("active", n === i); });
                dots.querySelectorAll("button").forEach(function (b, n) { b.classList.toggle("on", n === i); });
                steps(slides[i]).forEach(function (li) { li.classList.remove("cp-hidden"); });
                if (cap) { cap.textContent = slides[i].dataset.say || ""; }
            }
            function bestVoice() {
                if (!synth) { return null; }
                var vs = synth.getVoices().filter(function (v) { return /^es/i.test(v.lang); });
                var score = function (v) {
                    var s = 0;
                    if (/natural|neural|online|google|premium|enhanced/i.test(v.name)) { s += 10; }
                    if (/CO/.test(v.lang)) { s += 4; } else if (/419|MX|US/.test(v.lang)) { s += 3; }
                    if (v.localService === false) { s += 1; }
                    return s;
                };
                vs.sort(function (a, b) { return score(b) - score(a); });
                return vs[0] || null;
            }
            function audioFor(k) {
                if (!cache[k]) {
                    var a = new Audio(voiceUrl + k);
                    a.preload = "auto";
                    cache[k] = a;
                }
                return cache[k];
            }
            function next() {
                if (!playing) { return; }
                if (i < slides.length - 1) { timer = setTimeout(function () { show(i + 1); say(); }, 700); } else { stop(); }
            }
            function sayBrowser(text, my) {
                if (!(synth && window.SpeechSynthesisUtterance)) {
                    timer = setTimeout(next, Math.max(5000, text.length * 65));
                    return;
                }
                // Frase por frase: pausas naturales y sin el corte de Chrome en textos largos
                var parts = text.match(/[^.!?¿¡]+[.!?]*|[¿¡][^?!]+[?!]/g) || [text];
                var v = bestVoice(), done = 0, total = text.length || 1;
                var speakPart = function (k) {
                    if (!playing || my !== token) { return; }
                    if (k >= parts.length) { next(); return; }
                    var u = new SpeechSynthesisUtterance(parts[k].trim());
                    u.lang = v ? v.lang : "es-CO";
                    if (v) { u.voice = v; }
                    u.rate = 0.97;
                    u.pitch = 1;
                    u.onend = function () { done += parts[k].length; reveal(done / total); setTimeout(function () { speakPart(k + 1); }, 180); };
                    u.onerror = function () { speakPart(k + 1); };
                    synth.speak(u);
                };
                speakPart(0);
            }
            function say() {
                if (!playing) { return; }
                var my = ++token;
                var text = slides[i].dataset.say || "";
                reveal(0);
                if (serverOk) {
                    audio = audioFor(i);
                    audio.currentTime = 0;
                    audio.ontimeupdate = function () { if (audio.duration) { reveal(audio.currentTime / audio.duration); } };
                    audio.onended = function () { if (my === token) { reveal(1); next(); } };
                    audio.onerror = function () {
                        if (my !== token) { return; }
                        serverOk = false;  // el servicio de voz no respondió: voz del navegador
                        sayBrowser(text, my);
                    };
                    var pr = audio.play();
                    if (pr && pr.catch) { pr.catch(function () { if (my === token && playing) { serverOk = false; sayBrowser(text, my); } }); }
                    if (i + 1 < slides.length) { audioFor(i + 1); }
                } else {
                    sayBrowser(text, my);
                }
            }
            function stop() {
                playing = false;
                token++;
                clearTimeout(timer);
                if (audio) { audio.pause(); }
                if (synth) { synth.cancel(); }
                if (playBtn) { playBtn.innerHTML = playLabel; }
                steps(slides[i]).forEach(function (li) { li.classList.remove("cp-hidden"); });
            }
            if (playBtn) {
                playBtn.addEventListener("click", function () {
                    if (playing) { stop(); return; }
                    playing = true;
                    playBtn.textContent = "⏸ Pausar";
                    say();
                });
            }
            if (ccBtn && cap) {
                ccBtn.addEventListener("click", function () {
                    cap.hidden = !cap.hidden;
                    ccBtn.setAttribute("aria-pressed", cap.hidden ? "false" : "true");
                    ccBtn.classList.toggle("on", !cap.hidden);
                });
            }
            var fullBtn = deck.querySelector("[data-deck=full]");
            if (fullBtn) {
                fullBtn.addEventListener("click", function () {
                    if (document.fullscreenElement) { document.exitFullscreen(); }
                    else if (deck.requestFullscreen) { deck.requestFullscreen(); }
                });
            }
            deck.querySelector("[data-deck=prev]").addEventListener("click", function () { var was = playing; stop(); show(i - 1); if (was) { playBtn.click(); } });
            deck.querySelector("[data-deck=next]").addEventListener("click", function () { var was = playing; stop(); show(i + 1); if (was) { playBtn.click(); } });
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

        // Formularios con archivos que pueden parecer ataques (bancos GIFT, syllabus de
        // ciberseguridad): el archivo viaja en base64 y el servidor lo decodifica.
        document.querySelectorAll("form[data-cp-encode]").forEach(function (form) {
            form.addEventListener("submit", function (e) {
                if (form.dataset.cpEncoded === "1") { return; }
                var names = form.dataset.cpEncode.split(",");
                var inputs = names.map(function (n) { return form.querySelector('input[type=file][name="' + n.trim() + '"]'); })
                    .filter(function (i) { return i && i.files && i.files.length; });
                if (!inputs.length || typeof DataTransfer === "undefined" || typeof FileReader === "undefined") { return; }
                e.preventDefault();
                var btn = form.querySelector("button[type=submit]");
                if (btn) { btn.disabled = true; }
                Promise.all(inputs.map(function (input) {
                    // todos los archivos del campo (admite <input multiple>)
                    return Promise.all(Array.prototype.map.call(input.files, function (file) {
                        return new Promise(function (resolve, reject) {
                            var reader = new FileReader();
                            reader.onload = function () {
                                resolve(new File([String(reader.result).split(",")[1] || ""], file.name, { type: "text/plain" }));
                            };
                            reader.onerror = reject;
                            reader.readAsDataURL(file);
                        });
                    })).then(function (encoded) {
                        var dt = new DataTransfer();
                        encoded.forEach(function (f) { dt.items.add(f); });
                        input.files = dt.files;
                        var flag = document.createElement("input");
                        flag.type = "hidden"; flag.name = input.name + "_enc"; flag.value = "b64";
                        form.appendChild(flag);
                    });
                })).then(function () {
                    form.dataset.cpEncoded = "1";
                    form.submit();
                }).catch(function () { if (btn) { btn.disabled = false; } form.dataset.cpEncoded = "1"; form.submit(); });
            });
        });

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
                    // Se envía en base64: el firewall del hosting bloquea textos que parecen ataques
                    // (p. ej. una pregunta sobre inyección SQL en el curso de ciberseguridad).
                    body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { message_b64: b64text(text) } }),
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
