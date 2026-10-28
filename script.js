/* ============================================================
   Nathaniel — Runner's Log
   Reads data.json, renders training recap + race log + route + heatmap + elevation.
   ============================================================ */

const state = { data: null };

/* ---------- helpers ---------- */
function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;",
    }[c]));
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

function setTimeDisplay(id, timeStr) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!timeStr) { el.textContent = "—"; return; }
    const parts = timeStr.split(":");
    if (parts.length === 3) {
        el.innerHTML = `${escapeHtml(parts[0])}:${escapeHtml(parts[1])}<span class="ms">:${escapeHtml(parts[2])}</span>`;
    } else {
        el.textContent = timeStr;
    }
}

function shortMonth(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleDateString("id-ID", { month: "short" });
    } catch { return ""; }
}

function dayOfMonth(iso) {
    try {
        const d = new Date(iso);
        return String(d.getDate()).padStart(2, "0");
    } catch { return "—"; }
}

/* ---------- load ---------- */
async function loadData() {
    try {
        const res = await fetch("data.json", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        state.data = await res.json();
    } catch (err) {
        const list = document.getElementById("race-list");
        if (list) {
            list.innerHTML = `<li class="race-row"><p class="race-desc">
                Gagal memuat <code>data.json</code>: ${escapeHtml(err.message)}.<br>
                Jalankan <code>python tools/build_data.py</code> dulu, dan buka lewat server lokal (bukan file://).
            </p></li>`;
        }
        console.error(err);
        return;
    }

    renderTicker();
    renderHero();
    renderStats();
    renderChart();
    renderHeatmap();
    renderInsights();
    renderRecentRuns();
    renderRaces();
    renderRoute();
    renderElevation();
    initReveal();
}

/* ---------- ticker ---------- */
function renderTicker() {
    const track = document.getElementById("ticker-track");
    if (!track || !state.data) return;
    const s = state.data.summary || {};

    const items = [
        `${s.total_km?.toFixed(0) || 0} KM`,
        `${s.total_runs || 0} RUNS`,
        s.avg_pace && s.avg_pace !== "—" ? `AVG ${s.avg_pace}` : "",
        s.best_5k ? `5K PB ${s.best_5k.time}` : "",
        s.best_hm ? `HM PB ${s.best_hm.time}` : "",
        "Solo, ID",
    ].filter(Boolean);

    const html = items.map((t) => `<span>${escapeHtml(t)}</span><span class="sep">✳</span>`).join("");
    track.innerHTML = `<div class="ticker-group">${html}</div><div class="ticker-group">${html}</div>`;
}

/* ---------- hero card ---------- */
function renderHero() {
    if (!state.data) return;
    const s = state.data.summary || {};
    let featured = null;

    if (s.best_hm) {
        featured = {
            label: "Half Marathon · PB",
            flag: "21.1 KM",
            time: s.best_hm.time,
            meta: `${s.best_hm.name} · ${s.best_hm.date}`,
            splits: s.best_hm.splits || [],
        };
    } else if (s.best_5k) {
        featured = {
            label: "5K · PB", flag: "5.0 KM",
            time: s.best_5k.time, meta: s.best_5k.name, splits: [],
        };
    } else if (s.longest_run) {
        featured = {
            label: "Longest run",
            flag: `${s.longest_run.distance_km.toFixed(1)} KM`,
            time: s.longest_run.time,
            meta: `${s.longest_run.name} · ${s.longest_run.date}`,
            splits: [],
        };
    }

    if (!featured) {
        document.getElementById("pb-wrap")?.style.setProperty("display", "none");
        return;
    }

    setText("pb-label", featured.label);
    setText("pb-flag", featured.flag);
    setTimeDisplay("pb-time", featured.time);
    setText("pb-meta", featured.meta);

    const splitEl = document.getElementById("pb-split");
    const splitLabelEl = document.getElementById("pb-split-label");
    if (splitEl) {
        if (featured.splits.length) {
            const paces = featured.splits.filter((p) => p > 0);
            const minPace = Math.min(...paces);
            splitEl.innerHTML = paces
                .map((p) => `<span style="height:${Math.round((minPace / p) * 100)}%"></span>`)
                .join("");
            if (splitLabelEl) splitLabelEl.style.display = "";
        } else {
            splitEl.innerHTML = "";
            if (splitLabelEl) splitLabelEl.style.display = "none";
        }
    }

    setText("pb-5k-val", s.best_5k ? s.best_5k.time : "—");
    setText("pb-10k-val", s.best_10k ? s.best_10k.time : "—");
}

/* ---------- stats ---------- */
function renderStats() {
    if (!state.data) return;
    const s = state.data.summary || {};
    setText("stat-runs", String(s.total_runs || 0).padStart(2, "0"));
    setHtml("stat-km", `${(s.total_km || 0).toFixed(1)}<small> km</small>`);
    setText("stat-pace", s.avg_pace || "—");
    setText("stat-races", String(s.total_races || 0).padStart(2, "0"));
}

/* ---------- monthly volume chart ---------- */
function renderChart() {
    const el = document.getElementById("volume-chart");
    if (!el || !state.data) return;

    const all = state.data.monthly || [];
    const last12 = all.slice(-12);
    const maxKm = Math.max(...last12.map((m) => m.km), 1);

    el.innerHTML = last12.map((m) => {
        const h = m.km > 0 ? Math.max(3, Math.round((m.km / maxKm) * 100)) : 2;
        const label = m.km > 0 ? `${m.km} km` : "—";
        return `
            <div class="vcol" title="${escapeHtml(m.label)} · ${escapeHtml(label)}">
                <div class="vbar-track">
                    <div class="vbar" style="height:${h}%">
                        <span class="vval">${escapeHtml(label)}</span>
                    </div>
                </div>
                <span class="vlbl">${escapeHtml(m.abbr || m.month)}</span>
            </div>`;
    }).join("");

    setText("chart-range", last12.length < 12 ? `${last12.length} bulan` : "12 bulan terakhir");
}

/* ---------- heatmap ---------- */
function renderHeatmap() {
    if (!state.data || !state.data.heatmap) return;
    const h = state.data.heatmap;
    const grid = document.getElementById("heatmap-grid");
    const monthsEl = document.getElementById("heatmap-months");
    const daysEl = document.getElementById("heatmap-days");
    const noteEl = document.getElementById("heatmap-note");

    if (!grid || !monthsEl || !daysEl) return;

    const days = h.days;
    if (!days || !days.length) return;

    // thresholds berdasarkan data aktual
    const kms = days.filter((d) => d.km > 0).map((d) => d.km);
    const maxKm = Math.max(...kms, 1);
    const t1 = maxKm * 0.15;
    const t2 = maxKm * 0.4;
    const t3 = maxKm * 0.7;

    const levelOf = (km) => {
        if (km <= 0) return 0;
        if (km < t1) return 1;
        if (km < t2) return 2;
        if (km < t3) return 3;
        return 4;
    };

    // day labels kiri (Mon, Wed, Fri)
    const dayLabels = ["", "Mon", "", "Wed", "", "Fri", ""];
    daysEl.innerHTML = dayLabels
        .map((lbl) => `<span class="heatmap-day-lbl">${lbl}</span>`)
        .join("");

    // cells
    grid.innerHTML = days.map((d) => {
        const lvl = levelOf(d.km);
        const title = d.km > 0
            ? `${d.date} · ${d.km} km (${d.runs} run${d.runs > 1 ? "s" : ""})`
            : `${d.date} · no run`;
        return `<div class="heatmap-cell" data-level="${lvl}" title="${escapeHtml(title)}"></div>`;
    }).join("");

    // month labels (start position per bulan)
    const weeks = Math.ceil(days.length / 7);
    const monthSpans = [];
    let currentMonth = null;
    let currentSpan = 0;

    for (let w = 0; w < weeks; w++) {
        const dateStr = days[w * 7]?.date;
        const month = dateStr ? dateStr.substring(0, 7) : null;
        if (month && month !== currentMonth) {
            if (currentMonth && currentSpan > 0) {
                monthSpans.push({ month: currentMonth, span: currentSpan });
            }
            currentMonth = month;
            currentSpan = 1;
        } else {
            currentSpan++;
        }
    }
    if (currentMonth && currentSpan > 0) {
        monthSpans.push({ month: currentMonth, span: currentSpan });
    }

    monthsEl.innerHTML = monthSpans.map(({ month, span }) => {
        const d = new Date(month + "-01");
        const label = d.toLocaleDateString("id-ID", { month: "short" });
        return `<span style="flex:0 0 ${span * 14}px;white-space:nowrap;">${escapeHtml(label)}</span>`;
    }).join("");

    if (noteEl) {
        noteEl.textContent = `${h.total_runs} runs · ${h.total_km} km`;
    }
}

/* ---------- insights ---------- */
function renderInsights() {
    if (!state.data) return;
    const s = state.data.summary || {};

    setText("insight-time", s.total_time || "—");
    setHtml("insight-avg-week", `${s.avg_runs_per_week ?? "—"}<small> runs</small>`);

    if (s.best_week) {
        setHtml("insight-best-week", `${s.best_week.km.toFixed(1)}<small> km</small>`);
        setText("insight-best-week-date", s.best_week.label);
    } else {
        setText("insight-best-week", "—");
        setText("insight-best-week-date", "");
    }

    if (s.most_active_month) {
        setHtml("insight-best-month", `${s.most_active_month.km.toFixed(1)}<small> km</small>`);
        setText("insight-best-month-label", s.most_active_month.label);
    } else {
        setText("insight-best-month", "—");
        setText("insight-best-month-label", "");
    }
}

/* ---------- recent runs ---------- */
function renderRecentRuns() {
    const el = document.getElementById("recent-runs-list");
    if (!el || !state.data) return;

    const runs = state.data.recent_runs || [];
    if (!runs.length) {
        el.innerHTML = `<p style="color:var(--ink-faint);padding:1rem 0">Belum ada run.</p>`;
        return;
    }

    el.innerHTML = runs.map((r) => {
        const tag = r.is_race ? '<span class="run-tag">Race</span>' : "";
        const dateStr = r.iso_date || "";
        return `
            <div class="run-item">
                <div class="run-date">
                    <span class="run-day">${escapeHtml(dayOfMonth(dateStr))}</span>
                    <span class="run-month">${escapeHtml(shortMonth(dateStr))}</span>
                </div>
                <div class="run-main">
                    <h4>${escapeHtml(r.name)}${tag}</h4>
                    <p>${escapeHtml(r.category)} · <span>${escapeHtml(r.distance_km.toFixed(1))} km</span> · <span>${escapeHtml(r.pace)} /km</span></p>
                </div>
                <span style="font-family:var(--font-serif);font-size:1rem;color:var(--ink-soft)">${escapeHtml(r.time)}</span>
            </div>`;
    }).join("");
}

/* ---------- races ---------- */
function renderRaces() {
    const list = document.getElementById("race-list");
    if (!list || !state.data) return;

    const races = state.data.races || [];
    if (!races.length) {
        list.innerHTML = `<li class="race-row"><p class="race-desc">Belum ada race di data.json.</p></li>`;
        return;
    }

    list.innerHTML = races.map((race, i) => {
        const index = String(i + 1).padStart(2, "0");
        const pbChip = race.pb ? '<span class="chip chip-pb">PB</span>' : "";
        const meta = [race.location, race.date].filter(Boolean).join(" · ");

        return `
            <li class="race-row reveal" style="--d:${Math.min(i * 70, 280)}ms">
                <div class="race-index" aria-hidden="true">${index}</div>
                <div class="race-main">
                    <div class="race-tags">
                        <span class="chip">${escapeHtml(race.category)}</span>
                        <span class="chip chip-muted">${escapeHtml(race.badge)}</span>
                        ${pbChip}
                    </div>
                    <h3 class="race-name">${escapeHtml(race.name)}</h3>
                    <p class="race-loc">${escapeHtml(meta)}</p>
                    <p class="race-desc">${escapeHtml(race.description)}</p>
                </div>
                <div class="race-times">
                    <div class="t">
                        <span class="t-val">${escapeHtml(race.time)}</span>
                        <span class="t-lbl">Finish</span>
                    </div>
                    <div class="t">
                        <span class="t-val">${escapeHtml(race.pace)}</span>
                        <span class="t-lbl">Pace /km</span>
                    </div>
                </div>
            </li>`;
    }).join("");
}

/* ---------- route map ---------- */
function renderRoute() {
    if (!state.data) return;
    const s = state.data.summary || {};

    let target = null;
    if (s.best_hm && s.best_hm.route && s.best_hm.route.length) {
        target = { route: s.best_hm.route, label: s.best_hm.name, run: s.best_hm };
    } else if (s.longest_run && s.longest_run.route && s.longest_run.route.length) {
        target = { route: s.longest_run.route, label: s.longest_run.name, run: s.longest_run };
    }

    if (!target) {
        const grid = document.querySelector(".route-grid");
        if (grid) grid.style.display = "none";
        return;
    }

    initMap(target.route, target.label);
    setText("route-distance", `${target.run.distance_km || "—"} km`);
    setText("route-time", target.run.time || "—");
    setText("route-pace", `${target.run.pace || "—"} /km`);
    setText("route-date", target.run.date || "—");
    setText("route-name", target.run.name || "—");
}

function initMap(route, label) {
    const mapEl = document.getElementById("map");
    if (!mapEl || typeof L === "undefined") return;

    if (window._routeMap) window._routeMap.remove();

    const map = L.map(mapEl, { scrollWheelZoom: false, zoomControl: true, attributionControl: true });
    window._routeMap = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
    }).addTo(map);

    const line = L.polyline(route, {
        color: "#b8452f",
        weight: 3.5,
        opacity: 0.9,
        lineJoin: "round",
        lineCap: "round",
    }).addTo(map);

    L.circleMarker(route[0], {
        radius: 7, color: "#f3efe6", weight: 3,
        fillColor: "#b8452f", fillOpacity: 1,
    }).addTo(map).bindTooltip(label ? `Start · ${label}` : "Start / Finish");

    map.fitBounds(line.getBounds(), { padding: [28, 28] });
    setTimeout(() => map.invalidateSize(), 300);
    window.addEventListener("resize", () => map.invalidateSize(), { once: true });
}

/* ---------- elevation ---------- */
function renderElevation() {
    const block = document.getElementById("elevation-block");
    if (!block || !state.data) return;

    const s = state.data.summary || {};

    let target = null;
    if (s.best_hm && s.best_hm.elevation && s.best_hm.elevation.profile) {
        target = {
            name: s.best_hm.name,
            distance: s.best_hm.distance_km,
            ...s.best_hm.elevation,
        };
    } else if (s.longest_run && s.longest_run.elevation && s.longest_run.elevation.profile) {
        target = {
            name: s.longest_run.name,
            distance: s.longest_run.distance_km,
            ...s.longest_run.elevation,
        };
    }

    if (!target || !target.profile || target.profile.length < 2) {
        block.style.display = "none";
        return;
    }

    setText("elevation-note", target.name || "—");
    setHtml("elev-min", `${target.min}<small> m</small>`);
    setHtml("elev-max", `${target.max}<small> m</small>`);
    setHtml("elev-gain", `${target.gain}<small> m</small>`);
    setHtml("elev-distance", `${(target.distance || 0).toFixed(1)}<small> km</small>`);

    const container = document.getElementById("elevation-chart");
    if (!container) return;

    const accentColor = getComputedStyle(document.documentElement)
        .getPropertyValue("--accent").trim() || "#b8452f";

    const profile = target.profile;
    const W = 1000;
    const H = 140;
    const pad = 6;

    const minV = Math.min(...profile);
    const maxV = Math.max(...profile);
    const range = Math.max(maxV - minV, 1);

    const pts = profile.map((v, i) => {
        const x = (i / (profile.length - 1)) * (W - pad * 2) + pad;
        const y = H - pad - ((v - minV) / range) * (H - pad * 2);
        return [x, y];
    });

    const linePath = pts
        .map((p, i) => (i === 0 ? `M${p[0].toFixed(1)},${p[1].toFixed(1)}` : `L${p[0].toFixed(1)},${p[1].toFixed(1)}`))
        .join(" ");
    const areaPath = `${linePath} L${pts[pts.length - 1][0].toFixed(1)},${H - pad} L${pts[0][0].toFixed(1)},${H - pad} Z`;

    container.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="elev-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="${accentColor}" stop-opacity="0.32"/>
                    <stop offset="100%" stop-color="${accentColor}" stop-opacity="0.02"/>
                </linearGradient>
            </defs>
            <path d="${areaPath}" fill="url(#elev-grad)"/>
            <path d="${linePath}" fill="none" stroke="${accentColor}" stroke-width="1.5"
                  stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
        </svg>
    `;
}

/* ---------- scroll progress ---------- */
(function initProgress() {
    const bar = document.getElementById("progress");
    if (!bar) return;
    let ticking = false;
    const update = () => {
        const doc = document.documentElement;
        const max = doc.scrollHeight - doc.clientHeight;
        bar.style.transform = `scaleX(${max > 0 ? doc.scrollTop / max : 0})`;
        ticking = false;
    };
    window.addEventListener("scroll", () => {
        if (!ticking) { window.requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    update();
})();

/* ---------- reveal ---------- */
function initReveal() {
    const items = document.querySelectorAll(".reveal:not(.is-visible)");
    if (!items.length) return;
    if (!("IntersectionObserver" in window)) {
        items.forEach((el) => el.classList.add("is-visible"));
        return;
    }
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
        });
    }, { threshold: 0.12, rootMargin: "0px 0px -60px 0px" });
    items.forEach((el) => observer.observe(el));
}

/* ---------- tilt ---------- */
(function initTilt() {
    const wrap = document.querySelector(".pb-wrap");
    const card = document.querySelector("[data-tilt]");
    if (!wrap || !card) return;
    const canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!canHover || reduced) return;
    const MAX = 7;
    wrap.addEventListener("mousemove", (event) => {
        const rect = wrap.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        card.style.transform = `rotateY(${(x * MAX).toFixed(2)}deg) rotateX(${(-y * MAX).toFixed(2)}deg)`;
        card.style.setProperty("--mx", `${((x + 0.5) * 100).toFixed(1)}%`);
        card.style.setProperty("--my", `${((y + 0.5) * 100).toFixed(1)}%`);
    });
    wrap.addEventListener("mouseleave", () => { card.style.transform = ""; });
})();

/* ---------- boot ---------- */
document.addEventListener("DOMContentLoaded", loadData);