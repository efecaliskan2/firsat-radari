// Fırsat Radarı — arayüz
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = (url, body) => fetch(url, body === undefined ? {} : {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
}).then(r => r.json());

const CATS = [
  ["Tümü", null], ["Hackathon", "--c-hackathon"], ["Girişimcilik", "--c-girisim"],
  ["Eğitim", "--c-egitim"], ["Yarışma", "--c-yarisma"], ["Etkinlik", "--c-etkinlik"], ["Haber", "--c-haber"],
];
const CAT_VAR = Object.fromEntries(CATS.filter(c => c[1]));
const REGIONS = [["Türkiye", "Türkiye"], ["Yurt dışı", "Yurt dışı"], ["Tümü", "Tümü"]];
const MONTHS = ["oca", "şub", "mar", "nis", "may", "haz", "tem", "ağu", "eyl", "eki", "kas", "ara"];

let items = [], cat = "Tümü", region = "Türkiye", tab = "explore", wasRunning = false, loaded = false;

// ------------------------------------------------------------------ yardımcılar
const today = () => new Date(new Date().toDateString());
const daysLeft = iso => iso ? Math.round((new Date(iso) - today()) / 864e5) : null;
const catOf = i => i.kind === "event" ? i.category : "Haber";
const catColor = i => `var(${CAT_VAR[catOf(i)] || "--c-etkinlik"})`;
// Önemli tarih: son başvuru > henüz başlamadıysa başlangıç > bitiş
const keyDate = i => i.deadline || (i.start && daysLeft(i.start) >= 0 ? i.start : i.end || i.start);
const keyLabel = i => i.deadline ? "son başvuru" : i.kind !== "event" ? "yayın" : keyDate(i) === i.start ? "başlıyor" : "bitiyor";
// Son başvuru tarihi bilinmeyen duyuru: tarih sütunu yayın tarihini gösterir, bu yüzden ayrı görünmeli
const undated = i => i.kind !== "event" && !i.deadline;
const inRegion = i => region === "Tümü" || (i.region || "Yurt dışı") === region;
const active = i => i.status !== "hidden" && i.status !== "applied";
const fmtLong = iso => new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "long" });
const hash = s => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const initials = t => (t.replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/).filter(w => w.length > 1)
  .slice(0, 2).map(w => w[0]).join("") || "•").toLocaleUpperCase("tr");

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove("show"), 2200);
}

function media(i) {
  const mono = () => {
    const m = document.createElement("div");
    m.className = "mono";
    m.style.setProperty("--c", catColor(i));
    m.textContent = initials(i.org || i.title);
    return m;
  };
  if (!i.image) return mono();
  const img = new Image();
  img.alt = "";
  img.loading = "lazy";
  img.referrerPolicy = "no-referrer";
  img.src = i.image;
  img.onerror = () => img.replaceWith(mono());
  return img;
}

// ------------------------------------------------------------------ yükleme
async function load() {
  items = await api("/api/items");
  loaded = true;
  render();
}

function render() {
  const n = s => items.filter(i => i.status === s).length;
  $("#cSaved").textContent = n("saved") || "";
  $("#cApplied").textContent = n("applied") || "";
  if (tab === "explore") {
    renderHero();
    renderRegions();
    renderCats();
    renderTrack();
    renderExplore();
  }
  if (tab === "saved") renderRows($("#savedList"), sortByDate(items.filter(i => i.status === "saved")),
    ["Henüz takibe aldığın bir şey yok", "Bir fırsatın yanındaki yer imine bas; son güne 7, 3 ve 1 gün kala hatırlatırım."]);
  if (tab === "applied") renderRows($("#appliedList"), sortByDate(items.filter(i => i.status === "applied")),
    ["Burası şimdilik boş", "Başvurduğun fırsatları ✓ ile işaretle, hepsi burada birikir."]);
}

function pool() {        // bölge + min. puan + aktif (kategori/arama hariç)
  const min = +$("#minScore").value;
  return items.filter(i => active(i) && inRegion(i) && i.score >= min);
}

function visible() {
  const q = $("#q").value.trim().toLocaleLowerCase("tr");
  return pool()
    .filter(i => cat === "Tümü" || catOf(i) === cat)
    .filter(i => !$("#newOnly").checked || i.status === "new")
    .filter(i => !q || `${i.title} ${i.org} ${i.desc} ${i.location} ${i.source}`.toLocaleLowerCase("tr").includes(q));
}

const sortByDate = arr => [...arr].sort((a, b) => (keyDate(a) || "9999").localeCompare(keyDate(b) || "9999"));

// ------------------------------------------------------------------ hero
function renderHero() {
  const p = pool();
  const ev = p.filter(i => i.kind === "event");
  const week = ev.filter(i => { const d = daysLeft(keyDate(i)); return d !== null && d >= 0 && d <= 7; });
  const fresh = p.filter(i => i.status === "new").length;
  const where = region === "Tümü" ? "Her yerde" : region === "Türkiye" ? "Türkiye'de" : "Yurt dışında";

  $("#today").textContent = new Date().toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" }).toLocaleLowerCase("tr");
  $("#headline").innerHTML = !loaded ? "Radar ısınıyor…"
    : week.length ? `Bu hafta <mark>${week.length} başvuru</mark> kapanıyor.`
    : ev.length ? `Önünde <mark>${ev.length} açık fırsat</mark> var.`
    : "Şimdilik ufuk sakin.";

  const next = sortByDate(ev.filter(i => daysLeft(keyDate(i)) >= 0))[0];
  const lede = $("#lede");
  lede.textContent = loaded ? `${where} ${ev.length} açık fırsat ve ${p.length - ev.length} güncel duyuru var.` : "";
  if (next) {
    const d = daysLeft(keyDate(next));
    lede.textContent += ` En yakını “${next.title.replace(/ — YTÜ Startup House$/, "")}”: ${d === 0 ? "bugün" : d + " gün sonra"}.`;
  }

  const stats = [
    ["Açık fırsat", ev.length], ["Bu hafta biten", week.length, week.length > 0],
    ["Yeni", fresh], ["Takipte", items.filter(i => i.status === "saved").length],
  ];
  $("#stats").innerHTML = stats.map(([k, v, hot]) => `<div><dt>${k}</dt><dd class="${hot ? "hot" : ""}">${v}</dd></div>`).join("");
  drawRadar(ev);
}

function drawRadar(ev) {
  const svg = $("#radar");
  const R = d => 26 + 158 * Math.sqrt(Math.min(Math.max(d, 0), 45) / 45);
  const rings = [[3, "3g"], [7, "7g"], [14, "14g"], [30, "30g"]];
  let s = `<defs><linearGradient id="sw" gradientUnits="userSpaceOnUse" x1="0" y1="-184" x2="120" y2="-140">
      <stop offset="0" stop-color="#f0a646" stop-opacity=".32"/><stop offset="1" stop-color="#f0a646" stop-opacity="0"/></linearGradient></defs>`;
  s += `<circle class="ring r0" r="184"/>`;
  for (const [d, l] of rings) s += `<circle class="ring" r="${R(d)}"/><text class="rlbl" x="4" y="${-R(d) + 12}">${l}</text>`;
  s += `<line class="axis" x1="-184" y1="0" x2="184" y2="0"/><line class="axis" x1="0" y1="-184" x2="0" y2="184"/>`;
  s += `<g class="sweep"><path d="M0 0 L0 -184 A184 184 0 0 1 120 -139.5 Z" fill="url(#sw)"/><line x1="0" y1="0" x2="0" y2="-184" stroke="#f0a646" stroke-opacity=".55"/></g>`;

  const pts = [...ev].filter(i => daysLeft(keyDate(i)) >= 0).sort((a, b) => b.score - a.score).slice(0, 22);
  pts.forEach((i, k) => {
    const d = daysLeft(keyDate(i));
    const a = (hash(i.id) % 360) * Math.PI / 180;
    const r = R(d);
    const x = (Math.cos(a) * r).toFixed(1), y = (Math.sin(a) * r).toFixed(1);
    const size = 3 + i.score * .45;
    s += `<g class="blip ${i.status === "new" ? "new" : ""} ${i.score < 5 ? "other" : ""}" data-k="${k}" tabindex="0" transform="translate(${x} ${y})">
      <circle class="halo" r="${size * 2.2}"/><circle class="core" r="${size}"/></g>`;
  });
  s += `<circle class="center" r="3.5"/>`;
  svg.innerHTML = s;

  const tip = $("#tip"), wrap = $(".radar-wrap");
  $$(".blip", svg).forEach(g => {
    const i = pts[+g.dataset.k];
    const show = () => {
      const b = g.getBoundingClientRect(), w = wrap.getBoundingClientRect();
      const d = daysLeft(keyDate(i));
      tip.innerHTML = `<b></b><span></span>`;
      tip.firstChild.textContent = i.title;
      tip.lastChild.textContent = `${d === 0 ? "bugün" : d + " gün"} · ${keyLabel(i)} · ${i.score}/10`;
      tip.style.left = `${b.left - w.left + b.width / 2}px`;
      tip.style.top = `${b.top - w.top}px`;
      tip.hidden = false;
    };
    g.addEventListener("mouseenter", show);
    g.addEventListener("focus", show);
    g.addEventListener("mouseleave", () => tip.hidden = true);
    g.addEventListener("blur", () => tip.hidden = true);
    g.addEventListener("click", () => openItem(i));
    g.addEventListener("keydown", e => e.key === "Enter" && openItem(i));
  });
}

function renderRegions() {
  const box = $("#regions");
  box.innerHTML = "";
  const min = +$("#minScore").value;
  for (const [key, label] of REGIONS) {
    const cnt = items.filter(i => active(i) && i.score >= min && (key === "Tümü" || (i.region || "Yurt dışı") === key)).length;
    const b = document.createElement("button");
    b.className = key === region ? "on" : "";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", key === region);
    b.innerHTML = `${label}<i>${cnt}</i>`;
    b.onclick = () => {
      region = key;
      try { localStorage.setItem("region", key); } catch {}
      render();
    };
    box.append(b);
  }
}

function renderCats() {
  const box = $("#cats");
  box.innerHTML = "";
  const p = pool();
  for (const [c, v] of CATS) {
    const cnt = p.filter(i => c === "Tümü" || catOf(i) === c).length;
    const b = document.createElement("button");
    b.className = c === cat ? "on" : "";
    b.disabled = !cnt && c !== cat;
    b.setAttribute("role", "tab");
    b.innerHTML = `${v ? `<span class="dot" style="--c:var(${v})"></span>` : ""}${c}<i>${cnt}</i>`;
    b.onclick = () => { cat = c; render(); };
    box.append(b);
  }
}

function renderTrack() {
  const up = sortByDate(items.filter(i => i.status === "saved" && daysLeft(keyDate(i)) >= 0)).slice(0, 10);
  $("#deadlines").hidden = !up.length;
  const row = $("#trackRow");
  row.innerHTML = "";
  for (const i of up) {
    const d = daysLeft(keyDate(i));
    const b = document.createElement("button");
    b.className = "tick" + (d <= 3 ? " urgent" : "");
    b.innerHTML = `<span class="n">${d}<small>${d === 0 ? "bugün" : "gün"}</small></span><span class="t"></span>
      <span class="bar-p"><i style="width:${Math.max(6, 100 - Math.min(d, 30) / 30 * 100)}%"></i></span><span class="w"></span>`;
    $(".t", b).textContent = i.title;
    $(".w", b).textContent = `${keyLabel(i)} · ${fmtLong(keyDate(i))}`;
    b.onclick = () => openItem(i);
    row.append(b);
  }
}

function renderExplore() {
  let list = visible();
  const s = $("#sort").value;
  if (s === "date") list = sortByDate(list);
  if (s === "recent") list.sort((a, b) => b.first_seen.localeCompare(a.first_seen) || b.score - a.score);

  const hiddenLow = items.filter(i => active(i) && inRegion(i) && i.score < +$("#minScore").value).length;
  $("#summary").textContent = loaded ? `${list.length} sonuç` + (hiddenLow ? ` · ${hiddenLow} düşük puanlı gizli` : "") : "";

  const featBox = $("#featured");
  featBox.innerHTML = "";
  let rest = list;
  if (!$("#q").value.trim() && list.length > 4) {
    const top = list.filter(i => i.kind === "event").slice(0, 2);
    top.forEach(i => featBox.append(feat(i)));
    rest = list.filter(i => !top.includes(i));
  }
  renderRows($("#list"), rest, ["Bu filtrelerle bir şey çıkmadı",
    "Kategoriyi “Tümü” yap, uygunluk eşiğini düşür ya da başka bir kelime dene."]);
}

// ------------------------------------------------------------------ kartlar & satırlar
function renderRows(el, list, [h, p]) {
  el.innerHTML = "";
  if (!loaded) {
    el.innerHTML = Array.from({ length: 6 }, () =>
      `<li class="skel"><i class="dt"></i><i class="sq"></i><span><i style="width:60%"></i><i style="width:35%;margin-top:10px"></i></span></li>`).join("");
    return;
  }
  if (!list.length) {
    el.innerHTML = `<li class="empty"><svg viewBox="-60 -60 120 120"><circle r="56"/><circle r="36"/><circle r="16"/>
      <circle class="e-dot" cx="22" cy="-30" r="4"/></svg><h3></h3><p></p></li>`;
    $("h3", el).textContent = h;
    $("p", el).textContent = p;
    return;
  }
  const frag = document.createDocumentFragment();
  list.slice(0, 300).forEach((i, k) => frag.append(row(i, k)));
  el.append(frag);
}

function wire(el, i) {
  const set = async (st, msg) => {
    await api(`/api/items/${i.id}/status`, { status: st });
    i.status = st;
    if (msg) toast(msg);
    render();
  };
  $$(".title a, .btn-open", el).forEach(a => a.onclick = e => { e.preventDefault(); openItem(i); });
  const save = $(".a-save", el);
  if (save) {
    save.classList.toggle("on", i.status === "saved");
    save.title = i.status === "saved" ? "Takipten çıkar" : "Takibe al";
    save.onclick = () => i.status === "saved" ? set("seen", "Takipten çıkarıldı") : set("saved", "Takibe alındı · hatırlatacağım");
  }
  const ap = $(".a-applied", el);
  if (ap) {
    ap.classList.toggle("on", i.status === "applied");
    ap.onclick = () => i.status === "applied" ? set("saved", "Takibe geri alındı") : set("applied", "Başvurdum olarak işaretlendi");
  }
  const hide = $(".a-hide", el);
  if (hide) hide.onclick = () => set("hidden", "Gizlendi");
  const cal = $(".a-cal", el);
  if (cal) {
    if (!keyDate(i) || i.kind !== "event") cal.remove();
    else cal.onclick = () => { api(`/api/items/${i.id}/calendar`, {}); toast("Google Takvim açılıyor"); };
  }
}

function kicker(el, i) {
  const k = $(".kcat", el);
  k.textContent = i.kind === "page" ? "Program sayfası" : catOf(i);
  k.style.setProperty("--c", catColor(i));
  $(".ksrc", el).textContent = i.source;
  el.classList.toggle("is-new", i.status === "new");
}

function row(i, k) {
  const el = $("#rowT").content.firstElementChild.cloneNode(true);
  el.style.setProperty("--i", Math.min(k, 24));
  kicker(el, i);

  const kd = keyDate(i), d = daysLeft(kd), w = $(".when", el);
  if (kd) {
    const dt = new Date(kd);
    $(".d", el).textContent = dt.getDate();
    $(".m", el).textContent = MONTHS[dt.getMonth()];
    $(".lbl", el).textContent = undated(i) ? "yayın" : d === 0 ? "bugün" : d < 0 ? "geçti" : `${d} gün`;
    if (undated(i)) w.classList.add("pub");
    else if (d >= 0 && d <= 3) w.classList.add("urgent");
    else if (d >= 0 && d <= 7) w.classList.add("soon");
  } else {
    $(".d", el).textContent = "—";
    $(".lbl", el).textContent = "tarih yok";
    w.classList.add("none");
  }

  $(".thumb", el).append(media(i));
  $(".title a", el).textContent = i.title;
  $(".title a", el).href = i.url;
  $(".meta", el).textContent = [i.org, i.location, !undated(i) && kd ? `${keyLabel(i)} ${fmtLong(kd)}` : ""]
    .filter(Boolean).join("  ·  ");
  if (undated(i)) {
    const tag = document.createElement("span");
    tag.className = "warn";
    tag.textContent = "son başvuru tarihi belirtilmemiş · açıp kontrol et";
    $(".meta", el).append(tag);
  }
  $(".desc", el).textContent = i.desc;

  const sc = $(".score", el);
  $(".sf", sc).style.strokeDashoffset = 94.25 * (1 - i.score / 10);
  $("span", sc).textContent = i.score;
  if (i.score >= 6) sc.classList.add("hi");
  wire(el, i);
  return el;
}

function feat(i) {
  const el = $("#featT").content.firstElementChild.cloneNode(true);
  kicker(el, i);
  $(".feat-img", el).append(media(i));
  $(".title a", el).textContent = i.title;
  $(".title a", el).href = i.url;
  $(".meta", el).textContent = [i.org, i.location].filter(Boolean).join("  ·  ");
  const kd = keyDate(i), d = daysLeft(kd), c = $(".count", el);
  c.textContent = kd ? `${keyLabel(i)} · ${d === 0 ? "bugün" : d + " gün kaldı"}` : "tarih belirsiz";
  if (d !== null && d <= 3) c.classList.add("hot");
  el.addEventListener("pointermove", e => {
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  });
  wire(el, i);
  return el;
}

function openItem(i) {
  api(`/api/items/${i.id}/open`, {});
  if (i.status === "new") {
    api(`/api/items/${i.id}/status`, { status: "seen" });
    i.status = "seen";
    setTimeout(render, 300);
  }
}

// ------------------------------------------------------------------ durum & tarama
async function poll() {
  const s = await api("/api/status");
  const btn = $("#scanBtn");
  btn.disabled = s.running;
  btn.classList.toggle("busy", s.running);
  $("span", btn).textContent = s.running ? "Taranıyor" : "Şimdi tara";
  const lr = s.last_run ? new Date(s.last_run) : null;
  const ago = lr ? Math.round((Date.now() - lr) / 60000) : null;
  const when = ago === null ? "henüz taranmadı" : ago < 1 ? "az önce tarandı"
    : ago < 60 ? `${ago} dk önce tarandı` : `${Math.round(ago / 60)} sa önce tarandı`;
  const errs = Object.keys(s.errors || {}).length;
  const warn = s.offline ? "internet yok · birazdan yeniden denenecek" : errs ? `${errs} kaynağa ulaşılamadı` : "";
  $("#lastRun").innerHTML = `${when}${warn ? `<br><span class="err">${warn}</span>` : ""}`;
  $("#sErrors").innerHTML = "";
  if (s.offline) {
    const p = document.createElement("p");
    p.className = "err";
    p.textContent = "Son denemede internet bağlantısı yoktu (ya da tarama sırasında koptu). "
      + "Liste korunuyor; uygulama birkaç dakika içinde kendiliğinden yeniden tarayacak.";
    $("#sErrors").append(p);
  } else {
    for (const [k, v] of Object.entries(s.errors || {})) {
      const p = document.createElement("p");
      p.className = "err";
      p.textContent = `${k}: ${v}`;
      $("#sErrors").append(p);
    }
  }
  if (wasRunning && !s.running) {
    await load();
    toast(s.offline ? "İnternet yok · liste korunuyor, birazdan tekrar denenecek"
      : s.last_new ? `${s.last_new} yeni fırsat bulundu` : "Tarama bitti · yeni bir şey yok");
  }
  wasRunning = s.running;
}

$("#scanBtn").onclick = async () => { await api("/api/scan", {}); wasRunning = true; poll(); };
$("#seenAll").onclick = async () => { await api("/api/seen-all", {}); await load(); toast("Hepsi görüldü sayıldı"); };

// ------------------------------------------------------------------ sekmeler & filtreler
function go(t) {
  tab = t;
  $$("#tabs button").forEach(x => x.classList.toggle("on", x.dataset.tab === t));
  $$(".view").forEach(v => v.hidden = v.id !== t);
  window.scrollTo({ top: 0 });
  if (t === "settings") loadSettings(); else render();
}
$$("[data-tab]").forEach(b => b.addEventListener("click", e => { e.preventDefault(); go(b.dataset.tab); }));

for (const id of ["q", "newOnly", "sort", "minScore"]) {
  $("#" + id).addEventListener("input", () => {
    $("#minScoreV").textContent = $("#minScore").value;
    try { localStorage.setItem("filters", JSON.stringify({ minScore: $("#minScore").value, sort: $("#sort").value })); } catch {}
    render();
  });
}
try {
  const f = JSON.parse(localStorage.getItem("filters") || "{}");
  if (f.minScore) { $("#minScore").value = f.minScore; $("#minScoreV").textContent = f.minScore; }
  if (f.sort) $("#sort").value = f.sort;
  const r = localStorage.getItem("region");
  if (REGIONS.some(([k]) => k === r)) region = r;
} catch {}

// ------------------------------------------------------------------ ayarlar
async function loadSettings() {
  loadTg();
  const [cfg, st] = await Promise.all([api("/api/config"), api("/api/status")]);
  $("#sNotify").value = cfg.notify_min_score;
  $("#sHours").value = cfg.scan_hours;
  $("#sKeywords").value = (cfg.extra_keywords || []).join(", ");
  $("#sQueries").value = (cfg.extra_news_queries || []).join("\n");
  $("#sPages").value = (cfg.watch_pages || []).map(p => `${p.name} | ${p.url}`).join("\n");
  const box = $("#sSources");
  box.innerHTML = "";
  for (const s of st.sources) {
    const l = document.createElement("label");
    l.className = "switch";
    l.innerHTML = `<input type="checkbox"><i></i><span></span>`;
    $("span", l).textContent = s;
    $("input", l).checked = !(cfg.disabled_sources || []).includes(s);
    $("input", l).dataset.s = s;
    box.append(l);
  }
}

function showTg(t) {
  const el = $("#tgState");
  const ok = t.has_token && t.chat_id;
  el.className = "tg-state" + (ok ? " ok" : "");
  el.textContent = !t.has_token ? "Bağlı değil" : !t.chat_id ? "Token var · bota /start yaz" : "Telefonuna bağlı";
  $("#tgOn").checked = t.enabled !== false;
}
async function loadTg() { showTg(await api("/api/telegram")); }
$("#tgSave").onclick = async () => {
  const r = await api("/api/telegram", { token: $("#tgToken").value, enabled: $("#tgOn").checked });
  $("#tgToken").value = "";
  $("#tgMsg").textContent = r.msg || "";
  if (r.info) showTg(r.info);
};
$("#tgTest").onclick = async () => {
  const r = await api("/api/telegram/test", {});
  $("#tgMsg").textContent = r.ok ? "Gönderildi, telefonuna bak." : "Gönderilemedi: token ya da sohbet eksik.";
};

$("#saveSettings").onclick = async () => {
  const body = {
    notify_min_score: +$("#sNotify").value || 5,
    scan_hours: +$("#sHours").value || 4,
    disabled_sources: $$("#sSources input").filter(x => !x.checked).map(x => x.dataset.s),
    extra_keywords: $("#sKeywords").value.split(",").map(s => s.trim()).filter(Boolean),
    extra_news_queries: $("#sQueries").value.split("\n").map(s => s.trim()).filter(Boolean),
    watch_pages: $("#sPages").value.split("\n").map(l => l.split("|").map(s => s.trim()))
      .filter(p => p.length >= 2 && p[1]).map(([name, url]) => ({ name, url })),
  };
  await api("/api/config", body);
  toast("Ayarlar kaydedildi · bir sonraki taramada geçerli");
};

render();
load();
poll();
setInterval(poll, 3000);
