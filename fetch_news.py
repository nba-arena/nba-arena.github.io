# -*- coding: utf-8 -*-
"""
הרובוט של NBA ארנה: אוסף כותרות NBA מפידי ספורט בעברית ושומר אותן ב-news.json.
רץ אוטומטית ב-GitHub Actions. שומר רק כותרת, תקציר קצר (מה שהאתר המקורי נתן בפיד) וקישור.
"""
import json, re, html, os, sys, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ===== מקורות: אפשר להוסיף כאן עוד פידים בעתיד =====
FEEDS = [
    {"name": "ynet", "url": "https://www.ynet.co.il/Integration/StoryRss3.xml"},
    # בוואלה השעה שכתובה מקדימה ב-3 שעות (כתוב GMT, אבל זה בעצם GMT+3)
    {"name": "וואלה", "url": "https://rss.walla.co.il/feed/7", "fix_hours": 3},
    {"name": "מעריב", "url": "https://www.maariv.co.il/Rss/RssFeedsSport"},
]

# ===== מילים שמסמנות כתבה על ה-NBA =====
KEYWORDS = [
    "NBA", "אן.בי.איי", "אן בי איי", "אנ.בי.איי",
    # קבוצות
    "לייקרס", "קליפרס", "סלטיקס", "ווריורס", "גולדן סטייט", "בולס", "ניקס", "ברוקלין", "מיאמי היט",
    "אורלנדו", "ספרס", "רוקטס", "מאבריקס", "נאגטס", "ת'אנדר", "בלייזרס", "פורטלנד", "פיניקס",
    "סקרמנטו", "יוטה ג'אז", "גריזליס", "פליקנס", "טימברוולבס", "באקס", "פייסרס", "קאבלירס",
    "פיסטונס", "ראפטורס", "סיקסרס", "הוקס", "הורנטס", "וויזארדס",
    # שחקנים
    "אבדיה", "לברון", "סטף קרי", "סטפן קרי", "יוקיץ'", "וומבניאמה", "וומבי", "דונצ'יץ'",
    "יאניס", "אנטטוקומפו", "גילג'ס-אלכסנדר", "דוראנט", "טייטום", "אדוארדס", "בן שרף",
    "מוראנט", "לילארד", "אמביד", "ברונסון", "הארדן", "ווסטברוק", "קוואי", "זאיון", "ג'ימי באטלר",
]

MAX_ITEMS = 40          # כמה כתבות לשמור לכל היותר
MAX_AGE_DAYS = 21       # כתבות ישנות מזה נמחקות מהרשימה
MAX_SUMMARY_CHARS = 320 # תקציר קצר בלבד

HEB = "\u0590-\u05FF"
# מאפשר אותיות שימוש לפני המילה (ה, ו, ב, ל, מ, ש, כ), למשל "ללייקרס" או "והסלטיקס"
PATTERNS = [
    re.compile(r"(?<![%s\w])[והבלמשכ]{0,3}%s(?![%s\w])" % (HEB, re.escape(k), HEB), re.IGNORECASE)
    for k in KEYWORDS
]

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.json")


def clean(text):
    """מנקה HTML ורווחים מיותרים."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def short_summary(text):
    """מקצר את התקציר ל-3 משפטים / 320 תווים לכל היותר."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(sentences[:3])
    if len(out) > MAX_SUMMARY_CHARS:
        out = out[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."
    return out


def is_nba(text):
    return any(p.search(text) for p in PATTERNS)


def parse_date(s, fix_hours=0):
    now = datetime.now(timezone.utc)
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        d = d - timedelta(hours=fix_hours)  # תיקון לאתרים שהשעה שלהם לא נכונה
        return min(d, now)                   # הגנה: כתבה לא יכולה להיות מהעתיד
    except Exception:
        return now


def read_feed(feed):
    req = urllib.request.Request(feed["url"], headers={"User-Agent": "Mozilla/5.0 (NBA-Arena news bot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    root = ET.fromstring(data)
    items = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        raw_desc = it.findtext("description") or ""
        summary = short_summary(clean(raw_desc))
        if not title or not link.startswith("http"):
            continue
        if not is_nba(title + " " + summary):
            continue
        img = re.search(r"<img[^>]+src=['\"]([^'\"]+)", html.unescape(raw_desc))
        items.append({
            "title": title,
            "summary": summary,
            "link": link,
            "source": feed["name"],
            "date": parse_date(it.findtext("pubDate") or "", feed.get("fix_hours", 0)).isoformat(),
            "image": img.group(1) if img and img.group(1).startswith("https") else "",
            "time_ok": True,
        })
    return items


def main():
    fresh, ok = [], 0
    for f in FEEDS:
        try:
            got = read_feed(f)
            fresh += got
            ok += 1
            print(f"{f['name']}: {len(got)} כתבות NBA")
        except Exception as e:
            print(f"{f['name']}: שגיאה - {e}")
    if ok == 0:
        print("אף מקור לא עבד. משאירים את החדשות הקודמות כמו שהן.")
        return 0

    old = []
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as fh:
                old = json.load(fh).get("items", [])
        except Exception:
            old = []

    before = json.dumps(old, ensure_ascii=False)  # צילום של המצב לפני השינויים

    # תיקון חד-פעמי לכתבות שנשמרו לפני תיקון השעה
    fixes = {f["name"]: f.get("fix_hours", 0) for f in FEEDS}
    now = datetime.now(timezone.utc)
    for i in old:
        if not i.get("time_ok"):
            d = parse_date_iso(i["date"]) - timedelta(hours=fixes.get(i.get("source"), 0))
            i["date"] = min(d, now).isoformat()
            i["time_ok"] = True

    by_link = {i["link"]: i for i in old}
    for i in fresh:
        by_link[i["link"]] = i  # גרסה חדשה מחליפה ישנה
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    items = [i for i in by_link.values() if parse_date_iso(i["date"]) >= cutoff]
    items.sort(key=lambda i: parse_date_iso(i["date"]), reverse=True)
    items = items[:MAX_ITEMS]

    if json.dumps(items, ensure_ascii=False) == before:
        print("אין כתבות חדשות.")
        return 0

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "items": items},
                  fh, ensure_ascii=False, indent=1)
    print(f"נשמרו {len(items)} כתבות.")
    return 0


def parse_date_iso(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


if __name__ == "__main__":
    sys.exit(main())
