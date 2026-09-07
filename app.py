"""SocPublic — веб-форма создания заданий. Деплой на Railway."""

import json
import os
import re
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

SP_API_URL = "https://socpublic.com/api"
SP_API_ID  = os.environ.get("SP_API_ID",  "244")
SP_API_KEY = os.environ.get("SP_API_KEY", "48A8B0D6-296D-6FC0-94B3-A9500751A704")
PASSWORD   = os.environ.get("APP_PASSWORD", "")
PORT       = int(os.environ.get("PORT", "8080"))
COMMISSION = 1.3
STORE = os.environ.get("TASK_STORE", "created_tasks.json")


def store_load():
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def store_add(task_id, name):
    try:
        rows = store_load()
        if not any(r.get("id") == str(task_id) for r in rows):
            rows.append({"id": str(task_id), "name": name})
            with open(STORE, "w", encoding="utf-8") as f:
                json.dump(rows[-3000:], f, ensure_ascii=False)
    except Exception:
        pass

NETWORKS = ["Facebook", "Twitter", "LinkedIn", "Pinterest", "Threads", "Tumblr",
            "Vk.com", "Ok.ru", "Dzen.ru", "Livejournal", "Blogger", "Vseti.by"]


TEMPLATES = {
    "share": {
        "label": "Поделиться ссылкой",
        "title": "Поделиться в {network} {keyword}",
        "approve": "<strong>7 ссылок на посты.</strong>",
    },
    "seosp": {
        "label": "SeoSp",
        "title": "Поделиться в {network} {keyword}",
        "approve": "<strong>Ссылки на 7 репостов.</strong>",
    },
}


def build_description(url, network, template):
    if template == "seosp":
        return (
            "<p><strong>1. Поделиться ссылкой и 6 постами из канала "
            "с нативным текстом и хештегами</strong> "
            "(можно скопировать из страниц или сгенерировать в Gemini)</p>"
            f'<p><a href="{url}">{url}</a></p>'
            "<p><strong>2. Подписаться, поставить пару реакций на посты</strong></p>"
            f"<p>Платформа: <strong>{network}</strong></p>"
        )
    return (
        "<p><strong>Поделиться ссылкой 7 раз с нативным текстом "
        "и хештегами и с фоткой</strong></p>"
        f'<p><a href="{url}">{url}</a></p>'
        "<p>Тексты разные для каждого репоста.</p>"
        "<p>Фото берем из сайта.</p>"
        f"<p>Платформа: <strong>{network}</strong></p>"
    )


def create_task(url, keyword, network, price_user, quantity, template="share", custom=None, stub=False):
    def fill(text):
        return (text or "").replace("{network}", network) \
                           .replace("{keyword}", keyword) \
                           .replace("{url}", url)

    BLOCK_TAG = re.compile(r"^\s*<(p|div|ul|ol|li|h[1-6]|table|blockquote|pre)\b", re.I)

    def to_html(text):
        """Каждый абзац размечаем отдельно: готовый HTML не трогаем,
        обычный текст оборачиваем и сохраняем переносы строк."""
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        if not blocks:
            return text
        out = []
        for b in blocks:
            if BLOCK_TAG.match(b):
                out.append(b)                       # уже размеченный кусок
            else:
                out.append("<p>" + b.replace("\n", "<br>") + "</p>")
        return "".join(out)

    if template == "custom" and custom:
        raw_name = custom.get("name") or "Поделиться в {network} {keyword}"
        name = fill(raw_name).strip()[:70]
        desc = to_html(fill(custom.get("description")))
        approve = to_html(fill(custom.get("approve")))
    else:
        tpl = TEMPLATES.get(template, TEMPLATES["share"])
        name = tpl["title"].format(network=network, keyword=keyword).strip()[:70]
        desc = build_description(url, network, template)
        approve = tpl["approve"]

    balance = round(quantity * price_user * COMMISSION, 2)
    link = "https://www.google.com/" if stub else url
    task = {
        "name": name,
        "url": [link],
        "type": "social",
        "description": desc,
        "approve_type": "hand",
        "approve_text": approve,
        "price_user": price_user,
        "balance": balance,
        "turn_on": 1,
        "user_xp": 500,
        "work_time": 3600,
    }
    body = urllib.parse.urlencode({
        "api_id": SP_API_ID,
        "api_key": SP_API_KEY,
        "act": "task_create",
        "data": json.dumps(task, ensure_ascii=True),
    }).encode()
    req = urllib.request.Request(SP_API_URL, data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        result = json.loads(raw)
    except Exception:
        return {"status": -1, "text": raw[:300]}

    if result.get("status") == 0:
        tid = (result.get("data") or {}).get("id")
        if tid:
            store_add(tid, name)
    return result


def sp_api(act, **params):
    data = {"api_id": SP_API_ID, "api_key": SP_API_KEY, "act": act}
    data.update(params)
    req = urllib.request.Request(SP_API_URL, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"status": -1, "text": raw[:200]}


def collect_reports(keyword):
    """Ищет задания по ключевому слову в названии и собирает тексты отчётов."""
    keyword = keyword.strip().lower()
    if not keyword:
        return {"error": "Введи ключевое слово или номера заданий"}

    # если введены номера заданий через запятую/пробел — берём их напрямую
    direct = [t for t in re.split(r"[,\s]+", keyword) if t]
    if direct and all(t.isdigit() for t in direct):
        return gather(direct, match_all=True)

    # сперва ищем среди заданий, созданных этим инструментом
    known = [r["id"] for r in store_load() if keyword in r.get("name", "").lower()]
    if known:
        return gather(known, match_all=True)

    def flatten(v, acc):
        if isinstance(v, list):
            for x in v:
                flatten(x, acc)
        elif isinstance(v, dict):
            for x in v.values():
                flatten(x, acc)
        elif str(v).isdigit():
            acc.append(str(v))

    ids, last_err = [], None
    for state in ("all", "yes", "no"):
        lst = sp_api("task_list", data=json.dumps({"active": state}), active=state)
        if lst.get("status") != 0:
            detail = lst.get("text", "нет ответа")
            d = lst.get("data")
            if isinstance(d, dict) and d:
                detail += " — " + "; ".join(f"{k}: {v}" for k, v in d.items())
            last_err = f"task_list({state}): {detail}"
            continue
        found = []
        flatten(lst.get("data", []), found)
        for i in found:
            if i not in ids:
                ids.append(i)

    if not ids:
        return {"error": last_err or "task_list вернул пустой список"}

    # свежие задания имеют больший номер — начинаем с них
    ids.sort(key=int, reverse=True)
    limit = int(os.environ.get("SCAN_LIMIT", "400"))
    return gather(ids[:limit], keyword=keyword, scanned_total=len(ids))


def gather(ids, keyword="", match_all=False, scanned_total=None):
    tasks, texts = [], []
    seen_names, info_fail = [], 0
    for tid in ids:
        info = sp_api("task_info", task_id=tid)
        if info.get("status") != 0:
            info_fail += 1
            continue
        d = info.get("data", {})
        name = d.get("name", "")
        if len(seen_names) < 8:
            seen_names.append(name)
        if not match_all and keyword not in name.lower():
            continue

        count = 0
        for act, key in (("task_bids", "bids"), ("task_bids_history", "history")):
            r = sp_api(act, task_id=tid)
            if r.get("status") != 0:
                continue
            for bid in r.get("data", []) or []:
                if not isinstance(bid, dict):
                    continue
                if key == "history" and not str(bid.get("status", "")).startswith("pay"):
                    continue
                txt = bid.get("text") or ""
                if txt:
                    texts.append(txt)
                    count += 1
        tasks.append({"id": tid, "name": name, "reports": count})

    if not tasks:
        msg = f"Заданий со словом «{keyword}» не найдено. Просмотрено {len(ids)} самых свежих"
        if scanned_total and scanned_total > len(ids):
            msg += f" из {scanned_total}"
        if info_fail:
            msg += f", из них {info_fail} не открылись"
        if seen_names:
            msg += ". Примеры названий: " + " | ".join(seen_names)
        msg += ". Можно вписать номера заданий через запятую."
        return {"error": msg}
    return {"tasks": tasks, "text": "\n".join(texts)}


PAGE = r"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SocPublic — задания и ссылки</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
 background:#f4f5f7;color:#101828;padding:32px 16px 80px;-webkit-font-smoothing:antialiased}
.wrap{max-width:660px;margin:0 auto}

/* шапка */
.head{margin-bottom:20px}
.head h1{font-size:22px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}
.head p{font-size:14px;color:#667085}

/* вкладки */
.tabs{display:flex;gap:4px;background:#e9eaee;padding:4px;border-radius:11px;margin-bottom:18px}
.tab{flex:1;padding:10px 6px;border:none;border-radius:8px;background:transparent;color:#475467;
 font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .12s}
.tab:hover:not(.on){color:#101828}
.tab.on{background:#fff;color:#101828;box-shadow:0 1px 3px rgba(16,24,40,.1)}

/* карточка */
.card{background:#fff;border-radius:14px;padding:24px;box-shadow:0 1px 3px rgba(16,24,40,.06),0 0 0 1px rgba(16,24,40,.04)}
.card + .card{margin-top:14px}

/* шаги */
.step{display:flex;gap:12px;margin-bottom:22px}
.step:last-child{margin-bottom:0}
.num{flex:none;width:24px;height:24px;border-radius:50%;background:#eef2ff;color:#4f6fff;
 font-size:12.5px;font-weight:600;display:flex;align-items:center;justify-content:center;margin-top:1px}
.body{flex:1;min-width:0}
.body h3{font-size:14.5px;font-weight:600;margin-bottom:3px}
.body .sub{font-size:13px;color:#667085;margin-bottom:11px;line-height:1.5}

/* поля */
label{font-size:13px;color:#344054;font-weight:500;display:block;margin-bottom:5px}
input,textarea{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:10px 13px;
 font-size:14px;font-family:inherit;outline:none;color:#101828;transition:all .12s;background:#fff}
input::placeholder,textarea::placeholder{color:#98a2b3}
input:focus,textarea:focus{border-color:#4f6fff;box-shadow:0 0 0 3px rgba(79,111,255,.12)}
textarea{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
 line-height:1.6;resize:vertical;min-height:120px}
.field{margin-bottom:13px}
.field:last-child{margin-bottom:0}
.two{display:flex;gap:12px}
.two>div{flex:1}
.tip{font-size:12.5px;color:#667085;margin-top:6px;line-height:1.45}
.check{display:flex;gap:8px;align-items:flex-start;margin-top:9px;font-weight:400;
 font-size:12.5px;color:#475467;line-height:1.45;cursor:pointer}
.check input{width:auto;flex:none;margin-top:1px;accent-color:#4f6fff}
code{background:#f2f4f7;padding:1px 5px;border-radius:4px;font-size:12px;
 font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#344054}

/* соцсети */
.nethead{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:9px;flex-wrap:wrap}
.pick{display:flex;gap:4px}
.pick button{border:none;background:none;color:#4f6fff;font-size:12.5px;cursor:pointer;
 padding:3px 6px;border-radius:6px;font-family:inherit}
.pick button:hover{background:#eef2ff}
.nets{display:flex;flex-wrap:wrap;gap:7px}
.net{padding:7px 14px;border-radius:999px;font-size:13px;cursor:pointer;font-family:inherit;
 border:1px solid #4f6fff;background:#eef2ff;color:#3538cd;font-weight:500;transition:all .12s}
.net.off{border-color:#d0d5dd;background:#fff;color:#98a2b3;font-weight:400}
.net:hover{transform:translateY(-1px)}

/* кнопки */
.btn{width:100%;padding:13px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;
 border:none;background:#4f6fff;color:#fff;font-family:inherit;transition:background .12s}
.btn:hover:not(:disabled){background:#3f5ce0}
.btn:disabled{background:#d0d5dd;cursor:not-allowed}
.btn.ghost{background:#fff;color:#344054;border:1px solid #d0d5dd;font-weight:500;font-size:13.5px;padding:10px 16px;width:auto}
.btn.ghost:hover:not(:disabled){background:#f9fafb;border-color:#98a2b3}
.summary{background:#f9fafb;border:1px solid #eaecf0;border-radius:9px;padding:11px 14px;
 font-size:13px;color:#475467;text-align:center;margin-bottom:12px;line-height:1.5}
.summary b{color:#101828;font-weight:600}

/* результаты */
.err{font-size:13px;color:#d92d20;background:#fef3f2;border:1px solid #fecdca;
 border-radius:9px;padding:10px 13px;margin-bottom:12px;display:none}
.res{margin-top:16px;display:flex;flex-direction:column;gap:6px}
.r{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 14px;
 border-radius:9px;background:#f9fafb;border:1px solid #eaecf0;font-size:13.5px}
.r.ok{background:#f6fef9;border-color:#a6f4c5}
.r.no{background:#fffbfa;border-color:#fecdca}
.r .st{font-size:12px;color:#667085;text-align:right;max-width:60%}
.r.ok .st{color:#039855}
.r.no .st{color:#d92d20}
.done{margin-top:8px;padding:12px 14px;border-radius:9px;background:#f6fef9;
 border:1px solid #a6f4c5;font-size:13.5px;color:#027a48;font-weight:500;text-align:center}

/* сбор ссылок */
.srow{display:flex;gap:8px}
.srow input{flex:1}
.srow button{flex:none;padding:0 20px;border-radius:9px;border:none;background:#4f6fff;
 color:#fff;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;font-family:inherit}
.srow button:disabled{background:#d0d5dd;cursor:not-allowed}
.found{font-size:13px;color:#475467;background:#f9fafb;border:1px solid #eaecf0;
 border-radius:9px;padding:11px 14px;margin-top:11px;line-height:1.65;display:none}
.found b{color:#101828;font-weight:600}
.hintbox{background:#f9fafb;border:1px solid #eaecf0;border-radius:9px;padding:11px 14px;
 font-size:12.5px;color:#667085;margin-top:7px;line-height:1.5;min-height:18px}
.acts{display:flex;gap:8px;align-items:center;margin:14px 0 12px;flex-wrap:wrap}
.cnt{margin-left:auto;font-size:13px;color:#667085;font-weight:500}
.outwrap{position:relative}
</style></head><body>
<div class="wrap">

<div class="head">
<h1>SocPublic</h1>
<p>Создание заданий и сбор ссылок из отчётов</p>
</div>

<div class="tabs">
<button class="tab on" data-tpl="share">Поделиться ссылкой</button>
<button class="tab" data-tpl="seosp">SeoSp Socseti</button>
<button class="tab" data-tpl="custom">Свой текст</button>
<button class="tab" data-tpl="links">Сбор ссылок</button>
</div>

<!-- ============ СОЗДАНИЕ ЗАДАНИЙ ============ -->
<div id="pane-create">
<div class="card">

<div class="step">
<div class="num">1</div>
<div class="body">
<h3>Что продвигаем</h3>
<div class="sub" id="preview"></div>
__PASSFIELD__
<div class="field">
<label>Ссылка</label>
<input type="url" id="url" placeholder="https://biohack.kz/">
<label class="check"><input type="checkbox" id="stub"><span>В поле задания подставить google.com, а настоящую ссылку оставить только в описании</span></label>
<div class="tip">Пригодится, если SocPublic пишет «ссылка не открывается».</div>
</div>
<div class="field">
<label>Слово в названии задания</label>
<input type="text" id="kw" placeholder="biohack">
<div class="tip">Появится в названии: «Поделиться в Facebook <b>biohack</b>». По нему потом найдутся отчёты.</div>
</div>
</div>
</div>

<div class="step" id="editor" style="display:none">
<div class="num">2</div>
<div class="body">
<h3>Текст задания</h3>
<div class="sub">Подставляются автоматически: <code>{network}</code> — соцсеть, <code>{keyword}</code> — слово, <code>{url}</code> — ссылка.</div>
<div class="field">
<label>Название</label>
<input type="text" id="cname" value="Поделиться в {network} {keyword}">
</div>
<div class="field">
<label>Описание — что делать исполнителю</label>
<textarea id="cdesc" style="min-height:150px"></textarea>
<div class="tip">Пиши как обычный текст — переносы строк и пустые строки сохранятся. HTML тоже можно: &lt;p&gt;, &lt;strong&gt;, &lt;br&gt;. Минимум 100 символов.</div>
</div>
<div class="field">
<label>Отчёт — что прислать в подтверждение</label>
<textarea id="capprove" style="min-height:70px"></textarea>
</div>
<button class="btn ghost" id="reset">Вернуть исходный текст</button>
</div>
</div>

<div class="step">
<div class="num" id="num2">2</div>
<div class="body">
<h3>Где размещаем</h3>
<div class="nethead">
<span class="sub" style="margin:0" id="nl">Соцсети</span>
<div class="pick"><button id="all">выбрать все</button><button id="none">снять все</button></div>
</div>
<div class="nets" id="nets"></div>
</div>
</div>

<div class="step">
<div class="num" id="num3">3</div>
<div class="body">
<h3>Сколько платим</h3>
<div class="sub">На каждое задание уйдёт: количество × оплата + 30% комиссии.</div>
<div class="two">
<div><label>Оплата исполнителю, ₽</label><input type="number" id="price" value="6" min="1" step="0.5"></div>
<div><label>Количество выполнений</label><input type="number" id="qty" value="10" min="1" step="1"></div>
</div>
</div>
</div>

</div>

<div class="card">
<div class="err" id="err"></div>
<div class="summary" id="cost"></div>
<button class="btn" id="go">Создать задания</button>
<div class="res" id="res"></div>
</div>
</div>

<!-- ============ СБОР ССЫЛОК ============ -->
<div id="pane-links" style="display:none">
<div class="card">

<div class="step">
<div class="num">1</div>
<div class="body">
<h3>Найти задания</h3>
<div class="sub">Впиши слово из названия — или номера заданий через запятую, если знаешь их.</div>
<div class="srow">
<input type="text" id="kwsearch" placeholder="biohack — или 3069824, 3069825">
<button id="fetch">Найти</button>
</div>
<div class="found" id="found"></div>
</div>
</div>

<div class="step">
<div class="num">2</div>
<div class="body">
<h3>Отчёты исполнителей</h3>
<div class="sub">Подтянутся сами. Можно вставить текст и вручную.</div>
<textarea id="raw" placeholder="Тексты отчётов со ссылками…"></textarea>
</div>
</div>

<div class="step">
<div class="num">3</div>
<div class="body">
<h3>Сколько ссылок нужно</h3>
<div class="sub">Пусто — выйдут все найденные. Больше, чем есть — повторятся равномерно, подряд одинаковые не встанут.</div>
<input type="number" id="want" min="1" placeholder="например, 40">
<div class="hintbox" id="wanthint">Ссылки пока не найдены.</div>
</div>
</div>

</div>

<div class="card">
<button class="btn" id="mix">Извлечь и перемешать</button>
<div class="acts">
<button class="btn ghost" id="again">Перемешать ещё раз</button>
<button class="btn ghost" id="copy">Копировать</button>
<span class="cnt" id="cnt">0 ссылок</span>
</div>
<div class="outwrap"><textarea id="out" readonly placeholder="Здесь появятся готовые ссылки…"></textarea></div>
</div>
</div>

</div>
<script>
const NETWORKS=__NETWORKS__;
let sel=new Set(NETWORKS);
let tpl='share';
const $=id=>document.getElementById(id);
const PREVIEWS={
 share:'Задание: поделиться ссылкой 7 раз с нативным текстом и хештегами, с фото. Тексты разные, фото с сайта. Отчёт — 7 ссылок на посты.',
 seosp:'Задание: поделиться ссылкой и 6 постами из канала с нативным текстом и хештегами, подписаться и поставить пару реакций. Отчёт — ссылки на 7 репостов.',
 custom:'Текст задания редактируется ниже — можно поменять название, описание и требования к отчёту.'
};
const DEFAULTS={
 name:'Поделиться в {network} {keyword}',
 desc:'<p><strong>Поделиться ссылкой 7 раз с нативным текстом и хештегами и с фоткой</strong></p>\n<p><a href="{url}">{url}</a></p>\n<p>Тексты разные для каждого репоста.</p>\n<p>Фото берем из сайта.</p>\n<p>Платформа: <strong>{network}</strong></p>',
 approve:'<strong>7 ссылок на посты.</strong>'
};
function fillDefaults(){
  $('cname').value=DEFAULTS.name;
  $('cdesc').value=DEFAULTS.desc;
  $('capprove').value=DEFAULTS.approve;
}
fillDefaults();
$('reset').onclick=fillDefaults;
document.querySelectorAll('.tab').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
    t.classList.add('on');
    tpl=t.dataset.tpl;
    const links=tpl==='links', custom=tpl==='custom';
    $('pane-create').style.display=links?'none':'';
    $('pane-links').style.display=links?'':'none';
    $('editor').style.display=custom?'flex':'none';
    $('num2').textContent=custom?'3':'2';
    $('num3').textContent=custom?'4':'3';
    if(!links)$('preview').innerHTML=PREVIEWS[tpl];
  };
});
$('preview').innerHTML=PREVIEWS[tpl];

/* --- создание --- */
function refresh(){
  $('nl').textContent=`Соцсети — выбрано ${sel.size} из ${NETWORKS.length}`;
  const q=parseInt($('qty').value)||0, p=parseFloat($('price').value)||0;
  const per=q*p*1.3;
  $('cost').innerHTML=sel.size
    ? `${q} вып. × ${p} ₽ + 30% = <b>${per.toFixed(2)} ₽</b> за задание · итого <b>${(per*sel.size).toFixed(2)} ₽</b>`
    : 'Выбери хотя бы одну соцсеть';
}
NETWORKS.forEach(n=>{
  const b=document.createElement('button');
  b.className='net';b.textContent=n;
  b.onclick=()=>{sel.has(n)?(sel.delete(n),b.classList.add('off')):(sel.add(n),b.classList.remove('off'));refresh();};
  $('nets').appendChild(b);
});
$('all').onclick=()=>{sel=new Set(NETWORKS);document.querySelectorAll('.net').forEach(b=>b.classList.remove('off'));refresh();};
$('none').onclick=()=>{sel=new Set();document.querySelectorAll('.net').forEach(b=>b.classList.add('off'));refresh();};
$('qty').oninput=refresh;$('price').oninput=refresh;refresh();

$('go').onclick=async()=>{
  const url=$('url').value.trim();
  if(!url){$('err').textContent='Впиши ссылку в первом шаге';$('err').style.display='block';return;}
  if(!sel.size){$('err').textContent='Выбери хотя бы одну соцсеть';$('err').style.display='block';return;}
  $('err').style.display='none';$('res').innerHTML='';
  const nets=[...sel],rows={};
  nets.forEach(n=>{const d=document.createElement('div');d.className='r';
    d.innerHTML=`<span>${n}</span><span class="st">в очереди</span>`;$('res').appendChild(d);rows[n]=d;});
  $('go').disabled=true;
  let ok=0;
  const pw=$('pw')?$('pw').value:'';
  for(let i=0;i<nets.length;i++){
    const n=nets[i];
    $('go').textContent=`Создаю… ${i+1} из ${nets.length}`;
    rows[n].querySelector('.st').textContent='создаётся…';
    try{
      const r=await fetch('/create',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url,keyword:$('kw').value.trim(),network:n,
          price_user:parseFloat($('price').value)||6,quantity:parseInt($('qty').value)||10,password:pw,template:tpl,stub:$('stub').checked,
          custom:tpl==='custom'?{name:$('cname').value,description:$('cdesc').value,approve:$('capprove').value}:null})});
      const j=await r.json();
      if(j.status===0){rows[n].className='r ok';
        rows[n].querySelector('.st').textContent=`готово · №${j.data.id}`;ok++;}
      else{rows[n].className='r no';
        let why=j.text||'не создано';
        if(j.data&&typeof j.data==='object'){
          const parts=Object.entries(j.data).map(([k,v])=>`${k}: ${v}`);
          if(parts.length)why=parts.join('; ');
        }
        rows[n].querySelector('.st').textContent=why;}
    }catch(e){rows[n].className='r no';rows[n].querySelector('.st').textContent=e.message;}
  }
  $('go').disabled=false;$('go').textContent='Создать задания';
  const s=document.createElement('div');s.className='done';
  s.textContent=ok===nets.length?`Создано всё: ${ok} заданий`:`Создано ${ok} из ${nets.length}`;
  $('res').appendChild(s);
};

/* --- сбор ссылок --- */
const DOMAINS=['vk.com','vk.ru','vkontakte.ru','instagram.com','instagr.am','facebook.com','fb.com','fb.me','twitter.com','x.com','youtube.com','youtu.be','tiktok.com','t.me','telegram.me','rutube.ru','ok.ru','odnoklassniki.ru','threads.net','threads.com','linkedin.com','lnkd.in','pinterest.com','pin.it','reddit.com','discord.gg','twitch.tv','dzen.ru','zen.yandex.ru','tumblr.com','livejournal.com','blogger.com','blogspot.com','vseti.by'];
const URL_RE=/\b(?:https?:\/\/|www\.)[^\s<>"'()«»]+/gi;
function norm(u){u=u.trim().replace(/[.,;:!?)»\]]+$/,'');if(!/^https?:\/\//i.test(u))u='https://'+u.replace(/^\/\//,'');return u;}
function isSocial(u){const l=u.toLowerCase();
  return DOMAINS.some(d=>new RegExp('(?:^|//|\\.)'+d.replace(/\./g,'\\.')+'(?:[/:?#]|$)','i').test(l));}
function hasPath(u){try{const o=new URL(u);return o.pathname.replace(/\/+$/,'').length>0||o.search.length>1;}catch{return false;}}
function extract(t){return [...new Set((t.match(URL_RE)||[]).map(norm).filter(isSocial).filter(hasPath))];}
function shuffle(a){a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}
function expand(uniq,target){
  if(!uniq.length||target<=0)return [];
  if(target<=uniq.length)return shuffle(uniq).slice(0,target);
  const base=Math.floor(target/uniq.length), extra=target%uniq.length;
  const u=shuffle(uniq), c=u.map((_,i)=>base+(i<extra?1:0));
  const out=[]; let prev=-1;
  for(let s=0;s<target;s++){
    let bi=-1,bc=0;
    for(let i=0;i<c.length;i++){if(i===prev)continue;if(c[i]>bc){bc=c[i];bi=i;}}
    if(bi===-1){for(let i=0;i<c.length;i++)if(c[i]>0){bi=i;break;}if(bi===-1)break;}
    out.push(u[bi]);c[bi]--;prev=bi;
  }
  return out;
}
function render(list){$('out').value=list.join('\n');$('cnt').textContent=list.length+' ссылок';}
function updateHint(){
  const uniq=extract($('raw').value), t=parseInt($('want').value), h=$('wanthint');
  if(!uniq.length){h.textContent='Ссылки пока не найдены.';return;}
  if(!(t>0)){h.textContent=`Нашлось уникальных ссылок: ${uniq.length}. Выйдут все, вперемешку.`;return;}
  if(t<=uniq.length){h.textContent=`Нашлось ${uniq.length} — возьмём случайные ${t}.`;return;}
  const per=Math.floor(t/uniq.length), rest=t%uniq.length;
  h.textContent=`Нашлось ${uniq.length}. Каждая повторится ${per}${rest?'–'+(per+1):''} раз(а), подряд одинаковые не встанут.`;
}
function build(){
  const uniq=extract($('raw').value), t=parseInt($('want').value);
  render(t>0?expand(uniq,t):shuffle(uniq));
  updateHint();
}
$('want').oninput=updateHint;
$('raw').oninput=updateHint;
$('mix').onclick=build;
$('again').onclick=()=>{
  const cur=$('out').value.split('\n').filter(Boolean);
  if(!cur.length)return build();
  const t=parseInt($('want').value), uniq=[...new Set(cur)];
  render(t>0?expand(uniq,t):shuffle(cur));
};
$('copy').onclick=async()=>{
  if(!$('out').value)return;
  try{await navigator.clipboard.writeText($('out').value);}
  catch{$('out').select();document.execCommand('copy');}
  $('copy').textContent='Скопировано';
  setTimeout(()=>$('copy').textContent='Копировать',1400);
};
$('fetch').onclick=async()=>{
  const kw=$('kwsearch').value.trim();
  if(!kw)return;
  $('fetch').disabled=true;$('fetch').textContent='Ищу…';
  $('found').style.display='block';$('found').textContent='Просматриваю задания…';
  try{
    const r=await fetch('/create',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'reports',keyword:kw})});
    const j=await r.json();
    if(j.error){$('found').textContent=j.error;}
    else{
      $('raw').value=j.text||'';
      const total=j.tasks.reduce((a,b)=>a+b.reports,0);
      const rows=j.tasks.map(t=>`${t.name} — ${t.reports} отч.`).join('<br>');
      $('found').innerHTML=`<b>Заданий: ${j.tasks.length}, отчётов: ${total}</b><br>${rows}`;
      build();
    }
  }catch(e){$('found').textContent=e.message;}
  $('fetch').disabled=false;$('fetch').textContent='Найти';
};
</script></body></html>"""


PASS_FIELD = ('<div class="field"><label>Пароль</label>'
              '<input type="password" id="pw" placeholder="пароль"></div>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        page = (PAGE
                .replace("__NETWORKS__", json.dumps(NETWORKS, ensure_ascii=False))
                .replace("__PASSFIELD__", PASS_FIELD if PASSWORD else ""))
        self._send(200, "text/html; charset=utf-8", page.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            return self._send(400, "application/json", b'{"status":-1,"text":"bad json"}')

        if data.get("action") == "reports":
            try:
                out = collect_reports(data.get("keyword", ""))
            except Exception as e:
                out = {"error": str(e)}
            return self._send(200, "application/json; charset=utf-8",
                              json.dumps(out, ensure_ascii=False).encode())

        if PASSWORD and data.get("password", "") != PASSWORD:
            out = {"status": -1, "text": "неверный пароль"}
            return self._send(200, "application/json; charset=utf-8",
                              json.dumps(out, ensure_ascii=False).encode())
        try:
            result = create_task(data["url"], data.get("keyword", ""), data["network"],
                                 float(data["price_user"]), int(data["quantity"]),
                                 data.get("template", "share"), data.get("custom"),
                                 bool(data.get("stub")))
        except Exception as e:
            result = {"status": -1, "text": str(e)}
        self._send(200, "application/json; charset=utf-8",
                   json.dumps(result, ensure_ascii=False).encode())


if __name__ == "__main__":
    print(f"Запущено на порту {PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
