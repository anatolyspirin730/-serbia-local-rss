import re
import urllib.request
from html import unescape

URLS = [
    (
        "Subotica.com",
        "https://www.subotica.com/vesti/izbori-2026-od-cetvrtka-prijave-za-glasanje-van-birackog-mesta-objavljeni-brojevi-telefona-id55262.html",
    ),
    (
        "Subotičke",
        "https://suboticke.rs/jasna-vojnic-izbori-hrvatsko-nacionalno-vece/",
    ),
]

PATTERNS = {
    "article:published_time": (
        r'<meta[^>]+(?:property|name)=["\']article:published_time["\']'
        r'[^>]+content=["\']([^"\']+)'
    ),
    "datePublished JSON-LD": (
        r'"datePublished"\s*:\s*"([^"]+)"'
    ),
    "datePublished meta": (
        r'<meta[^>]+(?:itemprop|name)=["\']datePublished["\']'
        r'[^>]+content=["\']([^"\']+)'
    ),
    "time datetime": (
        r'<time\b[^>]*datetime=["\']([^"\']+)'
    ),
    "pubdate": (
        r'<[^>]+(?:pubdate|date-published)[^>]*>'
    ),
}


def download(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def main():
    for name, url in URLS:
        print(f"\n=== {name} ===")
        print(f"URL: {url}")

        try:
            html = download(url)
            print(f"HTML length: {len(html)}")

            found = False

            for label, pattern in PATTERNS.items():
                matches = re.findall(
                    pattern,
                    html,
                    flags=re.IGNORECASE,
                )

                if matches:
                    found = True
                    print(f"{label}: {matches[:5]}")

            if not found:
                print("NO STRUCTURED PUBLICATION DATE FOUND")

            print("\nDATE-RELATED HTML FRAGMENTS:")

            fragments = re.findall(
                r'.{0,100}(?:published|datetime|datum|datePublished|entry-date).{0,150}',
                html,
                flags=re.IGNORECASE,
            )

            for fragment in fragments[:10]:
                print(
                    unescape(
                        re.sub(r"\s+", " ", fragment)
                    )[:250]
                )

        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
