"""
Apex Legends Ranked Map Rotation Discord Bot
- Auto-alerts when Ranked map changes
- /currentmap  → current ranked map (fancy embed)
- /todaysmaps  → full ranked map schedule for today (fancy embed)

Requirements:
    pip install discord.py aiohttp python-dotenv

Setup:
    1. Create a .env file with:
       DISCORD_TOKEN=your_bot_token_here
       CHANNEL_ID=your_channel_id_here
       APEX_API_KEY=your_api_key_here
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

TOKEN        = os.getenv("DISCORD_TOKEN")
CHANNEL_ID   = int(os.getenv("CHANNEL_ID", "0"))
APEX_API_KEY = os.getenv("APEX_API_KEY")

CHECK_INTERVAL   = 60
API_URL          = f"https://api.mozambiquehe.re/maprotation?version=2&auth={APEX_API_KEY}"
API_URL_FULL_DAY = f"https://api.mozambiquehe.re/maprotation?version=2&tabid=1&auth={APEX_API_KEY}"

# ─── Map metadata ──────────────────────────────────────────────────────────────

MAP_DATA = {
    "Kings Canyon": {
        "color":       0xE8A237,
        "emoji":       "🏜️",
        "description": "The original Apex battleground. Tight corridors, canyon walls, and pure chaos.",
        "image":       "https://wallpapercave.com/wp/wp4413079.jpg",
    },
    "World's Edge": {
        "color":       0xE84A4A,
        "emoji":       "🌋",
        "description": "Volcanic terrain split by lava rifts. High ground and long sightlines dominate.",
        "image":       "https://wallpapercave.com/wp/wp11307860.jpg",
    },
    "Olympus": {
        "color":       0x6AB0E8,
        "emoji":       "☁️",
        "description": "A floating city in the clouds. Open rotations reward fast, mobile legends.",
        "image":       "https://wallpapercave.com/wp/wp11307899.jpg",
    },
    "Storm Point": {
        "color":       0x4AE8A2,
        "emoji":       "⚡",
        "description": "Sprawling tropical island with IMC Armories and aggressive wildlife.",
        "image":       "https://wallpapercave.com/wp/wp11307854.jpg",
    },
    "Broken Moon": {
        "color":       0xA259E8,
        "emoji":       "🌙",
        "description": "A fractured moon with zipline networks connecting distant POIs.",
        "image":       "https://www.videogameschronicle.com/files/2022/10/Broken-Moon-Loading-Screen.jpg",
    },
    "E-District": {
        "color":       0xFF6B9D,
        "emoji":       "🌆",
        "description": "A neon-lit urban sprawl. Vertical combat and dense cover everywhere.",
        "image":       "https://media.esports.gg/uploads/2025/07/E-District-Season-26-1080p.jpg",
    },
}

FALLBACK_MAP = {
    "color":       0x5865F2,
    "emoji":       "🗺️",
    "description": "Unknown map.",
    "image":       None,
}

# Ranked tier colors for visual flair
RANK_GRADIENT = 0xFFD700  # gold

# ─── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)

last_ranked_map = None


# ─── Helpers ───────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def get_map(map_name: str) -> dict:
    return MAP_DATA.get(map_name, FALLBACK_MAP)


def duration_bar(end_ts: int, total_minutes: int = 90) -> str:
    """Generate a visual progress bar showing how much time is left."""
    now_ts     = int(datetime.now(timezone.utc).timestamp())
    remaining  = max(0, end_ts - now_ts)
    elapsed    = max(0, total_minutes * 60 - remaining)
    progress   = min(1.0, elapsed / (total_minutes * 60))

    bar_length = 12
    filled     = round(progress * bar_length)
    empty      = bar_length - filled

    bar = "█" * filled + "░" * empty
    pct = round(progress * 100)
    return f"`{bar}` {pct}% elapsed"


async def fetch_rotation(session: aiohttp.ClientSession, url: str) -> dict | list | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print(f"[{now()}] API error: {e}")
    return None


# ─── Embed builders ────────────────────────────────────────────────────────────

def build_currentmap_embed(map_name: str, next_map: str, end_timestamp: int, start_timestamp: int = 0) -> discord.Embed:
    meta       = get_map(map_name)
    next_meta  = get_map(next_map)
    color      = meta["color"]
    emoji      = meta["emoji"]
    desc       = meta["description"]

    embed = discord.Embed(
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Title + map name as the main focus
    embed.set_author(
        name="APEX LEGENDS  •  RANKED",
        icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/Apex_legends_diamond_rank_insignia.png/240px-Apex_legends_diamond_rank_insignia.png",
    )

    embed.title = f"{emoji}  {map_name}"

    # Progress bar
    embed.add_field(
        name="⏳ Time Remaining",
        value=f"{duration_bar(end_timestamp)}\nEnds <t:{end_timestamp}:R> at <t:{end_timestamp}:t>",
        inline=False,
    )

    # Next map + status side by side
    embed.add_field(
        name="🔜 Up Next",
        value=f"{next_meta['emoji']}  **{next_map}**",
        inline=True,
    )

    embed.add_field(
        name="📡 Status",
        value="🟢  **LIVE NOW**",
        inline=True,
    )


    if meta.get("image"):
        embed.set_image(url=meta["image"])

    embed.set_footer(
        text="🏆 Ranked  •  Apex Map Tracker  •  Updates every 60s",
    )

    return embed


def build_todays_schedule_embed(ranked_rotations: list) -> discord.Embed:
    now_ts = int(datetime.now(timezone.utc).timestamp())

    embed = discord.Embed(
        title="Ranked Map Schedule",
        color=RANK_GRADIENT,
        timestamp=datetime.now(timezone.utc),
    )

    embed.set_author(
        name="APEX LEGENDS  •  RANKED  •  NEXT 24 HOURS",
        icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/Apex_legends_diamond_rank_insignia.png/240px-Apex_legends_diamond_rank_insignia.png",
    )

    if not ranked_rotations:
        embed.description = "❌ Could not load today's schedule. Try again later."
        return embed

    lines = []
    for i, slot in enumerate(ranked_rotations):
        map_name  = slot.get("map", "Unknown")
        start_ts  = slot.get("start", 0)
        end_ts    = slot.get("end", 0)
        meta      = get_map(map_name)
        emoji     = meta["emoji"]
        is_active = start_ts <= now_ts < end_ts

        if is_active:
            # Active slot — highlighted
            remaining = max(0, end_ts - now_ts)
            mins      = remaining // 60
            line = (
                f"🟢 **NOW LIVE**\n"
                f"**{emoji}  {map_name}**\n"
                f"<t:{start_ts}:t> → <t:{end_ts}:t>  •  *{mins}m left*"
            )
        else:
            # Upcoming slot
            number = f"`{i + 1}.`"
            line = (
                f"{number} {emoji}  **{map_name}**\n"
                f"　<t:{start_ts}:t> → <t:{end_ts}:t>"
            )

        lines.append((line, is_active))

    # Separate active from upcoming for cleaner layout
    active_lines   = [l for l, active in lines if active]
    upcoming_lines = [l for l, active in lines if not active]

    if active_lines:
        embed.add_field(
            name="⚔️ Current Map",
            value="\n".join(active_lines),
            inline=False,
        )

    if upcoming_lines:
        # Split into chunks if needed (Discord field limit 1024 chars)
        chunk = ""
        field_count = 0
        for line in upcoming_lines:
            if len(chunk) + len(line) + 2 > 1000:
                label = "🗓️ Coming Up" if field_count == 0 else "🗓️ Coming Up (cont.)"
                embed.add_field(name=label, value=chunk.strip(), inline=False)
                chunk = ""
                field_count += 1
            chunk += line + "\n"

        if chunk:
            label = "🗓️ Coming Up" if field_count == 0 else "🗓️ Coming Up (cont.)"
            embed.add_field(name=label, value=chunk.strip(), inline=False)

    total = len(ranked_rotations)
    embed.set_footer(text=f"🏆 Ranked  •  {total} slots shown  •  Times in your local timezone")
    return embed


def build_alert_embed(map_name: str, next_map: str, end_timestamp: int) -> discord.Embed:
    """Fancy auto-alert embed when map changes."""
    meta      = get_map(map_name)
    next_meta = get_map(next_map)
    color     = meta["color"]
    emoji     = meta["emoji"]

    embed = discord.Embed(
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    embed.set_author(
        name="🔄  RANKED MAP ROTATION",
        icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/Apex_legends_diamond_rank_insignia.png/240px-Apex_legends_diamond_rank_insignia.png",
    )

    embed.title = f"{emoji}  {map_name} is now live!"
    embed.description = f"*{meta['description']}*"

    embed.add_field(
        name="⏱️ Ends",
        value=f"<t:{end_timestamp}:t> (<t:{end_timestamp}:R>)",
        inline=True,
    )
    embed.add_field(
        name="🔜 Next Up",
        value=f"{next_meta['emoji']}  **{next_map}**",
        inline=True,
    )

    if meta.get("image"):
        embed.set_image(url=meta["image"])

    embed.set_footer(text="🏆 Apex Legends Ranked Tracker")
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
        start_ts      = current.get("start", 0)

        embed = build_currentmap_embed(map_name, next_map, end_timestamp, start_ts)
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
        ranked   = data.get("ranked", {})
        current  = ranked.get("current", {})
        upcoming = ranked.get("upcoming", [])

        rotations = []

        if current.get("map"):
            rotations.append({
                "map":   current.get("map"),
                "start": current.get("start", 0),
                "end":   current.get("end", 0),
            })

        for slot in upcoming:
            if slot.get("map"):
                rotations.append({
                    "map":   slot.get("map"),
                    "start": slot.get("start", 0),
                    "end":   slot.get("end", 0),
                })

        if not upcoming:
            nxt = ranked.get("next", {})
            if nxt.get("map"):
                rotations.append({
                    "map":   nxt.get("map"),
                    "start": current.get("end", 0),
                    "end":   nxt.get("end", 0),
                })

        now_ts      = int(datetime.now(timezone.utc).timestamp())
        cutoff_ts   = now_ts + 86400
        today_slots = [s for s in rotations if s["end"] > now_ts and s["start"] < cutoff_ts]

        embed = build_todays_schedule_embed(today_slots)
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
                            embed = build_alert_embed(map_name, next_map, end_timestamp)
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
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Ranked Map Rotation 🗺️"
        )
    )
    print(f"[{now()}] 🤖 Logged in as {client.user}")
    print(f"[{now()}] ✅ Slash commands registered: /currentmap, /todaysmaps")
    print(f"[{now()}] 🔄 Polling every {CHECK_INTERVAL}s for ranked map changes...")
    # client.loop.create_task(ranked_map_loop())


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set in .env")
        exit(1)
    if not CHANNEL_ID:
        print("❌ CHANNEL_ID not set in .env")
        exit(1)

    client.run(TOKEN)