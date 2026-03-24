import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
import requests as req
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from riot_api import (
    get_summoner, get_summoner_by_puuid, get_spectator,
    get_last_match_id, get_match_details, get_elo,
    get_champion_icon_url, get_latest_version,
    QUEUE_NAMES, LANE_NAMES
)

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ── JOUEURS ──
def load_joueurs():
    if not os.path.exists("joueurs.json"):
        with open("joueurs.json", "w") as f:
            json.dump({"joueurs": []}, f)
    with open("joueurs.json", "r") as f:
        return json.load(f)["joueurs"]

def save_joueurs(joueurs):
    with open("joueurs.json", "w") as f:
        json.dump({"joueurs": joueurs}, f, indent=2)

# ── CHAMPIONS ──
champion_id_to_name = {}
ddragon_version = "16.6.1"

def load_champion_data():
    global champion_id_to_name, ddragon_version
    try:
        version_r = req.get("https://ddragon.leagueoflegends.com/api/versions.json")
        ddragon_version = version_r.json()[0]
        print(f"✅ Version Data Dragon : {ddragon_version}")
        r = req.get(f"https://ddragon.leagueoflegends.com/cdn/{ddragon_version}/data/fr_FR/champion.json")
        data = r.json()["data"]
        champion_id_to_name = {int(v["key"]): v["id"] for v in data.values()}
        print(f"✅ {len(champion_id_to_name)} champions charges")
    except Exception as e:
        print(f"Erreur chargement champions : {e}")

def get_champion_name(champion_id):
    return champion_id_to_name.get(int(champion_id), str(champion_id))

def get_champ_icon(champion_name):
    try:
        url = get_champion_icon_url(champion_name, ddragon_version)
        r = req.get(url, timeout=5)
        img = Image.open(BytesIO(r.content)).convert("RGBA").resize((80, 80))
        return img
    except:
        return None

# ── TIER IMAGES & ORDRE ──
TIER_IMAGES = {
    "CHALLENGER":   "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-challenger.png",
    "GRANDMASTER":  "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-grandmaster.png",
    "MASTER":       "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-master.png",
    "DIAMOND":      "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-diamond.png",
    "EMERALD":      "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-emerald.png",
    "PLATINUM":     "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-platinum.png",
    "GOLD":         "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-gold.png",
    "SILVER":       "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-silver.png",
    "BRONZE":       "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-bronze.png",
    "IRON":         "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-iron.png",
    "ZZZ":          "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/ranked-emblem/emblem-unranked.png",
}

TIER_ORDER = ["CHALLENGER", "GRANDMASTER", "MASTER", "DIAMOND", "EMERALD", "PLATINUM", "GOLD", "SILVER", "BRONZE", "IRON", "ZZZ"]

LANE_COLORS = {
    "Top":     (200, 150, 50),
    "Jungle":  (80, 180, 80),
    "Mid":     (150, 100, 220),
    "Bot":     (50, 150, 220),
    "Support": (220, 100, 150),
    "Inconnue":(150, 150, 150),
}

# ── GENERATION IMAGE FLEX ──
def generate_flex_image(blue_team, red_team, win, mode, duration, lp_data):
    ICON_SIZE = 80
    PADDING = 12
    VS_WIDTH = 50
    TEXT_HEIGHT = 18
    BG_COLOR = (15, 15, 25)
    WHITE = (255, 255, 255)
    GRAY = (150, 150, 150)
    YELLOW = (255, 200, 0)
    GREEN = (80, 220, 80)
    RED_C = (220, 80, 80)

    n = 5
    icon_block_w = (n * (ICON_SIZE + PADDING)) * 2 + VS_WIDTH + PADDING * 6
    icon_block_h = ICON_SIZE + TEXT_HEIGHT * 3 + PADDING * 4
    header_h = 90
    footer_h = 30 * len(lp_data) + PADDING * 2 if lp_data else 0

    total_width = icon_block_w
    total_height = header_h + icon_block_h + footer_h

    img = Image.new("RGB", (total_width, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_vs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_role = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
    except:
        font_bold = font = font_title = font_sub = font_vs = font_role = ImageFont.load_default()

    result_color = GREEN if win else RED_C

    # Ligne couleur résultat en haut
    draw.rectangle([0, 0, total_width, 4], fill=result_color)

    # Titre sans emojis
    title = "VICTOIRE" if win else "DEFAITE"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((total_width - tw) // 2, 14), title, font=font_title, fill=result_color)

    # Sous-titre sans emojis
    tracked_count = len(lp_data)
    sub = f"{mode}  |  {duration}  |  {tracked_count} joueur(s) suivi(s)"
    bbox = draw.textbbox((0, 0), sub, font=font_sub)
    tw = bbox[2] - bbox[0]
    draw.text(((total_width - tw) // 2, 48), sub, font=font_sub, fill=GRAY)

    # Séparateur
    draw.rectangle([PADDING * 2, 78, total_width - PADDING * 2, 80], fill=(40, 40, 60))

    def draw_team(team_data, start_x, border_color, icon_color, offset_y):
        for i, (champ, kda, role) in enumerate(team_data):
            x = start_x + i * (ICON_SIZE + PADDING)
            y = offset_y + PADDING

            champ_icon = get_champ_icon(champ)
            if champ_icon:
                draw.rectangle([x - 2, y - 2, x + ICON_SIZE + 2, y + ICON_SIZE + 2], fill=border_color)
                img.paste(champ_icon, (x, y), champ_icon)
            else:
                draw.rectangle([x - 2, y - 2, x + ICON_SIZE + 2, y + ICON_SIZE + 2], fill=border_color)
                draw.rectangle([x, y, x + ICON_SIZE, y + ICON_SIZE], fill=icon_color)
                initials = champ[:2].upper()
                bbox = draw.textbbox((0, 0), initials, font=font_bold)
                tw2, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((x + (ICON_SIZE - tw2) // 2, y + (ICON_SIZE - th) // 2), initials, font=font_bold, fill=WHITE)

            name = champ[:8]
            bbox = draw.textbbox((0, 0), name, font=font)
            tw2 = bbox[2] - bbox[0]
            draw.text((x + (ICON_SIZE - tw2) // 2, y + ICON_SIZE + 4), name, font=font, fill=GRAY)

            bbox2 = draw.textbbox((0, 0), kda, font=font_bold)
            tw2 = bbox2[2] - bbox2[0]
            draw.text((x + (ICON_SIZE - tw2) // 2, y + ICON_SIZE + TEXT_HEIGHT + 5), kda, font=font_bold, fill=WHITE)

            role_color = LANE_COLORS.get(role, (150, 150, 150))
            bbox3 = draw.textbbox((0, 0), role, font=font_role)
            tw2 = bbox3[2] - bbox3[0]
            draw.text((x + (ICON_SIZE - tw2) // 2, y + ICON_SIZE + TEXT_HEIGHT * 2 + 6), role, font=font_role, fill=role_color)

    offset_y = header_h
    draw_team(blue_team, PADDING, (40, 80, 160), (50, 100, 200), offset_y)

    vs_x = PADDING + n * (ICON_SIZE + PADDING) + PADDING
    draw.text((vs_x + 4, offset_y + ICON_SIZE // 2), "VS", font=font_vs, fill=YELLOW)

    red_start = vs_x + VS_WIDTH + PADDING
    draw_team(red_team, red_start, (160, 40, 40), (200, 50, 50), offset_y)

    # Footer LP sans emojis
    if lp_data:
        footer_y = header_h + icon_block_h
        draw.rectangle([PADDING * 2, footer_y, total_width - PADDING * 2, footer_y + 2], fill=(40, 40, 60))
        for i, (pseudo, rank_str, lp_before, lp_after) in enumerate(lp_data):
            y = footer_y + PADDING + i * 30
            diff = lp_after - lp_before
            diff_color = GREEN if diff >= 0 else RED_C
            diff_str = f"+{diff}" if diff >= 0 else str(diff)
            line = f"{pseudo}  -  {rank_str}  |  {lp_before} -> {lp_after} LP  ({diff_str})"
            draw.text((PADDING * 3, y + 6), line, font=font_sub, fill=WHITE)

    draw.rectangle([0, total_height - 4, total_width, total_height], fill=result_color)

    output = BytesIO()
    img.convert("RGB").save(output, format="PNG")
    output.seek(0)
    return output


# ── ELO EMBED ──
def build_elo_embed(lines, page, total_pages, file_name, total_joueurs):
    chunk = lines[page * 10:(page + 1) * 10]
    top_tier = chunk[0][0] if chunk else "ZZZ"
    tier_image = TIER_IMAGES.get(top_tier, TIER_IMAGES["ZZZ"])
    embed = discord.Embed(title=f"📊 Classement — {file_name}", color=0x2ecc71)
    embed.set_thumbnail(url=tier_image)
    description = ""
    for i, (tier, rank, lp, text) in enumerate(chunk):
        position = page * 10 + i + 1
        description += f"`#{position:02}` {text}\n\n"
    embed.description = description
    embed.set_footer(text=f"Page {page + 1}/{total_pages} • {total_joueurs} joueurs suivis")
    return embed


class EloView(discord.ui.View):
    def __init__(self, lines, file_name, total_joueurs):
        super().__init__(timeout=120)
        self.lines = lines
        self.file_name = file_name
        self.total_joueurs = total_joueurs
        self.page = 0
        self.total_pages = (len(lines) + 9) // 10
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1
        self.page_label.label = f"{self.page + 1} / {self.total_pages}"

    @discord.ui.button(label="◀ Précédent", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.update_buttons()
        embed = build_elo_embed(self.lines, self.page, self.total_pages, self.file_name, self.total_joueurs)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Suivant ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.update_buttons()
        embed = build_elo_embed(self.lines, self.page, self.total_pages, self.file_name, self.total_joueurs)
        await interaction.edit_original_response(embed=embed, view=self)


# ── ETAT DES GAMES ──
en_game = {}
lp_snapshot = {}
# Suivi des recaps groupés déjà envoyés : match_id -> True
group_recap_sent = {}


@bot.event
async def setup_hook():
    load_champion_data()


@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot connecté : {bot.user}")
    check_games.start()


# ── COMMANDES ──
@tree.command(name="ajouter", description="Ajouter un joueur à surveiller")
@app_commands.describe(pseudo="Pseudo du joueur", tag="Tag (ex: EUW)")
async def ajouter(interaction: discord.Interaction, pseudo: str, tag: str):
    await interaction.response.defer()
    data = get_summoner(pseudo, tag)
    if not data:
        await interaction.followup.send(f"❌ Joueur `{pseudo}#{tag}` introuvable !", ephemeral=True)
        return
    puuid = data["puuid"]
    summoner = get_summoner_by_puuid(puuid)
    joueurs = load_joueurs()
    if any(j["puuid"] == puuid for j in joueurs):
        await interaction.followup.send(f"⚠️ `{pseudo}#{tag}` est déjà dans la liste !", ephemeral=True)
        return
    summoner_id = summoner.get("id", puuid)
    joueurs.append({"pseudo": pseudo, "tag": tag, "puuid": puuid, "summoner_id": summoner_id})
    save_joueurs(joueurs)
    await interaction.followup.send(f"✅ `{pseudo}#{tag}` ajouté à la liste de surveillance !")


@tree.command(name="supprimer", description="Supprimer un joueur de la surveillance")
@app_commands.describe(pseudo="Pseudo du joueur")
async def supprimer(interaction: discord.Interaction, pseudo: str):
    joueurs = load_joueurs()
    new_list = [j for j in joueurs if j["pseudo"].lower() != pseudo.lower()]
    if len(new_list) == len(joueurs):
        await interaction.response.send_message(f"❌ `{pseudo}` introuvable dans la liste !", ephemeral=True)
        return
    save_joueurs(new_list)
    await interaction.response.send_message(f"✅ `{pseudo}` supprimé de la liste !")


@tree.command(name="elo", description="Afficher l'elo de tous les joueurs suivis")
@app_commands.describe(file="La file : solo ou flex")
async def elo(interaction: discord.Interaction, file: str = "solo"):
    await interaction.response.defer()
    joueurs = load_joueurs()
    if not joueurs:
        await interaction.followup.send("❌ Aucun joueur dans la liste !")
        return

    queue_type = "RANKED_SOLO_5x5" if "solo" in file.lower() else "RANKED_FLEX_SR"
    file_name = "Ranked Solo/Duo" if queue_type == "RANKED_SOLO_5x5" else "Ranked Flex"

    lines = []
    for j in joueurs:
        elo_data = get_elo(j["puuid"])
        entry = next((e for e in elo_data if e["queueType"] == queue_type), None)
        if entry:
            tier = entry["tier"]
            rank = entry["rank"]
            lp = entry["leaguePoints"]
            wins = entry["wins"]
            losses = entry["losses"]
            total = wins + losses
            winrate = round((wins / total) * 100) if total > 0 else 0
            lines.append((tier, rank, lp,
                f"**{j['pseudo']}**\n"
                f"┣ {tier.capitalize()} {rank} — {lp} LP\n"
                f"┗ {wins}W / {losses}L — {winrate}% WR"
            ))
        else:
            lines.append(("ZZZ", "Z", 0,
                f"**{j['pseudo']}**\n"
                f"┗ Non classé"
            ))

    rank_order = {"I": 0, "II": 1, "III": 2, "IV": 3, "Z": 4}
    lines.sort(key=lambda x: (
        TIER_ORDER.index(x[0]) if x[0] in TIER_ORDER else 99,
        rank_order.get(x[1], 9),
        -x[2]
    ))

    total_pages = (len(lines) + 9) // 10
    view = EloView(lines, file_name, len(joueurs)) if total_pages > 1 else None
    embed = build_elo_embed(lines, 0, total_pages, file_name, len(joueurs))
    if view:
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(embed=embed)


# ── BOUCLE PRINCIPALE ──
@tasks.loop(seconds=60)
async def check_games():
    print("🔄 Vérification des games...")
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Salon introuvable !")
        return
    joueurs = load_joueurs()
    print(f"👥 {len(joueurs)} joueur(s) surveillé(s)")

    # Regrouper les joueurs actifs par gameId
    active_games = {}
    for j in joueurs:
        puuid = j["puuid"]
        game_data = get_spectator(puuid)
        if game_data:
            game_id = str(game_data.get("gameId", ""))
            if game_id not in active_games:
                active_games[game_id] = []
            active_games[game_id].append((j, game_data))

    # Traiter les nouveaux en game
    for game_id, players in active_games.items():
        for j, game_data in players:
            puuid = j["puuid"]
            pseudo = j["pseudo"]

            if puuid not in en_game:
                print(f"🎮 {pseudo} est en game !")
                queue_id = game_data.get("gameQueueConfigId", 0)
                mode = QUEUE_NAMES.get(queue_id, "Autre mode")
                last_match = get_last_match_id(puuid)

                player_data = next((p for p in game_data["participants"] if p["puuid"] == puuid), None)
                if not player_data:
                    continue

                champion = get_champion_name(player_data["championId"])

                # Sauvegarder LP avant la game
                queue_type = "RANKED_FLEX_SR" if queue_id == 440 else "RANKED_SOLO_5x5"
                elo_data = get_elo(puuid)
                entry = next((e for e in elo_data if e["queueType"] == queue_type), None)
                lp_before = entry["leaguePoints"] if entry else None
                rank_str = f"{entry['tier'].capitalize()} {entry['rank']}" if entry else "Non classe"

                lp_snapshot[puuid] = {
                    "lp": lp_before,
                    "rank": rank_str,
                    "queue_type": queue_type
                }

                en_game[puuid] = {
                    "champion": champion,
                    "mode": mode,
                    "queue_id": queue_id,
                    "game_id": game_id,
                    "last_match_before": last_match
                }

                embed = discord.Embed(title="🎮 En Game !", color=0x2ecc71)
                embed.add_field(name="👤 Joueur", value=pseudo, inline=True)
                embed.add_field(name="🎯 Mode", value=mode, inline=True)
                embed.add_field(name="🏆 Champion", value=champion, inline=True)
                if lp_before is not None:
                    embed.add_field(name="📊 Rang actuel", value=f"{rank_str} — {lp_before} LP", inline=False)
                embed.set_thumbnail(url=get_champion_icon_url(champion, ddragon_version))
                await channel.send(embed=embed)

    # Détecter les fins de game
    puuids_en_game = list(en_game.keys())
    active_puuids = {j["puuid"] for players in active_games.values() for j, _ in players}

    for puuid in puuids_en_game:
        if puuid in active_puuids:
            continue

        j = next((j for j in joueurs if j["puuid"] == puuid), None)
        if not j:
            en_game.pop(puuid, None)
            continue

        pseudo = j["pseudo"]
        game_info = en_game.pop(puuid)
        print(f"🏁 Fin de game pour {pseudo}, attente 30s...")
        await asyncio.sleep(30)

        new_match_id = get_last_match_id(puuid)
        if not new_match_id or new_match_id == game_info["last_match_before"]:
            print(f"⚠️ Pas de nouveau match pour {pseudo}")
            lp_snapshot.pop(puuid, None)
            continue

        match = get_match_details(new_match_id)
        if not match:
            lp_snapshot.pop(puuid, None)
            continue

        info = match["info"]
        duration_sec = info["gameDuration"]
        duration = f"{duration_sec // 60} min {duration_sec % 60} sec"
        queue_id = info.get("queueId", 0)
        mode = QUEUE_NAMES.get(queue_id, game_info["mode"])
        is_flex = queue_id == 440

        player_stats = next((p for p in info["participants"] if p["puuid"] == puuid), None)
        if not player_stats:
            lp_snapshot.pop(puuid, None)
            continue

        win = player_stats["win"]

        # LP après la game
        snap = lp_snapshot.pop(puuid, None)
        lp_after = None
        if snap:
            elo_after = get_elo(puuid)
            entry_after = next((e for e in elo_after if e["queueType"] == snap["queue_type"]), None)
            if entry_after:
                lp_after = entry_after["leaguePoints"]

        # ── RECAP GROUPE FLEX ──
        if is_flex:
            # Vérifier si ce match_id a déjà eu un recap groupé
            if new_match_id in group_recap_sent:
                # Ajouter juste les LP de ce joueur si pas déjà dedans
                continue

            # Chercher tous les joueurs suivis dans ce match
            all_participants_puuids = {p["puuid"] for p in info["participants"]}
            tracked_in_game = [
                j2 for j2 in joueurs
                if j2["puuid"] in all_participants_puuids
            ]

            if len(tracked_in_game) > 1:
                # Recap groupé
                group_recap_sent[new_match_id] = True

                # Retirer les autres joueurs de en_game pour éviter des recaps solo
                for j2 in tracked_in_game:
                    if j2["puuid"] != puuid:
                        en_game.pop(j2["puuid"], None)

                all_participants = info["participants"]
                blue = [p for p in all_participants if p["teamId"] == 100]
                red = [p for p in all_participants if p["teamId"] == 200]

                def build_team(team):
                    result = []
                    for p in team:
                        kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
                        lane = LANE_NAMES.get(p.get("teamPosition", ""), "Inconnue")
                        result.append((p["championName"], kda, lane))
                    return result

                blue_team = build_team(blue)
                red_team = build_team(red)

                # LP data pour tous les joueurs suivis dans la game
                lp_data = []
                for j2 in tracked_in_game:
                    p2_puuid = j2["puuid"]
                    snap2 = lp_snapshot.pop(p2_puuid, None)
                    if p2_puuid == puuid:
                        snap2 = snap
                        lp_after2 = lp_after
                    else:
                        elo2 = get_elo(p2_puuid)
                        queue_type2 = snap2["queue_type"] if snap2 else "RANKED_FLEX_SR"
                        entry2 = next((e for e in elo2 if e["queueType"] == queue_type2), None)
                        lp_after2 = entry2["leaguePoints"] if entry2 else None

                    if snap2 and snap2["lp"] is not None and lp_after2 is not None:
                        lp_data.append((
                            j2["pseudo"],
                            snap2["rank"],
                            snap2["lp"],
                            lp_after2
                        ))

                img_bytes = generate_flex_image(blue_team, red_team, win, mode, duration, lp_data)
                file = discord.File(img_bytes, filename="recap_flex.png")
                embed = discord.Embed(
                    title="Game Flex terminee !",
                    color=0x2ecc71 if win else 0xe74c3c
                )
                embed.set_image(url="attachment://recap_flex.png")
                await channel.send(embed=embed, file=file)
                continue

        # ── RECAP SOLO ──
        champ_player = player_stats["championName"]
        kda_player = f"{player_stats['kills']} / {player_stats['deaths']} / {player_stats['assists']}"
        lane = LANE_NAMES.get(player_stats.get("teamPosition", ""), "Inconnue")

        opponent_stats = next((
            p for p in info["participants"]
            if p.get("teamPosition") == player_stats.get("teamPosition")
            and p["teamId"] != player_stats["teamId"]
        ), None)

        champ_opp = opponent_stats["championName"] if opponent_stats else "Inconnu"
        kda_opp = f"{opponent_stats['kills']} / {opponent_stats['deaths']} / {opponent_stats['assists']}" if opponent_stats else "N/A"

        embed = discord.Embed(
            title="✅ Game terminée !",
            color=0x2ecc71 if win else 0xe74c3c
        )
        embed.add_field(name="👤 Joueur", value=pseudo, inline=True)
        embed.add_field(name="🎯 Mode", value=mode, inline=True)
        embed.add_field(name="⏱️ Durée", value=duration, inline=True)
        embed.add_field(name="⚔️ Matchup", value=f"{pseudo} ({champ_player}) vs {champ_opp} — {lane}", inline=False)
        embed.add_field(name=f"📊 KDA {pseudo}", value=kda_player, inline=True)
        embed.add_field(name=f"📊 KDA {champ_opp}", value=kda_opp, inline=True)

        if snap and snap["lp"] is not None and lp_after is not None:
            diff = lp_after - snap["lp"]
            diff_str = f"+{diff}" if diff >= 0 else str(diff)
            embed.add_field(
                name="📈 LP",
                value=f"{snap['lp']} -> {lp_after} LP ({diff_str})",
                inline=False
            )

        embed.add_field(name="🏆 Résultat", value="VICTOIRE 🏆" if win else "DÉFAITE 💀", inline=False)
        embed.set_thumbnail(url=get_champion_icon_url(champ_player, ddragon_version))
        embed.set_image(url=get_champion_icon_url(champ_opp, ddragon_version))
        await channel.send(embed=embed)


bot.run(DISCORD_TOKEN)
