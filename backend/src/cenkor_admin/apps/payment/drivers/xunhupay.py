"""虎皮椒 / 讯虎（xunhupay）聚合支付驱动。

一个账号同时支持微信与支付宝，用 sub_type 区分；type 参数决定实际收单方式：
  sub_type=alipay  -> 默认 WAP（手机网站）或 NATIVE（扫码）
  sub_type=wechat  -> 默认 MOBILE（H5）或 NATIVE（扫码）

签名：参数按 key 字典序、**原值不编码**拼接后直接追加 appsecret 取 MD5 小写
（虎皮椒服务端不做 URL 编码，带 `%XX` 的值会导致 40029 签名错误）
长度：`wap_url` 超过 49 字符会被网关判成 `{"errcode":500,"errmsg":"系统内部错误"}`
（不是签名问题，也不报参数名，极易误判），所以只送站点根地址。
二维码：`url_qrcode` 是「二维码图片的生成地址」（302 到 /qrcode/xxx.html?data=<base64>），
**不是可扫的支付串**；直接把它编码成二维码，用户扫出来只会再看到一张二维码。
真串在 data 里（微信为 `weixin://wxpay/bizpayurl?pr=...`），下单时多跟一次重定向解出来。
金额：内部「分」<-> 虎皮椒「元」
注意：退款需先在虎皮椒后台开通，未开通的账号调用会报错。
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import structlog

from cenkor_admin.apps.payment.drivers.base import (
    NotifyResult,
    PayError,
    PaymentDriver,
    PayRequest,
    PayResult,
    register_driver,
)

log = structlog.get_logger()

DEFAULT_API = "https://api.xunhupay.com"
PAID_STATUS = {"OD"}

DEFAULT_TYPE = {"alipay": "WAP", "wechat": "MOBILE", "": "NATIVE"}

# wap_url 实测上限 49 字符（50 起报 errcode 500），留余量按 40 处理
MAX_WAP_URL_LEN = 40
# 只有浏览器跳转类收单方式需要在虎皮椒页面显示「返回商家」，PC 扫码不必送 wap_*
BROWSER_PAY_TYPES = {"WAP", "MOBILE", "WECHAT", "JS", "JSAPI", "PUBLIC"}


def _yuan(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _to_cents(amount: Any) -> int:
    try:
        return int(round(float(amount) * 100))
    except Exception:  # noqa: BLE001
        return 0


def _site_root(url: str) -> str:
    """取站点根地址（scheme://host）。

    wap_url 的语义是「商家站点」，用于支付完成后回跳链接的展示；收银台深层链接
    又长又没意义，还会踩上门限长，所以只截根地址。
    """
    parts = urlsplit(url or "")
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return (url or "")[:MAX_WAP_URL_LEN]


def _sign(params: dict[str, Any], secret: str) -> str:
    """虎皮椒签名：字典序 + **原值**拼接，末尾直接接 appsecret（不 urlencode）。"""
    items = sorted(
        (k, str(v)) for k, v in params.items()
        if k != "hash" and v not in (None, "")
    )
    raw = "&".join(f"{k}={v}" for k, v in items) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


@register_driver
class XunhuDriver(PaymentDriver):
    provider = "xunhupay"
    display_name = "虎皮椒 / 讯虎（第三方聚合）"
    supports_refund = True
    sub_types = [("wechat", "微信支付"), ("alipay", "支付宝")]
    # 暴露给 service.get_channel 做终端选路：config.pay_type 留空时按此表取默认
    default_pay_types = DEFAULT_TYPE
    config_fields = [
        {"key": "appid", "label": "AppID", "type": "text", "required": True,
         "placeholder": "虎皮椒后台的 AppID"},
        {"key": "appsecret", "label": "AppSecret", "type": "text", "required": True,
         "secret": True, "placeholder": "虎皮椒后台的 AppSecret"},
        {"key": "api_url", "label": "接口地址", "type": "text", "required": False,
         "placeholder": DEFAULT_API, "hint": "讯虎独立部署填自己的域名"},
        {"key": "pay_type", "label": "收单方式", "type": "select", "required": False,
         "default": "", "hint": "留空则按支付方式自动选择",
         "options": [
             {"value": "", "label": "自动"},
             {"value": "NATIVE", "label": "NATIVE（PC 扫码）"},
             {"value": "WAP", "label": "WAP（支付宝手机网站）"},
             {"value": "MOBILE", "label": "MOBILE（微信 H5）"},
             {"value": "WECHAT", "label": "WECHAT（微信内 JSAPI）"},
         ]},
    ]

    # ---------- 内部工具 ----------

    def _api(self) -> str:
        return (self.one("api_url", DEFAULT_API) or DEFAULT_API).rstrip("/")

    def _pay_type(self) -> str:
        explicit = self.one("pay_type")
        if explicit:
            return explicit.upper()
        return DEFAULT_TYPE.get(self.sub_type, "NATIVE")

    def _sign_params(self, params: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in params.items() if v not in (None, "")}
        out["hash"] = _sign(out, self.one("appsecret"))
        return out

    async def _post(self, path: str, params: dict[str, Any]) -> dict:
        signed = self._sign_params(params)
        url = f"{self._api()}{path}"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, data=signed)
        except Exception as exc:  # noqa: BLE001
            raise PayError("无法连接虎皮椒网关", detail=str(exc), code="network") from exc
        try:
            node = resp.json()
        except Exception:  # noqa: BLE001
            raise PayError("虎皮椒返回内容无法解析", detail=resp.text[:500], code="bad_response")
        return node if isinstance(node, dict) else {"errcode": -1, "errmsg": "返回格式异常"}

    @staticmethod
    def _ensure_ok(node: dict, fallback: str) -> dict:
        if int(node.get("errcode") or 0) != 0:
            raise PayError(
                f"{fallback}：{node.get('errmsg') or '未知错误'}",
                detail=json.dumps(node, ensure_ascii=False)[:500],
                code=str(node.get("errcode", "")),
            )
        return node

    # ---------- 对外能力 ----------

    async def create_pay(self, req: PayRequest) -> PayResult:
        pay_type = self._pay_type()
        params = {
            "version": "1.1",
            "appid": self.one("appid"),
            "trade_order_id": req.out_trade_no,
            "total_fee": _yuan(req.amount_cents),
            "title": (req.subject or "订单支付")[:127],
            "time": str(int(time.time())),
            "notify_url": req.notify_url,
            "nonce_str": uuid.uuid4().hex,
            "type": pay_type,
        }
        if req.return_url:
            params["return_url"] = req.return_url
            # wap_* 只在浏览器跳转类收单有意义；wap_url 必须短，超长会被网关判 500
            if pay_type in BROWSER_PAY_TYPES:
                wap_url = _site_root(req.return_url)
                if len(wap_url) <= MAX_WAP_URL_LEN:
                    params["wap_url"] = wap_url
                    params["wap_name"] = (self.one("wap_name") or req.subject or "订单支付")[:32]
                else:
                    log.warning("xunhupay.wap_url_too_long", wap_url=wap_url,
                                limit=MAX_WAP_URL_LEN, hint="站点域名过长，已省略 wap_url/wap_name")
        if pay_type == "WECHAT" and req.openid:
            params["openid"] = req.openid

        node = self._ensure_ok(await self._post("/payment/do.html", params), "虎皮椒下单失败")
        url = node.get("url") or ""
        qr = node.get("url_qrcode") or ""
        if url and pay_type != "NATIVE":
            return PayResult(
                mode="redirect",
                payload={"url": url, "out_trade_no": req.out_trade_no,
                         "amount_cents": req.amount_cents, "pay_type": pay_type},
                raw=node,
            )
        if not qr:
            raise PayError("虎皮椒未返回支付地址", detail=json.dumps(node, ensure_ascii=False)[:500])
        code_url = await self._resolve_code_url(qr)
        if not code_url:
            log.warning("xunhupay.qrcode_fallback_img", out_trade_no=req.out_trade_no,
                        hint="未能从 url_qrcode 解出支付串，收银台降级为直接显示第三方二维码图")
        return PayResult(
            mode="qrcode",
            payload={
                "code_url": code_url,     # 真正可扫的支付串（weixin://…）
                "code_img": qr,           # 虎皮椒二维码图地址（降级用）
                "out_trade_no": req.out_trade_no,
                "amount_cents": req.amount_cents, "pay_type": pay_type,
            },
            raw=node,
        )

    async def _resolve_code_url(self, qr_image_url: str) -> str:
        """把虎皮椒的「二维码图片地址」还原成真正可扫的支付串。

        只读一次 302 的 Location（不下载图片），取 `data` 参数的 base64。
        解不出来返回空串，由调用方降级为 `<img>` 直接显示第三方二维码。
        """
        if not qr_image_url.startswith("http"):
            return ""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(qr_image_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("xunhupay.qrcode_resolve_failed", error=str(exc), url=qr_image_url[:120])
            return ""
        loc = resp.headers.get("location") or ""
        data = dict(parse_qsl(urlsplit(loc).query)).get("data") if loc else None
        if not data:
            log.warning("xunhupay.qrcode_no_data", status=resp.status_code, location=loc[:120])
            return ""
        try:
            return base64.b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("xunhupay.qrcode_decode_failed", error=str(exc))
            return ""

    async def query(self, out_trade_no: str) -> dict[str, Any]:
        params = {
            "appid": self.one("appid"),
            "out_trade_order": out_trade_no,
            "time": str(int(time.time())),
            "nonce_str": uuid.uuid4().hex,
        }
        node = await self._post("/payment/query.html", params)
        if int(node.get("errcode") or 0) != 0:
            return {
                "paid": False,
                "status": str(node.get("errcode", "")),
                "trade_no": "",
                "amount_cents": 0,
                "message": node.get("errmsg", ""),
                "raw": node,
            }
        data = node.get("data") or node
        status = str(data.get("status", ""))
        return {
            "paid": status in PAID_STATUS,
            "status": status,
            "trade_no": str(data.get("transaction_id", "")),
            "amount_cents": _to_cents(data.get("total_fee")),
            "message": "",
            "raw": data,
        }

    async def refund(
        self,
        out_trade_no: str,
        amount_cents: int,
        out_refund_no: str,
        reason: str = "",
        total_cents: int = 0,
    ) -> dict[str, Any]:
        params = {
            "appid": self.one("appid"),
            "out_trade_order": out_trade_no,
            "refund_fee": _yuan(amount_cents),
            "reason": (reason or "用户申请退款")[:64],
            "time": str(int(time.time())),
            "nonce_str": uuid.uuid4().hex,
        }
        node = await self._post("/payment/refund.html", params)
        ok = int(node.get("errcode") or 0) == 0
        return {
            "ok": ok,
            "refund_trade_no": str((node.get("data") or {}).get("refund_id", "")),
            "message": node.get("errmsg") or ("退款已受理" if ok else "退款失败"),
            "raw": node,
        }

    async def verify_notify(self, headers: dict[str, str], body: bytes) -> NotifyResult:
        text = body.decode("utf-8", errors="replace")
        params = dict(parse_qsl(text, keep_blank_values=True))
        given = params.pop("hash", "")
        if not given:
            return NotifyResult(ok=False, error="回调缺少 hash", reply="fail", raw=params)

        expect = _sign(params, self.one("appsecret"))
        if expect.lower() != given.lower():
            log.warning("payment.xunhupay.notify_verify_failed",
                        out_trade_no=params.get("trade_order_id", ""))
            return NotifyResult(ok=False, error="回调验签失败", reply="fail", raw=params)

        status = str(params.get("status", ""))
        return NotifyResult(
            ok=True,
            out_trade_no=params.get("trade_order_id", ""),
            trade_no=str(params.get("transaction_id", "")),
            amount_cents=_to_cents(params.get("total_fee")),
            paid=status in PAID_STATUS,
            close=status not in PAID_STATUS and status != "",
            raw=params,
            reply="success",
        )
