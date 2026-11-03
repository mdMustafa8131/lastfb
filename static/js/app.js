const toastBox = document.getElementById("toasts");

function toast(msg, bad) {
    const el = document.createElement("div");
    el.className = "toast" + (bad ? " bad" : "");
    el.textContent = msg;
    toastBox.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

async function post(url, body) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        toast(data.detail || "Kuch galat hua", true);
        throw new Error(data.detail || "error");
    }
    return data;
}

document.getElementById("disconnectBtn")?.addEventListener("click", async () => {
    if (!confirm("Disconnect karna hai?")) return;
    await post("/api/disconnect");
    location.reload();
});

document.getElementById("stopBtn")?.addEventListener("click", async () => {
    if (!confirm("Server band karna hai?")) return;
    try { await post("/api/shutdown"); } catch { }
    document.body.innerHTML =
        '<div style="font-family:system-ui;padding:40px;text-align:center">' +
        "<h2>Server band ho gaya</h2><p>Dobara chalane ke liye: python app.py</p></div>";
});

document.getElementById("connectForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = e.target.querySelector("button");
    btn.disabled = true;
    try {
        const r = await post("/api/connect", {
            app_id: f.get("app_id"),
            app_secret: f.get("app_secret"),
            user_token: f.get("user_token"),
        });
        toast(r.pages + " pages mile");
        location.reload();
    } finally {
        btn.disabled = false;
    }
});

document.getElementById("syncBtn")?.addEventListener("click", async () => {
    try {
        const r = await post("/api/sync");
        toast(r.pages + " pages sync");
        location.reload();
    } catch { }
});

document.getElementById("dryRunBtn")?.addEventListener("click", async () => {
    const on = !document.getElementById("dryRunBtn").textContent.includes("ON");
    await post("/api/dryrun", { on });
    location.reload();
});

document.querySelectorAll("[data-open]").forEach((el) => {
    el.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        location.href = "/page/" + el.dataset.open;
    });
});

if (window.PAGE_ID) {
    const id = window.PAGE_ID;

    const refreshReady = async () => {
        const grid = document.getElementById("readyGrid");
        const info = document.getElementById("poolInfo");
        if (!grid) return;
        try {
            const r = await fetch(`/api/pages/${id}/ready`).then((x) => x.json());
            grid.innerHTML = r.urls
                .map((u) => `<img src="${u}" alt="preview" loading="lazy">`)
                .join("");
            if (info) info.textContent = `Buffer: ${r.count} · pool me bache: ${r.remaining}`;
        } catch { }
    };

    document.querySelectorAll("[data-sec]").forEach((b) => b.addEventListener("click", async () => {
        await post(`/api/pages/${id}/section`, { section: b.dataset.sec });
        location.reload();
    }));

    document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", async () => {
        const on = !b.classList.contains("on");
        await post(`/api/pages/${id}/lang`, { lang: b.dataset.lang, on });
        b.classList.toggle("on", on);
    }));

    document.querySelectorAll("[data-bg]").forEach((b) => b.addEventListener("click", async () => {
        await post(`/api/pages/${id}/bgmode`, { mode: b.dataset.bg });
        document.querySelectorAll("[data-bg]").forEach((x) => x.classList.toggle("on", x === b));
    }));

    document.querySelectorAll("[data-sent]").forEach((b) => b.addEventListener("click", async () => {
        await post(`/api/pages/${id}/sentences`, { sentences: Number(b.dataset.sent) });
        document.querySelectorAll("[data-sent]").forEach((x) => x.classList.toggle("on", x === b));
    }));

    document.getElementById("questionToggle")?.addEventListener("change", (e) =>
        post(`/api/pages/${id}/question`, { on: e.target.checked }));

    document.getElementById("sourceColor")?.addEventListener("change", (e) =>
        post(`/api/pages/${id}/sourcecolor`, { color: e.target.value }));

    document.getElementById("brandSave")?.addEventListener("click", async () => {
        await post(`/api/pages/${id}/brand`, {
            brand: document.getElementById("brandInput").value,
        });
        toast("Handle save ho gaya");
    });

    document.getElementById("logoForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        await fetch(`/api/pages/${id}/logo`, { method: "POST", body: new FormData(e.target) });
        toast("Logo save ho gaya");
        location.reload();
    });

    document.getElementById("logoClear")?.addEventListener("click", async () => {
        await fetch(`/api/pages/${id}/logo`, { method: "POST", body: new FormData() });
        toast("Logo hata diya");
        location.reload();
    });

    document.getElementById("scheduleForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        await post(`/api/pages/${id}/schedule`, {
            day: {
                start: f.get("day_start"), end: f.get("day_end"),
                min: Number(f.get("day_min")), max: Number(f.get("day_max")),
            },
            night: {
                start: f.get("night_start"), end: f.get("night_end"),
                min: Number(f.get("night_min")), max: Number(f.get("night_max")),
            },
        });
        toast("Timing save");
    });

    document.getElementById("enableToggle")?.addEventListener("change", async (e) => {
        try {
            const r = await post(`/api/pages/${id}/toggle`, { on: e.target.checked });
            e.target.checked = r.enabled;
            toast(r.enabled ? "Auto posting ON" : "Auto posting OFF");
        } catch {
            e.target.checked = !e.target.checked;
        }
    });

    document.getElementById("previewBtn")?.addEventListener("click", async () => {
        try {
            await post(`/api/pages/${id}/preview`);
            toast("Image ban gayi");
        } catch { }
        refreshReady();
    });

    document.getElementById("refillBtn")?.addEventListener("click", async () => {
        const r = await post(`/api/pages/${id}/buffer`);
        toast(r.made + " image bani");
        refreshReady();
    });

    document.getElementById("clearBtn")?.addEventListener("click", async () => {
        if (!confirm("Bani hui images clear?")) return;
        await post(`/api/pages/${id}/clear`);
        toast("Images clear");
        refreshReady();
    });

    document.getElementById("purgePoolBtn")?.addEventListener("click", async () => {
        if (!confirm("Jo data use ho chuka hai wo delete?")) return;
        await post(`/api/pool/${document.querySelector("[data-sec].on")?.dataset.sec || ""}/purge`);
        toast("Used data delete");
        refreshReady();
    });

    document.getElementById("purgeUnusedBtn")?.addEventListener("click", async () => {
        if (!confirm("Jo data bacha hai (use nahi hua) wo delete ho jayega?")) return;
        await post(`/api/pages/${id}/purge-unused`);
        toast("Bache hue data delete");
        refreshReady();
    });

    document.getElementById("wipeBtn")?.addEventListener("click", async () => {
        if (!confirm("Us section ka poora data aur images clear?")) return;
        await post(`/api/pages/${id}/wipe`);
        toast("Sab clear ho gaya");
        refreshReady();
    });

    document.getElementById("captionBtn")?.addEventListener("click", async () => {
        const box = document.getElementById("captionBox");
        try {
            const r = await post(`/api/pages/${id}/caption`);
            box.textContent = r.caption;
        } catch {
            box.textContent = "";
        }
    });

    document.getElementById("postNowBtn")?.addEventListener("click", async () => {
        if (!confirm("Abhi post kar dena hai?")) return;
        try {
            const r = await post(`/api/pages/${id}/post-now`);
            toast(r.dry ? "Dry run: post simulate hua" : "Post ho gaya");
        } catch { }
        refreshReady();
    });

    document.getElementById("importForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = document.getElementById("importMsg");
        const res = await fetch(`/api/pages/${id}/import`, {
            method: "POST",
            body: new FormData(e.target),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            msg.textContent = data.detail || "Import fail";
            return;
        }
        msg.textContent = `${data.added} entries add hui` +
            (data.errors?.length ? ` · ${data.errors.length} errors` : "");
        e.target.reset();
        refreshReady();
    });

    // ---------- news ----------
    document.querySelectorAll("[data-news-mode]").forEach((b) => b.addEventListener("click", async () => {
        await post(`/api/pages/${id}/news`, { mode: b.dataset.newsMode });
        document.querySelectorAll("[data-news-mode]").forEach((x) =>
            x.classList.toggle("on", x === b));
    }));

    document.getElementById("newsRegion")?.addEventListener("change", (e) =>
        post(`/api/pages/${id}/news`, { region: e.target.value }));
    document.getElementById("newsTpl")?.addEventListener("change", (e) =>
        post(`/api/pages/${id}/news`, { tpl: Number(e.target.value) }));
    document.getElementById("newsCat")?.addEventListener("change", (e) =>
        post(`/api/pages/${id}/news`, { category: e.target.value }));
    document.getElementById("newsSub")?.addEventListener("change", (e) =>
        post(`/api/pages/${id}/news`, { sub: e.target.value.trim() }));

    document.getElementById("newsFetchBtn")?.addEventListener("click", async () => {
        const msg = document.getElementById("newsMsg");
        const mode = document.querySelector("[data-news-mode].on")?.dataset.newsMode || "auto";
        msg.textContent = "chal raha hai…";
        try {
            const r = await post("/api/news/fetch", {
                mode,
                region: document.getElementById("newsRegion")?.value || "in",
                sub: document.getElementById("newsSub")?.value.trim() || "worldnews",
                category: document.getElementById("newsCat")?.value || null,
                page_id: id,
                limit: 5,
            });
            msg.textContent =
                `tags: ${(r.tags || []).join(", ")}\n` +
                `keywords: ${(r.keywords || []).join(", ")}\n` +
                `${r.added} news · ${r.made} image · pool: ${r.remaining}\n` +
                `top: ${r.top || "—"}`;
            msg.style.whiteSpace = "pre-wrap";
            refreshReady();
        } catch (e) {
            msg.textContent = "fail: " + e.message;
        }
    });
    document.getElementById("newsCatAddBtn")?.addEventListener("click", async () => {
        const name = prompt("Category ka naam?");
        if (!name) return;
        const kw = prompt("Keywords (comma se alag karo)");
        if (!kw) return;
        await post("/api/news/categories", { name, keywords: kw });
        location.reload();
    });

    document.getElementById("newsCatDelBtn")?.addEventListener("click", async () => {
        const cat = document.getElementById("newsCat")?.value;
        if (!cat) return toast("Pehle category select karo");
        if (!confirm("Category delete?")) return;
        await fetch(`/api/news/categories/${cat}`, { method: "DELETE" });
        location.reload();
    });

    refreshReady();
    setInterval(refreshReady, 20000);

    // status poll
    setInterval(async () => {
        try {
            const s = await fetch("/api/state").then((r) => r.json());
            const me = s.pages.find((p) => p.id === id);
            if (!me) return;
            const st = document.getElementById("statusText");
            if (st) st.textContent = me.status;
            const nx = document.getElementById("nextText");
            if (nx) nx.textContent = me.next_post_at || "—";
        } catch { }
    }, 15000);
}