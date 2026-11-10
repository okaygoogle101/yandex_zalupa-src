#include <amxmodx>
#include <fakemeta>
#include <hamsandwich>

#define MAX_BALES 204
#define MAX_LAYERS 8
#define MAX_STAGES 5
#define TASK_RESET 17401
#define TASK_SWEEP 17402
#define TASK_NEXT_STAGE 17403
#define TASK_BALE_BASE 18000
#define TASK_NEEDLE 18300
#define MAGIC_BALE 0x53454E42
#define MAGIC_NEEDLE 0x53454E4E
#define BREAK_METAL 0x02
#define BREAK_WOOD 0x08
#define BALE_LIGHT 200
#define NEEDLE_LIGHT 220
#define SWEEP_FX_EVERY 4

new const BALE_MODEL[] = "models/yz_seno/bale.mdl";
new const NEEDLE_MODEL[] = "models/yz_seno/needle.mdl";
new const SND_BALE_BREAK[] = "yz_seno/bale_break.wav";
new const SND_NEEDLE_APPEAR[] = "ambience/lv_fruitwin.wav";
new const SND_NEEDLE_BREAK[] = "weapons/c4_explode1.wav";
new const FINISH_TARGET[] = "seno_finish";
new const FINISH_TARGET_2[] = "seno_finish_2";
new const FINISH_TARGET_3[] = "seno_finish_3";
new const FINISH_TARGET_4[] = "seno_finish_4";
new const FINISH_TARGET_5[] = "seno_finish_5";
new const Float:STAGE_BASE_Z[MAX_STAGES + 1] = {0.0, 64.0, -512.0, -1088.0, -1664.0, -2240.0};
new const Float:STAGE_TOP_Z[MAX_STAGES + 1] = {0.0, 448.0, -128.0, -704.0, -1280.0, -1856.0};

new g_bale[MAX_BALES], g_layer[MAX_BALES], g_bale_x[MAX_BALES], g_bale_y[MAX_BALES];
new bool:g_alive[MAX_BALES], bool:g_pending[MAX_BALES];
new g_grid[MAX_LAYERS][MAX_LAYERS][MAX_LAYERS];
new bool:g_visible[MAX_BALES], bool:g_force_visible[MAX_BALES];
new g_count, g_needle, g_hidden, g_sweep_layer, g_sweep_fx_count, g_active_layers, g_stage;
new bool:g_finishing, bool:g_signalled, bool:g_needle_pending;
new bool:g_round_resetting, bool:g_map_active, bool:g_knife_attack[33];
new g_round_generation;
new g_cvar_size, g_cvar_layers, g_cvar_hp, g_cvar_needle_hp, g_cvar_interval;
new g_mdl_bale, g_mdl_needle;
new bool:g_snd_bale_break, bool:g_snd_needle_appear, bool:g_snd_needle_break;

public plugin_precache()
{
    new current[32];
    get_mapname(current, charsmax(current));
    if (!equal(current, "yandex_zalupa")) return;
    if (!file_exists(BALE_MODEL) || !file_exists(NEEDLE_MODEL)) {
        log_amx("Seno: model files missing in cstrike/models/yz_seno; plugin disabled");
        set_fail_state("Seno model files are missing");
        return;
    }
    g_mdl_bale = precache_model(BALE_MODEL);
    g_mdl_needle = precache_model(NEEDLE_MODEL);
    g_snd_bale_break = precache_sound_checked(SND_BALE_BREAK);
    g_snd_needle_appear = precache_sound_checked(SND_NEEDLE_APPEAR);
    g_snd_needle_break = precache_sound_checked(SND_NEEDLE_BREAK);
}

stock bool:precache_sound_checked(const sample[])
{
    new path[64];
    formatex(path, charsmax(path), "sound/%s", sample);
    if (!file_exists(path)) {
        log_amx("Seno: sound file %s missing; sound disabled", path);
        return false;
    }
    precache_sound(sample);
    return true;
}

public plugin_init()
{
    register_plugin("Seno Pyramid", "0.8", "Next21");
    g_cvar_size = register_cvar("seno_bale_size", "48");
    g_cvar_layers = register_cvar("seno_layers", "8");
    g_cvar_hp = register_cvar("seno_bale_hp", "1000");
    g_cvar_needle_hp = register_cvar("seno_needle_hp", "100");
    g_cvar_interval = register_cvar("seno_layer_interval", "0.5");

    new current[32];
    get_mapname(current, charsmax(current));
    g_map_active = equal(current, "yandex_zalupa") != 0;
    if (!g_map_active) return;

    register_event("HLTV", "on_new_round", "a", "1=0", "2=0");
    RegisterHam(Ham_TraceAttack, "info_target", "on_trace_attack");
    RegisterHam(Ham_TakeDamage, "info_target", "on_take_damage");
    RegisterHam(Ham_TakeDamage, "player", "on_player_take_damage");
    RegisterHam(Ham_Weapon_PrimaryAttack, "weapon_knife", "on_knife_pre");
    RegisterHam(Ham_Weapon_PrimaryAttack, "weapon_knife", "on_knife_post", 1);
    RegisterHam(Ham_Weapon_SecondaryAttack, "weapon_knife", "on_knife_pre");
    RegisterHam(Ham_Weapon_SecondaryAttack, "weapon_knife", "on_knife_post", 1);
    register_forward(FM_AddToFullPack, "on_add_to_fullpack");
}

public on_add_to_fullpack(es, e, ent, host, hostflags, player, pset)
{
    if (!pev_valid(ent)) return FMRES_IGNORED;
    new magic = pev(ent, pev_iuser1);
    if (magic == MAGIC_BALE && pev(ent, pev_iuser3) == g_round_generation) {
        new slot = pev(ent, pev_iuser2);
        if (slot >= 0 && slot < g_count && !g_visible[slot]) {
            forward_return(FMV_CELL, 0);
            return FMRES_SUPERCEDE;
        }
    }
    if (magic == MAGIC_NEEDLE && (pev(ent, pev_effects) & EF_NODRAW)) {
        forward_return(FMV_CELL, 0);
        return FMRES_SUPERCEDE;
    }
    return FMRES_IGNORED;
}

public on_knife_pre(weapon)
{
    new owner = pev(weapon, pev_owner);
    if (owner >= 1 && owner <= 32) g_knife_attack[owner] = true;
}

public on_knife_post(weapon)
{
    new owner = pev(weapon, pev_owner);
    if (owner >= 1 && owner <= 32) g_knife_attack[owner] = false;
}

public client_disconnected(id)
{
    if (id >= 1 && id <= 32) {
        g_knife_attack[id] = false;
    }
}

public plugin_cfg()
{
    if (is_enabled()) {
        set_task(0.2, "reset_round", TASK_RESET);
    }
}

public on_new_round()
{
    if (!is_enabled()) return;
    g_round_resetting = true;
    remove_task(TASK_SWEEP);
    remove_task(TASK_NEXT_STAGE);
    remove_task(TASK_NEEDLE);
    for (new i = 0; i < g_count; i++) remove_task(TASK_BALE_BASE + i);
    remove_task(TASK_RESET);
    set_task(0.2, "reset_round", TASK_RESET);
}

bool:is_enabled()
{
    return g_map_active;
}

stock get_finish_target(stage, target[], len)
{
    switch (stage) {
        case 2: copy(target, len, FINISH_TARGET_2);
        case 3: copy(target, len, FINISH_TARGET_3);
        case 4: copy(target, len, FINISH_TARGET_4);
        case 5: copy(target, len, FINISH_TARGET_5);
        default: copy(target, len, FINISH_TARGET);
    }
}

stock count_target_relays(const target[])
{
    new count, ent = 0, classname[32];
    while ((ent = engfunc(EngFunc_FindEntityByString, ent, "targetname", target))) {
        pev(ent, pev_classname, classname, charsmax(classname));
        if (equal(classname, "trigger_relay")) count++;
    }
    return count;
}

stock fire_relay(const target[])
{
    new ent = 0, classname[32];
    while ((ent = engfunc(EngFunc_FindEntityByString, ent, "targetname", target))) {
        pev(ent, pev_classname, classname, charsmax(classname));
        if (!equal(classname, "trigger_relay")) continue;
        dllfunc(DLLFunc_Use, ent, 0);
        return 1;
    }
    log_amx("Seno: trigger_relay %s not found", target);
    return 0;
}

stock remove_all_seno_entities()
{
    new ent = 0;
    while ((ent = engfunc(EngFunc_FindEntityByString, ent, "classname", "info_target"))) {
        new magic = pev(ent, pev_iuser1);
        if (magic == MAGIC_BALE || magic == MAGIC_NEEDLE)
            engfunc(EngFunc_RemoveEntity, ent);
    }
}

stock clear_stack()
{
    remove_task(TASK_SWEEP);
    remove_task(TASK_NEXT_STAGE);
    remove_task(TASK_NEEDLE);
    for (new i = 0; i < MAX_BALES; i++) remove_task(TASK_BALE_BASE + i);

    // Remove bales and needles of every stage, not just the current generation.
    remove_all_seno_entities();

    for (new i = 0; i < MAX_BALES; i++) {
        g_bale[i] = 0;
        g_alive[i] = false;
        g_pending[i] = false;
        g_visible[i] = false;
        g_force_visible[i] = false;
    }
    g_needle = 0;
    g_needle_pending = false;
    g_count = 0;
    g_hidden = -1;
    g_finishing = false;
    g_signalled = false;
    g_sweep_layer = -1;
}

public reset_round()
{
    g_round_resetting = true;
    clear_stack();
    g_stage = 0;
    g_round_generation = 0;

    new names[MAX_STAGES][32], counts[MAX_STAGES];
    new bool:relay_ok = true;
    for (new s = 0; s < MAX_STAGES; s++) {
        get_finish_target(s + 1, names[s], charsmax(names[]));
        counts[s] = count_target_relays(names[s]);
        if (counts[s] != 1) relay_ok = false;
    }
    if (!relay_ok) {
        log_amx("Seno: relay check failed: %s=%d %s=%d %s=%d %s=%d %s=%d; round disabled",
            names[0], counts[0], names[1], counts[1], names[2], counts[2],
            names[3], counts[3], names[4], counts[4]);
        return;
    }

    if (!spawn_stage(1)) {
        log_amx("Seno: stage=1 creation failed; round disabled");
        return;
    }
    g_round_resetting = false;
}

stock bool:spawn_stage(stage)
{
    if (stage < 1 || stage > MAX_STAGES) return false;
    if (stage > 1 && !g_signalled) {
        log_amx("Seno: stage=%d creation refused, previous finale not signalled", stage);
        return false;
    }
    if (stage > 1 && (count_alive() != 0 || pev_valid(g_needle))) {
        log_amx("Seno: stage=%d creation refused, previous stack still present (alive=%d needle=%d)",
            stage, count_alive(), pev_valid(g_needle));
        return false;
    }

    new layers = clamp(get_pcvar_num(g_cvar_layers), 1, MAX_LAYERS);
    new expected;
    for (new l = 0; l < layers; l++) {
        new n = layers - l;
        expected += n * n;
    }
    if (expected > MAX_BALES) {
        log_amx("Seno: stage=%d layout needs %d bales, limit is %d; refused", stage, expected, MAX_BALES);
        return false;
    }

    new size = get_pcvar_num(g_cvar_size);
    if (size != 48) {
        log_amx("Seno: seno_bale_size=%d requires a matching rebuilt model and map; using 48", size);
        size = 48;
    }
    new hp = max(1, get_pcvar_num(g_cvar_hp));
    new Float:base_z = STAGE_BASE_Z[stage];
    new Float:stack_top = base_z + float(layers * size);
    if (layers == MAX_LAYERS && stack_top != STAGE_TOP_Z[stage]) {
        log_amx("Seno: stage=%d top mismatch: %.1f expected %.1f; refused",
            stage, stack_top, STAGE_TOP_Z[stage]);
        return false;
    }

    g_round_generation++;
    g_stage = stage;
    g_count = 0;
    g_hidden = -1;
    g_finishing = false;
    g_signalled = false;
    g_needle_pending = false;
    g_needle = 0;
    g_sweep_layer = -1;
    for (new i = 0; i < MAX_BALES; i++) {
        g_bale[i] = 0;
        g_alive[i] = false;
        g_pending[i] = false;
        g_visible[i] = false;
        g_force_visible[i] = false;
    }

    g_active_layers = layers;
    for (new layer = 0; layer < MAX_LAYERS; layer++)
        for (new x = 0; x < MAX_LAYERS; x++)
            for (new y = 0; y < MAX_LAYERS; y++) g_grid[layer][x][y] = -1;

    new created;
    for (new layer = 0; layer < layers; layer++) {
        new n = layers - layer;
        for (new y = 0; y < n; y++) {
            for (new x = 0; x < n; x++) {
                new slot = g_count++;
                g_layer[slot] = layer;
                g_bale_x[slot] = x;
                g_bale_y[slot] = y;
                g_grid[layer][x][y] = slot;
                new Float:origin[3];
                origin[0] = (float(x) - float(n - 1) * 0.5) * float(size);
                origin[1] = (float(y) - float(n - 1) * 0.5) * float(size);
                origin[2] = base_z + (float(layer) + 0.5) * float(size);
                g_bale[slot] = create_object(BALE_MODEL, origin, float(size) * 0.5, float(hp), MAGIC_BALE, slot);
                g_alive[slot] = pev_valid(g_bale[slot]) != 0;
                if (g_alive[slot]) created++;
            }
        }
    }

    // One uniform draw over the created bales: every bale has the same chance,
    // independent of its layer. The fallback below runs only if a bale failed
    // to spawn, so the normal path is exactly random(g_count).
    g_hidden = -1;
    if (g_count > 0) g_hidden = random(g_count);
    if (g_hidden < 0 || g_hidden >= g_count || !g_alive[g_hidden]) {
        new alive_count;
        for (new i = 0; i < g_count; i++) if (g_alive[i]) alive_count++;
        if (alive_count) {
            new pick = random(alive_count);
            for (new i = 0; i < g_count; i++) {
                if (!g_alive[i]) continue;
                if (pick == 0) { g_hidden = i; break; }
                pick--;
            }
        }
    }

    if (created == g_count && g_hidden >= 0) {
        new Float:needle_origin[3];
        pev(g_bale[g_hidden], pev_origin, needle_origin);
        g_needle = create_object(NEEDLE_MODEL, needle_origin, 10.0,
            float(max(1, get_pcvar_num(g_cvar_needle_hp))), MAGIC_NEEDLE, -1);
        if (pev_valid(g_needle)) {
            set_pev(g_needle, pev_solid, SOLID_NOT);
            set_pev(g_needle, pev_takedamage, 0.0);
            set_pev(g_needle, pev_effects, pev(g_needle, pev_effects) | EF_NODRAW);
            engfunc(EngFunc_SetOrigin, g_needle, needle_origin);
        }
    }

    if (created != g_count || g_hidden < 0 || !pev_valid(g_needle)) {
        log_amx("Seno: stage=%d entity creation failed (%d/%d bales, needle=%d); stack removed",
            stage, created, g_count, g_needle);
        for (new i = 0; i < g_count; i++) {
            if (pev_valid(g_bale[i]) && pev(g_bale[i], pev_iuser1) == MAGIC_BALE
                && pev(g_bale[i], pev_iuser3) == g_round_generation)
                engfunc(EngFunc_RemoveEntity, g_bale[i]);
            g_alive[i] = false;
            g_pending[i] = false;
            g_visible[i] = false;
            g_force_visible[i] = false;
            g_bale[i] = 0;
        }
        if (pev_valid(g_needle) && pev(g_needle, pev_iuser1) == MAGIC_NEEDLE
            && pev(g_needle, pev_iuser3) == g_round_generation)
            engfunc(EngFunc_RemoveEntity, g_needle);
        g_needle = 0;
        g_count = 0;
        g_hidden = -1;
        g_active_layers = 0;
        g_stage = 0;
        return false;
    }

    refresh_visibility();
    new needle_layer = -1;
    if (g_hidden >= 0 && g_hidden < g_count) needle_layer = g_layer[g_hidden];
    log_amx("Seno: stage=%d gen=%d layers=%d bales=%d visible=%d needle_slot=%d needle_layer=%d",
        stage, g_round_generation, g_active_layers, created, count_visible(), g_hidden, needle_layer);
    return true;
}

stock bool:is_alive_cell(layer, x, y)
{
    new slot = g_grid[layer][x][y];
    return slot >= 0 && g_alive[slot];
}

stock refresh_visibility()
{
    for (new slot = 0; slot < g_count; slot++) {
        if (!g_alive[slot]) { g_visible[slot] = false; continue; }
        if (g_force_visible[slot]) { g_visible[slot] = true; continue; }
        new layer = g_layer[slot], x = g_bale_x[slot], y = g_bale_y[slot];
        new n = g_active_layers - layer;
        if (x == 0 || y == 0 || x == n - 1 || y == n - 1) {
            g_visible[slot] = true;
            continue;
        }
        new bool:open_side = !is_alive_cell(layer, x-1, y)
            || !is_alive_cell(layer, x+1, y)
            || !is_alive_cell(layer, x, y-1)
            || !is_alive_cell(layer, x, y+1);
        new bool:open_top = layer == g_active_layers - 1;
        if (!open_top) open_top = !is_alive_cell(layer+1, x-1, y-1)
            || !is_alive_cell(layer+1, x-1, y)
            || !is_alive_cell(layer+1, x, y-1)
            || !is_alive_cell(layer+1, x, y);
        new bool:open_bottom = false;
        if (layer > 0) open_bottom = !is_alive_cell(layer-1, x, y)
            || !is_alive_cell(layer-1, x+1, y)
            || !is_alive_cell(layer-1, x, y+1)
            || !is_alive_cell(layer-1, x+1, y+1);
        g_visible[slot] = open_side || open_top || open_bottom;
    }
}

stock count_visible()
{
    new count;
    for (new slot = 0; slot < g_count; slot++) if (g_visible[slot]) count++;
    return count;
}

stock count_alive()
{
    new count;
    for (new slot = 0; slot < g_count; slot++) if (g_alive[slot]) count++;
    return count;
}

stock create_object(const model[], const Float:origin[3], Float:half, Float:hp, magic, slot)
{
    new ent = engfunc(EngFunc_CreateNamedEntity, engfunc(EngFunc_AllocString, "info_target"));
    if (!pev_valid(ent)) return 0;
    engfunc(EngFunc_SetModel, ent, model);
    new Float:mins[3], Float:maxs[3];
    mins[0] = mins[1] = mins[2] = -half;
    maxs[0] = maxs[1] = maxs[2] = half;
    set_pev(ent, pev_movetype, MOVETYPE_NONE);
    set_pev(ent, pev_solid, SOLID_BBOX);
    engfunc(EngFunc_SetSize, ent, mins, maxs);
    engfunc(EngFunc_SetOrigin, ent, origin);
    set_pev(ent, pev_light_level, (magic == MAGIC_NEEDLE) ? NEEDLE_LIGHT : BALE_LIGHT);
    set_pev(ent, pev_takedamage, 2.0);
    set_pev(ent, pev_health, hp);
    set_pev(ent, pev_iuser1, magic);
    set_pev(ent, pev_iuser2, slot);
    set_pev(ent, pev_iuser3, g_round_generation);
    return ent;
}

public on_trace_attack(ent, attacker, Float:damage, Float:direction[3], trace, damagebits)
{
    if (!pev_valid(ent)) return HAM_IGNORED;
    new magic = pev(ent, pev_iuser1);
    if (magic != MAGIC_BALE && magic != MAGIC_NEEDLE) return HAM_IGNORED;
    if (pev(ent, pev_iuser3) != g_round_generation) return HAM_SUPERCEDE;
    if (g_round_resetting || g_finishing || attacker < 1 || attacker > 32
        || !is_user_alive(attacker) || !g_knife_attack[attacker]
        || get_user_weapon(attacker) != CSW_KNIFE)
        return HAM_SUPERCEDE;
    new slot = pev(ent, pev_iuser2);
    if (magic == MAGIC_BALE && (slot < 0 || slot >= g_count || g_pending[slot])) return HAM_SUPERCEDE;
    if (magic == MAGIC_NEEDLE && g_needle_pending) return HAM_SUPERCEDE;
    if (magic == MAGIC_BALE && !g_visible[slot]) {
        g_force_visible[slot] = true;
        set_pev(ent, pev_light_level, BALE_LIGHT);
        refresh_visibility();
    }

    new Float:health;
    pev(ent, pev_health, health);
    health -= damage;
    if (health > 0.0) {
        set_pev(ent, pev_health, health);
        return HAM_SUPERCEDE;
    }
    if (magic == MAGIC_NEEDLE) {
        g_needle_pending = true;
        set_pev(ent, pev_takedamage, 0.0);
        set_task(0.1, "destroy_needle", TASK_NEEDLE);
        return HAM_SUPERCEDE;
    }
    if (slot < 0 || slot >= g_count || g_bale[slot] != ent || !g_alive[slot]) return HAM_SUPERCEDE;
    g_pending[slot] = true;
    set_pev(ent, pev_takedamage, 0.0);
    set_task(0.1, "destroy_bale", TASK_BALE_BASE + slot);
    return HAM_SUPERCEDE;
}

public destroy_bale(taskid)
{
    new slot = taskid - TASK_BALE_BASE;
    if (slot < 0 || slot >= g_count || !g_pending[slot] || !g_alive[slot]) return;
    new ent = g_bale[slot];
    if (!pev_valid(ent) || pev(ent, pev_iuser1) != MAGIC_BALE
        || pev(ent, pev_iuser3) != g_round_generation) return;
    new Float:origin[3];
    pev(ent, pev_origin, origin);
    g_pending[slot] = false;
    g_alive[slot] = false;
    g_bale[slot] = 0;
    engfunc(EngFunc_RemoveEntity, ent);
    bale_break_fx(origin);
    refresh_visibility();
    if (slot == g_hidden) reveal_needle(origin);
}

public destroy_needle()
{
    if (!g_needle_pending || !pev_valid(g_needle)
        || pev(g_needle, pev_iuser1) != MAGIC_NEEDLE
        || pev(g_needle, pev_iuser3) != g_round_generation) return;
    new Float:origin[3];
    pev(g_needle, pev_origin, origin);
    engfunc(EngFunc_RemoveEntity, g_needle);
    g_needle = 0;
    g_needle_pending = false;
    needle_break_fx(origin);
    start_finale();
}

public on_take_damage(ent, inflictor, attacker, Float:damage, damagebits)
{
    if (!pev_valid(ent)) return HAM_IGNORED;
    new magic = pev(ent, pev_iuser1);
    if (magic == MAGIC_BALE || magic == MAGIC_NEEDLE) return HAM_SUPERCEDE;
    return HAM_IGNORED;
}

public on_player_take_damage(victim, inflictor, attacker, Float:damage, damagebits)
{
    if (!g_map_active) return HAM_IGNORED;
    if (!(damagebits & DMG_FALL)) return HAM_IGNORED;
    return HAM_SUPERCEDE;
}

stock reveal_needle(const Float:origin[3])
{
    if (!pev_valid(g_needle)) return;
    set_pev(g_needle, pev_effects, pev(g_needle, pev_effects) & ~EF_NODRAW);
    set_pev(g_needle, pev_solid, SOLID_BBOX);
    set_pev(g_needle, pev_movetype, MOVETYPE_TOSS);
    set_pev(g_needle, pev_takedamage, 2.0);
    set_pev(g_needle, pev_light_level, NEEDLE_LIGHT);
    engfunc(EngFunc_SetOrigin, g_needle, origin);
    if (g_snd_needle_appear)
        emit_at_origin(SND_NEEDLE_APPEAR, origin, 0.75, PITCH_NORM);
    dlight_fx(origin, 220, 255, 225, 150, 8, 2);
    // The needle settles on remaining hay or on the room floor as supports disappear.
}

stock bale_break_fx(const Float:origin[3])
{
    if (g_snd_bale_break)
        emit_at_origin(SND_BALE_BREAK, origin, 0.65, random_num(96, 104));
    breakmodel_fx(g_mdl_bale, origin, 24, random_num(3, 5), 8, BREAK_WOOD);
}

stock needle_break_fx(const Float:origin[3])
{
    if (g_snd_needle_break)
        emit_at_origin(SND_NEEDLE_BREAK, origin, VOL_NORM, PITCH_NORM);
    breakmodel_fx(g_mdl_needle, origin, 12, 6, 10, BREAK_METAL);
    dlight_fx(origin, 280, 255, 180, 80, 10, 3);
}

stock emit_at_origin(const sample[], const Float:origin[3], Float:volume, pitch)
{
    // Core emit_sound() has no origin argument in AMXX 1.9 and index 0 means
    // "all clients". The engine's ambient emit is the positional one-shot.
    engfunc(EngFunc_EmitAmbientSound, 0, origin, sample, volume, ATTN_NORM, 0, pitch);
}

stock breakmodel_fx(modelindex, const Float:origin[3], half_size, count, life, flags)
{
    if (modelindex <= 0) return;
    message_begin_f(MSG_BROADCAST, SVC_TEMPENTITY, origin);
    write_byte(TE_BREAKMODEL);
    write_coord_f(origin[0]);
    write_coord_f(origin[1]);
    write_coord_f(origin[2]);
    write_coord(half_size);
    write_coord(half_size);
    write_coord(half_size);
    write_coord(0);
    write_coord(0);
    write_coord(160);
    write_byte(30);
    write_short(modelindex);
    write_byte(count);
    write_byte(life);
    write_byte(flags);
    message_end();
}

stock dlight_fx(const Float:origin[3], radius, red, green, blue, life, decay)
{
    message_begin_f(MSG_BROADCAST, SVC_TEMPENTITY, origin);
    write_byte(TE_DLIGHT);
    write_coord_f(origin[0]);
    write_coord_f(origin[1]);
    write_coord_f(origin[2]);
    write_byte(radius / 10);
    write_byte(red);
    write_byte(green);
    write_byte(blue);
    write_byte(life);
    write_byte(decay);
    message_end();
}

stock start_finale()
{
    if (g_finishing) return;
    g_finishing = true;
    g_sweep_fx_count = 0;
    for (new slot = 0; slot < g_count; slot++) {
        if (g_pending[slot]) {
            remove_task(TASK_BALE_BASE + slot);
            g_pending[slot] = false;
        }
    }
    g_sweep_layer = g_active_layers - 1;
    sweep_layer();
}

public sweep_layer()
{
    if (!g_finishing) return;
    while (g_sweep_layer >= 0) {
        new removed;
        for (new i = 0; i < g_count; i++) {
            if (g_layer[i] != g_sweep_layer || !g_alive[i]) continue;
            new Float:origin[3];
            new bool:had_entity;
            if (pev_valid(g_bale[i]) && pev(g_bale[i], pev_iuser1) == MAGIC_BALE
                && pev(g_bale[i], pev_iuser3) == g_round_generation) {
                pev(g_bale[i], pev_origin, origin);
                engfunc(EngFunc_RemoveEntity, g_bale[i]);
                had_entity = true;
            }
            if (had_entity) {
                // Finale sweep: keep one sound + breakmodel per SWEEP_FX_EVERY bales.
                if (g_sweep_fx_count % SWEEP_FX_EVERY == 0) bale_break_fx(origin);
                g_sweep_fx_count++;
            }
            g_alive[i] = false;
            g_bale[i] = 0;
            removed++;
        }
        g_sweep_layer--;
        if (removed) {
            refresh_visibility();
            break;
        }
    }
    if (g_sweep_layer < 0) {
        signal_finish();
        return;
    }
    new Float:interval = get_pcvar_float(g_cvar_interval);
    if (interval < 0.1) interval = 0.1;
    set_task(interval, "sweep_layer", TASK_SWEEP);
}

stock signal_finish()
{
    if (g_signalled) return;
    g_signalled = true;
    new stage = g_stage;
    new target[32];
    get_finish_target(stage, target, charsmax(target));
    new fired = fire_relay(target);
    log_amx("Seno: stage=%d finale completed, target=%s fired=%d", stage, target, fired);
    if (stage < MAX_STAGES) set_task(0.1, "begin_next_stage", TASK_NEXT_STAGE);
}

public begin_next_stage()
{
    if (!is_enabled() || g_round_resetting) return;
    if (!g_signalled) return;
    new next = g_stage + 1;
    if (next > MAX_STAGES) return;
    if (!spawn_stage(next))
        log_amx("Seno: stage=%d not created; trial stops at stage %d", next, g_stage);
}
