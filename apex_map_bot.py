"""
Apex Legends Ranked Map Rotation Discord Bot
- Auto-alerts when Ranked map changes
- /currentmap  → current ranked map
- /todaysmaps  → full ranked map schedule for today

Requirements:
    pip install discord.py aiohttp python-dotenv

Setup:
    1. Create a .env file with:
       DISCORD_TOKEN=your_bot_token_here
       CHANNEL_ID=your_channel_id_here
    2. Run: python apex_map_bot.py
"""

import discord
from discord import app_commands
import aiohttp
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ─── Config ────────────────────────────────────────────────────────────────────

TOKEN      = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

CHECK_INTERVAL = 60  # seconds

APEX_API_KEY     = os.getenv("APEX_API_KEY")
API_URL          = f"https://api.mozambiquehe.re/maprotation?version=2&auth={APEX_API_KEY}"
API_URL_FULL_DAY = f"https://api.mozambiquehe.re/maprotation?version=2&tabid=1&auth={APEX_API_KEY}"

# ─── Map metadata ──────────────────────────────────────────────────────────────

MAP_COLORS = {
    "Kings Canyon":  0xE8A237,
    "World's Edge":  0xE84A4A,
    "Olympus":       0x6AB0E8,
    "Storm Point":   0x4AE8A2,
    "Broken Moon":   0xA259E8,
    "E-District":    0xFF6B9D,
}

MAP_EMOJIS = {
    "Kings Canyon":  "🏜️",
    "World's Edge":  "🌋",
    "Olympus":       "☁️",
    "Storm Point":   "⚡",
    "Broken Moon":   "🌙",
    "E-District":    "🌆",
}

# ─── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)

last_ranked_map = None


# ─── Helpers ───────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


async def fetch_rotation(session: aiohttp.ClientSession, url: str) -> dict | list | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print(f"[{now()}] API error: {e}")
    return None


def build_ranked_embed(map_name: str, next_map: str, end_timestamp: int, title: str = "🏆 Ranked Map Changed") -> discord.Embed:
    color      = MAP_COLORS.get(map_name, 0x5865F2)
    emoji      = MAP_EMOJIS.get(map_name, "🗺️")
    next_emoji = MAP_EMOJIS.get(next_map, "🗺️")

    embed = discord.Embed(
        title=title,
        description=f"## {emoji}  {map_name}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="⏱️ Ends",
        value=f"<t:{end_timestamp}:t> (<t:{end_timestamp}:R>)",
        inline=True,
    )
    embed.add_field(
        name="➡️ Next",
        value=f"{next_emoji}  {next_map}" if next_map else "Unknown",
        inline=True,
    )
    embed.set_footer(text="Apex Legends Ranked Tracker")
    return embed


def build_todays_schedule(ranked_rotations: list) -> discord.Embed:
    """
    Build a full-day schedule embed from a list of ranked rotation slots.
    Each slot is expected to have: map, start (epoch), end (epoch).
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())

    embed = discord.Embed(
        title="🏆 Ranked Map Schedule — Today",
        description="All ranked map slots for the next 24 hours.\nTimes shown in your local timezone.",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )

    if not ranked_rotations:
        embed.description = "❌ Could not load today's schedule. Try again later."
        return embed

    lines = []
    for slot in ranked_rotations:
        map_name  = slot.get("map", "Unknown")
        start_ts  = slot.get("start", 0)
        end_ts    = slot.get("end", 0)
        emoji     = MAP_EMOJIS.get(map_name, "🗺️")

        # Mark the currently active slot
        is_active = start_ts <= now_ts < end_ts
        indicator = "▶️" if is_active else "   "

        line = (
            f"{indicator} {emoji} **{map_name}**\n"
            f"　　<t:{start_ts}:t> → <t:{end_ts}:t>"
        )
        lines.append(line)

    # Discord embed field value limit is 1024 chars; split into chunks if needed
    chunk = ""
    field_count = 1
    for line in lines:
        if len(chunk) + len(line) + 2 > 1024:
            embed.add_field(name=f"Schedule (cont.)" if field_count > 1 else "Schedule", value=chunk, inline=False)
            chunk = ""
            field_count += 1
        chunk += line + "\n\n"

    if chunk:
        embed.add_field(name="Schedule" if field_count == 1 else "Schedule (cont.)", value=chunk.strip(), inline=False)

    embed.set_footer(text="▶️ = current slot  •  Apex Legends Ranked Tracker")
    return embed


# ─── Slash commands ────────────────────────────────────────────────────────────

@tree.command(name="currentmap", description="Check the current Apex Legends Ranked map")
async def currentmap(interaction: discord.Interaction):
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        data = await fetch_rotation(session, API_URL)

    if not data:
        await interaction.followup.send("❌ Could not reach the Apex API. Try again in a moment.")
        return

    try:
        ranked        = data.get("ranked", {})
        current       = ranked.get("current", {})
        nxt           = ranked.get("next", {})

        map_name      = current.get("map", "Unknown")
        next_map      = nxt.get("map", "Unknown")
        end_timestamp = current.get("end", 0)

        embed = build_ranked_embed(map_name, next_map, end_timestamp, title="🏆 Current Ranked Map")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error parsing map data: {e}")


@tree.command(name="todaysmaps", description="Show all Apex Legends Ranked map rotations for today")
async def todaysmaps(interaction: discord.Interaction):
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        data = await fetch_rotation(session, API_URL)

    if not data:
        await interaction.followup.send("❌ Could not reach the Apex API. Try again in a moment.")
        return

    try:
        ranked = data.get("ranked", {})

        # The API returns current + next slots; build a list of all available slots
        rotations = []

        current = ranked.get("current", {})
        if current.get("map"):
            rotations.append({
                "map":   current.get("map"),
                "start": current.get("start", 0),
                "end":   current.get("end", 0),
            })

        # Some API responses include a list of upcoming slots under "upcoming"
        upcoming = ranked.get("upcoming", [])
        for slot in upcoming:
            if slot.get("map"):
                rotations.append({
                    "map":   slot.get("map"),
                    "start": slot.get("start", 0),
                    "end":   slot.get("end", 0),
                })

        # Fallback: if no upcoming list, at least show current + next
        if not upcoming:
            nxt = ranked.get("next", {})
            if nxt.get("map"):
                rotations.append({
                    "map":   nxt.get("map"),
                    "start": current.get("end", 0),       # next starts when current ends
                    "end":   nxt.get("end", 0),
                })

        # Filter to only today's slots (within next 24 hours)
        now_ts      = int(datetime.now(timezone.utc).timestamp())
        cutoff_ts   = now_ts + 86400  # 24 hours from now
        today_slots = [s for s in rotations if s["end"] > now_ts and s["start"] < cutoff_ts]

        embed = build_todays_schedule(today_slots)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error building schedule: {e}")


# ─── Background auto-alert loop ────────────────────────────────────────────────

async def ranked_map_loop():
    global last_ranked_map

    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[{now()}] ❌ Channel ID {CHANNEL_ID} not found. Check your .env file.")
        return

    print(f"[{now()}] ✅ Watching Ranked map in #{channel.name}")

    async with aiohttp.ClientSession() as session:
        while True:
            data = await fetch_rotation(session, API_URL)

            if data:
                try:
                    ranked        = data.get("ranked", {})
                    current       = ranked.get("current", {})
                    nxt           = ranked.get("next", {})

                    map_name      = current.get("map")
                    next_map      = nxt.get("map")
                    end_timestamp = current.get("end", 0)

                    if map_name and map_name != last_ranked_map:
                        if last_ranked_map is not None:
                            embed = build_ranked_embed(map_name, next_map, end_timestamp)
                            await channel.send(embed=embed)
                            print(f"[{now()}] 📢 Ranked map changed → {map_name}")
                        else:
                            print(f"[{now()}] 🗺️  Startup — Ranked: {map_name} (next: {next_map})")
                        last_ranked_map = map_name

                except Exception as e:
                    print(f"[{now()}] Parse error: {e}")

            await asyncio.sleep(CHECK_INTERVAL)


# ─── Events ────────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    await tree.sync()
    print(f"[{now()}] 🤖 Logged in as {client.user}")
    print(f"[{now()}] ✅ Slash commands registered: /currentmap, /todaysmaps")
    print(f"[{now()}] 🔄 Polling every {CHECK_INTERVAL}s for ranked map changes...")
    client.loop.create_task(ranked_map_loop())


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set in .env")
        exit(1)
    if not CHANNEL_ID:
        print("❌ CHANNEL_ID not set in .env")
        exit(1)

    client.run(TOKEN)
