import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
import requests as req
from datetime import datetime
from dotenv import load_dotenv
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

# Charger les joueurs
def load_joueurs():
    with open("joueurs.json", "r") as f:
        return json.load(f)["joueurs"]

def save_joueurs(joueurs):
    with open("joueurs.json", "w") as f:
        json.dump({"joueurs": joueurs}, f, indent=2)

# Dictionnaire des noms de champions (id -> nom)
champion_id_to_name = {}
ddragon_version = "15.6.1"

def load_champion_data():
    global champion_id_to_name, ddragon_version
    try:
        version_r = req.get("https://ddragon.leagueoflegends.com/api/versions.json")
        ddragon_version = version_r.json()[0]
        print(f"✅ Version Data Dragon : {ddragon_version}")
        r = req.get(f"https://ddragon.leagueoflegends.com/cdn/{ddragon_version}/data/fr_FR/champion.json")
        data = r.json()["data"]
        champion_id_to_name = {int(v["key"]): v["id"] for v in data.values()}
        print(f"✅ {len(champion_id_to_name)} champions chargés")
    except Exception as e:
        print(f"❌ Erreur chargement champions : {e}")

def get_champion_name(champion_id):
    return champion_id_to_name.get(int(champion_id), str(champion_id))

# Images de rang officielles Riot
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

def build_elo_embed(lines, page, total_pages, file_name, total_joueurs):
    chunk = lines[page * 10:(page + 1) * 10]
    top_tier = chunk[0][0] if chunk else "ZZZ"
    tier_image = TIER_IMAGES.get(top_tier, TIER_IMAGES["ZZZ"])

    embed = discord.Embed(
        title=f"📊 Classement — {file_name}",
        color=0x2ecc71
    )
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


# Etat des joueurs en game
en_game = {}

@bot.event
async def setup_hook():
    load_champion_data()

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot connecté : {bot.user}")
    check_games.start()

# Commande /ajouter
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

# Commande /supprimer
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

# Commande /elo
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
            lines.append((
                tier, rank, lp,
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
    await interaction.followup.send(embed=embed, view=view)

# Boucle de vérification toutes les 60 secondes
@tasks.loop(seconds=60)
async def check_games():
    print("🔄 Vérification des games...")
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Salon introuvable !")
        return
    joueurs = load_joueurs()
    print(f"👥 {len(joueurs)} joueur(s) surveillé(s)")

    for j in joueurs:
        puuid = j["puuid"]
        pseudo = j["pseudo"]
        print(f"🔍 Vérification de {pseudo}...")
        game_data = get_spectator(puuid)

        if game_data:
            print(f"🎮 {pseudo} est en game !")
            if puuid not in en_game:
                queue_id = game_data.get("gameQueueConfigId", 0)
                mode = QUEUE_NAMES.get(queue_id, "Autre mode")
                last_match = get_last_match_id(puuid)

                player_data = next((p for p in game_data["participants"] if p["puuid"] == puuid), None)
                if not player_data:
                    continue

                champion = get_champion_name(player_data["championId"])

                en_game[puuid] = {
                    "champion": champion,
                    "mode": mode,
                    "last_match_before": last_match
                }

                embed = discord.Embed(title="🎮 En Game !", color=0x2ecc71)
                embed.add_field(name="👤 Joueur", value=pseudo, inline=True)
                embed.add_field(name="🎯 Mode", value=mode, inline=True)
                embed.add_field(name="🏆 Champion", value=champion, inline=True)
                embed.set_thumbnail(url=get_champion_icon_url(champion, ddragon_version))
                await channel.send(embed=embed)

        else:
            print(f"💤 {pseudo} n'est pas en game")
            if puuid in en_game:
                game_info = en_game.pop(puuid)
                print(f"🏁 Fin de game détectée pour {pseudo}, attente 30s...")
                await asyncio.sleep(30)

                new_match_id = get_last_match_id(puuid)
                if not new_match_id or new_match_id == game_info["last_match_before"]:
                    print(f"⚠️ Pas de nouveau match trouvé pour {pseudo}")
                    continue

                match = get_match_details(new_match_id)
                if not match:
                    continue

                info = match["info"]
                duration_sec = info["gameDuration"]
                duration = f"{duration_sec // 60} min {duration_sec % 60} sec"

                player_stats = next((p for p in info["participants"] if p["puuid"] == puuid), None)
                if not player_stats:
                    continue

                win = player_stats["win"]
                kda_player = f"{player_stats['kills']} / {player_stats['deaths']} / {player_stats['assists']}"
                champ_player = player_stats["championName"]
                lane = LANE_NAMES.get(player_stats.get("teamPosition", ""), "Inconnue")

                opponent_stats = next((
                    p for p in info["participants"]
                    if p.get("teamPosition") == player_stats.get("teamPosition")
                    and p["teamId"] != player_stats["teamId"]
                ), None)

                champ_opp = opponent_stats["championName"] if opponent_stats else "Inconnu"
                kda_opp = f"{opponent_stats['kills']} / {opponent_stats['deaths']} / {opponent_stats['assists']}" if opponent_stats else "N/A"

                queue_id = info.get("queueId", 0)
                mode = QUEUE_NAMES.get(queue_id, game_info["mode"])

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
                embed.add_field(name="🏆 Résultat", value="VICTOIRE 🏆" if win else "DÉFAITE 💀", inline=False)
                embed.set_thumbnail(url=get_champion_icon_url(champ_player, ddragon_version))
                embed.set_image(url=get_champion_icon_url(champ_opp, ddragon_version))
                await channel.send(embed=embed)

bot.run(DISCORD_TOKEN)
