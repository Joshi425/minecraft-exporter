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
minecraft_blocks_mined
minecraft_blocks_picked_up
minecraft_player_deaths
minecraft_player_jumps
minecraft_cm_traveled
minecraft_player_xp_total
minecraft_player_current_level
minecraft_player_food_level
minecraft_player_health
minecraft_player_score
minecraft_entities_killed
minecraft_damage_taken
minecraft_damage_dealt
minecraft_blocks_crafted
minecraft_player_playtime
minecraft_player_advancements
minecraft_player_slept
minecraft_player_used_crafting_table
minecraft_player_quests_finished # support for betterquesting
minecraft_custom # for 1.15
```

The following Metrics are only exported if RCON is configured:

```
minecraft_player_online
```

The following Metrics are exposed if FORGE_SERVER is enabled and RCON is configured:

```
forge_dim_tps
forge_dim_ticktime
forge_overall_tps
forge_overall_ticktime
forge_entities
```

The following Metrics are exposed if Dynmap Support is enabled and RCON is configured:

```
dynmap_tile_render_statistics
dynmap_chunk_loading_statistics_count
dynmap_chunk_loading_statistics_duration
```

The following Metrics are exposed if PAPER_SERVER is enabled and RCON is configured:
```
paper_tps_1m
paper_tps_5m
paper_tps_15m

```

# Dashboards

In the folder dashboards you'll find grafana dashboards for these metrics, they are however incomplete and can be expanded
or use the following dasboards:

https://grafana.com/grafana/dashboards/11993
https://grafana.com/grafana/dashboards/11994
