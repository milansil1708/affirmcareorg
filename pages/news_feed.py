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

            values = {}

            for child in item:
                tag = child.tag.split("}")[-1]
                values[tag] = "".join(child.itertext()).strip()

            title = values.get("title", "")
            link = values.get("link", "")
            description = values.get("description", "")
            pub_date = values.get("pubDate", "")

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

            if len(stories) >= limit:
                break

        return stories

    except Exception as exc:
        return [
            {
                "title": "RSS ERROR",
                "link": "#",
                "description": f"{type(exc).__name__}: {exc}",
                "pub_date": "",
            }
        ]


def get_news_sections():
    sections = []

    for category, url in NEWS_FEEDS.items():
        cache_key = (
            f"affirmcare_news_diagnostic_"
            f"{category.lower().replace(' ', '_')}"
        )

        stories = cache.get(cache_key)

        if stories is None:
            stories = fetch_news_feed(url)
            cache.set(cache_key, stories, 60)

        sections.append(
            {
                "category": category,
                "stories": stories,
            }
        )

    return sections
