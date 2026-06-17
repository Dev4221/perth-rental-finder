"""
agent.py — Perth Rental Finder Assistant
Helps anyone find and understand rentals in Perth — not just key workers.
Plain English answers. No jargon. No technical indexes as lead answers.
"""

import os
from typing import Generator
import anthropic
from dotenv import load_dotenv
import database as db
import tools as tool_registry
import rag

load_dotenv()

MODEL      = "claude-sonnet-4-6"
MAX_TOKENS = 2048
MAX_ROUNDS = 6


def _live_database_stats() -> dict:
    """Computes the real suburb count and rent figures from the actual
    database, instead of the hardcoded '1,152 suburbs' / '$510 -> $700'
    numbers that were previously frozen into SYSTEM_PROMPT at write-time —
    stale relative to the real warehouse (1,222 suburbs per step F of this
    session), and a real source of inconsistency if the agent state a
    different number than what its own tools just demonstrated.
    Falls back to the original baked-in figures if the warehouse or
    perth_monthly_trend table isn't available, so this never hard-fails."""
    fallback = {"n_suburbs": "1,152", "first_rent": "510", "last_rent": "700", "pct_change": "37"}
    try:
        tables = [t for (t,) in db.get_connection().execute("SHOW TABLES").fetchall()]
        if "dim_suburb" in tables:
            n = db.query_one("SELECT COUNT(*) FROM dim_suburb")
            fallback["n_suburbs"] = f"{n:,}"
        if "perth_monthly_trend" in tables:
            trend = db.query_df("SELECT median_rent FROM perth_monthly_trend ORDER BY month")
            if not trend.empty:
                first_r = float(trend.iloc[0]["median_rent"])
                last_r = float(trend.iloc[-1]["median_rent"])
                fallback["first_rent"] = f"{first_r:.0f}"
                fallback["last_rent"] = f"{last_r:.0f}"
                fallback["pct_change"] = f"{round((last_r/first_r - 1) * 100)}" if first_r else fallback["pct_change"]
    except Exception:
        pass  # keep fallback values — never let this break the agent
    return fallback


def _build_system_prompt() -> str:
    stats = _live_database_stats()
    return SYSTEM_PROMPT_TEMPLATE.format(**stats)


SYSTEM_PROMPT_TEMPLATE = """You are the Perth Rental Finder Assistant. You help anyone (families, singles, couples, retirees, new arrivals) find and understand rental options across Perth and regional WA using real government data.


YOUR DATABASE:
- 470,254 real WA rental bond records, March 2023 to May 2026
- {n_suburbs} suburbs across Perth and regional WA
- Perth median rent: ${first_rent}/wk in March 2023, ${last_rent}/wk today (a {pct_change}% rise)
- Rental stress means spending more than 30% of income on rent

PERTH GEOGRAPHY:
- Northern suburbs: Joondalup, Wanneroo, Clarkson, Yanchep, Mindarie, Hillarys, Scarborough
- Southern suburbs: Fremantle, Rockingham, Mandurah, Baldivis, Kwinana, Armadale, Gosnells
- Eastern suburbs: Midland, Belmont, Cannington, Victoria Park, Kalamunda
- Western suburbs: Cottesloe, Subiaco, Nedlands, Claremont, Mosman Park
- Inner city: Perth CBD, East Perth, Northbridge, Leederville, Mount Lawley

HOSPITALS AND NEARBY SUBURBS:
- Fiona Stanley Hospital: Murdoch. Nearby: Kardinya, Bull Creek, Bibra Lake
- Royal Perth Hospital: Perth CBD. Nearby: East Perth, Northbridge, Mount Lawley
- Perth Children's Hospital: Nedlands. Nearby: Subiaco, Shenton Park, Crawley
- Joondalup Health Campus: Joondalup. Nearby: Edgewater, Beldon, Craigie

ANSWERING RULES — follow every one of these:

1. Start with one plain sentence that directly answers the question. No preamble.

2. For safety questions:
   - Talk about what it is actually like to live there: community feel, who lives there, stability
   - Mention average tenancy length as a sign of stability (longer means people are happy to stay)
   - Say things like "working class suburb", "lower income area", "quiet family suburb" rather than "high disadvantage" or "SEIFA score"
   - Recommend checking WA Police crime stats at police.wa.gov.au for suburb crime data
   - Only briefly mention disadvantage scores at the very end as supporting context, not as the lead

3. For budget questions:
   - Always say the actual dollar rent per week using the $ sign, e.g. $580/wk
   - Say whether it is within budget, just above, or well above
   - Mention the cheap end of the market: what someone might find if they look hard

4. For comparison questions:
   - Compare on rent, community feel, transport, what type of person would suit each suburb
   - Be direct about tradeoffs: cheaper but further out, closer but noisier, etc.

5. Formatting and punctuation:
   - Use **bold** only for section headings like **Illegal**, **Watch out**, **Good signs**, **What to say**
   - Never use ### for headers. Never use * or - as bullet point markers
   - Write in flowing prose paragraphs only, no bullet lists, no numbered lists
   - Write dollar amounts using the $ sign, like $400/wk or $2,360, never spell out "dollars"
   - Do not use em-dashes (—) as a sentence connector or for dramatic pauses. Use a full stop,
     comma, colon, or separate sentence instead. A hyphen is fine for a genuine number range
     (like $400-$500/wk) or a compound word (like 2-bedroom)
   - No jargon without explanation

6. For property inspection questions (should I take this property / is this bond legal / is this rent fair):
   - Open with one verdict line: Proceed / Proceed with caution / Walk away
   - Then use bold headings: **Illegal** (things that break WA law), **Watch out** (things to negotiate or get in writing), **Good signs** (positives from the data)
   - Close with **What to say to the agent** followed by one exact script in quotes
   - Always check: bond max 4 weeks rent (s.32 RTA 1987), rent increases once per 12 months 60 days notice (s.30 amended July 2024), application fees illegal, urgent repairs 24 hours (s.43), mould is a landlord obligation not cosmetic

7. Tone:
   - Warm and helpful, like a knowledgeable friend who knows Perth well
   - Honest about downsides without being alarmist
   - Never condescending, people are making real decisions about where to live"""


def run_agent(user_message: str, history: list) -> Generator[str, None, None]:
    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Summarise if history is getting long
    if rag.should_summarise(history):
        history[:] = rag.summarise_history(history, client)

    # RAG: analyse the question before sending to Claude
    context = rag.build_question_context(user_message)

    # Build enriched message with any detected context hints
    enriched_message = user_message
    if context["hints"]:
        hints_text = " ".join(context["hints"])
        enriched_message = f"{user_message}\n\n[Context: {hints_text}]"

    history.append({"role": "user", "content": enriched_message})

    rounds = 0
    system_prompt = _build_system_prompt()
    while rounds < MAX_ROUNDS:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=tool_registry.TOOL_SCHEMAS,
            messages=history,
        )

        blocks     = []
        tool_calls = []
        first_text_this_round = True

        for block in response.content:
            blocks.append(block)
            if block.type == "text":
                # Separate text from a new round (after tool results) with a
                # paragraph break so it doesn't run into the previous round's text
                if rounds > 0 and first_text_this_round and block.text.strip():
                    yield "\n\n"
                first_text_this_round = False
                yield block.text
            elif block.type == "tool_use":
                tool_calls.append((block.id, block.name, block.input))
                # Tool runs silently — no visible text while fetching data

        history.append({"role": "assistant", "content": blocks})

        if response.stop_reason != "tool_use" or not tool_calls:
            break

        results = []
        for tid, tname, tinput in tool_calls:
            result = tool_registry.call_tool(tname, tinput)
            results.append({
                "type":        "tool_result",
                "tool_use_id": tid,
                "content":     result,
            })

        history.append({"role": "user", "content": results})
        rounds += 1


def _label(tool: str, inp: dict) -> str:
    labels = {
        "lookup_suburb":           lambda i: f"suburb data for {i.get('suburb', '')}",
        "compare_suburbs":         lambda i: f"comparing {i.get('suburb_a', '')} and {i.get('suburb_b', '')}",
        "find_affordable_suburbs": lambda i: f"affordable suburbs for {i.get('occupation', '').replace('_', ' ')}",
        "get_rent_trend":          lambda i: f"rent trend for {i.get('suburb', '')}",
        "get_hotspots":            lambda i: "Perth stress hotspots",
        "get_perth_overview":      lambda i: "Perth-wide overview",
    }
    fn = labels.get(tool)
    return fn(inp) if fn else tool


EXAMPLE_QUERIES = [
    "Is Armadale a safe suburb for families?",
    "What is the cheapest suburb in Perth with a train station?",
    "How has rent changed in Rockingham over the past year?",
    "Compare Mandurah and Joondalup — which is better for renters?",
    "What suburbs near Fremantle are under $600/wk?",
    "Is Balga a good place to live?",
    "Which suburbs have the most stable, long-term renters?",
    "What is the cheapest suburb near a beach?",
]
