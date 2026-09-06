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
        "title": "{network} {keyword}",
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


PAGE = """<!DOCTYPE html>
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
<script>
const NETWORKS=__NETWORKS__;
let sel=new Set(NETWORKS);
let tpl='share';
const $=id=>document.getElementById(id);
const PREVIEWS={
 share:'<b>Название:</b> Поделиться в {соцсеть} {слово}<br><b>Задание:</b> поделиться ссылкой 7 раз с нативным текстом и хештегами, с фото. Тексты разные, фото с сайта.<br><b>Отчёт:</b> 7 ссылок на посты.',
 seosp:'<b>Название:</b> {соцсеть} {слово}<br><b>Задание:</b> поделиться ссылкой и 6 постами из канала с нативным текстом и хештегами. Подписаться, поставить пару реакций.<br><b>Отчёт:</b> ссылки на 7 репостов.'
};
document.querySelectorAll('.tab').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
    t.classList.add('on');
    tpl=t.dataset.tpl;
    $('preview').innerHTML=PREVIEWS[tpl];
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
