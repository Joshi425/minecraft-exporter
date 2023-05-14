import json
import os
import re
import time
from os import listdir
from os.path import isfile, join

import nbt
import requests
import schedule
from mcrcon import MCRcon, MCRconException
from prometheus_client import Metric, REGISTRY, start_http_server


class MinecraftCollector(object):
    def __init__(self):
        self.stats_directory = "/world/stats"
        self.player_directory = "/world/playerdata"
        self.advancements_directory = "/world/advancements"
        self.better_questing = "/world/betterquesting"
        self.player_map = dict()
        self.quests_enabled = False

        self.rcon = None
        self.rcon_connected = False
        if all(x in os.environ for x in ['RCON_HOST', 'RCON_PASSWORD']):
            self.rcon = MCRcon(os.environ['RCON_HOST'], os.environ['RCON_PASSWORD'], port=int(os.environ['RCON_PORT']))
            print("RCON is enabled for " + os.environ['RCON_HOST'])

        if os.path.isdir(self.better_questing):
            self.quests_enabled = True

        schedule.every().day.at("01:00").do(self.flush_playernamecache)

    def get_players(self):
        return [f[:-5] for f in listdir(self.stats_directory) if isfile(join(self.stats_directory, f))]

    def flush_playernamecache(self):
        print("flushing playername cache")
        self.player_map = dict()

    def uuid_to_player(self, uuid):
        if uuid in self.player_map:
            return self.player_map[uuid]
        else:
            try:
                result = requests.get('https://sessionserver.mojang.com/session/minecraft/profile/' + uuid)
                self.player_map[uuid] = result.json()['name']
                return (result.json()['name'])
            except:
                return

    def rcon_connect(self):
        try:
            self.rcon.connect()
            self.rcon_connected = True
            print("Successfully connected to RCON")
            return True
        except Exception as e:
            print("Failed to connect to RCON")
            print(e)
        return False

    def rcon_disconnect(self):
        self.rcon.disconnect()
        self.rcon_connected = False

    def rcon_command(self, command):
        try:
            response = self.rcon.command(command)
        except MCRconException as e:
            response = None
            if e == "Connection timeout error":
                print("Lost RCON Connection")
                self.rcon_disconnect()
            else:
                print("RCON command failed")
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            print("Lost RCON Connection")
            self.rcon_disconnect()
            response = None

        return response

    def get_server_stats(self):
        if self.rcon is None or (not self.rcon_connected and not self.rcon_connect()):
            return []

        metrics = []

        forge_dim_tps = Metric('forge_dim_tps', 'TPS of a dimension', "counter")
        forge_dim_ticktime = Metric('forge_dim_ticktime', "Time a Tick took in a Dimension", "counter")
        forge_overall_tps = Metric('forge_overall_tps', 'overall TPS', "counter")
        forge_overall_ticktime = Metric('forge_overall_ticktime', "overall Ticktime", "counter")
        minecraft_player_online = Metric('minecraft_player_online', "is 1 if player is online", "counter")
        forge_entities = Metric('forge_entities', "type and count of active entites", "counter")
        paper_tps_1m = Metric('paper_tps_1m', '1 Minute TPS', "counter")
        paper_tps_5m = Metric('paper_tps_5m', '5 Minute TPS', "counter")
        paper_tps_15m = Metric('paper_tps_15m', '15 Minute TPS', "counter")

        metrics.extend(
            [forge_dim_tps, forge_dim_ticktime, forge_overall_tps, forge_overall_ticktime, minecraft_player_online, forge_entities, paper_tps_1m, paper_tps_5m, paper_tps_15m])
        if 'PAPER_SERVER' in os.environ and os.environ['PAPER_SERVER'].lower() == "true":
            resp = str(self.rcon_command("tps")).strip().replace("§a", "")
            tpsregex = re.compile("TPS from last 1m, 5m, 15m: (\d*\.\d*), (\d*\.\d*), (\d*\.\d*)")
            for m1, m5, m15 in tpsregex.findall(resp):
                paper_tps_1m.add_sample('paper_tps_1m', value=m1, labels={'tps': '1m'})
                paper_tps_5m.add_sample('paper_tps_5m', value=m5, labels={'tps': '5m'})
                paper_tps_15m.add_sample('paper_tps_15m', value=m15, labels={'tps': '15m'})
        if 'FORGE_SERVER' in os.environ and os.environ['FORGE_SERVER'].lower() == "true":
            # dimensions
            resp = self.rcon_command("forge tps")
            dimtpsregex = re.compile("Dim\s*(-*\d*)\s\((.*?)\)\s:\sMean tick time:\s(.*?) ms\. Mean TPS: (\d*\.\d*)")
            for dimid, dimname, meanticktime, meantps in dimtpsregex.findall(resp):
                forge_dim_tps.add_sample('forge_dim_tps', value=meantps, labels={'dimension_id': dimid, 'dimension_name': dimname})
                forge_dim_ticktime.add_sample('forge_dim_ticktime', value=meanticktime,
                                        labels={'dimension_id': dimid, 'dimension_name': dimname})
            overallregex = re.compile("Overall\s?: Mean tick time: (.*) ms. Mean TPS: (.*)")
            forge_overall_tps.add_sample('forge_overall_tps', value=overallregex.findall(resp)[0][1], labels={})
            forge_overall_ticktime.add_sample('forge_overall_ticktime', value=overallregex.findall(resp)[0][0], labels={})

            # entites
            resp = self.rcon_command("forge entity list")
            entityregex = re.compile("(\d+): (.*?:.*?)\s")
            for entitycount, entityname in entityregex.findall(resp):
                forge_entities.add_sample('forge_entities', value=entitycount, labels={'entity': entityname})

        # dynmap
        if 'DYNMAP_ENABLED' in os.environ and os.environ['DYNMAP_ENABLED'].lower() == "true":
            dynmap_tile_render_statistics = Metric('dynmap_tile_render_statistics',
                                                   'Tile Render Statistics reported by Dynmap', "counter")
            dynmap_chunk_loading_statistics_count = Metric('dynmap_chunk_loading_statistics_count',
                                                           'Chunk Loading Statistics reported by Dynmap', "counter")
            dynmap_chunk_loading_statistics_duration = Metric('dynmap_chunk_loading_statistics_duration',
                                                              'Chunk Loading Statistics reported by Dynmap', "counter")
            metrics.extend([dynmap_tile_render_statistics, dynmap_chunk_loading_statistics_count,
                            dynmap_chunk_loading_statistics_duration])

            resp = self.rcon_command("dynmap stats")

            dynmaptilerenderregex = re.compile("  (.*?): processed=(\d*), rendered=(\d*), updated=(\d*)")
            for dim, processed, rendered, updated in dynmaptilerenderregex.findall(resp):
                dynmap_tile_render_statistics.add_sample('dynmap_tile_render_statistics', value=processed,
                                                         labels={'type': 'processed', 'file': dim})
                dynmap_tile_render_statistics.add_sample('dynmap_tile_render_statistics', value=rendered,
                                                         labels={'type': 'rendered', 'file': dim})
                dynmap_tile_render_statistics.add_sample('dynmap_tile_render_statistics', value=updated,
                                                         labels={'type': 'updated', 'file': dim})

            dynmapchunkloadingregex = re.compile("Chunks processed: (.*?): count=(\d*), (\d*.\d*)")
            for state, count, duration_per_chunk in dynmapchunkloadingregex.findall(resp):
                dynmap_chunk_loading_statistics_count.add_sample('dynmap_chunk_loading_statistics', value=count,
                                                                 labels={'type': state})
                dynmap_chunk_loading_statistics_duration.add_sample('dynmap_chunk_loading_duration',
                                                                    value=duration_per_chunk, labels={'type': state})

        # player
        resp = self.rcon_command("list")
        playerregex = re.compile("players online:(.*)")
        if playerregex.findall(resp):
            for player in playerregex.findall(resp)[0].split(","):
                if not player.isspace():
                    minecraft_player_online.add_sample('minecraft_player_online', value=1, labels={'player': player.lstrip()})

        return metrics

    def get_player_quests_finished(self, uuid):
        with open(self.better_questing + "/QuestProgress.json") as json_file:
            data = json.load(json_file)
            json_file.close()
        counter = 0
        for _, value in data['questProgress:9'].items():
            for _, u in value['tasks:9']['0:10']['completeUsers:9'].items():
                if u == uuid:
                    counter += 1
        return counter

    def get_player_stats(self, uuid):
        with open(self.stats_directory + "/" + uuid + ".json") as json_file:
            data = json.load(json_file)
            json_file.close()
        nbtfile = nbt.nbt.NBTFile(self.player_directory + "/" + uuid + ".dat", 'rb')
        data["stat.XpTotal"] = nbtfile.get("XpTotal").value
        data["stat.XpLevel"] = nbtfile.get("XpLevel").value
        data["stat.Score"] = nbtfile.get("Score").value
        data["stat.Health"] = nbtfile.get("Health").value
        data["stat.foodLevel"] = nbtfile.get("foodLevel").value
        with open(self.advancements_directory + "/" + uuid + ".json") as json_file:
            count = 0
            advancements = json.load(json_file)
            for key, value in advancements.items():
                if key in ("DataVersion"):
                    continue
                if value["done"] == True:
                    count += 1
        data["stat.advancements"] = count
        if self.quests_enabled:
            data["stat.questsFinished"] = self.get_player_quests_finished(uuid)
        return data

    def update_metrics_for_player(self, uuid):
        name = self.uuid_to_player(uuid)
        if not name:
            return

        data = self.get_player_stats(uuid)

        minecraft_blocks_mined = Metric('minecraft_blocks_mined', 'Blocks a Player mined', "counter")
        minecraft_blocks_picked_up = Metric('minecraft_blocks_picked_up', 'Blocks a Player picked up', "counter")
        minecraft_player_deaths = Metric('minecraft_player_deaths', 'How often a Player died', "counter")
        minecraft_player_jumps = Metric('minecraft_player_jumps', 'How often a Player has jumped', "counter")
        minecraft_cm_traveled = Metric('minecraft_cm_traveled', 'How many cm a Player traveled, whatever that means', "counter")
        minecraft_player_xp_total = Metric('minecraft_player_xp_total', "How much total XP a player has", "counter")
        minecraft_player_current_level = Metric('minecraft_player_current_level', "How much current XP a player has", "counter")
        minecraft_player_food_level = Metric('minecraft_player_food_level', "How much food the player currently has", "counter")
        minecraft_player_health = Metric('minecraft_player_health', "How much Health the player currently has", "counter")
        minecraft_player_score = Metric('minecraft_player_score', "The Score of the player", "counter")
        minecraft_entities_killed = Metric('minecraft_entities_killed', "Entities killed by player", "counter")
        minecraft_damage_taken = Metric('minecraft_damage_taken', "Damage Taken by Player", "counter")
        minecraft_damage_dealt = Metric('minecraft_damage_dealt', "Damage dealt by Player", "counter")
        minecraft_blocks_crafted = Metric('minecraft_blocks_crafted', "Items a Player crafted", "counter")
        minecraft_player_playtime = Metric('minecraft_player_playtime', "Time in Minutes a Player was online", "counter")
        minecraft_player_advancements = Metric('minecraft_player_advancements', "Number of completed advances of a player", "counter")
        minecraft_player_slept = Metric('minecraft_player_slept', "Times a Player slept in a bed", "counter")
        minecraft_player_quests_finished = Metric('minecraft_player_quests_finished', 'Number of quests a Player has finished', 'counter')
        minecraft_player_used_crafting_table = Metric('minecraft_player_used_crafting_table', "Times a Player used a Crafting Table",
                                            "counter")
        minecraft_custom = Metric('minecraft_custom', "Custom Minecraft stat", "counter")
        for key, value in data.items():  # pre 1.15
            if key in ("stats", "DataVersion"):
                continue
            stat = key.split(".")[1]  # entityKilledBy
            if stat == "mineBlock":
                minecraft_blocks_mined.add_sample("minecraft_blocks_mined", value=value, labels={'player': name, 'block': '.'.join(
                    (key.split(".")[2], key.split(".")[3]))})
            elif stat == "pickup":
                minecraft_blocks_picked_up.add_sample("minecraft_blocks_picked_up", value=value, labels={'player': name, 'block': '.'.join(
                    (key.split(".")[2], key.split(".")[3]))})
            elif stat == "entityKilledBy":
                if len(key.split(".")) == 4:
                    minecraft_player_deaths.add_sample('minecraft_player_deaths', value=value, labels={'player': name, 'cause': '.'.join(
                        (key.split(".")[2], key.split(".")[3]))})
                else:
                    minecraft_player_deaths.add_sample('minecraft_player_deaths', value=value,
                                             labels={'player': name, 'cause': key.split(".")[2]})
            elif stat == "jump":
                minecraft_player_jumps.add_sample("minecraft_player_jumps", value=value, labels={'player': name})
            elif stat == "walkOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "walking"})
            elif stat == "swimOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "swimming"})
            elif stat == "sprintOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "sprinting"})
            elif stat == "diveOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "diving"})
            elif stat == "fallOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "falling"})
            elif stat == "flyOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "flying"})
            elif stat == "boatOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "boat"})
            elif stat == "horseOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "horse"})
            elif stat == "climbOneCm":
                minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "climbing"})
            elif stat == "XpTotal":
                minecraft_player_xp_total.add_sample('minecraft_player_xp_total', value=value, labels={'player': name})
            elif stat == "XpLevel":
                minecraft_player_current_level.add_sample('minecraft_player_current_level', value=value, labels={'player': name})
            elif stat == "foodLevel":
                minecraft_player_food_level.add_sample('minecraft_player_food_level', value=value, labels={'player': name})
            elif stat == "Health":
                minecraft_player_health.add_sample('minecraft_player_health', value=value, labels={'player': name})
            elif stat == "Score":
                minecraft_player_score.add_sample('minecraft_player_score', value=value, labels={'player': name})
            elif stat == "killEntity":
                minecraft_entities_killed.add_sample('minecraft_entities_killed', value=value,
                                           labels={'player': name, "entity": key.split(".")[2]})
            elif stat == "damageDealt":
                minecraft_damage_dealt.add_sample('minecraft_damage_dealt', value=value, labels={'player': name})
            elif stat == "damageTaken":
                minecraft_damage_dealt.add_sample('minecraft_damage_taken', value=value, labels={'player': name})
            elif stat == "craftItem":
                minecraft_blocks_crafted.add_sample('minecraft_blocks_crafted', value=value, labels={'player': name, 'block': '.'.join(
                    (key.split(".")[2], key.split(".")[3]))})
            elif stat == "playOneMinute":
                minecraft_player_playtime.add_sample('minecraft_player_playtime', value=value, labels={'player': name})
            elif stat == "advancements":
                minecraft_player_advancements.add_sample('minecraft_player_advancements', value=value, labels={'player': name})
            elif stat == "sleepInBed":
                minecraft_player_slept.add_sample('minecraft_player_slept', value=value, labels={'player': name})
            elif stat == "craftingTableInteraction":
                minecraft_player_used_crafting_table.add_sample('minecraft_player_used_crafting_table', value=value,
                                                      labels={'player': name})
            elif stat == "questsFinished":
                minecraft_player_quests_finished.add_sample('minecraft_player_quests_finished', value=value, labels={'player': name})

        if "stats" in data:  # Minecraft > 1.15
            if "minecraft:crafted" in data["stats"]:
                for block, value in data["stats"]["minecraft:crafted"].items():
                    minecraft_blocks_crafted.add_sample('minecraft_blocks_crafted', value=value, labels={'player': name, 'block': block})
            if "minecraft:mined" in data["stats"]:
                for block, value in data["stats"]["minecraft:mined"].items():
                    minecraft_blocks_mined.add_sample("minecraft_blocks_mined", value=value, labels={'player': name, 'block': block})
            if "minecraft:picked_up" in data["stats"]:
                for block, value in data["stats"]["minecraft:picked_up"].items():
                    minecraft_blocks_picked_up.add_sample("minecraft_blocks_picked_up", value=value,
                                                labels={'player': name, 'block': block})
            if "minecraft:killed" in data["stats"]:
                for entity, value in data["stats"]["minecraft:killed"].items():
                    minecraft_entities_killed.add_sample('minecraft_entities_killed', value=value,
                                               labels={'player': name, "entity": entity})
            if "minecraft:killed_by" in data["stats"]:
                for entity, value in data["stats"]["minecraft:killed_by"].items():
                    minecraft_player_deaths.add_sample('minecraft_player_deaths', value=value, labels={'player': name, 'cause': entity})
            for stat, value in data["stats"]["minecraft:custom"].items():
                if stat == "minecraft:jump":
                    minecraft_player_jumps.add_sample("minecraft_player_jumps", value=value, labels={'player': name})
                elif stat == "minecraft:deaths":
                    minecraft_player_deaths.add_sample('minecraft_player_deaths', value=value, labels={'player': name})
                elif stat == "minecraft:minecraft_damage_taken":
                    minecraft_damage_taken.add_sample('minecraft_damage_taken', value=value, labels={'player': name})
                elif stat == "minecraft:minecraft_damage_dealt":
                    minecraft_damage_dealt.add_sample('minecraft_damage_dealt',value=value,labels={'player':name})
                elif stat == "minecraft:play_time":
                    minecraft_player_playtime.add_sample('minecraft_player_playtime',value=value,labels={'player':name})
                elif stat == "minecraft:play_one_minute": # pre 1.17
                    minecraft_player_playtime.add_sample('minecraft_player_playtime',value=value,labels={'player':name})
                elif stat == "minecraft:walk_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "walking"})
                elif stat == "minecraft:walk_on_water_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "swimming"})
                elif stat == "minecraft:sprint_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "sprinting"})
                elif stat == "minecraft:walk_under_water_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "diving"})
                elif stat == "minecraft:fall_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "falling"})
                elif stat == "minecraft:fly_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "flying"})
                elif stat == "minecraft:boat_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "boat"})
                elif stat == "minecraft:horse_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "horse"})
                elif stat == "minecraft:climb_one_cm":
                    minecraft_cm_traveled.add_sample("minecraft_cm_traveled", value=value, labels={'player': name, 'method': "climbing"})
                elif stat == "minecraft:sleep_in_bed":
                    minecraft_player_slept.add_sample('minecraft_player_slept', value=value, labels={'player': name})
                elif stat == "minecraft:interact_with_crafting_table":
                    minecraft_player_used_crafting_table.add_sample('minecraft_player_used_crafting_table', value=value,
                                                          labels={'player': name})
                else:
                    minecraft_custom.add_sample('minecraft_custom', value=value, labels={'stat': stat})
        return [minecraft_blocks_mined, minecraft_blocks_picked_up, minecraft_player_deaths, minecraft_player_jumps, minecraft_cm_traveled, minecraft_player_xp_total,
                minecraft_player_current_level, minecraft_player_food_level, minecraft_player_health, minecraft_player_score, minecraft_entities_killed, minecraft_damage_taken,
                minecraft_damage_dealt, minecraft_blocks_crafted, minecraft_player_playtime, minecraft_player_advancements, minecraft_player_slept,
                minecraft_player_used_crafting_table, minecraft_player_quests_finished, minecraft_custom]

    def collect(self):
        for player in self.get_players():
            metrics = self.update_metrics_for_player(player)
            if not metrics:
                continue

            for metric in metrics:
                yield metric

        for metric in self.get_server_stats():
            yield metric


if __name__ == '__main__':
    try:
        HTTP_PORT = int(os.environ.get('HTTP_PORT'))
    except:
        HTTP_PORT = 8000

    start_http_server(HTTP_PORT)
    REGISTRY.register(MinecraftCollector())

    print(f'Exporter started on Port {HTTP_PORT}')

    while True:
        try:
            time.sleep(1)
            schedule.run_pending()
        except MCRconException:
            # RCON timeout
            collector.rcon_disconnect()
