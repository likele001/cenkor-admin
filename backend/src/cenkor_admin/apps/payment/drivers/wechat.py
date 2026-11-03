"""微信支付官方驱动（APIv3）。

覆盖：Native 扫码（默认）/ JSAPI
签名：商户私钥 SHA256withRSA，Authorization 头 WECHATPAY2-SHA256-RSA2048
回调：APIv3 密钥 AES-256-GCM 解密 resource；配置了平台证书则额外验签
金额：内部与微信一致，均为「分」
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import httpx
import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cenkor_admin.apps.payment.drivers.base import (
    NotifyResult,
    PayError,
    PaymentDriver,
    PayRequest,
    PayResult,
    register_driver,
)

log = structlog.get_logger()

LIVE_BASE = "https://api.mch.weixin.qq.com"


def _ensure_pem(raw: str, label: str) -> bytes:
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
    raise PayError("微信商户私钥格式不正确（需 apiclient_key.pem）", code="bad_private_key")


def _load_public_key(raw: str):
    for label in ("PUBLIC KEY", "CERTIFICATE"):
        try:
            if label == "CERTIFICATE":
                from cryptography import x509
                cert = x509.load_pem_x509_certificate(_ensure_pem(raw, label))
                return cert.public_key()
            return serialization.load_pem_public_key(_ensure_pem(raw, label))
        except Exception:
            continue
    raise PayError("微信支付平台证书格式不正确", code="bad_public_key")


@register_driver
class WechatDriver(PaymentDriver):
    provider = "wechat"
    display_name = "微信支付（官方）"
    supports_refund = True
    config_fields = [
        {"key": "app_id", "label": "AppID", "type": "text", "required": True,
         "placeholder": "wx1234567890abcd",
         "hint": "公众号 / 小程序 / APP 的 AppID，wx 开头共 18 位"},
        {"key": "mch_id", "label": "商户号", "type": "text", "required": True,
         "placeholder": "1600000000"},
        {"key": "api_v3_key", "label": "APIv3 密钥", "type": "text", "required": True,
         "secret": True, "placeholder": "32 位字符串", "hint": "用于回调解密，务必与商户平台一致"},
        {"key": "cert_serial_no", "label": "商户证书序列号", "type": "text", "required": True,
         "placeholder": "以 16 进制表示"},
        {"key": "private_key", "label": "商户私钥", "type": "textarea", "required": True,
         "secret": True, "placeholder": "-----BEGIN PRIVATE KEY-----", "hint": "apiclient_key.pem"},
        {"key": "platform_cert", "label": "平台证书", "type": "textarea", "required": False,
         "secret": True, "placeholder": "-----BEGIN CERTIFICATE-----",
         "hint": "填写后回调会额外验签，更安全"},
    ]

    # ---------- 内部工具 ----------

    def _base(self) -> str:
        return self.one("base_url", LIVE_BASE).rstrip("/") or LIVE_BASE

    def _auth_header(self, method: str, url_path: str, body_str: str) -> str:
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body_str}\n"
        key = _load_private_key(self.one("private_key"))
        signature = base64.b64encode(
            key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        ).decode()
        return (
            'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{self.one("mch_id")}",'
            f'nonce_str="{nonce}",'
            f'signature="{signature}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{self.one("cert_serial_no")}"'
        )

    async def _request(
        self, method: str, url_path: str, payload: dict | None = None,
    ) -> tuple[int, dict]:
        body_str = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False) if payload is not None else ""
        headers = {
            "Authorization": self._auth_header(method, url_path, body_str),
            "Accept": "application/json",
            "User-Agent": "cenkor-payment/1.0",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        url = self._base() + url_path
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                else:
                    resp = await client.post(url, content=body_str.encode("utf-8"), headers=headers)
        except Exception as exc:
            raise PayError("无法连接微信支付网关", detail=str(exc), code="network") from exc

        text = resp.text or ""
        try:
            data = json.loads(text) if text.strip() else {}
        except Exception:
            data = {"_raw": text[:500]}
        return resp.status_code, data

    @staticmethod
    def _fail(node: dict, fallback: str = "微信支付请求失败") -> PayError:
        msg = node.get("message") or fallback
        code = node.get("code", "")
        return PayError(f"{fallback}：{msg}", detail=json.dumps(node, ensure_ascii=False)[:500], code=code)

    # ---------- 对外能力 ----------

    async def create_pay(self, req: PayRequest) -> PayResult:
        pay_method = (req.extra or {}).get("pay_method") or "native"
        if pay_method == "jsapi":
            if not req.openid:
                raise PayError("JSAPI 下单需要 openid", code="missing_openid")
            return await self._jsapi(req)
        return await self._native(req)

    async def _native(self, req: PayRequest) -> PayResult:
        path = "/v3/pay/transactions/native"
        payload = {
            "appid": self.one("app_id"),
            "mchid": self.one("mch_id"),
            "description": (req.description or req.subject or "订单支付")[:127],
            "out_trade_no": req.out_trade_no,
            "notify_url": req.notify_url,
            "amount": {"total": req.amount_cents, "currency": "CNY"},
        }
        status, node = await self._request("POST", path, payload)
        if status not in (200, 201):
            raise self._fail(node, "微信下单失败")
        return PayResult(
            mode="qrcode",
            payload={
                "code_url": node.get("code_url", ""),
                "out_trade_no": req.out_trade_no,
                "amount_cents": req.amount_cents,
            },
            raw=node,
        )

    async def _jsapi(self, req: PayRequest) -> PayResult:
        path = "/v3/pay/transactions/jsapi"
        payload = {
            "appid": self.one("app_id"),
            "mchid": self.one("mch_id"),
            "description": (req.description or req.subject or "订单支付")[:127],
            "out_trade_no": req.out_trade_no,
            "notify_url": req.notify_url,
            "amount": {"total": req.amount_cents, "currency": "CNY"},
            "payer": {"openid": req.openid},
        }
        status, node = await self._request("POST", path, payload)
        if status not in (200, 201):
            raise self._fail(node, "微信 JSAPI 下单失败")
        prepay_id = node.get("prepay_id", "")
        return PayResult(mode="jsapi", payload=self._jsapi_params(prepay_id), raw=node)

    def _jsapi_params(self, prepay_id: str) -> dict:
        """构造 wx.chooseWXPay 调起参数（需对 package 再签一次名）。"""
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        pkg = f"prepay_id={prepay_id}"
        message = f"{self.one('app_id')}\n{timestamp}\n{nonce}\n{pkg}\n"
        key = _load_private_key(self.one("private_key"))
        pay_sign = base64.b64encode(
            key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        ).decode()
        return {
            "appId": self.one("app_id"),
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": pkg,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    async def query(self, out_trade_no: str) -> dict[str, Any]:
        path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={self.one('mch_id')}"
        status, node = await self._request("GET", path)
        if status != 200:
            return {
                "paid": False,
                "status": node.get("code", str(status)),
                "trade_no": "",
                "amount_cents": 0,
                "message": node.get("message", ""),
                "raw": node,
            }
        state = node.get("trade_state", "")
        return {
            "paid": state == "SUCCESS",
            "status": state,
            "trade_no": node.get("transaction_id", ""),
            "amount_cents": int((node.get("amount") or {}).get("total") or 0),
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
        path = "/v3/refund/domestic/refunds"
        payload = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "reason": (reason or "用户申请退款")[:80],
            "amount": {
                "refund": amount_cents,
                "total": total_cents or amount_cents,
                "currency": "CNY",
            },
        }
        status, node = await self._request("POST", path, payload)
        if status not in (200, 201):
            return {
                "ok": False,
                "refund_trade_no": "",
                "message": node.get("message", "退款失败"),
                "raw": node,
            }
        return {
            "ok": node.get("status") in ("SUCCESS", "PROCESSING"),
            "refund_trade_no": node.get("refund_id", ""),
            "message": node.get("status", ""),
            "raw": node,
        }

    async def verify_notify(self, headers: dict[str, str], body: bytes) -> NotifyResult:
        headers = {str(k).lower(): v for k, v in (headers or {}).items()}
        text = body.decode("utf-8", errors="replace")
        try:
            envelope = json.loads(text)
        except Exception as exc:
            return NotifyResult(ok=False, error=f"回调非 JSON：{exc}", reply="", raw={})

        resource = envelope.get("resource") or {}
        ciphertext_b64 = resource.get("ciphertext")
        if not ciphertext_b64:
            return NotifyResult(ok=False, error="回调缺少 resource.ciphertext",
                                reply="", raw=envelope)

        # 可选：平台证书验签
        platform_cert = self.one("platform_cert")
        if platform_cert and not self._verify_signature(headers, text, platform_cert):
            return NotifyResult(ok=False, error="回调验签失败",
                                reply="", raw=envelope)

        try:
            plain = AESGCM(self.one("api_v3_key").encode("utf-8")).decrypt(
                (resource.get("nonce") or "").encode("utf-8"),
                base64.b64decode(ciphertext_b64),
                (resource.get("associated_data") or "").encode("utf-8") or None,
            )
            data = json.loads(plain.decode("utf-8"))
        except Exception as exc:
            log.warning("payment.wechat.notify_decrypt_failed", error=str(exc))
            return NotifyResult(ok=False, error=f"回调解密失败：{exc}", reply="", raw=envelope)

        state = data.get("trade_state", "")
        return NotifyResult(
            ok=True,
            out_trade_no=data.get("out_trade_no", ""),
            trade_no=data.get("transaction_id", ""),
            amount_cents=int((data.get("amount") or {}).get("total") or 0),
            paid=state == "SUCCESS",
            close=state == "CLOSED",
            raw=data,
            reply=json.dumps({"code": "SUCCESS", "message": "成功"}),
            content_type="application/json",
        )

    @staticmethod
    def _verify_signature(headers: dict[str, str], body_text: str, platform_cert: str) -> bool:
        timestamp = headers.get("wechatpay-timestamp", "")
        nonce = headers.get("wechatpay-nonce", "")
        signature = headers.get("wechatpay-signature", "")
        if not (timestamp and nonce and signature):
            return False
        message = f"{timestamp}\n{nonce}\n{body_text}\n"
        try:
            _load_public_key(platform_cert).verify(
                base64.b64decode(signature), message.encode("utf-8"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
            return True
        except Exception as exc:
            log.warning("payment.wechat.notify_verify_failed", error=str(exc))
            return False
