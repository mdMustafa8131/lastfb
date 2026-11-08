(() => {
    const id = window.PAGE_ID;
    if (!id) return;
    const card = document.getElementById("reelCard");
    const fcard = document.getElementById("folderCard");
    const info = document.getElementById("reelInfo");
    const toggle = document.getElementById("reelToggle");
    if (!card) return;

    fetch(`/api/pages/${id}/state`).then((x) => x.json()).then((s) => {
        if (s.section !== "islam" && s.section !== "english") return;
        card.style.display = "";
        fcard.style.display = "";
        window.SEC = s.section;

        const vcard = document.getElementById("voiceCard");
        if (vcard) {
            vcard.style.display = "";
            const vt = document.getElementById("voiceToggle");
            const vg = document.getElementById("voiceGender");
            const vr = document.getElementById("voiceRate");
            const vrVal = document.getElementById("voiceRateVal");
            const ht = document.getElementById("hlToggle");
            const lt = document.getElementById("lineToggle");
            const ul = document.getElementById("ulToggle");
            const ulBox = document.getElementById("ulBox");
            const ulKeys = [["En", "en"], ["Bn", "bn"], ["Hi", "hi"]];
            const ulStyle = document.getElementById("ulStyle");
            const ulAlpha = document.getElementById("ulAlpha");
            const ulAlphaVal = document.getElementById("ulAlphaVal");
            const post = (path, body) => fetch(`/api/pages/${id}/${path}`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const ulSend = (body) => post("ul", body);

            vt.checked = !!s.voice_on;
            vg.value = s.voice_gender || "female";
            vr.value = s.voice_rate === undefined ? -6 : s.voice_rate;
            vrVal.textContent = vr.value;
            ht.checked = s.hl_on !== false;
            lt.checked = s.line_on !== false;

            const syncUl = () => {
                ul.checked = !!s.ul_on;
                ul.disabled = !vt.checked;
                ulBox.style.display = (ul.checked && vt.checked) ? "" : "none";
                ulStyle.querySelectorAll("[data-style]").forEach((b) =>
                    b.classList.toggle("on", b.dataset.style === (s.ul_style || "underline")));
                ulAlpha.value = s.ul_alpha || 38;
                ulAlphaVal.textContent = ulAlpha.value;
                for (const [n, k] of ulKeys) {
                    document.getElementById("ulColor" + n).value = (s.ul_color || {})[k] || "#FFD400";
                    document.getElementById("ulPx" + n).value = (s.ul_px || {})[k] || 6;
                }
            };
            syncUl();

            vt.addEventListener("change", async () => {
                await post("voice", { on: vt.checked });
                ul.disabled = !vt.checked;
                ulBox.style.display = (vt.checked && ul.checked) ? "" : "none";
            });
            vg.addEventListener("change", () => post("voicegender", { gender: vg.value }));
            vr.addEventListener("input", () => { vrVal.textContent = vr.value; });
            vr.addEventListener("change", () => post("voicerate", { rate: Number(vr.value) }));
            ht.addEventListener("change", () => post("hl", { on: ht.checked }));
            lt.addEventListener("change", () => post("line", { on: lt.checked }));
            ul.addEventListener("change", async () => {
                ulBox.style.display = (ul.checked && vt.checked) ? "" : "none";
                await ulSend({ on: ul.checked });
            });
            ulStyle.querySelectorAll("[data-style]").forEach((b) =>
                b.addEventListener("click", async () => {
                    s.ul_style = b.dataset.style;
                    ulStyle.querySelectorAll("[data-style]").forEach((x) =>
                        x.classList.toggle("on", x === b));
                    await ulSend({ style: b.dataset.style });
                }));
            ulAlpha.addEventListener("input", () => { ulAlphaVal.textContent = ulAlpha.value; });
            ulAlpha.addEventListener("change", () => ulSend({ alpha: Number(ulAlpha.value) }));
            for (const [n, k] of ulKeys) {
                document.getElementById("ulColor" + n).addEventListener("change", (e) =>
                    ulSend({ ["color_" + k]: e.target.value }));
                document.getElementById("ulPx" + n).addEventListener("change", (e) =>
                    ulSend({ ["px_" + k]: Number(e.target.value) }));
            }
        }

        toggle.checked = !!s.reel;

        const mv = document.getElementById("musicVol");
        const mvVal = document.getElementById("musicVolVal");
        if (mv) {
            mv.value = s.music_vol === undefined ? 20 : s.music_vol;
            mvVal.textContent = mv.value;
            mv.addEventListener("input", () => { mvVal.textContent = mv.value; });
            mv.addEventListener("change", () => fetch(`/api/pages/${id}/musicvol`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vol: Number(mv.value) }),
            }));
        }

        const mrow = document.getElementById("reelMusicRow");
        const mtog = document.getElementById("reelMusic");
        if (s.section === "english" && mrow) {
            mrow.style.display = "";
            mtog.checked = s.reel_music !== false;
            mtog.addEventListener("change", async () => {
                const r = await fetch(`/api/pages/${id}/reelmusic`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ on: mtog.checked }),
                });
                if (!r.ok) mtog.checked = !mtog.checked;
            });
        }

        const MODES = s.section === "english"
            ? ["zoomout", "wave", "ripple"]
            : ["zoom", "zoomout", "pan", "wave", "warp", "ripple", "pulse", "rgb"];
        const box = document.getElementById("reelModes");
        box.innerHTML = MODES.map((m) =>
            `<button class="btn btn-sm${s.reel_mode === m ? " btn-primary" : ""}" data-mode="${m}">${m}</button>`).join("");
        box.querySelectorAll("[data-mode]").forEach((b) => {
            b.onclick = async () => {
                await fetch(`/api/pages/${id}/reelmode`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ mode: b.dataset.mode }),
                });
                box.querySelectorAll("[data-mode]").forEach((x) =>
                    x.classList.toggle("btn-primary", x === b));
            };
        });
        load();
    }).catch(() => { });

    async function load() {
        if (window.SEC === "english") {
            const sel = document.getElementById("fKindSel");
            sel.value = "music";
            [...sel.options].forEach((o) => { o.hidden = o.value !== "music"; });
        }
        const r = await fetch(`/api/media/${window.SEC}`).then((x) => x.json()).catch(() => null);
        if (!r) return;
        info.textContent = `music: ${r.music.reduce((a, c) => a + c.count, 0)} track · ${r.seconds}s video`;
        document.getElementById("fLoose").textContent =
            `folder ke bahar: ${r.loose_bg} photo · ${r.loose_music} music`;
        const kind = document.getElementById("fKindSel").value;
        const list = r[kind] || [];
        document.getElementById("fList").innerHTML = list.length
            ? list.map((c) => `<div class="rowbar-actions small"><span>${c.name} — ${c.count}</span>
          <button class="btn btn-sm" data-open="${c.name}">Files</button>
          <button class="btn btn-sm" data-del="${c.name}">Delete folder</button></div>`).join("")
            : `<p class="muted small">koi folder nahi</p>`;
        document.querySelectorAll("[data-del]").forEach((b) => {
            b.onclick = async () => {
                if (!confirm(`${b.dataset.del} folder delete?`)) return;
                await fetch(`/api/media/${window.SEC}/${kind}/folder/${encodeURIComponent(b.dataset.del)}`,
                    { method: "DELETE" });
                load();
            };
        });
        document.querySelectorAll("[data-open]").forEach((b) => {
            b.onclick = async () => {
                const cat = b.dataset.open;
                const r2 = await fetch(`/api/media/${window.SEC}/${kind}/${encodeURIComponent(cat)}/files`)
                    .then((x) => x.json()).catch(() => ({ files: [] }));
                document.getElementById("fFiles").innerHTML = r2.files.length
                    ? `<p class="small">${cat} ki files:</p>` + r2.files.map((f) =>
                        `<div class="rowbar-actions small"><span>${f}</span>
               <button class="btn btn-sm" data-rm="${f}" data-cat="${cat}">x</button></div>`).join("")
                    : `<p class="muted small">${cat} khali hai</p>`;
                document.querySelectorAll("[data-rm]").forEach((x) => {
                    x.onclick = async () => {
                        await fetch(`/api/media/${window.SEC}/${kind}/${encodeURIComponent(x.dataset.cat)}/file/${encodeURIComponent(x.dataset.rm)}`,
                            { method: "DELETE" });
                        b.click();
                        load();
                    };
                });
            };
        });
    }

    document.getElementById("fKindSel").onchange = load;

    toggle.addEventListener("change", async () => {
        const r = await fetch(`/api/pages/${id}/reel`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ on: toggle.checked }),
        });
        if (!r.ok) { toggle.checked = !toggle.checked; alert((await r.json()).detail || "Fail"); }
    });

    document.getElementById("fNew").onclick = async () => {
        const name = document.getElementById("fName").value.trim();
        if (!name) return alert("Naam do");
        const kind = document.getElementById("fKindSel").value;
        const r = await fetch(`/api/media/${window.SEC}/${kind}/folder`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
        });
        if (r.ok) { document.getElementById("fName").value = ""; load(); }
        else alert((await r.json()).detail || "Fail");
    };

    document.getElementById("fUp").onclick = async () => {
        const cat = document.getElementById("fCat").value.trim();
        const files = document.getElementById("fFile").files;
        if (!cat) return alert("Folder naam likho");
        if (!files.length) return alert("Files chuno");
        const kind = document.getElementById("fKindSel").value;
        for (const f of files) {
            const fd = new FormData();
            fd.append("file", f);
            await fetch(`/api/media/${window.SEC}/${kind}/${encodeURIComponent(cat)}/file`,
                { method: "POST", body: fd });
        }
        document.getElementById("fFile").value = "";
        load();
    };
})();