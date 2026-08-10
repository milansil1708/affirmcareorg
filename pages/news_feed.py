import re
import urllib.request
import xml.etree.ElementTree as ET

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

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_element_text(item, name):
    for child in item:
        tag = child.tag.split("}")[-1]

        if tag == name:
            return "".join(child.itertext()).strip()

    return ""


def fetch_news_feed(url, limit=6):
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)

        stories = []

        for item in root.iter():
            if item.tag.split("}")[-1] != "item":
                continue

            title = get_element_text(item, "title")
            link = get_element_text(item, "link")
            description = get_element_text(item, "description")
            pub_date = get_element_text(item, "pubDate")

            if not title or not link:
                continue

            stories.append(
                {
                    "title": clean_html(title),
                    "link": link.strip(),
                    "description": clean_html(description),
                    "pub_date": pub_date.strip(),
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
            f"affirmcare_news_v2_"
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
