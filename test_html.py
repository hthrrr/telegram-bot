#!/usr/bin/env python3
"""Generate a sample HTML report to preview the layout."""

from fetch_messages import build_html

sample_data = [
    {
        "name": "עמית סגל",
        "messages": [
            {"ts": "2026-03-18 21:13 UTC", "sender": "amitsegal", "text": "מפקד פיקוד המרכז במכתב גלוי: האלימות של קומץ יהודים פוגעת במדינה", "media_path": None, "media_type": None},
            {"ts": "2026-03-18 21:30 UTC", "sender": "amitsegal", "text": "דיווח ראשוני: פיצוץ נשמע באזור הצפון, פרטים נוספים בהמשך", "media_path": None, "media_type": None},
            {"ts": "2026-03-18 21:45 UTC", "sender": "amitsegal", "text": "תמונה מזירת האירוע", "media_path": "https://placehold.co/600x400?text=Photo+Example", "media_type": "photo"},
        ],
    },
    {
        "name": "אבו עלי אקספרס",
        "messages": [
            {"ts": "2026-03-18 20:00 UTC", "sender": "abualiexpress", "text": "דיווחים פלסטיניים: כוחות צה״ל פועלים בג׳נין ובמחנה הפליטים", "media_path": None, "media_type": None},
            {"ts": "2026-03-18 20:15 UTC", "sender": "abualiexpress", "text": "", "media_path": "https://placehold.co/600x400?text=Photo+2", "media_type": "photo"},
            {"ts": "2026-03-18 20:30 UTC", "sender": "abualiexpress", "text": "סרטון מהשטח", "media_path": "https://www.w3schools.com/html/mov_bbb.mp4", "media_type": "video"},
        ],
    },
    {
        "name": "גזרת איראן - רגע NEWS",
        "messages": [
            {"ts": "2026-03-18 19:00 UTC", "sender": "reganews", "text": "סוכנות הידיעות האיראנית מדווחת על תרגיל צבאי נרחב במפרץ הפרסי", "media_path": None, "media_type": None},
            {"ts": "2026-03-18 19:30 UTC", "sender": "reganews", "text": "", "media_path": "https://placehold.co/600x400?text=Map+Image", "media_type": "photo"},
            {"ts": "2026-03-18 20:00 UTC", "sender": "reganews", "text": "בכיר אמריקני: ארה״ב עוקבת בדאגה אחרי התרגיל הצבאי האיראני", "media_path": None, "media_type": None},
            {"ts": "2026-03-18 20:30 UTC", "sender": "reganews", "text": "דיווח: ישראל העבירה מסר לאיראן דרך צד שלישי", "media_path": None, "media_type": None},
        ],
    },
    {
        "name": "הלל ביטון רוזן",
        "messages": [
            {"ts": "2026-03-18 21:07 UTC", "sender": "HallelBittonRosen", "text": "בשמחה תמיד: לוחמינו האריות מגדוד המילואים", "media_path": "https://placehold.co/600x400?text=Soldiers", "media_type": "photo"},
        ],
    },
    {
        "name": "חדשות 14",
        "messages": [
            {"ts": "2026-03-18 18:00 UTC", "sender": "news14", "text": "ראש הממשלה בנימין נתניהו קיים הערב התייעצות ביטחונית", "media_path": None, "media_type": None},
            {"ts": "2026-03-18 18:30 UTC", "sender": "news14", "text": "סיכום חדשות הערב", "media_path": "https://www.w3schools.com/html/mov_bbb.mp4", "media_type": "video"},
        ],
    },
]

out_path = "sample_report.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(build_html(sample_data))
print(f"Sample report saved to {out_path}")
