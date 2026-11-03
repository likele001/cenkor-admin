"""支付宝官方（开放平台）驱动。

覆盖：当面付扫码（默认）/ 电脑网站支付 / 手机网站支付
签名：RSA2（SHA256withRSA）；异步通知验签排除 sign 与 sign_type
金额：内部「分」<-> 支付宝「元」
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx
import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from cenkor_admin.apps.payment.drivers.base import (
    NotifyResult,
    PayError,
    PaymentDriver,
    PayRequest,
    PayResult,
    register_driver,
)

log = structlog.get_logger()

LIVE_GATEWAY = "https://openapi.alipay.com/gateway.do"
SANDBOX_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
PAID_STATES = {"TRADE_SUCCESS", "TRADE_FINISHED"}


def _ensure_pem(raw: str, label: str) -> bytes:
    """兼容用户直接粘贴一行 base64（无 PEM 头）。"""
    text = (raw or "").strip()
    if "-----BEGIN" in text:
        return text.encode()
    body = "".join(text.split())
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return (
        f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"
    ).encode()


def _load_private_key(raw: str):
    for label in ("PRIVATE KEY", "RSA PRIVATE KEY"):
        try:
            return serialization.load_pem_private_key(_ensure_pem(raw, label), password=None)
        except Exception:
            continue
    raise PayError("支付宝应用私钥格式不正确", code="bad_private_key")


def _load_public_key(raw: str):
    try:
        return serialization.load_pem_public_key(_ensure_pem(raw, "PUBLIC KEY"))
    except Exception as exc:
        raise PayError("支付宝公钥格式不正确", detail=str(exc), code="bad_public_key")


def _yuan(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _to_cents(amount: Any) -> int:
    try:
        return round(float(amount) * 100)
    except Exception:
        return 0


def _sign_content(params: dict[str, Any]) -> str:
    """待签串：按 key 字典序拼接，跳过 sign 与 None（空串保留）。"""
    items = sorted(
        (k, str(v)) for k, v in params.items() if v is not None and k != "sign"
    )
    return "&".join(f"{k}={v}" for k, v in items)


def _extract_raw_json(text: str, key: str) -> str:
    """从响应原文里抠出某个 key 对应的原始 JSON 子串（验签必须用原文）。"""
    marker = f'"{key}"'
    idx = text.find(marker)
    if idx < 0:
        return ""
    colon = text.find(":", idx + len(marker))
    if colon < 0:
        return ""
    sub = text[colon + 1:].lstrip()
    try:
        _, end = json.JSONDecoder().raw_decode(sub)
    except Exception:
        return ""
    return sub[:end]


@register_driver
class AlipayDriver(PaymentDriver):
    provider = "alipay"
    display_name = "支付宝（官方）"
    supports_refund = True
    config_fields = [
        {"key": "app_id", "label": "应用 AppID", "type": "text", "required": True,
         "placeholder": "2021000000000000"},
        {"key": "private_key", "label": "应用私钥", "type": "textarea", "required": True,
         "secret": True, "placeholder": "-----BEGIN PRIVATE KEY-----"},
        {"key": "alipay_public_key", "label": "支付宝公钥", "type": "textarea", "required": True,
         "secret": True, "placeholder": "-----BEGIN PUBLIC KEY-----"},
        {"key": "gateway", "label": "网关地址", "type": "text", "required": False,
         "placeholder": LIVE_GATEWAY, "hint": "留空则按环境自动选择"},
        {"key": "sign_type", "label": "签名算法", "type": "select", "required": False,
         "default": "RSA2", "options": [{"value": "RSA2", "label": "RSA2（推荐）"}]},
        {"key": "verify_response", "label": "校验响应签名", "type": "switch", "required": False,
         "default": True, "hint": "生产环境建议开启"},
    ]

    # ---------- 内部工具 ----------

    def _gateway(self) -> str:
        gw = self.one("gateway")
        if gw:
            return gw
        return SANDBOX_GATEWAY if self.mode == "sandbox" else LIVE_GATEWAY

    def _base_params(
        self, method: str, biz: dict, notify_url: str = "", return_url: str = "",
    ) -> dict[str, str]:
        params = {
            "app_id": self.one("app_id"),
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": self.one("sign_type", "RSA2"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz, separators=(",", ":"), ensure_ascii=False),
        }
        if notify_url:
            params["notify_url"] = notify_url
        if return_url:
            params["return_url"] = return_url
        return params

    def _sign(self, params: dict[str, Any]) -> str:
        content = _sign_content(params)
        key = _load_private_key(self.one("private_key"))
        sig = key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()

    def _verify_enabled(self) -> bool:
        val = self.config.get("verify_response")
        if val is None or val == "":
            return True
        return str(val).lower() not in ("false", "0", "no", "off")

    def _verify_response(self, text: str, data: dict, method: str) -> None:
        if not self._verify_enabled():
            return
        pub_raw = self.one("alipay_public_key")
        sign = data.get("sign")
        if not pub_raw or not sign:
            return
        node_str = _extract_raw_json(text, f"{method.replace('.', '_')}_response")
        if not node_str:
            log.warning("payment.alipay.response_raw_not_found", method=method)
            return
        try:
            _load_public_key(pub_raw).verify(
                base64.b64decode(sign), node_str.encode("utf-8"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except Exception as exc:
            raise PayError("支付宝响应验签失败", detail=str(exc), code="bad_response_sign") from exc

    @staticmethod
    def _node(data: dict, key: str) -> dict:
        return data.get(key) or {}

    async def _call(
        self, method: str, biz: dict, *, notify_url: str = "", return_url: str = "",
    ) -> dict:
        params = self._base_params(method, biz, notify_url, return_url)
        params["sign"] = self._sign(params)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(self._gateway(), data=params)
        except Exception as exc:
            raise PayError("无法连接支付宝网关", detail=str(exc), code="network") from exc

        text = resp.text
        try:
            data = json.loads(text)
        except Exception as exc:
            raise PayError("支付宝返回内容无法解析", detail=text[:500], code="bad_response") from exc
        self._verify_response(text, data, method)
        return data

    # ---------- 对外能力 ----------

    async def create_pay(self, req: PayRequest) -> PayResult:
        pay_method = (req.extra or {}).get("pay_method") or "precreate"
        if pay_method == "page":
            return await self._page_pay(req, "alipay.trade.page.pay", "FAST_INSTANT_TRADE_PAY")
        if pay_method == "wap":
            return await self._page_pay(req, "alipay.trade.wap.pay", "QUICK_WAP_WAY")
        return await self._precreate(req)

    async def _precreate(self, req: PayRequest) -> PayResult:
        biz = {
            "out_trade_no": req.out_trade_no,
            "total_amount": _yuan(req.amount_cents),
            "subject": (req.subject or "订单支付")[:256],
        }
        data = await self._call("alipay.trade.precreate", biz, notify_url=req.notify_url)
        node = self._node(data, "alipay_trade_precreate_response")
        if node.get("code") != "10000":
            raise PayError(
                f"支付宝下单失败：{node.get('sub_msg') or node.get('msg') or '未知错误'}",
                detail=json.dumps(node, ensure_ascii=False)[:500],
                code=node.get("sub_code", ""),
            )
        return PayResult(
            mode="qrcode",
            payload={
                "code_url": node.get("qr_code", ""),
                "out_trade_no": req.out_trade_no,
                "amount_cents": req.amount_cents,
            },
            raw=node,
        )

    async def _page_pay(self, req: PayRequest, method: str, product_code: str) -> PayResult:
        biz = {
            "out_trade_no": req.out_trade_no,
            "total_amount": _yuan(req.amount_cents),
            "subject": (req.subject or "订单支付")[:256],
            "product_code": product_code,
        }
        if req.return_url:
            biz["quit_url"] = req.return_url
        params = self._base_params(method, biz, req.notify_url, req.return_url)
        params["sign"] = self._sign(params)
        return PayResult(
            mode="redirect",
            payload={"url": f"{self._gateway()}?{urlencode(params)}", "out_trade_no": req.out_trade_no},
            raw={k: v for k, v in params.items() if k != "sign"},
        )

    async def query(self, out_trade_no: str) -> dict[str, Any]:
        data = await self._call("alipay.trade.query", {"out_trade_no": out_trade_no})
        node = self._node(data, "alipay_trade_query_response")
        status = node.get("trade_status", "")
        if node.get("code") != "10000":
            return {
                "paid": False,
                "status": status or node.get("code", ""),
                "trade_no": node.get("trade_no", ""),
                "amount_cents": 0,
                "message": node.get("sub_msg") or node.get("msg") or "",
                "raw": node,
            }
        return {
            "paid": status in PAID_STATES,
            "status": status,
            "trade_no": node.get("trade_no", ""),
            "amount_cents": _to_cents(node.get("total_amount")),
            "message": "",
            "raw": node,
        }

    async def refund(
        self,
        out_trade_no: str,
        amount_cents: int,
        out_refund_no: str,
        reason: str = "",
        total_cents: int = 0,
    ) -> dict[str, Any]:
        biz = {
            "out_trade_no": out_trade_no,
            "refund_amount": _yuan(amount_cents),
            "out_request_no": out_refund_no,
        }
        if reason:
            biz["refund_reason"] = reason[:256]
        data = await self._call("alipay.trade.refund", biz)
        node = self._node(data, "alipay_trade_refund_response")
        ok = node.get("code") == "10000"
        return {
            "ok": ok,
            "refund_trade_no": node.get("trade_no", ""),
            "message": node.get("sub_msg") or node.get("msg") or ("退款已受理" if ok else "退款失败"),
            "raw": node,
        }

    async def verify_notify(self, headers: dict[str, str], body: bytes) -> NotifyResult:
        text = body.decode("utf-8", errors="replace")
        params = dict(parse_qsl(text, keep_blank_values=True))
        sign = params.pop("sign", "")
        params.pop("sign_type", None)
        if not sign:
            return NotifyResult(ok=False, error="回调缺少 sign", reply="failure", raw=params)

        try:
            content = _sign_content(params)
            _load_public_key(self.one("alipay_public_key")).verify(
                base64.b64decode(sign), content.encode("utf-8"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except Exception as exc:
            log.warning("payment.alipay.notify_verify_failed", error=str(exc),
                        out_trade_no=params.get("out_trade_no", ""))
            return NotifyResult(ok=False, error=f"验签失败：{exc}", reply="failure", raw=params)

        status = params.get("trade_status", "")
        return NotifyResult(
            ok=True,
            out_trade_no=params.get("out_trade_no", ""),
            trade_no=params.get("trade_no", ""),
            amount_cents=_to_cents(params.get("total_amount")),
            paid=status in PAID_STATES,
            close=status == "TRADE_CLOSED",
            raw=params,
            reply="success",
        )
