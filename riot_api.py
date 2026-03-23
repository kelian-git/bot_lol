import requests
import os
from dotenv import load_dotenv

load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

REGION = "euw1"
REGION_V5 = "europe"

def get_summoner(game_name, tag_line):
    url = f"https://{REGION_V5}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_API_KEY})
    if r.status_code != 200:
        return None
    return r.json()

def get_summoner_by_puuid(puuid):
    url = f"https://{REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_API_KEY})
    if r.status_code != 200:
        return {"id": puuid}
    data = r.json()
    return data if "id" in data else {"id": puuid}

def get_spectator(puuid):
    url = f"https://{REGION}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_API_KEY})
    if r.status_code == 200:
        return r.json()
    return None

def get_last_match_id(puuid):
    url = f"https://{REGION_V5}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=1"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_API_KEY})
    if r.status_code != 200:
        return None
    matches = r.json()
    return matches[0] if matches else None

def get_match_details(match_id):
    url = f"https://{REGION_V5}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_API_KEY})
    if r.status_code != 200:
        return None
    return r.json()

def get_elo(puuid):
    url = f"https://{REGION}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_API_KEY})
    if r.status_code != 200:
        return []
    return r.json()

def get_latest_version():
    try:
        r = requests.get("https://ddragon.leagueoflegends.com/api/versions.json")
        return r.json()[0]
    except:
        return "15.6.1"

def get_champion_icon_url(champion_name, version=None):
    if not version:
        version = get_latest_version()
    return f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champion_name}.png"

QUEUE_NAMES = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    400: "Normal Draft",
    430: "Normal Blind",
    450: "ARAM",
    900: "URF",
    1020: "One for All",
}

LANE_NAMES = {
    "TOP": "Top",
    "JUNGLE": "Jungle",
    "MIDDLE": "Mid",
    "BOTTOM": "Bot",
    "UTILITY": "Support",
}
