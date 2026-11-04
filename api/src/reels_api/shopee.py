"""Shopee Affiliate Open API (GraphQL), called only from the worker with a member's own App ID and Secret.

Three calls: `productOfferV2` (search products, or read one again by its item id), `generateShortLink` (a member's
affiliate link, with sub ids naming the video and the Page) and `conversionReport` (orders credited to the account).
A pasted short link (s.shopee.vn) is only asked where it redirects, to read the item id from the address; the page
itself is never opened or read.

Shopee publishes its API documentation only inside the affiliate dashboard, so the signature, the field names, the
sort numbers and the shop type codes below follow third-party clients and are tested only against the fake service
(api/scripts/fake_services.py). This file is the one place to change them.
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from . import config

REQUEST_TIMEOUT = 20
SORT_BY_SALES = 2  # productOfferV2 sortType: 1 relevance, 2 items sold, 5 commission
# productOfferV2's shopType codes, strongest first: Mall (official shop), Yêu Thích+, Yêu Thích.
SHOP_TYPE_CODES = {1: "mall", 4: "preferred_plus", 2: "preferred"}
AUTH_ERRORS = {10020, 10035}
RATE_LIMIT_ERRORS = {10030}
REPORT_PAGES = 10  # pages of conversionReport read per account and round
REPORT_PAGE_SIZE = 500


class ShopeeError(Exception):
    """`message` is shown to members, `detail` is diagnostic."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class Credentials:
    app_id: str
    secret: str = field(repr=False)


@dataclass(frozen=True)
class Offer:
    item_id: int
    name: str
    shop_name: str
    shop_type: str  # a key of affiliate.SHOP_TYPES["shopee"]
    rating: float
    sold: int
    price: int  # VND
    commission_rate: float  # percent
    page_url: str
    image_url: str | None
    commission_end_at: datetime | None


@dataclass(frozen=True)
class Conversion:
    external_id: str  # order and item, unique per account
    purchased_at: datetime
    item_name: str
    commission: int  # VND
    status: str
    sub_ids: list[str]


def _signed(credentials: Credentials, payload: str) -> str:
    timestamp = str(int(time.time()))
    signature = hashlib.sha256(f"{credentials.app_id}{timestamp}{payload}{credentials.secret}".encode()).hexdigest()
    return f"SHA256 Credential={credentials.app_id}, Timestamp={timestamp}, Signature={signature}"


def _call(credentials: Credentials, query: str) -> dict:
    payload = json.dumps({"query": query}, ensure_ascii=False)
    request = urllib.request.Request(
        config.shopee_affiliate_api_url(),
        data=payload.encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": _signed(credentials, payload)},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as err:
        detail = f"HTTP {err.code}: {err.read(2000).decode('utf-8', 'replace')}"
        if err.code in (401, 403):
            raise ShopeeError(
                "Shopee từ chối App ID/Secret, hãy kiểm tra lại trong Tài khoản affiliate", detail
            ) from None
        raise ShopeeError(f"Shopee đang lỗi (HTTP {err.code}), thử lại sau", detail) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except OSError as err:
        raise ShopeeError("Không kết nối được Shopee, kiểm tra mạng rồi thử lại", str(err)) from None
    except ValueError as err:
        raise ShopeeError("Shopee trả dữ liệu không đọc được, thử lại sau", str(err)) from None
    errors = body.get("errors") if isinstance(body, dict) else None
    if errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        code = (first.get("extensions") or {}).get("code")
        detail = json.dumps(errors, ensure_ascii=False)[:2000]
        if code in AUTH_ERRORS:
            raise ShopeeError("Shopee từ chối App ID/Secret, hãy kiểm tra lại trong Tài khoản affiliate", detail)
        if code in RATE_LIMIT_ERRORS:
            raise ShopeeError("Shopee đang giới hạn lượt gọi, thử lại sau", detail)
        raise ShopeeError(f"Shopee báo lỗi: {first.get('message') or 'không rõ'}", detail)
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise ShopeeError("Shopee trả dữ liệu không đọc được, thử lại sau", str(body)[:2000])
    return body["data"]


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _number(value: object, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _shop_type(codes: object) -> str:
    codes = codes if isinstance(codes, list) else [codes]
    return next((name for code, name in SHOP_TYPE_CODES.items() if code in codes), "other")


def _at(seconds: object) -> datetime | None:
    value = int(_number(seconds))
    return datetime.fromtimestamp(value, UTC) if value > 0 else None


OFFER_FIELDS = (
    "itemId productName shopName shopType ratingStar sales priceMin commissionRate productLink imageUrl periodEndTime"
)


def _offer(node: dict) -> Offer | None:
    try:
        item_id = int(node["itemId"])
        name = str(node["productName"]).strip()
    except (KeyError, TypeError, ValueError):
        return None
    if not name:
        return None
    return Offer(
        item_id=item_id,
        name=name[:300],
        shop_name=str(node.get("shopName") or "Shop")[:200],
        shop_type=_shop_type(node.get("shopType")),
        rating=round(_number(node.get("ratingStar")), 2),
        sold=int(_number(node.get("sales"))),
        price=round(_number(node.get("priceMin"))),
        # Shopee gives the rate as a fraction ("0.07"); the app keeps percent.
        commission_rate=round(_number(node.get("commissionRate")) * 100, 2),
        page_url=str(node.get("productLink") or ""),
        image_url=node.get("imageUrl") or None,
        commission_end_at=_at(node.get("periodEndTime")),
    )


def _offers(data: dict) -> list[Offer]:
    nodes = ((data.get("productOfferV2") or {}).get("nodes")) or []
    return [offer for offer in (_offer(node) for node in nodes if isinstance(node, dict)) if offer]


def search(credentials: Credentials, keyword: str, limit: int = 20) -> list[Offer]:
    query = (
        f"{{productOfferV2(keyword: {_quoted(keyword)}, sortType: {SORT_BY_SALES}, page: 1, limit: {limit})"
        f" {{nodes {{{OFFER_FIELDS}}}}}}}"
    )
    return _offers(_call(credentials, query))


def offer(credentials: Credentials, item_id: int) -> Offer | None:
    """The product as Shopee offers it now; None when it no longer has an affiliate offer."""
    query = f"{{productOfferV2(itemId: {int(item_id)}, page: 1, limit: 1) {{nodes {{{OFFER_FIELDS}}}}}}}"
    found = _offers(_call(credentials, query))
    return found[0] if found else None


PRODUCT_HOSTS = {"shopee.vn", "www.shopee.vn", "m.shopee.vn"}
SHORT_HOSTS = {"s.shopee.vn", "shp.ee", "shope.ee"}
# shopee.vn/product/<shop>/<item>, shopee.vn/<name>-i.<shop>.<item>, and the affiliate redirect's
# shopee.vn/<anything>/<shop>/<item>.
ITEM_IN_NAME = re.compile(r"-i\.(\d+)\.(\d+)$")
ITEM_IN_PATH = re.compile(r"/(\d+)/(\d+)/?$")


def is_shopee_link(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() in PRODUCT_HOSTS | SHORT_HOSTS


def item_id_of(url: str) -> int | None:
    """The item id a product page link names; None for a short link or anything else."""
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in PRODUCT_HOSTS:
        return None
    path = urllib.parse.unquote(parts.path)
    match = ITEM_IN_NAME.search(path) or ITEM_IN_PATH.search(path)
    return int(match.group(2)) if match else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def resolve(url: str) -> str:
    """Where a short link leads, read from its redirect without opening the page; a product link comes back as it
    is. Raises ShopeeError."""
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in SHORT_HOSTS:
        return url
    target = f"{config.shopee_short_link_url()}{parts.path}"
    request = urllib.request.Request(target, method="HEAD")
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=REQUEST_TIMEOUT):
            pass
    except urllib.error.HTTPError as err:
        location = err.headers.get("Location") if 300 <= err.code < 400 else None
        if location:
            return urllib.parse.urljoin(target, location)
        raise ShopeeError("Link Shopee không mở được, hãy kiểm tra lại link", f"HTTP {err.code}") from None
    except OSError as err:
        raise ShopeeError("Không kết nối được Shopee, kiểm tra mạng rồi thử lại", str(err)) from None
    raise ShopeeError("Link Shopee không dẫn tới sản phẩm nào, hãy kiểm tra lại link", target)


def short_link(credentials: Credentials, origin_url: str, sub_ids: list[str]) -> str:
    query = (
        f"mutation {{generateShortLink(input: {{originUrl: {_quoted(origin_url)}, subIds: {json.dumps(sub_ids)}}})"
        " {shortLink}}"
    )
    link = ((_call(credentials, query).get("generateShortLink")) or {}).get("shortLink")
    if not isinstance(link, str) or not link.startswith(("http://", "https://")):
        raise ShopeeError("Shopee không trả link affiliate, thử lại sau", str(link))
    return link


def conversions(credentials: Credentials, start: datetime, end: datetime) -> list[Conversion]:
    """Every order item bought between `start` and `end`, at most REPORT_PAGES pages."""
    found: list[Conversion] = []
    scroll = ""
    for _ in range(REPORT_PAGES):
        scroll_arg = f", scrollId: {_quoted(scroll)}" if scroll else ""
        query = (
            f"{{conversionReport(purchaseTimeStart: {int(start.timestamp())}, purchaseTimeEnd: {int(end.timestamp())},"
            f" limit: {REPORT_PAGE_SIZE}{scroll_arg}) {{nodes {{purchaseTime conversionId utmContent"
            " orders {orderId orderStatus items {itemId itemName itemTotalCommission}}} pageInfo {hasNextPage scrollId}}}"
        )
        report = _call(credentials, query).get("conversionReport") or {}
        for node in report.get("nodes") or []:
            purchased = _at(node.get("purchaseTime")) or datetime.now(UTC)
            sub_ids = [part for part in str(node.get("utmContent") or "").split("-") if part]
            for order in node.get("orders") or []:
                for item in order.get("items") or []:
                    found.append(
                        Conversion(
                            external_id=f"{order.get('orderId')}:{item.get('itemId')}"[:100],
                            purchased_at=purchased,
                            item_name=str(item.get("itemName") or "")[:300],
                            commission=round(_number(item.get("itemTotalCommission"))),
                            status=str(order.get("orderStatus") or "")[:32],
                            sub_ids=sub_ids,
                        )
                    )
        page = report.get("pageInfo") or {}
        scroll = page.get("scrollId") or ""
        if not page.get("hasNextPage") or not scroll:
            break
    return found
