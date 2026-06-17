"""
rag.py — RAG layer for Perth Rental Finder.
Focused on helping anyone find a rental — not occupation-specific.
"""

import re
from typing import Optional
import pandas as pd
import database as db


# ── Geography resolver ─────────────────────────────────────────────────────

GEOGRAPHY_HINTS = {
    # Hospitals
    "fiona stanley":      ["Murdoch", "Kardinya", "Bull Creek", "Bibra Lake", "Spearwood"],
    "fsh":                ["Murdoch", "Kardinya", "Bull Creek"],
    "royal perth":        ["Perth", "East Perth", "Northbridge", "Mount Lawley"],
    "perth children":     ["Nedlands", "Subiaco", "Shenton Park", "Crawley"],
    "joondalup hospital": ["Joondalup", "Edgewater", "Beldon", "Craigie"],
    "fremantle hospital": ["Fremantle", "Hilton", "Hamilton Hill", "Palmyra"],

    # Directions
    "south of the river": ["Fremantle", "Cockburn", "Rockingham", "Mandurah",
                           "Armadale", "Gosnells", "Canning Vale"],
    "north of the river": ["Joondalup", "Wanneroo", "Stirling", "Morley", "Midland"],
    "inner city":         ["Perth", "East Perth", "West Perth", "Northbridge",
                           "Leederville", "Mount Lawley"],
    "outer suburbs":      ["Armadale", "Rockingham", "Mandurah", "Baldivis",
                           "Ellenbrook", "Joondalup"],
    "coastal":            ["Scarborough", "Cottesloe", "Fremantle", "Mandurah",
                           "Rockingham", "Hillarys"],
    "beach":              ["Scarborough", "Cottesloe", "Fremantle", "Mandurah",
                           "Rockingham", "Hillarys", "Sorrento"],
    "hills":              ["Kalamunda", "Mundaring", "Midland"],
    "near fremantle":     ["Fremantle", "North Fremantle", "Hamilton Hill", "Palmyra", "White Gum Valley"],
    "near cbd":           ["Perth", "East Perth", "Northbridge", "Leederville", "Mount Lawley"],
    "near joondalup":     ["Joondalup", "Edgewater", "Beldon", "Craigie", "Currambine"],
}

def resolve_geography(text: str) -> list:
    text_lower = text.lower()
    suburbs = []
    for hint, suburb_list in GEOGRAPHY_HINTS.items():
        if hint in text_lower:
            suburbs.extend(suburb_list)
    return list(dict.fromkeys(suburbs))


# ── Intent detector ────────────────────────────────────────────────────────

def build_question_context(question: str) -> dict:
    q = question.lower()

    geo_suburbs = resolve_geography(question)

    is_safety    = any(w in q for w in ["safe", "safety", "crime", "dangerous", "security", "good area", "bad area", "nice area"])
    is_trend     = any(w in q for w in ["trend", "change", "risen", "gone up", "increase", "history", "past year", "last year"])
    is_compare   = any(w in q for w in ["compare", "vs", "versus", "difference between", "better", "cheaper between", "or"])
    is_cheap     = any(w in q for w in ["cheap", "affordable", "cheapest", "budget", "under", "less than", "below"])
    is_overview  = any(w in q for w in ["overview", "overall", "perth", "crisis", "how bad", "general", "market"])
    is_near      = any(w in q for w in ["near", "close to", "next to", "within", "vicinity", "around"])
    is_beach     = any(w in q for w in ["beach", "coast", "ocean", "seaside", "waterfront"])

    hints = []
    if geo_suburbs:
        hints.append(f"Relevant suburbs based on location: {', '.join(geo_suburbs[:4])}.")
    if is_safety:
        hints.append("The person is asking about safety and what the area is like to live in.")
    if is_trend:
        hints.append("The person wants to know how rent has changed over time.")
    if is_compare:
        hints.append("The person wants to compare two or more places.")
    if is_cheap:
        hints.append("The person is looking for the most affordable options.")
    if is_beach:
        hints.append("The person wants to be near the beach or coast.")

    return {
        "suburbs":    geo_suburbs,
        "is_safety":  is_safety,
        "is_trend":   is_trend,
        "is_compare": is_compare,
        "is_cheap":   is_cheap,
        "is_near":    is_near,
        "is_beach":   is_beach,
        "is_overview":is_overview,
        "hints":      hints,
    }


# ── Conversation summariser ────────────────────────────────────────────────

def should_summarise(history: list) -> bool:
    user_messages = [m for m in history if m["role"] == "user"]
    return len(user_messages) > 6


def summarise_history(history: list, client) -> list:
    if len(history) <= 8:
        return history

    recent = history[-8:]
    older  = history[:-8]

    older_text = "\n".join([
        f"{m['role'].upper()}: {m['content'] if isinstance(m['content'], str) else '[tool call]'}"
        for m in older
        if isinstance(m.get('content'), str)
    ])

    if not older_text.strip():
        return history

    try:
        summary_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"Summarise this rental search conversation in 2 sentences. "
                    f"Focus on what suburbs were discussed, what budget was mentioned, "
                    f"and what questions were asked.\n\n{older_text}"
                )
            }]
        )
        summary_text = summary_response.content[0].text
        return [
            {"role": "user",      "content": f"[Earlier in this conversation: {summary_text}]"},
            {"role": "assistant", "content": "Got it — I have context from our earlier discussion."},
        ] + recent
    except Exception:
        return history[-8:]


# ── Perth knowledge base ───────────────────────────────────────────────────

PERTH_FACTS = """
PERTH GEOGRAPHY AND LIFESTYLE FACTS:

Perth metropolitan area spans about 120km north to south.
Population: 2.4 million people as of 2024.

SUBURB CHARACTER GUIDE:
- Inner city (0-5km from CBD): Perth, East Perth, Northbridge, Leederville, Mount Lawley, Subiaco, West Perth. Higher rents, walkable, good for young professionals.
- Inner western suburbs: Cottesloe, Nedlands, Claremont, Subiaco, Mosman Park. Very expensive, near beach and river, highly regarded schools.
- Northern suburbs: Joondalup, Wanneroo, Clarkson, Yanchep, Mindarie, Scarborough. Mix of established and new estates, good train access in many areas.
- Southern suburbs: Fremantle, Cockburn, Rockingham, Mandurah, Armadale, Gosnells, Kwinana. More affordable, some beach access, long commute to CBD.
- Eastern suburbs: Midland, Belmont, Victoria Park, Cannington, Kalamunda. Affordable, good access to Midland and Armadale train lines.

TRANSPORT:
- Train lines: Joondalup/Clarkson line (north), Midland line (east), Armadale/Thornlie line (south-east), Mandurah line (south), Fremantle line (south-west)
- Bus: extensive network but less reliable than train for commuting
- Car: most outer suburbs require a car

TYPICAL SUBURB PROFILES:
- Armadale: affordable outer suburb, train line, lower income area, growing
- Balga: northern suburb, lower income, affordable, close to Stirling
- Baldivis: new outer southern suburb, mostly families, car dependent
- Bentley: near Curtin University, diverse, relatively affordable
- Ellenbrook: outer northern suburb, newer estates, car dependent
- Fremantle: historic port, beach access, cafes, higher rent but great lifestyle
- Gosnells: southern middle suburb, affordable, train access
- Joondalup: major northern hub, university, hospital, good amenities
- Mandurah: coastal town 70km south, very affordable, beach lifestyle
- Midland: eastern hub, hospital, train, affordable, growing
- Rockingham: southern coastal, beach, affordable, long commute
- Scarborough: northern beach suburb, popular, moderate rents
- Subiaco: inner western, expensive, cafe culture, great walkability

SAFETY NOTE:
- Perth is generally a safe city compared to global standards
- For specific crime data, always refer users to WA Police crime statistics: police.wa.gov.au
- Suburbs with lower incomes can have higher property crime rates but this varies greatly by street
- Average tenancy length is a good proxy for community stability — longer = more settled community
"""
