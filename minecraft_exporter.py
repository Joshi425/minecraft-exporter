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
        self.usercache_file = "/usercache.json"
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

    def uuid_to_player_usercache(self, uuid):
        with open(self.usercache_file) as json_file:
            data = json.load(json_file)
            json_file.close()
        for user in data:
            if user["uuid"] == uuid:
                return user["name"]
        return

    def uuid_to_player_mojang(self, uuid):
        try:
            result = requests.get('https://sessionserver.mojang.com/session/minecraft/profile/' + uuid)
            return (result.json()['name'])
        except:
            return
        
    def uuid_to_player(self, uuid):
        if uuid in self.player_map:
            return self.player_map[uuid]
        else:
            player = self.uuid_to_player_usercache(uuid)
            if not player:
                player = self.uuid_to_player_mojang(uuid)
            self.player_map[uuid] = player
            return player
    
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

        dim_tps = Metric('dim_tps', 'TPS of a dimension', "counter")
        dim_ticktime = Metric('dim_ticktime', "Time a Tick took in a Dimension", "counter")
        overall_tps = Metric('overall_tps', 'overall TPS', "counter")
        overall_ticktime = Metric('overall_ticktime', "overall Ticktime", "counter")
        player_online = Metric('player_online', "is 1 if player is online", "counter")
        entities = Metric('entities', "type and count of active entites", "counter")
        tps_1m = Metric('paper_tps_1m', '1 Minute TPS', "counter")
        tps_5m = Metric('paper_tps_5m', '5 Minute TPS', "counter")
        tps_15m = Metric('paper_tps_15m', '15 Minute TPS', "counter")

        metrics.extend(
            [dim_tps, dim_ticktime, overall_tps, overall_ticktime, player_online, entities, tps_1m, tps_5m, tps_15m])
        if 'PAPER_SERVER' in os.environ and os.environ['PAPER_SERVER'] == "True":
            resp = str(self.rcon_command("tps")).strip().replace("§a", "")
            tpsregex = re.compile("TPS from last 1m, 5m, 15m: (\d*\.\d*), (\d*\.\d*), (\d*\.\d*)")
            for m1, m5, m15 in tpsregex.findall(resp):
                tps_1m.add_sample('paper_tps_1m', value=m1, labels={'tps': '1m'})
                tps_5m.add_sample('paper_tps_5m', value=m5, labels={'tps': '5m'})
                tps_15m.add_sample('paper_tps_15m', value=m15, labels={'tps': '15m'})
        if 'FORGE_SERVER' in os.environ and os.environ['FORGE_SERVER'] == "True":
            # dimensions
            resp = self.rcon_command("forge tps")
            dimtpsregex = re.compile("Dim\s*(-*\d*)\s\((.*?)\)\s:\sMean tick time:\s(.*?) ms\. Mean TPS: (\d*\.\d*)")
            for dimid, dimname, meanticktime, meantps in dimtpsregex.findall(resp):
                dim_tps.add_sample('dim_tps', value=meantps, labels={'dimension_id': dimid, 'dimension_name': dimname})
                dim_ticktime.add_sample('dim_ticktime', value=meanticktime,
                                        labels={'dimension_id': dimid, 'dimension_name': dimname})
            overallregex = re.compile("Overall\s?: Mean tick time: (.*) ms. Mean TPS: (.*)")
            overall_tps.add_sample('overall_tps', value=overallregex.findall(resp)[0][1], labels={})
            overall_ticktime.add_sample('overall_ticktime', value=overallregex.findall(resp)[0][0], labels={})

            # entites
            resp = self.rcon_command("forge entity list")
            entityregex = re.compile("(\d+): (.*?:.*?)\s")
            for entitycount, entityname in entityregex.findall(resp):
                entities.add_sample('entities', value=entitycount, labels={'entity': entityname})

        # dynmap
        if 'DYNMAP_ENABLED' in os.environ and os.environ['DYNMAP_ENABLED'] == "True":
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
                    player_online.add_sample('player_online', value=1, labels={'player': player.lstrip()})

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

        blocks_mined = Metric('blocks_mined', 'Blocks a Player mined', "counter")
        blocks_picked_up = Metric('blocks_picked_up', 'Blocks a Player picked up', "counter")
        player_deaths = Metric('player_deaths', 'How often a Player died', "counter")
        player_jumps = Metric('player_jumps', 'How often a Player has jumped', "counter")
        cm_traveled = Metric('cm_traveled', 'How many cm a Player traveled, whatever that means', "counter")
        player_xp_total = Metric('player_xp_total', "How much total XP a player has", "counter")
        player_current_level = Metric('player_current_level', "How much current XP a player has", "counter")
        player_food_level = Metric('player_food_level', "How much food the player currently has", "counter")
        player_health = Metric('player_health', "How much Health the player currently has", "counter")
        player_score = Metric('player_score', "The Score of the player", "counter")
        entities_killed = Metric('entities_killed', "Entities killed by player", "counter")
        damage_taken = Metric('damage_taken', "Damage Taken by Player", "counter")
        damage_dealt = Metric('damage_dealt', "Damage dealt by Player", "counter")
        blocks_crafted = Metric('blocks_crafted', "Items a Player crafted", "counter")
        player_playtime = Metric('player_playtime', "Time in Minutes a Player was online", "counter")
        player_advancements = Metric('player_advancements', "Number of completed advances of a player", "counter")
        player_slept = Metric('player_slept', "Times a Player slept in a bed", "counter")
        player_quests_finished = Metric('player_quests_finished', 'Number of quests a Player has finished', 'counter')
        player_used_crafting_table = Metric('player_used_crafting_table', "Times a Player used a Crafting Table",
                                            "counter")
        mc_custom = Metric('mc_custom', "Custom Minecraft stat", "counter")
        for key, value in data.items():  # pre 1.15
            if key in ("stats", "DataVersion"):
                continue
            stat = key.split(".")[1]  # entityKilledBy
            if stat == "mineBlock":
                blocks_mined.add_sample("blocks_mined", value=value, labels={'player': name, 'block': '.'.join(
                    (key.split(".")[2], key.split(".")[3]))})
            elif stat == "pickup":
                blocks_picked_up.add_sample("blocks_picked_up", value=value, labels={'player': name, 'block': '.'.join(
                    (key.split(".")[2], key.split(".")[3]))})
            elif stat == "entityKilledBy":
                if len(key.split(".")) == 4:
                    player_deaths.add_sample('player_deaths', value=value, labels={'player': name, 'cause': '.'.join(
                        (key.split(".")[2], key.split(".")[3]))})
                else:
                    player_deaths.add_sample('player_deaths', value=value,
                                             labels={'player': name, 'cause': key.split(".")[2]})
            elif stat == "jump":
                player_jumps.add_sample("player_jumps", value=value, labels={'player': name})
            elif stat == "walkOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "walking"})
            elif stat == "swimOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "swimming"})
            elif stat == "sprintOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "sprinting"})
            elif stat == "diveOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "diving"})
            elif stat == "fallOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "falling"})
            elif stat == "flyOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "flying"})
            elif stat == "boatOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "boat"})
            elif stat == "horseOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "horse"})
            elif stat == "climbOneCm":
                cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "climbing"})
            elif stat == "XpTotal":
                player_xp_total.add_sample('player_xp_total', value=value, labels={'player': name})
            elif stat == "XpLevel":
                player_current_level.add_sample('player_current_level', value=value, labels={'player': name})
            elif stat == "foodLevel":
                player_food_level.add_sample('player_food_level', value=value, labels={'player': name})
            elif stat == "Health":
                player_health.add_sample('player_health', value=value, labels={'player': name})
            elif stat == "Score":
                player_score.add_sample('player_score', value=value, labels={'player': name})
            elif stat == "killEntity":
                entities_killed.add_sample('entities_killed', value=value,
                                           labels={'player': name, "entity": key.split(".")[2]})
            elif stat == "damageDealt":
                damage_dealt.add_sample('damage_dealt', value=value, labels={'player': name})
            elif stat == "damageTaken":
                damage_dealt.add_sample('damage_taken', value=value, labels={'player': name})
            elif stat == "craftItem":
                blocks_crafted.add_sample('blocks_crafted', value=value, labels={'player': name, 'block': '.'.join(
                    (key.split(".")[2], key.split(".")[3]))})
            elif stat == "playOneMinute":
                player_playtime.add_sample('player_playtime', value=value, labels={'player': name})
            elif stat == "advancements":
                player_advancements.add_sample('player_advancements', value=value, labels={'player': name})
            elif stat == "sleepInBed":
                player_slept.add_sample('player_slept', value=value, labels={'player': name})
            elif stat == "craftingTableInteraction":
                player_used_crafting_table.add_sample('player_used_crafting_table', value=value,
                                                      labels={'player': name})
            elif stat == "questsFinished":
                player_quests_finished.add_sample('player_quests_finished', value=value, labels={'player': name})

        if "stats" in data:  # Minecraft > 1.15
            if "minecraft:crafted" in data["stats"]:
                for block, value in data["stats"]["minecraft:crafted"].items():
                    blocks_crafted.add_sample('blocks_crafted', value=value, labels={'player': name, 'block': block})
            if "minecraft:mined" in data["stats"]:
                for block, value in data["stats"]["minecraft:mined"].items():
                    blocks_mined.add_sample("blocks_mined", value=value, labels={'player': name, 'block': block})
            if "minecraft:picked_up" in data["stats"]:
                for block, value in data["stats"]["minecraft:picked_up"].items():
                    blocks_picked_up.add_sample("blocks_picked_up", value=value,
                                                labels={'player': name, 'block': block})
            if "minecraft:killed" in data["stats"]:
                for entity, value in data["stats"]["minecraft:killed"].items():
                    entities_killed.add_sample('entities_killed', value=value,
                                               labels={'player': name, "entity": entity})
            if "minecraft:killed_by" in data["stats"]:
                for entity, value in data["stats"]["minecraft:killed_by"].items():
                    player_deaths.add_sample('player_deaths', value=value, labels={'player': name, 'cause': entity})
            for stat, value in data["stats"]["minecraft:custom"].items():
                if stat == "minecraft:jump":
                    player_jumps.add_sample("player_jumps", value=value, labels={'player': name})
                elif stat == "minecraft:deaths":
                    player_deaths.add_sample('player_deaths', value=value, labels={'player': name})
                elif stat == "minecraft:damage_taken":
                    damage_taken.add_sample('damage_taken', value=value, labels={'player': name})
                elif stat == "minecraft:damage_dealt":
                    damage_dealt.add_sample('damage_dealt',value=value,labels={'player':name})
                elif stat == "minecraft:play_time":
                    player_playtime.add_sample('player_playtime',value=value,labels={'player':name})
                elif stat == "minecraft:play_one_minute": # pre 1.17
                    player_playtime.add_sample('player_playtime',value=value,labels={'player':name})
                elif stat == "minecraft:walk_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "walking"})
                elif stat == "minecraft:walk_on_water_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "swimming"})
                elif stat == "minecraft:sprint_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "sprinting"})
                elif stat == "minecraft:walk_under_water_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "diving"})
                elif stat == "minecraft:fall_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "falling"})
                elif stat == "minecraft:fly_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "flying"})
                elif stat == "minecraft:boat_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "boat"})
                elif stat == "minecraft:horse_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "horse"})
                elif stat == "minecraft:climb_one_cm":
                    cm_traveled.add_sample("cm_traveled", value=value, labels={'player': name, 'method': "climbing"})
                elif stat == "minecraft:sleep_in_bed":
                    player_slept.add_sample('player_slept', value=value, labels={'player': name})
                elif stat == "minecraft:interact_with_crafting_table":
                    player_used_crafting_table.add_sample('player_used_crafting_table', value=value,
                                                          labels={'player': name})
                else:
                    mc_custom.add_sample('mc_custom', value=value, labels={'stat': stat})
        return [blocks_mined, blocks_picked_up, player_deaths, player_jumps, cm_traveled, player_xp_total,
                player_current_level, player_food_level, player_health, player_score, entities_killed, damage_taken,
                damage_dealt, blocks_crafted, player_playtime, player_advancements, player_slept,
                player_used_crafting_table, player_quests_finished, mc_custom]

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
