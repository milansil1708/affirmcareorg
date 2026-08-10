import re
import urllib.request
from html import unescape

from django.core.cache import cache


NEWS_FEEDS = {
    "Latest News": "https://tools.prnewswire.com/en-us/live/28741/rss/fulltext",
    "Policy & Legislation": "https://tools.prnewswire.com/en-us/live/28745/rss/fulltext",
    "Research": "https://tools.prnewswire.com/en-us/live/28747/rss/fulltext",
    "Education": "https://tools.prnewswire.com/en-us/live/28748/rss/fulltext",
    "Healthcare": "https://tools.prnewswire.com/en-us/live/28746/rss/fulltext",
    "AI & Health Care": "https://tools.prnewswire.com/en-us/live/28749/rss/fulltext",
}


def clean_text(value):
    if not value:
        return ""

    value = unescape(value)

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def clean_url(value):
    """
    Clean RSS article URLs so malformed trailing characters
    such as '"/' are removed.
    """
    if not value:
        return ""

    value = unescape(value).strip()

    # Remove surrounding quotation marks if present.
    value = value.strip('"').strip("'").strip()

    # Remove a stray trailing slash after a quotation mark
    # or a trailing slash after a PRNewswire .html URL.
    value = re.sub(
        r'(["\']?)/$',
        "",
        value,
    )

    # Remove any remaining surrounding quotation marks.
    value = value.strip('"').strip("'").strip()

    return value


def extract_tag(block, tag):
    pattern = (
        rf"<{tag}(?:\s[^>]*)?>"
        rf"(.*?)"
        rf"</{tag}>"
    )

    match = re.search(
        pattern,
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return ""

    return match.group(1).strip()


def fetch_news_feed(url, limit=6):
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            raw_data = response.read()

        xml_text = raw_data.decode(
            "utf-8",
            errors="replace",
        )

        item_blocks = re.findall(
            r"<item\b[^>]*>(.*?)</item\s*>",
            xml_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        stories = []

        for block in item_blocks:
            title = extract_tag(block, "title")
            link = extract_tag(block, "link")
            description = extract_tag(block, "description")
            pub_date = extract_tag(block, "pubDate")

            title = clean_text(title)
            description = clean_text(description)
            link = clean_url(link)
            pub_date = clean_text(pub_date)

            if not title:
                continue

            # Some RSS feeds put the link in an encoded form.
            # Try to find a PRNewswire URL if the normal link is missing.
            if not link:
                url_match = re.search(
                    r"https?://www\.prnewswire\.com/[^\s\"<]+",
                    block,
                    flags=re.IGNORECASE,
                )

                if url_match:
                    link = clean_url(url_match.group(0))

            if not link:
                continue

            stories.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                }
            )

            if len(stories) >= limit:
                break

        return stories

    except Exception:
        return []


def get_news_sections():
    sections = []

    for category, url in NEWS_FEEDS.items():
        cache_key = (
            "affirmcare_news_v6_"
            f"{category.lower().replace(' ', '_')}"
        )

        stories = cache.get(cache_key)

        if stories is None:
            stories = fetch_news_feed(url)
            cache.set(
                cache_key,
                stories,
                900,
            )

        sections.append(
            {
                "category": category,
                "stories": stories,
            }
        )

    return sections
