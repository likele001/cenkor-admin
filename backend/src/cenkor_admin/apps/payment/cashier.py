"""收银台页面（服务端渲染，免登录）。

零构建依赖：二维码由自托管的 `static/qrcode.min.js`（qrcode-generator，MIT）
在浏览器里生成 SVG，不依赖任何第三方 CDN；加载或生成失败时降级为
可复制的支付链接并给出提示。
页面只暴露该笔订单的必要信息，轮询走 /api/v1/public/payment/status/{单号}。
"""
from __future__ import annotations

import html as _html
from typing import Any
from urllib.parse import urlsplit

_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>收银台 · __SUBJECT__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
background:#f5f6f8;color:#1a1a1a;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.card{width:100%;max-width:420px;background:#fff;border-radius:16px;padding:32px 24px;
box-shadow:0 1px 3px rgba(0,0,0,.06),0 8px 24px rgba(0,0,0,.04)}
.head{text-align:center;padding-bottom:20px;border-bottom:1px solid #eee}
.scene{font-size:12px;color:#8a8a8a;letter-spacing:.4px;text-transform:uppercase}
.subject{font-size:16px;font-weight:500;margin-top:8px;line-height:1.4;word-break:break-all}
.amount{text-align:center;margin:28px 0 24px}
.amount .num{font-size:40px;font-weight:500;letter-spacing:-.5px}
.amount .cur{font-size:18px;font-weight:500;margin-right:4px;vertical-align:6px}
.amount .no{font-size:12px;color:#9a9a9a;margin-top:10px;font-family:ui-monospace,Menlo,Consolas,monospace}
.panel{text-align:center;min-height:230px}
#qrcode{display:inline-block;padding:12px;background:#fff;border:1px solid #eee;border-radius:12px}
#qrcode img,#qrcode canvas,#qrcode svg{display:block}
.qrph{width:220px;height:220px;max-width:70vw;max-height:70vw;display:flex;align-items:center;
justify-content:center;font-size:13px;color:#bbb}
.qrlong{display:none;font-size:12px;color:#9a9a9a;word-break:break-all;margin:14px auto 0;
max-width:320px;padding:10px;background:#fafafa;border:1px dashed #e5e5e5;border-radius:8px;
text-align:left;font-family:ui-monospace,Menlo,Consolas,monospace}
.tip{font-size:13px;color:#666;margin-top:16px;line-height:1.7}
.btn{display:block;width:100%;padding:14px;background:#1668dc;color:#fff;border:0;border-radius:10px;
font-size:15px;font-weight:500;cursor:pointer;text-decoration:none;text-align:center;margin-top:20px}
.btn:hover{background:#0f56bb}
.link{font-size:12px;color:#9a9a9a;word-break:break-all;margin-top:14px;font-family:ui-monospace,Menlo,Consolas,monospace}
.state{font-size:14px;padding:14px;border-radius:10px;margin-top:16px}
.state.ok{background:#f0f9f2;color:#237804;border:1px solid #b7e3c3}
.state.wait{background:#fafafa;color:#666;border:1px solid #eee}
.state.err{background:#fff5f5;color:#a8071a;border:1px solid #ffccc7}
.state a{color:inherit;text-decoration:underline}
.foot{text-align:center;font-size:12px;color:#b0b0b0;margin-top:24px}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#52c41a;margin-right:6px;
vertical-align:middle;animation:bp 1.4s ease-in-out infinite}
@keyframes bp{0%,100%{opacity:1}50%{opacity:.25}}
.guide{margin-top:16px}
.guide .kbd{display:inline-block;padding:1px 7px;border:1px solid #d9d9d9;border-radius:5px;
background:#fafafa;font-weight:600;font-size:13px;line-height:18px}
.guide .arrow{display:block;font-size:22px;color:#1668dc;margin:10px 0 2px}
.btn-ghost{display:block;width:100%;padding:12px;background:#fff;color:#1668dc;border:1px solid #91caff;
border-radius:10px;font-size:14px;font-weight:500;cursor:pointer;margin-top:16px}
.btn-ghost:hover{background:#f0f7ff}
</style>
</head>
<body>
<div class="card">
  <div class="head">
    <div class="scene">__SCENE__</div>
    <div class="subject">__SUBJECT__</div>
  </div>
  <div class="amount">
    <div><span class="cur">¥</span><span class="num">__AMOUNT__</span></div>
    <div class="no">订单号 __OUT_TRADE_NO__</div>
  </div>
  <div class="panel" id="panel">__PANEL__</div>
  <div id="state"></div>
  <div class="foot">支付完成后本页会自动刷新状态</div>
</div>
<script src="__QR_LIB_URL__" onerror="window.__QR_LIB_FAIL__=1"></script>
<script>
var OUT_TRADE_NO = "__OUT_TRADE_NO__";
var STATUS_URL = "__STATUS_URL__";
var RETURN_URL = "__RETURN_URL__";
var INITIALLY_PAID = __INITIALLY_PAID__;
function el(id){return document.getElementById(id)}
function backTarget(){
  if(!RETURN_URL) return '';
  try{
    var a = document.createElement('a'); a.href = RETURN_URL;
    // 回跳地址指向本页时必须停下，否则「已支付 → 跳本页 → 又判已支付 → 又跳」会无限循环
    if(a.pathname === location.pathname && a.search === location.search) return '';
  }catch(e){}
  return RETURN_URL;
}
function showState(cls, html){el('state').innerHTML = '<div class="state '+cls+'">'+html+'</div>';}
function copyLink(btn){
  var url = location.href;
  function done(){ btn.textContent = '已复制'; setTimeout(function(){ btn.textContent = '复制支付链接'; }, 1500); }
  function legacy(){
    var t = document.createElement('textarea');
    t.value = url; t.setAttribute('readonly',''); t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select();
    try{ document.execCommand('copy'); done(); }catch(e){}
    document.body.removeChild(t);
  }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(url).then(done, legacy);
  } else { legacy(); }
}
var done = false;
function poll(){
  if(done) return;
  fetch(STATUS_URL, {headers:{'Accept':'application/json'}})
    .then(function(r){return r.json()})
    .then(function(d){
      if(d && d.paid){
        done = true;
        var target = backTarget();
        if(target && !INITIALLY_PAID){
          showState('ok','支付成功，正在返回…');
          setTimeout(function(){ location.href = target; }, 1200);
        } else if(target){
          showState('ok','支付成功，感谢购买　<a href="'+target+'">返回商家</a>');
        } else {
          showState('ok','支付成功，感谢购买，可以关闭本页面了');
        }
      } else if(d && (d.status === 'closed' || d.status === 'failed')){
        done = true;
        showState('err','订单已关闭或支付失败');
      } else {
        showState('wait','<span class="dot"></span>等待支付中…');
      }
    })
    .catch(function(){});
}
if(__HAS_QR__){
  (function(){
    var holder = el('qrcode');
    var qr = "__QR__";
    function showLink(msg){
      if(holder){ holder.innerHTML = ''; }
      var box = el('qrlong');
      if(box){ box.textContent = qr; box.style.display = 'block'; }
      if(msg){ var t = el('qrtip'); if(t){ t.innerHTML = msg; } }
    }
    if(window.__QR_LIB_FAIL__){ showLink('二维码组件加载失败，请复制下方链接到浏览器打开支付'); return; }
    if(typeof window.qrcode !== 'function'){ showLink('二维码组件未就绪，请刷新页面或复制下方链接支付'); return; }
    try{
      var obj = window.qrcode(0, 'M');   // typeNumber=0 自动选版本，纠错等级 M
      obj.addData(qr);
      obj.make();
      holder.innerHTML = obj.createSvgTag({cellSize: 4, margin: 16, scalable: true});
      var svg = holder.getElementsByTagName('svg')[0];
      if(!svg){ throw new Error('svg not rendered'); }
      svg.setAttribute('style', 'width:220px;height:220px;max-width:70vw;max-height:70vw');
    }catch(e){ showLink('二维码生成失败，请复制下方链接到浏览器打开支付'); }
  })();
}
(function(){
  var img = el('qrimg');
  if(!img) return;
  img.onerror = function(){
    img.style.display = 'none';
    var t = el('qrtip');
    if(t){ t.innerHTML = '二维码图片加载失败，请刷新页面重试'; }
  };
})();
setInterval(poll, 3000); poll();
</script>
</body>
</html>
"""

_PANEL_QR = (
    '<div id="qrcode"><div class="qrph">正在生成二维码…</div></div>'
    '<div class="tip" id="qrtip">请使用 __PAY_HINT__ 扫描上方二维码完成支付</div>'
    '<div class="qrlong" id="qrlong"></div>'
    '<button class="btn-ghost" type="button" onclick="copyLink(this)">复制支付链接</button>'
)
# 降级形态：解不出可扫支付串时，直接显示虎皮椒自己生成的二维码图
# （它本身就是一个 302 到 PNG 的地址，当 img src 用是正确的）。
_PANEL_QR_IMG = (
    '<div id="qrcode"><img id="qrimg" class="qrimg" src="__QR_IMG__"'
    ' width="220" height="220" alt="支付二维码"></div>'
    '<div class="tip" id="qrtip">请使用 __PAY_HINT__ 扫描上方二维码完成支付</div>'
    '<button class="btn-ghost" type="button" onclick="copyLink(this)">复制支付链接</button>'
)
_PANEL_REDIRECT = '<a class="btn" href="__PAY_URL__">前往支付</a><div class="tip">点击按钮跳转到收银页面</div>'
# 微信内置浏览器会拦截 H5 支付（MWEB），且无法调起未开 JSAPI 的支付，
# 因此在这里直接引导用户改用系统浏览器打开本页（顺带给一键复制兜底）。
_PANEL_WECHAT = (
    '<div class="state wait">微信内无法直接调起支付</div>'
    '<div class="guide">'
    '<div class="tip">请点击右上角 <span class="kbd">···</span> 菜单，选择'
    ' <b>在浏览器中打开</b>，再继续完成支付<span class="arrow">↗</span></div>'
    '</div>'
    '<button class="btn-ghost" type="button" onclick="copyLink(this)">复制支付链接</button>'
    '<div class="tip">若菜单里没有「在浏览器中打开」，可先复制链接再粘贴到浏览器</div>'
)
_PANEL_DONE = '<div class="state ok">该订单已完成支付</div>'
_PANEL_CLOSED = '<div class="state err">该订单已关闭或支付失败，请重新下单</div>'


def _fy(cents: int) -> str:
    return f"{cents / 100:.2f}"


# 虎皮椒「二维码图片地址」的特征串：命中则说明这个值不能当二维码内容编码
_QR_IMG_MARKS = ("/payments/wechat/qrcode", "/payments/alipay/qrcode", "/qrcode/")


def _is_qr_image_url(value: str) -> bool:
    return value.startswith("http") and "xunhupay.com" in value and any(
        m in value for m in _QR_IMG_MARKS
    )


def _is_self_page(url: str, out_trade_no: str) -> bool:
    """回跳地址是否就是本收银台页。

    业务方不传 ``return_url`` 时，支付中心会默认把回跳地址指向收银台自己；
    页面再自动跳回去就会形成死循环，所以要先识别出来。
    """
    if not url:
        return False
    return urlsplit(url).path.endswith(f"/payment/cashier/{out_trade_no}")


def render_cashier(
    order: Any,
    *,
    scene_name: str = "",
    status_url: str = "",
    in_wechat: bool = False,
) -> str:
    """渲染收银台 HTML。order 为 PayOrder 实例。

    ``in_wechat`` 由调用方按 User-Agent 判定后传入：微信内置浏览器拿不到
    H5/JSAPI 支付（JSAPI 需要 openid 链路），直接渲染改浏览器打开的引导。
    """
    payload: dict = order.pay_payload or {}
    mode = order.pay_mode or ""
    qr = str(payload.get("code_url") or "")
    qr_img = str(payload.get("code_img") or "")
    pay_url = str(payload.get("url") or "")
    provider = order.provider or ""
    sub_type = order.sub_type or ""
    # 回跳指向本页时置空：交给前端 backTarget() 也兼容，但这里先清掉最干净
    ret_url = "" if _is_self_page(str(order.return_url or ""), order.out_trade_no) else str(order.return_url or "")
    # 兼容历史订单：早期把虎皮椒「二维码图片地址」当成 code_url 存了库，
    # 扫出来只会再看到一张二维码；这里改走 img 分支直接显示第三方图。
    if qr and not qr_img and _is_qr_image_url(qr):
        qr_img, qr = qr, ""

    if order.status == "paid":
        panel = _PANEL_DONE
        has_qr = False
    elif order.status in ("closed", "failed"):
        panel = _PANEL_CLOSED
        has_qr = False
    elif in_wechat:
        # 优先级放在支付方式判断之前：微信内无论哪种收单方式都不可用
        panel = _PANEL_WECHAT
        has_qr = False
    elif mode == "qrcode" and (qr or qr_img):
        hint = "微信" if (provider == "wechat" or sub_type == "wechat") else "支付宝"
        if qr:
            panel = _PANEL_QR.replace("__PAY_HINT__", hint)
            has_qr = True
        else:
            panel = (
                _PANEL_QR_IMG.replace("__QR_IMG__", _html.escape(qr_img, quote=True))
                .replace("__PAY_HINT__", hint)
            )
            has_qr = False
    elif mode == "redirect" and pay_url:
        panel = _PANEL_REDIRECT.replace("__PAY_URL__", pay_url)
        has_qr = False
    elif mode == "jsapi":
        panel = '<div class="tip">请在微信内打开本页完成支付</div>'
        has_qr = False
    else:
        panel = '<div class="tip">暂无可用的支付方式，请联系商户</div>'
        has_qr = False

    html = _TEMPLATE
    replacements = {
        "__SUBJECT__": (order.subject or "订单支付"),
        "__SCENE__": scene_name or order.scene_key or "",
        "__AMOUNT__": _fy(order.amount_cents or 0),
        "__OUT_TRADE_NO__": order.out_trade_no,
        "__PANEL__": panel,
        "__QR__": qr.replace("\\", "\\\\").replace('"', '\\"'),
        "__PAY_URL__": pay_url,
        "__STATUS_URL__": status_url or f"/api/v1/public/payment/status/{order.out_trade_no}",
        "__RETURN_URL__": ret_url,
        "__INITIALLY_PAID__": "true" if (order.status or "") == "paid" else "false",
        "__QR_LIB_URL__": "/api/v1/public/payment/assets/qrcode.min.js",
        "__HAS_QR__": "true" if has_qr else "false",
    }
    for key, val in replacements.items():
        html = html.replace(key, str(val))
    return html
