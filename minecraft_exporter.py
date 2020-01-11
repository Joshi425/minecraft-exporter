from prometheus_client import start_http_server, REGISTRY, Metric
import time
import requests
import json
import nbt 
import re
import os
from mcrcon import MCRcon
from os import listdir
from os.path import isfile, join

class MinecraftCollector(object):
    def __init__(self):
        self.statsdirectory = "/world/stats"
        self.playerdirectory = "/world/playerdata"
        self.advancementsdirectory = "/world/advancements"
        self.betterquesting = "/world/betterquesting"
        self.map = dict()
        self.questsEnabled = False
        if os.path.isdir(self.betterquesting):
            self.questsEnabled = True

    def get_players(self):
        return [f[:-5] for f in listdir(self.statsdirectory) if isfile(join(self.statsdirectory, f))]

    def uuid_to_player(self,uuid):
        uuid = uuid.replace('-','')
        if uuid in self.map:
            return self.map[uuid] 
        else:
            result = requests.get('https://api.mojang.com/user/profiles/'+uuid+'/names')
            self.map[uuid] = result.json()[0]['name']
            return(result.json()[0]['name'])

    def get_server_stats(self):
        if not all(x in os.environ for x in ['RCON_HOST','RCON_PASSWORD']):
            return []
        dim_tps          = Metric('dim_tps','TPS of a dimension',"counter")
        dim_ticktime     = Metric('dim_ticktime',"Time a Tick took in a Dimension","counter")
        overall_tps      = Metric('overall_tps','overall TPS',"counter")
        overall_ticktime = Metric('overall_ticktime',"overall Ticktime","counter")
        player_online    = Metric('player_online',"is 1 if player is online","counter")
        entities         = Metric('entities',"type and count of active entites", "counter")
        mcr = MCRcon(os.environ['RCON_HOST'],os.environ['RCON_PASSWORD'],port=int(os.environ['RCON_PORT']))
        mcr.connect()

        # dimensions
        resp = mcr.command("forge tps")
        dimtpsregex = re.compile("Dim\s*(-*\d*)\s\((.*?)\)\s:\sMean tick time:\s(.*?) ms\. Mean TPS: (\d*\.\d*)")
        for dimid, dimname, meanticktime, meantps in dimtpsregex.findall(resp):
            dim_tps.add_sample('dim_tps',value=meantps,labels={'dimension_id':dimid,'dimension_name':dimname})
            dim_ticktime.add_sample('dim_ticktime',value=meanticktime,labels={'dimension_id':dimid,'dimension_name':dimname})
        overallregex = re.compile("Overall : Mean tick time: (.*) ms. Mean TPS: (.*)")
        overall_tps.add_sample('overall_tps',value=overallregex.findall(resp)[0][1],labels={})
        overall_ticktime.add_sample('overall_ticktime',value=overallregex.findall(resp)[0][0],labels={})

        # entites
        resp = mcr.command("forge entity list")
        entityregex = re.compile("(\d+): (.*?:.*?)\s")
        for entitycount, entityname in entityregex.findall(resp):
            entities.add_sample('entities',value=entitycount,labels={'entity':entityname})

        # player
        resp = mcr.command("list")
        playerregex = re.compile("There are \d*\/20 players online:(.*)")
        if playerregex.findall(resp):
            for player in playerregex.findall(resp)[0].split(","):
                if player:
                    player_online.add_sample('player_online',value=1,labels={'player':player.lstrip()})

        return[dim_tps,dim_ticktime,overall_tps,overall_ticktime,player_online,entities]

    def get_player_quests_finished(self,uuid):
        with open(self.betterquesting+"/QuestProgress.json") as json_file:
            data = json.load(json_file)
            json_file.close()
        counter = 0
        for _, value in data['questProgress:9'].items():
            for _, uuid in value['tasks:9']['0:10']['completeUsers:9'].items():
                if uuid == player['uuid']:
                    counter++
        return counter

    def get_player_stats(self,uuid):
        with open(self.statsdirectory+"/"+uuid+".json") as json_file:
            data = json.load(json_file)
            json_file.close()
        nbtfile = nbt.nbt.NBTFile(self.playerdirectory+"/"+uuid+".dat",'rb')
        data["stat.XpTotal"]  = nbtfile.get("XpTotal").value
        data["stat.XpLevel"]  = nbtfile.get("XpLevel").value
        data["stat.Score"]    = nbtfile.get("Score").value
        data["stat.Health"]   = nbtfile.get("Health").value
        data["stat.foodLevel"]= nbtfile.get("foodLevel").value
        with open(self.advancementsdirectory+"/"+uuid+".json") as json_file:
            count = 0
            advancements = json.load(json_file)
            for key, value in advancements.items():
                if value["done"] == True: 
                    count += 1
        data["stat.advancements"] = count
        if self.questsEnabled:
            data["quests_finished"] = get_player_quests_finished(uuid)
        return data

    def update_metrics_for_player(self,uuid):
        data = self.get_player_stats(uuid)
        name = self.uuid_to_player(uuid)
        blocks_mined        = Metric('blocks_mined','Blocks a Player mined',"counter")
        blocks_picked_up    = Metric('blocks_picked_up','Blocks a Player picked up',"counter")
        player_deaths       = Metric('player_deaths','How often a Player died',"counter")
        player_jumps        = Metric('player_jumps','How often a Player has jumped',"counter")
        cm_traveled         = Metric('cm_traveled','How many cm a Player traveled, whatever that means',"counter")
        player_xp_total     = Metric('player_xp_total',"How much total XP a player has","counter")
        player_current_level= Metric('player_current_level',"How much current XP a player has","counter")
        player_food_level   = Metric('player_food_level',"How much food the player currently has","counter")
        player_health       = Metric('player_health',"How much Health the player currently has","counter")
        player_score        = Metric('player_score',"The Score of the player","counter")
        entities_killed     = Metric('entities_killed',"Entities killed by player","counter")
        damage_taken        = Metric('damage_taken',"Damage Taken by Player","counter")
        damage_dealt        = Metric('damage_dealt',"Damage dealt by Player","counter")
        blocks_crafted      = Metric('blocks_crafted',"Items a Player crafted","counter")
        player_playtime     = Metric('player_playtime',"Time in Minutes a Player was online","counter")
        player_advancements = Metric('player_advancements', "Number of completed advances of a player","counter")
        player_slept        = Metric('player_slept',"Times a Player slept in a bed","counter")
        player_quests_finished = Metric('player_quests_finished', 'Number of quests a Player has finished', 'counter')
        player_used_crafting_table = Metric('player_used_crafting_table',"Times a Player used a Crafting Table","counter")
        for key, value in data.items():
            stat = key.split(".")[1] # entityKilledBy
            if stat == "mineBlock":
                blocks_mined.add_sample("blocks_mined",value=value,labels={'player':name,'block':'.'.join((key.split(".")[2],key.split(".")[3]))})
            elif stat == "pickup":
                blocks_picked_up.add_sample("blocks_picked_up",value=value,labels={'player':name,'block':'.'.join((key.split(".")[2],key.split(".")[3]))})
            elif stat == "entityKilledBy":
                if len(key.split(".")) == 4:
                    player_deaths.add_sample('player_deaths',value=value,labels={'player':name,'cause':'.'.join((key.split(".")[2],key.split(".")[3]))})
                else:
                    player_deaths.add_sample('player_deaths',value=value,labels={'player':name,'cause':key.split(".")[2]})
            elif stat == "jump":
                player_jumps.add_sample("player_jumps",value=value,labels={'player':name})
            elif stat == "walkOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"walking"})
            elif stat == "swimOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"swimming"})
            elif stat == "sprintOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"sprinting"})
            elif stat == "diveOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"diving"})
            elif stat == "fallOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"falling"})
            elif stat == "flyOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"flying"})
            elif stat == "boatOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"boat"})
            elif stat == "horseOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"horse"})
            elif stat == "climbOneCm":
                cm_traveled.add_sample("cm_traveled",value=value,labels={'player':name,'method':"climbing"})
            elif stat == "XpTotal":
                player_xp_total.add_sample('player_xp_total',value=value,labels={'player':name})
            elif stat == "XpLevel":
                player_current_level.add_sample('player_current_level',value=value,labels={'player':name})
            elif stat == "foodLevel":
                player_food_level.add_sample('player_food_level',value=value,labels={'player':name})
            elif stat == "Health":
                player_health.add_sample('player_health',value=value,labels={'player':name})
            elif stat == "Score":
                player_score.add_sample('player_score',value=value,labels={'player':name})
            elif stat == "killEntity":
                entities_killed.add_sample('entities_killed',value=value,labels={'player':name,"entity":key.split(".")[2]})
            elif stat == "damageDealt":
                damage_dealt.add_sample('damage_dealt',value=value,labels={'player':name})
            elif stat == "damageTaken":
                damage_dealt.add_sample('damage_taken',value=value,labels={'player':name})
            elif stat == "craftItem":
                blocks_crafted.add_sample('blocks_crafted',value=value,labels={'player':name,'block':'.'.join((key.split(".")[2],key.split(".")[3]))})
            elif stat == "playOneMinute":
                player_playtime.add_sample('player_playtime',value=value,labels={'player':name})
            elif stat == "advancements":
                player_advancements.add_sample('player_advancements',value=value,labels={'player':name})
            elif stat == "sleepInBed":
                player_slept.add_sample('player_slept',value=value,labels={'player':name})
            elif stat == "craftingTableInteraction":
                player_used_crafting_table.add_sample('player_used_crafting_table',value=value,labels={'player':name})
            elif stat == "questsFinished":
                player_quests_finished.add_sample('player_quests_finished',value=value,labels={'player':name})
        return [blocks_mined,blocks_picked_up,player_deaths,player_jumps,cm_traveled,player_xp_total,player_current_level,player_food_level,player_health,player_score,entities_killed,damage_taken,damage_dealt,blocks_crafted,player_playtime,player_advancements,player_slept,player_used_crafting_table]

    def collect(self):
        for player in self.get_players():
            for metric in self.update_metrics_for_player(player)+self.get_server_stats():
                yield metric


if __name__ == '__main__':
    if all(x in os.environ for x in ['RCON_HOST','RCON_PASSWORD']):
        print("RCON is enabled for "+ os.environ['RCON_HOST'])

    start_http_server(8000)
    REGISTRY.register(MinecraftCollector())
    print("Exporter started on Port 8000")
    while True:
        time.sleep(1)
