"""Stock photo sites and their image servers. What is reached from Google Ảnh on them is their watermarked preview,
sold under licence: a pasted link from one is warned about, and an automatic pick from Google never uses one."""

import urllib.parse

STOCK_SITES = {
    "shutterstock.com": "Shutterstock",
    "gettyimages.com": "Getty Images",
    "istockphoto.com": "iStock",
    "alamy.com": "Alamy",
    "123rf.com": "123RF",
    "dreamstime.com": "Dreamstime",
    "depositphotos.com": "Depositphotos",
    "stock.adobe.com": "Adobe Stock",
    "ftcdn.net": "Adobe Stock",
    "canstockphoto.com": "Can Stock Photo",
    "bigstockphoto.com": "Bigstock",
    "vectorstock.com": "VectorStock",
    "pond5.com": "Pond5",
}


def stock_site(url: str) -> str | None:
    """The stock photo site a link belongs to (its own pages or its image servers), or None."""
    host = (urllib.parse.urlsplit(url.strip()).hostname or "").lower().rstrip(".")
    for domain, name in STOCK_SITES.items():
        if host == domain or host.endswith("." + domain) or (domain.count(".") == 1 and _country_site(host, domain)):
            return name
    return None


def _country_site(host: str, domain: str) -> bool:
    """gettyimages.co.uk, shutterstock.vn…: the same site under a country's domain."""
    name = domain.split(".")[0]
    labels = host.split(".")
    if name not in labels:
        return False
    rest = labels[len(labels) - labels[::-1].index(name) :]
    return len(rest) == 1 or (len(rest) == 2 and rest[0] in ("co", "com"))
