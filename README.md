# minecraft-exporter

this is a prometheus minecraft exporter
This exporter reads minecrafts nbt files, the advancements files and can optionally connect via RCON to your minecraft server.

to use it mount your world to /world in the container

rcon connection only works on forge servers, it only executes `forge tps` to get tps and tick time informations

to enable rcon on your minecraft server add the following to the server.properties file:

```
broadcast-rcon-to-ops=false
rcon.port=25575
rcon.password=Password
enable-rcon=true
```

The RCON Module is only enabled if `RCON_HOST` and `RCON_PASSWORD` is set


# Usage

```
docker run -e RCON_HOST=127.0.0.1 \
	   -e RCON_PORT=25575 \
	   -e RCON_PASSWORD="Password" \
	   -e DYNMAP_ENABLED="True" \
	   -p 8000:8000 \
	   -v /opt/all_the_mods_3/world:/world \
	   joshi425/minecraft_exporter
```

# Metrics

```
blocks_mined
blocks_picked_up
player_deaths
player_jumps
cm_traveled
player_xp_total
player_current_level
player_food_level
player_health
player_score
entities_killed
damage_taken
damage_dealt
blocks_crafted
player_playtime
player_advancements
player_slept
player_used_crafting_table
player_quests_finished # support for betterquesting
```
the following Metrics are only exported if RCON is configured:
```
dim_tps
dim_ticktime
overall_tps
overall_ticktime
player_online
```

the following Metrics are exposed if Dynmap Support is enabled:

```
dynmap_tile_render_statistics
dynmap_chunk_loading_statistics_count
dynmap_chunk_loading_statistics_duration
```

# Dashboards

In the folder dashboards you'll find grafana dashboards for these metrics, they are however incomplete and can be expanded 
or use the following dasboards:

https://grafana.com/grafana/dashboards/11993
https://grafana.com/grafana/dashboards/11994
