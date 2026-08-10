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


def clean_html(text):
    if not text:
        return ""

    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_tag_value(block, tag):
    pattern = rf"<{tag}(?:\s[^>]*)?>(.*?)</{tag}>"

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
                "User-Agent": "Mozilla/5.0 (compatible; AffirmCare/1.0)",
                "Accept": "*/*",
            },
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            raw_data = response.read()

        xml_text = raw_data.decode("utf-8", errors="replace")

        # Find RSS <item> blocks without requiring the entire
        # document to be valid XML.
        item_blocks = re.findall(
            r"<item(?:\s[^>]*)?>(.*?)</item>",
            xml_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        stories = []

        for block in item_blocks[:limit]:
            title = get_tag_value(block, "title")
            link = get_tag_value(block, "link")
            description = get_tag_value(block, "description")
            pub_date = get_tag_value(block, "pubDate")

            title = clean_html(title)
            description = clean_html(description)
            link = unescape(link).strip()
            pub_date = clean_html(pub_date)

            if not title or not link:
                continue

            stories.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                }
            )

        return stories

    except Exception:
        return []


def get_news_sections():
    sections = []

    for category, url in NEWS_FEEDS.items():
        cache_key = (
            f"affirmcare_news_v4_"
            f"{category.lower().replace(' ', '_')}"
        )

        stories = cache.get(cache_key)

        if stories is None:
            stories = fetch_news_feed(url)
            cache.set(cache_key, stories, 900)

        sections.append(
            {
                "category": category,
                "stories": stories,
            }
        )

    return sections
