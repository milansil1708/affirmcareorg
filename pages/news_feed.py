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


FALLBACK_FEEDS = {
    "Latest News": (
        "https://news.google.com/rss/search?"
        "q=%28transgender+OR+%22gender-affirming%22%29+"
        "%28health+OR+healthcare+OR+policy+OR+rights%29"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "Policy & Legislation": (
        "https://news.google.com/rss/search?"
        "q=%28transgender+OR+%22gender-affirming%22%29+"
        "%28law+OR+legislation+OR+policy+OR+court+OR+Medicaid%29"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "Research": (
        "https://news.google.com/rss/search?"
        "q=%28transgender+OR+%22gender-affirming%22%29+"
        "%28research+OR+study+OR+findings+OR+journal%29"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "Education": (
        "https://news.google.com/rss/search?"
        "q=%28transgender+OR+%22gender+identity%22%29+"
        "%28school+OR+education+OR+student+OR+university%29"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "Healthcare": (
        "https://news.google.com/rss/search?"
        "q=%28transgender+OR+%22gender-affirming%22%29+"
        "%28healthcare+OR+health+OR+medical+OR+patient+OR+clinic%29"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "AI & Health Care": (
        "https://news.google.com/rss/search?"
        "q=%28transgender+OR+%22gender-affirming%22%29+"
        "%28%22artificial+intelligence%22+OR+AI+OR+%22machine+learning%22%29+"
        "%28health+OR+healthcare+OR+medical%29"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
}


CORE_RELEVANCE_TERMS = (
    "transgender",
    "gender-affirming",
    "gender affirming",
    "gender-diverse",
    "gender diverse",
    "nonbinary",
    "non-binary",
    "gender identity",
    "gender dysphoria",
    "trans health",
    "trans healthcare",
    "trans health care",
    "transgender health",
    "transgender healthcare",
    "transgender health care",
    "lgbtq health",
    "lgbtq+ health",
    "lgbtq healthcare",
    "lgbtq+ healthcare",
    "gender-affirming care",
    "gender affirming care",
    "gender-affirming healthcare",
    "gender affirming healthcare",
    "puberty blockers",
    "gender-affirming surgery",
    "gender affirming surgery",
)

CATEGORY_RELEVANCE_TERMS = {
    "Latest News": (
        "health",
        "healthcare",
        "health care",
        "medical",
        "patient",
        "hospital",
        "clinic",
        "law",
        "legislation",
        "policy",
        "court",
        "lawsuit",
        "rights",
        "insurance",
        "medicaid",
        "education",
        "school",
        "student",
        "research",
        "study",
    ),

    "Policy & Legislation": (
        "law",
        "legislation",
        "legislature",
        "bill",
        "policy",
        "regulation",
        "court",
        "lawsuit",
        "judge",
        "ruling",
        "ban",
        "restriction",
        "executive order",
        "medicaid",
        "medicare",
        "insurance",
        "government",
    ),

    "Research": (
        "research",
        "study",
        "studies",
        "survey",
        "data",
        "findings",
        "journal",
        "clinical study",
        "clinical trial",
        "researchers",
        "scientists",
        "analysis",
    ),

    "Education": (
        "education",
        "school",
        "schools",
        "student",
        "students",
        "teacher",
        "teachers",
        "college",
        "university",
        "campus",
        "classroom",
        "curriculum",
        "school district",
    ),

    "Healthcare": (
        "health",
        "healthcare",
        "health care",
        "medical",
        "medicine",
        "patient",
        "patients",
        "hospital",
        "clinic",
        "doctor",
        "physician",
        "treatment",
        "therapy",
        "surgery",
        "care",
        "insurance",
    ),

    "AI & Health Care": (
        "artificial intelligence",
        " ai ",
        "ai-powered",
        "ai-enabled",
        "machine learning",
        "algorithm",
        "algorithms",
        "large language model",
        "clinical ai",
        "generative ai",
    ),
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
    if not value:
        return ""

    value = unescape(value).strip()

    # Remove surrounding quotes.
    value = value.strip('"').strip("'").strip()

    # Remove malformed trailing slash/quote combinations.
    value = re.sub(
        r'(["\']?)/$',
        "",
        value,
    )

    value = value.strip('"').strip("'").strip()

    return value


def contains_any_term(text, terms):
    return any(term in text for term in terms)


def relevance_score(title, description, category):
    title_text = f" {title} ".casefold()
    full_text = f" {title} {description} ".casefold()

    score = 0

    strong_terms = (
        "gender-affirming care",
        "gender affirming care",
        "transgender healthcare",
        "transgender health care",
        "transgender health",
        "trans health",
        "gender-affirming healthcare",
        "gender affirming healthcare",
    )

    core_terms = (
        "transgender",
        "gender-affirming",
        "gender affirming",
        "nonbinary",
        "non-binary",
        "gender identity",
        "gender dysphoria",
        "gender-diverse",
        "gender diverse",
    )

    broader_terms = (
        "lgbtq health",
        "lgbtq+ health",
        "lgbtq healthcare",
        "lgbtq+ healthcare",
        "lgbtq",
        "lgbtq+",
    )

    for term in strong_terms:
        if term in title_text:
            score += 12
        elif term in full_text:
            score += 8

    for term in core_terms:
        if term in title_text:
            score += 7
        elif term in full_text:
            score += 4

    for term in broader_terms:
        if term in title_text:
            score += 3
        elif term in full_text:
            score += 1

    category_terms = CATEGORY_RELEVANCE_TERMS.get(category, ())

    if contains_any_term(title_text, category_terms):
        score += 4
    elif contains_any_term(full_text, category_terms):
        score += 2

    # Generic LGBTQ lifestyle/travel/entertainment stories should
    # not become AffirmCare news just because they mention LGBTQ.
    off_topic_terms = (
        "resort",
        "travel",
        "vacation",
        "hotel",
        "entertainment",
        "fashion",
        "concert",
        "music festival",
        "tourism",
    )

    if contains_any_term(full_text, off_topic_terms):
        score -= 6

    return score


def is_relevant_story(title, description, category):
    score = relevance_score(
        title,
        description,
        category,
    )

    # Require meaningful relevance to AffirmCare.
    return score >= 6



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


def fetch_news_feed(url, category, limit=6):
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

            if not is_relevant_story(
                title,
                description,
                category,
            ):
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
            "affirmcare_news_v10_"
            f"{category.lower().replace(' ', '_')}"
        )

        stories = cache.get(cache_key)

        if stories is None:
            stories = fetch_news_feed(url, category)

            # If Cision does not provide enough genuinely relevant
            # stories, supplement the section with a tightly targeted
            # fallback news feed.
            if len(stories) < 3:
                fallback_url = FALLBACK_FEEDS.get(category)

                if fallback_url:
                    fallback_stories = fetch_news_feed(
                        fallback_url,
                        category,
                        limit=6,
                    )

                    existing_links = {
                        story["link"]
                        for story in stories
                    }

                    existing_titles = {
                        story["title"].casefold()
                        for story in stories
                    }

                    for story in fallback_stories:
                        if story["link"] in existing_links:
                            continue

                        if story["title"].casefold() in existing_titles:
                            continue

                        stories.append(story)
                        existing_links.add(story["link"])
                        existing_titles.add(
                            story["title"].casefold()
                        )

                        if len(stories) >= 6:
                            break

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
