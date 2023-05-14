# minecraft-exporter

This is a prometheus minecraft exporter

This exporter reads minecrafts nbt files, the advancements files and can optionally connect via RCON to your minecraft server.

To use it mount your world to /world in the container

RCON connection is used to get online Players
On Forge Servers enable FORGE_SERVER to get tps information
On Paper Servers enable PAPER_SERVER to get tps information

To enable rcon on your minecraft server add the following to the server.properties file:

```
broadcast-rcon-to-ops=false
rcon.port=25575
rcon.password=Password
enable-rcon=true
```

> Note: Broadcast RCON to ops is disabled, to avoid ops receiving spam whilst ingame.

---

# Environment Variables

| Name          | Default | Description                                       |
| ------------- | ------- | ------------------------------------------------- |
| RCON_HOST     | `None`  | Host of the RCON server                           |
| RCON_PORT     | `None`  | Port RCON is hosted on                            |
| RCON_PASSWORD | `None`  | RCON Password for access                          |
| HTTP_PORT     | `8000`  | Port to host on, in case of using outside docker* |

> * Or other cases where you have limited control of port mappings, eg Pterodactyl.

---

# Usage

```
docker run
       -e RCON_HOST=127.0.0.1                                  \
       -e RCON_PORT=25575                                      \
       -e RCON_PASSWORD="Password"                             \
       -e FORGE_SERVER="true"                                  \
       -e PAPER_SERVER="true"                                  \
       -e DYNMAP_ENABLED="true"                                \
       -p 8000:8000                                            \
       -v /path/to/minecraft/world:/world                      \
       ghcr.io/heathcliff26/grafana-minecraft-exporter:main
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
mc_custom # for 1.15
```

The following Metrics are only exported if RCON is configured:

```
dim_tps
dim_ticktime
overall_tps
overall_ticktime
player_online
```

The following Metrics are exposed if Dynmap Support is enabled:

```
dynmap_tile_render_statistics
dynmap_chunk_loading_statistics_count
dynmap_chunk_loading_statistics_duration
```

The following Metrics are exposed if PAPER_SERVER is enabled:
```
tps_1m
tps_5m
tps_15m

```

# Dashboards

In the folder dashboards you'll find grafana dashboards for these metrics, they are however incomplete and can be expanded
or use the following dasboards:

https://grafana.com/grafana/dashboards/11993
https://grafana.com/grafana/dashboards/11994
