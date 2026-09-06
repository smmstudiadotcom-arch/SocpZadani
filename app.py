"""SocPublic — веб-форма создания заданий. Деплой на Railway."""

import json
import os
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

SP_API_URL = "https://socpublic.com/api"
SP_API_ID  = os.environ.get("SP_API_ID",  "244")
SP_API_KEY = os.environ.get("SP_API_KEY", "48A8B0D6-296D-6FC0-94B3-A9500751A704")
PASSWORD   = os.environ.get("APP_PASSWORD", "")
PORT       = int(os.environ.get("PORT", "8080"))
COMMISSION = 1.3

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


def create_task(url, keyword, network, price_user, quantity, template="share"):
    tpl = TEMPLATES.get(template, TEMPLATES["share"])
    name = tpl["title"].format(network=network, keyword=keyword).strip()[:70]
    balance = round(quantity * price_user * COMMISSION, 2)
    task = {
        "name": name,
        "url": [url],
        "type": "social",
        "description": build_description(url, network, template),
        "approve_type": "hand",
        "approve_text": tpl["approve"],
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
        return json.loads(raw)
    except Exception:
        return {"status": -1, "text": raw[:300]}


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
        return {"error": "Введи ключевое слово"}

    lst = sp_api("task_list", data=json.dumps({"active": "all"}), active="all")
    if lst.get("status") != 0:
        detail = lst.get("text", "не удалось получить список заданий")
        d = lst.get("data")
        if isinstance(d, dict) and d:
            detail += " — " + "; ".join(f"{k}: {v}" for k, v in d.items())
        return {"error": f"task_list: {detail}"}

    raw_ids = lst.get("data", [])
    while isinstance(raw_ids, list) and len(raw_ids) == 1 and isinstance(raw_ids[0], list):
        raw_ids = raw_ids[0]
    ids = [str(i) for i in raw_ids if str(i).isdigit()]

    tasks, texts = [], []
    for tid in ids:
        info = sp_api("task_info", task_id=tid)
        if info.get("status") != 0:
            continue
        d = info.get("data", {})
        name = d.get("name", "")
        if keyword not in name.lower():
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
        return {"error": f"Заданий со словом «{keyword}» не найдено"}
    return {"tasks": tasks, "text": "\n".join(texts)}


PAGE = r"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SocPublic — Создать задания</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#f6f7f9;color:#1a1d24;padding:40px 16px;min-height:100vh}
.wrap{max-width:600px;margin:0 auto;background:#fff;border-radius:14px;padding:30px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:20px;font-weight:600;margin-bottom:6px}
.sub{font-size:13px;color:#6b7280;margin-bottom:20px}
.tabs{display:flex;gap:4px;background:#f3f4f6;padding:4px;border-radius:10px;margin-bottom:22px}
.tab{flex:1;padding:9px;border:none;border-radius:7px;background:transparent;color:#6b7280;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit}
.tab.on{background:#fff;color:#1a1d24;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.preview{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin-bottom:18px;font-size:12.5px;color:#4b5563;line-height:1.5}
.preview b{color:#1a1d24;font-weight:600}
textarea{width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px 13px;font-size:12.5px;outline:none;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.55;resize:vertical;min-height:150px}
textarea:focus{border-color:#4f6fff;box-shadow:0 0 0 3px rgba(79,111,255,.1)}
.hint{font-size:12px;color:#6b7280;margin-bottom:14px;line-height:1.5}
.srow{display:flex;gap:8px;margin-bottom:14px}
.srow input{flex:1}
.srow button{padding:0 18px;border-radius:8px;border:none;background:#4f6fff;color:#fff;font-size:13.5px;font-weight:600;cursor:pointer;white-space:nowrap;font-family:inherit}
.srow button:disabled{background:#c7cbd4;cursor:not-allowed}
.found{font-size:12.5px;color:#4b5563;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 13px;margin-bottom:14px;line-height:1.6}
.found b{color:#1a1d24}
.orow{display:flex;gap:8px;align-items:center;margin:12px 0}
.orow input{width:90px}
.orow button{padding:9px 14px;border-radius:8px;border:1px solid #d1d5db;background:#fff;color:#374151;font-size:12.5px;cursor:pointer;font-family:inherit}
.orow button:hover{border-color:#4f6fff;color:#4f6fff}
.cnt{font-size:12px;color:#6b7280;margin-left:auto}
label{font-size:13px;color:#374151;display:block;margin-bottom:5px;font-weight:500}
input{width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px 13px;font-size:14px;outline:none}
input:focus{border-color:#4f6fff;box-shadow:0 0 0 3px rgba(79,111,255,.1)}
.field{margin-bottom:14px}
.row{display:flex;gap:12px}.row>div{flex:1}
.nets{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px}
.net{padding:6px 13px;border-radius:20px;font-size:12.5px;cursor:pointer;border:1px solid #4f6fff;background:#eef2ff;color:#4f46e5}
.net.off{border-color:#e5e7eb;background:#fff;color:#9ca3af}
.netshead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.netshead label{margin-bottom:0}
.pick{display:flex;gap:6px}
.pick button{border:none;background:none;color:#4f6fff;font-size:12.5px;cursor:pointer;padding:2px 4px;font-family:inherit}
.pick button:hover{text-decoration:underline}
.pick span{color:#d1d5db;font-size:12px}
button.main{width:100%;padding:13px;border-radius:9px;font-size:15px;font-weight:600;cursor:pointer;border:none;background:#4f6fff;color:#fff}
button.main:disabled{background:#c7cbd4;cursor:not-allowed}
.cost{font-size:13px;color:#6b7280;text-align:center;margin-bottom:12px}
.err{font-size:13px;color:#dc2626;margin-bottom:10px;display:none}
.res{margin-top:20px;display:flex;flex-direction:column;gap:6px}
.r{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;border-radius:8px;background:#f9fafb;border:1px solid #e5e7eb;font-size:13px}
.r.ok{background:#f0fdf4;border-color:#bbf7d0}
.r.no{background:#fef2f2;border-color:#fecaca}
.r span:last-child{font-size:12px;color:#6b7280;text-align:right;max-width:62%}
.r.ok span:last-child{color:#16a34a}
.r.no span:last-child{color:#dc2626}
.sum{margin-top:8px;padding:11px 14px;border-radius:8px;background:#f0fdf4;border:1px solid #bbf7d0;font-size:13.5px;color:#15803d;font-weight:500}
</style></head><body>
<div class="wrap">
<h1>Создать задания на SocPublic</h1>
<p class="sub">Одна ссылка — задание в каждой выбранной соцсети</p>
<div class="tabs">
<button class="tab on" data-tpl="share">Поделиться ссылкой</button>
<button class="tab" data-tpl="seosp">SeoSp Socseti</button>
<button class="tab" data-tpl="links">Сбор ссылок</button>
</div>
<div class="preview" id="preview"></div>
__PASSFIELD__
<div class="field"><label>Ссылка</label><input type="url" id="url" placeholder="https://biohack.kz/"></div>
<div class="field"><label>Ключевое слово в названии</label><input type="text" id="kw" placeholder="biohack"></div>
<div class="row field">
<div><label>Оплата исполнителю, ₽</label><input type="number" id="price" value="6" min="1" step="0.5"></div>
<div><label>Количество выполнений</label><input type="number" id="qty" value="10" min="1" step="1"></div>
</div>
<div class="netshead">
<label id="nl">Соцсети</label>
<div class="pick"><button id="all">выбрать все</button><span>·</span><button id="none">снять все</button></div>
</div>
<div class="nets" id="nets"></div>
<p class="err" id="err"></p>
<p class="cost" id="cost"></p>
<button class="main" id="go">Создать задания</button>
<div class="res" id="res"></div>
</div>

<div id="pane-links" style="display:none">
<p class="hint">Забирает отчёты исполнителей из заданий SocPublic по слову в названии, вытаскивает ссылки на соцсети и перемешивает их.</p>
<div class="srow">
<input type="text" id="kwsearch" placeholder="слово в названии задания, напр. club199609929">
<button id="fetch">Собрать отчёты</button>
</div>
<div class="found" id="found" style="display:none"></div>
<label>Текст отчётов</label>
<textarea id="raw" placeholder="Сюда попадут отчёты исполнителей. Можно вставить текст и вручную."></textarea>
<div class="orow">
<input type="number" id="want" min="1" placeholder="сколько">
<button id="mix">Извлечь и перемешать</button>
<button id="again">Ещё раз</button>
<button id="copy">Копировать</button>
<span class="cnt" id="cnt">0 ссылок</span>
</div>
<textarea id="out" readonly placeholder="Здесь появятся ссылки..."></textarea>
</div>
<script>
const NETWORKS=__NETWORKS__;
let sel=new Set(NETWORKS);
let tpl='share';
const $=id=>document.getElementById(id);
const PREVIEWS={
 share:'<b>Название:</b> Поделиться в {соцсеть} {слово}<br><b>Задание:</b> поделиться ссылкой 7 раз с нативным текстом и хештегами, с фото. Тексты разные, фото с сайта.<br><b>Отчёт:</b> 7 ссылок на посты.',
 seosp:'<b>Название:</b> Поделиться в {соцсеть} {слово}<br><b>Задание:</b> поделиться ссылкой и 6 постами из канала с нативным текстом и хештегами. Подписаться, поставить пару реакций.<br><b>Отчёт:</b> ссылки на 7 репостов.'
};
const CREATE_IDS=['preview','url','kw','price','qty','nl','nets','err','cost','go','res'];
function showPane(){
  const links=tpl==='links';
  CREATE_IDS.forEach(id=>{const e=$(id);if(e){const w=e.closest('.field')||e.closest('.row')||e.closest('.netshead')||e;w.style.display=links?'none':'';}});
  const nh=document.querySelector('.netshead');if(nh)nh.style.display=links?'none':'';
  const nets=$('nets');if(nets)nets.style.display=links?'none':'flex';
  $('pane-links').style.display=links?'block':'none';
}
document.querySelectorAll('.tab').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
    t.classList.add('on');
    tpl=t.dataset.tpl;
    if(tpl!=='links')$('preview').innerHTML=PREVIEWS[tpl];
    showPane();
  };
});
function refresh(){
  $('nl').textContent=`Соцсети — выбрано ${sel.size}`;
  const q=parseInt($('qty').value)||0, p=parseFloat($('price').value)||0;
  const per=q*p*1.3;
  $('cost').textContent=sel.size?`${q} вып. × ${p} ₽ = ${per.toFixed(2)} ₽ за задание · всего ${(per*sel.size).toFixed(2)} ₽`:'';
}
NETWORKS.forEach(n=>{
  const b=document.createElement('button');
  b.className='net';b.textContent=n;
  b.onclick=()=>{sel.has(n)?(sel.delete(n),b.classList.add('off')):(sel.add(n),b.classList.remove('off'));refresh();};
  $('nets').appendChild(b);
});
$('all').onclick=()=>{sel=new Set(NETWORKS);
  document.querySelectorAll('.net').forEach(b=>b.classList.remove('off'));refresh();};
$('none').onclick=()=>{sel=new Set();
  document.querySelectorAll('.net').forEach(b=>b.classList.add('off'));refresh();};
$('qty').oninput=refresh;$('price').oninput=refresh;refresh();
$('preview').innerHTML=PREVIEWS[tpl];
$('go').onclick=async()=>{
  const url=$('url').value.trim();
  if(!url){$('err').textContent='Введи ссылку';$('err').style.display='block';return;}
  if(!sel.size){$('err').textContent='Выбери хотя бы одну соцсеть';$('err').style.display='block';return;}
  $('err').style.display='none';$('res').innerHTML='';
  const nets=[...sel],rows={};
  nets.forEach(n=>{const d=document.createElement('div');d.className='r';
    d.innerHTML=`<span>${n}</span><span>в очереди</span>`;$('res').appendChild(d);rows[n]=d;});
  $('go').disabled=true;
  let ok=0;
  const pw=$('pw')?$('pw').value:'';
  for(let i=0;i<nets.length;i++){
    const n=nets[i];
    $('go').textContent=`Создаю… ${i+1} из ${nets.length}`;
    rows[n].querySelector('span:last-child').textContent='создаётся…';
    try{
      const r=await fetch('/create',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url,keyword:$('kw').value.trim(),network:n,
          price_user:parseFloat($('price').value)||6,quantity:parseInt($('qty').value)||10,password:pw,template:tpl})});
      const j=await r.json();
      if(j.status===0){rows[n].className='r ok';
        rows[n].querySelector('span:last-child').textContent=`создано · id ${j.data.id}`;ok++;}
      else{rows[n].className='r no';
        let why=j.text||'не создано';
        if(j.data&&typeof j.data==='object'){
          const parts=Object.entries(j.data).map(([k,v])=>`${k}: ${v}`);
          if(parts.length)why=parts.join('; ');
        }
        rows[n].querySelector('span:last-child').textContent=why;}
    }catch(e){rows[n].className='r no';
      rows[n].querySelector('span:last-child').textContent=e.message;}
  }
  $('go').disabled=false;$('go').textContent='Создать задания';
  const s=document.createElement('div');s.className='sum';
  s.textContent=`Создано ${ok} из ${nets.length}`;$('res').appendChild(s);
};

const DOMAINS=['vk.com','vk.ru','vkontakte.ru','instagram.com','instagr.am','facebook.com','fb.com','fb.me','twitter.com','x.com','youtube.com','youtu.be','tiktok.com','t.me','telegram.me','rutube.ru','ok.ru','odnoklassniki.ru','threads.net','threads.com','linkedin.com','lnkd.in','pinterest.com','pin.it','reddit.com','discord.gg','twitch.tv','dzen.ru','zen.yandex.ru','tumblr.com','livejournal.com','blogger.com','blogspot.com','vseti.by'];
const URL_RE=/\b(?:https?:\/\/|www\.)[^\s<>"'()«»]+/gi;

function norm(u){
  u=u.trim().replace(/[.,;:!?)»\]]+$/,'');
  if(!/^https?:\/\//i.test(u))u='https://'+u.replace(/^\/\//,'');
  return u;
}
function isSocial(u){
  const l=u.toLowerCase();
  return DOMAINS.some(d=>new RegExp('(?:^|//|\\.)'+d.replace(/\./g,'\\.')+'(?:[/:?#]|$)','i').test(l));
}
function hasPath(u){
  try{const o=new URL(u);return o.pathname.replace(/\/+$/,'').length>0||o.search.length>1;}catch{return false;}
}
function extract(text){
  return [...new Set((text.match(URL_RE)||[]).map(norm).filter(isSocial).filter(hasPath))];
}
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
function render(list){
  $('out').value=list.join('\n');
  $('cnt').textContent=list.length+' ссылок';
}
function build(){
  const uniq=extract($('raw').value);
  const t=parseInt($('want').value);
  render(t>0?expand(uniq,t):shuffle(uniq));
}
$('mix').onclick=build;
$('again').onclick=()=>{
  const cur=$('out').value.split('\n').filter(Boolean);
  if(!cur.length)return build();
  const t=parseInt($('want').value);
  const uniq=[...new Set(cur)];
  render(t>0?expand(uniq,t):shuffle(cur));
};
$('copy').onclick=async()=>{
  if(!$('out').value)return;
  try{await navigator.clipboard.writeText($('out').value);$('copy').textContent='Скопировано';}
  catch{$('out').select();document.execCommand('copy');$('copy').textContent='Скопировано';}
  setTimeout(()=>$('copy').textContent='Копировать',1400);
};
$('fetch').onclick=async()=>{
  const kw=$('kwsearch').value.trim();
  if(!kw)return;
  $('fetch').disabled=true;$('fetch').textContent='Ищу…';
  $('found').style.display='block';$('found').textContent='Просматриваю задания, это займёт минуту…';
  try{
    const r=await fetch('/create',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'reports',keyword:kw})});
    const j=await r.json();
    if(j.error){$('found').textContent=j.error;}
    else{
      $('raw').value=j.text||'';
      const rows=j.tasks.map(t=>`${t.name} — ${t.reports} отч.`).join('<br>');
      const total=j.tasks.reduce((a,b)=>a+b.reports,0);
      $('found').innerHTML=`<b>Заданий: ${j.tasks.length}, отчётов: ${total}</b><br>${rows}`;
      build();
    }
  }catch(e){$('found').textContent=e.message;}
  $('fetch').disabled=false;$('fetch').textContent='Собрать отчёты';
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
                                 data.get("template", "share"))
        except Exception as e:
            result = {"status": -1, "text": str(e)}
        self._send(200, "application/json; charset=utf-8",
                   json.dumps(result, ensure_ascii=False).encode())


if __name__ == "__main__":
    print(f"Запущено на порту {PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
