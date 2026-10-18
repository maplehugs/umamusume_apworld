//! Port of race_field.py -- multi-horse field coordination. Not part of the
//! original TS engine (which runs every RaceSolver in isolation, oblivious
//! to other horses).
//!
//! `RaceField` owns every solver in `RefCell`s so one can be borrowed
//! mutably (to step it) while its own methods borrow the others
//! immutably to answer blocking/lane/order queries -- the same access
//! pattern Python gets for free via shared references. Solvers do not hold
//! a reference back to the field: instead `field: Option<&RaceField>` is
//! threaded as an explicit parameter through `RaceSolver::step` and every
//! condition-checking closure (see `activation_conditions::DynCond`), so
//! nothing here needs a self-referential pointer or unsafe code.
//!
//! Ported already carrying the perf fixes validated on the Python engine:
//! each solver's own roster index is stored on it directly (`field_index`)
//! rather than found by a linear scan, `side_room`/`is_surrounded` early-out
//! once both/all flags are set, and `pacemaker()` is computed once per tick
//! and cached rather than recomputed per asking horse.

use std::cell::{Cell, RefCell};

use crate::horse_types::{strategy_matches, Strategy};
use crate::race_solver::{ skill_target, Perspective, RaceSolver, SkillEffect};

/// 1 horse-lane = 1/18 course-width (doc). `lane` fields elsewhere are
/// stored in course-width units; this converts a horse-lane count into
/// that unit wherever the doc states a threshold in horse-lanes.
pub const HORSE_LANE: f64 = 1.0 / 18.0;

/// Doc's pacemaker strategy groups, most-forward first.
const PACEMAKER_GROUPS: &[&[Strategy]] = &[&[Strategy::Nige, Strategy::Oonige], &[Strategy::Senkou], &[Strategy::Sasi], &[Strategy::Oikomi]];

pub struct RaceField {
    pub solvers: Vec<RefCell<RaceSolver>>,
    pub n: usize,
    /// Each solver's fixed strategy, mirrored outside its `RefCell` so
    /// `pacemaker()` can scan every horse's strategy -- including the one
    /// currently mid-`step()` and thus already mutably borrowed -- without
    /// re-entering that `RefCell`.
    strategies: Vec<Strategy>,
    rank_of: RefCell<Vec<usize>>,
    order: RefCell<Vec<usize>>,
    prev_rank_of: RefCell<Vec<usize>>,
    pacemaker_idx: Cell<Option<usize>>,
    pacemaker_valid: Cell<bool>,
    /// Effects aimed at other horses (debuffs), applied once the whole field
    /// has stepped: (target_index, effect, duration, skill_id).
    external: RefCell<Vec<(usize, SkillEffect, f64, String)>>,
    /// Spot struggle happens at most once per strategy group.
    compete_top_done: RefCell<Vec<Strategy>>,
    /// ability types of the skills each runner activated on the previous
    /// tick (is_other_character_activate_advantage_skill, target 23)
    advantage_prev: RefCell<Vec<(usize, Vec<i32>)>>,
}

impl RaceField {
    pub fn new(mut solvers: Vec<RaceSolver>) -> RaceField {
        let n = solvers.len();
        for (i, s) in solvers.iter_mut().enumerate() {
            s.field_index = Some(i);
        }
        let strategies = solvers.iter().map(|s| s.horse.strategy).collect();
        let field = RaceField {
            solvers: solvers.into_iter().map(RefCell::new).collect(),
            n,
            strategies,
            rank_of: RefCell::new(vec![0; n]),
            order: RefCell::new((0..n).collect()),
            prev_rank_of: RefCell::new(vec![0; n]),
            pacemaker_idx: Cell::new(None),
            pacemaker_valid: Cell::new(false),
            external: RefCell::new(Vec::new()),
            compete_top_done: RefCell::new(Vec::new()),
            advantage_prev: RefCell::new(Vec::new()),
        };
        field.update();
        // effects aimed at others that fired at the gate, before this field
        // existed (a friend's passive for Silence Suzuka, say)
        for i in 0..n {
            let (deferred, pos, lane, chara_id, vision, team, cancel) = {
                let mut s = field.solvers[i].borrow_mut();
                (std::mem::take(&mut s.deferred_external), s.pos, s.lane, s.chara_id, s.visible_distance(), s.context.get("teamId").and_then(crate::json::Value::as_i64).unwrap_or(0), s.debuff_cancel)
            };
            for (ef, duration, skill_id, log_index) in deferred {
                let hit = field.queue_external_effect(i, pos, lane, chara_id, vision, team, cancel, &ef, duration, &skill_id);
                let mut s = field.solvers[i].borrow_mut();
                if let Some(a) = s.activation_log.get_mut(log_index) {
                    for t in hit {
                        if !a.targets.contains(&t) {
                            a.targets.push(t);
                        }
                    }
                }
            }
        }
        let mut boosted: Vec<usize> = field.external.borrow().iter().map(|e| e.0).collect();
        boosted.sort_unstable();
        boosted.dedup();
        field.apply_external_effects();
        for idx in boosted {
            field.solvers[idx].borrow_mut().refresh_derived_stats();
        }
        field
    }

    /// Remaining distance of the viewer's (the player's) own horse; NaN (every
    /// comparison false) when she isn't in the race. `i` is the asking horse,
    /// mid-step and already borrowed -- the caller checks her itself.
    pub fn viewer_remain_distance(&self, i: usize) -> f64 {
        for j in 0..self.n {
            if j == i {
                continue;
            }
            let s = self.solvers[j].borrow();
            if s.is_viewer {
                return s.course.distance - s.pos;
            }
        }
        f64::NAN
    }

    pub fn other_activated_advantage(&self, i: usize, ability_type: i32) -> bool {
        self.advantage_prev.borrow().iter().any(|(j, types)| *j != i && types.contains(&ability_type))
    }

    /// Recompute live order/rank from each solver's current `pos`. Call
    /// once after every horse has been stepped for this tick.
    pub fn update(&self) {
        let mut prev = self.prev_rank_of.borrow_mut();
        let rank = self.rank_of.borrow();
        prev.copy_from_slice(&rank);
        drop(rank);
        self.pacemaker_valid.set(false);

        let positions: Vec<f64> = self.solvers.iter().map(|s| s.borrow().pos).collect();
        let mut idx: Vec<usize> = (0..self.n).collect();
        idx.sort_by(|&a, &b| positions[b].partial_cmp(&positions[a]).unwrap());
        let mut rank_of = vec![0usize; self.n];
        for (rank, &i) in idx.iter().enumerate() {
            rank_of[i] = rank + 1;
        }
        *self.rank_of.borrow_mut() = rank_of;
        *self.order.borrow_mut() = idx;
    }

    /// Step every still-racing solver by `dt`, then resolve what happens
    /// BETWEEN horses this tick (debuffs, overlaps, spot struggles) and
    /// refresh the shared order/rank snapshot. Doing the between-horse part
    /// after everyone has stepped keeps it independent of stepping order.
    pub fn step_all(&self, dt: f64, active_indices: &[usize]) {
        for &i in active_indices {
            self.solvers[i].borrow_mut().step(dt, Some(self));
        }
        self.apply_external_effects();
        self.resolve_overlaps();
        self.update();
        self.update_compete_top();
        let mut prev = Vec::new();
        for j in 0..self.n {
            let mut s = self.solvers[j].borrow_mut();
            if !s.advantage_types.is_empty() {
                prev.push((j, std::mem::take(&mut s.advantage_types)));
            }
        }
        *self.advantage_prev.borrow_mut() = prev;
    }

    /// Other horses still running (a finished horse sits frozen on the line
    /// and must not block or crowd the ones still running). Never borrows
    /// `i`, which may be mid-`step()`.
    fn running_others(&self, i: usize) -> impl Iterator<Item = (usize, std::cell::Ref<'_, RaceSolver>)> + '_ {
        (0..self.n).filter(move |&j| j != i).map(move |j| (j, self.solvers[j].borrow())).filter(|(_, s)| !s.finished)
    }

    // -- effects on other horses (debuffs) ---------------------------------

    /// Doc's Skill Target: which horses an effect aimed at others lands on,
    /// nearest first where the target type is a count.
    pub fn select_targets(&self, i: usize, pos: f64, lane: f64, chara_id: i32, vision: f64, team: i64, target_type: i32, target_value: i32) -> Vec<usize> {
        if target_type == skill_target::UMA_ID {
            // that character, whoever carries the skill (herself included)
            return (0..self.n)
                .filter(|&j| if j == i { chara_id == target_value } else {
                    let s = self.solvers[j].borrow();
                    !s.finished && s.chara_id == target_value
                })
                .collect();
        }
        let others: Vec<(usize, f64, f64, bool, Strategy)> = self
            .running_others(i)
            .map(|(j, s)| (j, s.pos, s.lane, s.is_kakari, s.horse.strategy))
            .collect();
        let take = target_value.max(0) as usize;
        let nearest = |mut v: Vec<(usize, f64)>| -> Vec<usize> {
            v.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
            v.into_iter().take(take).map(|(j, _)| j).collect()
        };
        match target_type {
            skill_target::ALL => std::iter::once(i).chain(others.iter().map(|o| o.0)).collect(),
            3 => others.iter().map(|o| o.0).collect(),
            skill_target::ALL_ALLIES => others.iter().filter(|o| team != 0 && self.solvers[o.0].borrow().context.get("teamId").and_then(crate::json::Value::as_i64).unwrap_or(0) == team).map(|o| o.0).collect(),
            skill_target::IN_FOV => nearest(others.iter().filter(|o| o.1 >= pos && o.1 - pos <= vision && (o.2 - lane).abs() <= (((o.1 - pos)/vision.max(0.001))*11.5*HORSE_LANE+2.0*HORSE_LANE)/2.0).map(|o| (o.0, o.1 - pos)).collect()),
            skill_target::AHEAD_OF_SELF => nearest(others.iter().filter(|o| o.1 > pos).map(|o| (o.0, o.1 - pos)).collect()),
            skill_target::BEHIND_SELF => nearest(others.iter().filter(|o| o.1 < pos).map(|o| (o.0, pos - o.1)).collect()),
            skill_target::ENEMY_STRATEGY => match Strategy::from_i32(target_value) {
                Ok(st) => others.iter().filter(|o| strategy_matches(o.4, st)).map(|o| o.0).collect(),
                Err(_) => Vec::new(),
            },
            skill_target::KAKARI_AHEAD => nearest(others.iter().filter(|o| o.3 && o.1 > pos).map(|o| (o.0, o.1 - pos)).collect()),
            skill_target::KAKARI_BEHIND => nearest(others.iter().filter(|o| o.3 && o.1 < pos).map(|o| (o.0, pos - o.1)).collect()),
            skill_target::KAKARI_STRATEGY => others.iter().filter(|o| o.3 && o.4 as i32 == target_value).map(|o| o.0).collect(),
            skill_target::AHEAD_OF_POSITION => nearest(others.iter().filter(|o| o.1 > pos).map(|o| (o.0, o.1 - pos)).collect()),
            skill_target::USED_RECOVERY => {
                let prev = self.advantage_prev.borrow();
                others
                    .iter()
                    .filter(|o| prev.iter().any(|(j, types)| *j == o.0 && types.contains(&(crate::race_solver::SkillType::Recovery as i32))))
                    .map(|o| o.0)
                    .take(take)
                    .collect()
            }
            // ALL_ALLIES / UMA_ID / USED_RECOVERY / AHEAD_OF_POSITION: need
            // team or character data this engine does not carry.
            _ => Vec::new(),
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn queue_external_effect(&self, i: usize, pos: f64, lane: f64, chara_id: i32, vision: f64, team: i64, cancel: bool, effect: &SkillEffect, duration: f64, skill_id: &str) -> Vec<usize> {
        let targets: Vec<usize> = self.select_targets(i, pos, lane, chara_id, vision, team, effect.target, effect.target_value).into_iter().filter(|&t| !(effect.modifier < 0.0 && if t == i { cancel } else { self.solvers[t].borrow().debuff_cancel })).collect();
        let mut ext = self.external.borrow_mut();
        for &t in &targets {
            ext.push((t, *effect, duration, skill_id.to_string()));
        }
        targets
    }

    fn apply_external_effects(&self) {
        let pending = std::mem::take(&mut *self.external.borrow_mut());
        for (idx, effect, duration, skill_id) in pending {
            let mut target = self.solvers[idx].borrow_mut();
            if !target.finished && !(target.debuff_cancel && effect.modifier < 0.0) {
                target.apply_effect(&effect, duration, &skill_id, Perspective::Other, Some(self));
            }
        }
    }

    // -- spot struggle (doc: Spot Struggle / Lead Competition, CompeteTop) ---

    /// Between two or more Front Runners (or two or more Oonige -- never
    /// mixed) close to the frontmost of their group, once the leader is 150m
    /// out, while one of them is still before section 6. At most once per
    /// group. Participants drop out when more than 5m behind every other
    /// struggler or 0.416 course-widths away laterally.
    fn update_compete_top(&self) {
        for group in [Strategy::Nige, Strategy::Oonige] {
            let active: Vec<usize> = (0..self.n)
                .filter(|&j| {
                    let s = self.solvers[j].borrow();
                    s.compete_top_active && s.horse.strategy == group
                })
                .collect();
            for &a in &active {
                let (finished, pos, lane) = {
                    let s = self.solvers[a].borrow();
                    (s.finished, s.pos, s.lane)
                };
                if finished {
                    self.solvers[a].borrow_mut().end_compete_top();
                    continue;
                }
                let keep = active.iter().any(|&o| {
                    if o == a {
                        return false;
                    }
                    let s = self.solvers[o].borrow();
                    s.compete_top_active && s.pos - pos <= 5.0 && (s.lane - lane).abs() <= 0.416
                });
                if !keep {
                    self.solvers[a].borrow_mut().end_compete_top();
                }
            }
        }
        if self.n == 0 || self.solvers[self.order.borrow()[0]].borrow().pos < 150.0 {
            return;
        }
        for group in [Strategy::Nige, Strategy::Oonige] {
            if self.compete_top_done.borrow().contains(&group) {
                continue;
            }
            let members: Vec<(usize, f64, f64, f64)> = (0..self.n)
                .filter_map(|j| {
                    let s = self.solvers[j].borrow();
                    (s.horse.strategy == group && !s.finished).then(|| (j, s.pos, s.lane, s.course.distance / 24.0))
                })
                .collect();
            if members.len() < 2 {
                continue;
            }
            let mut front = members[0];
            for m in &members {
                if m.1 > front.1 {
                    front = *m;
                }
            }
            let cands: Vec<(usize, f64, f64, f64)> = members.iter().copied().filter(|m| front.1 - m.1 < 3.75 && (front.2 - m.2).abs() < 0.165).collect();
            if cands.len() < 2 || !cands.iter().any(|m| m.1 < m.3 * 5.0) {
                continue;
            }
            self.compete_top_done.borrow_mut().push(group);
            for m in &cands {
                self.solvers[m.0].borrow_mut().start_compete_top();
            }
        }
    }

    // -- overlapping (doc: Overlapping) -------------------------------------

    /// Two horses within 0.4m and 0.4 horse-lanes: the outer one is bumped
    /// 0.4 horse-lanes further out and re-picks her target lane.
    fn resolve_overlaps(&self) {
        let running: Vec<usize> = (0..self.n).filter(|&j| !self.solvers[j].borrow().finished).collect();
        for ai in 0..running.len() {
            for &b in &running[ai + 1..] {
                let a = running[ai];
                let (a_pos, a_lane) = {
                    let s = self.solvers[a].borrow();
                    (s.pos, s.lane)
                };
                let (b_pos, b_lane) = {
                    let s = self.solvers[b].borrow();
                    (s.pos, s.lane)
                };
                if (a_pos - b_pos).abs() < 0.4 && (a_lane - b_lane).abs() < 0.4 * HORSE_LANE {
                    let outer = if b_lane > a_lane || (b_lane == a_lane && b > a) { b } else { a };
                    let mut o = self.solvers[outer].borrow_mut();
                    o.lane = o.course.max_lane.min(o.lane + 0.4 * HORSE_LANE);
                    o.lane_retarget = true;
                }
            }
        }
    }

    pub fn order_of(&self, i: usize) -> usize {
        self.rank_of.borrow()[i]
    }

    pub fn previous_order_of(&self, i: usize) -> usize {
        self.prev_rank_of.borrow()[i]
    }

    /// `my_pos`/`my_lane` below are the querying horse `i`'s own current
    /// values, passed in by the caller instead of re-borrowed here -- `i`
    /// may be the solver currently mid-`step()` and thus already mutably
    /// borrowed via its `RefCell`, so this must never index `self.solvers[i]`.
    pub fn distance_to_leader(&self, i: usize, my_pos: f64) -> f64 {
        let leader = self.order.borrow()[0];
        let leader_pos = if leader == i { my_pos } else { self.solvers[leader].borrow().pos };
        (leader_pos - my_pos).max(0.0)
    }

    pub fn distance_to_ahead(&self, i: usize, my_pos: f64) -> Option<f64> {
        let r = self.rank_of.borrow()[i];
        if r <= 1 {
            return None;
        }
        let ahead = self.order.borrow()[r - 2];
        Some((self.solvers[ahead].borrow().pos - my_pos).max(0.0))
    }

    pub fn distance_to_behind(&self, i: usize, my_pos: f64) -> Option<f64> {
        let r = self.rank_of.borrow()[i];
        if r >= self.n {
            return None;
        }
        let behind = self.order.borrow()[r];
        Some((my_pos - self.solvers[behind].borrow().pos).max(0.0))
    }

    pub fn lane_gap_to_ahead(&self, i: usize, my_lane: f64) -> Option<f64> {
        let r = self.rank_of.borrow()[i];
        if r <= 1 {
            return None;
        }
        let ahead = self.order.borrow()[r - 2];
        Some(self.solvers[ahead].borrow().lane - my_lane)
    }

    pub fn lane_gap_to_behind(&self, i: usize, my_lane: f64) -> Option<f64> {
        let r = self.rank_of.borrow()[i];
        if r >= self.n {
            return None;
        }
        let behind = self.order.borrow()[r];
        Some(my_lane - self.solvers[behind].borrow().lane)
    }

    /// True on the tick this solver's rank improved (took over at least one
    /// other horse) versus the previous tick.
    pub fn did_overtake(&self, i: usize) -> bool {
        self.rank_of.borrow()[i] < self.prev_rank_of.borrow()[i]
    }

    /// Doc: front block = 0 < distGap < 2m AND |laneGap| <= a tolerance that
    /// shrinks from 0.75 horse-lanes at 0m to 0.3 at 2m. Lowest
    /// distance-gap qualifying horse wins. Returns (other_index, dist_gap).
    pub fn front_blocker(&self, i: usize, pos: f64, lane: f64) -> Option<(usize, f64)> {
        let mut best: Option<(usize, f64)> = None;
        for (j, other) in self.running_others(i) {
            let dist_gap = other.pos - pos;
            if !(dist_gap > 0.0 && dist_gap < 2.0) {
                continue;
            }
            let lane_gap = (other.lane - lane).abs();
            let tolerance = (1.0 - 0.6 * dist_gap / 2.0) * 0.75 * HORSE_LANE;
            if lane_gap <= tolerance && best.map_or(true, |(_, bd)| dist_gap < bd) {
                best = Some((j, dist_gap));
            }
        }
        best
    }

    /// Doc: side block = |distGap| < 1.05m AND |laneGap| < 2 horse-lanes.
    /// Returns (inner_blocked, outer_blocked) -- inner = lower lane (toward
    /// the rail), outer = higher lane.
    pub fn side_room(&self, i: usize, pos: f64, lane: f64) -> (bool, bool) {
        let mut inner_blocked = false;
        let mut outer_blocked = false;
        let lane_tol = 2.0 * HORSE_LANE;
        for (_, other) in self.running_others(i) {
            let d = other.pos - pos;
            if !(-1.05 < d && d < 1.05) {
                continue;
            }
            let lane_gap = other.lane - lane;
            if !(-lane_tol < lane_gap && lane_gap < lane_tol) {
                continue;
            }
            if lane_gap < 0.0 {
                inner_blocked = true;
                if outer_blocked {
                    break;
                }
            } else if lane_gap > 0.0 {
                outer_blocked = true;
                if inner_blocked {
                    break;
                }
            }
        }
        (inner_blocked, outer_blocked)
    }

    /// Doc: true if ALL THREE of Out/Front/Behind each find another horse
    /// (the same horse may satisfy more than one direction).
    pub fn is_surrounded(&self, i: usize, pos: f64, lane: f64) -> bool {
        let mut out = false;
        let mut front = false;
        let mut behind = false;
        for (_, other) in self.running_others(i) {
            let dist_gap = other.pos - pos;
            let lane_gap = other.lane - lane;
            if dist_gap.abs() < 1.5 && lane_gap > 0.0 && lane_gap < 3.0 * HORSE_LANE {
                out = true;
            }
            if dist_gap > 0.0 && dist_gap < 3.0 && lane_gap.abs() < 1.5 * HORSE_LANE {
                front = true;
            }
            if dist_gap > -3.0 && dist_gap < 0.0 && lane_gap.abs() < 1.5 * HORSE_LANE {
                behind = true;
            }
            if out && front && behind {
                break;
            }
        }
        out && front && behind
    }

    pub fn is_solo_front_runner(&self, i: usize) -> bool {
        !self.running_others(i).any(|(j, _)| strategy_matches(self.strategies[j], Strategy::Nige))
    }

    /// Doc's pre-1.5-anniversary pacemaker rule: the 1st-place horse among
    /// the field's most-forward strategy group that's actually present.
    /// Depends only on `order` (refreshed once per tick by `update`) and
    /// solvers' fixed strategies, so it is computed once per tick and
    /// cached rather than recomputed per asking horse.
    pub fn pacemaker(&self) -> Option<usize> {
        if self.pacemaker_valid.get() {
            return self.pacemaker_idx.get();
        }
        let order = self.order.borrow();
        let mut result = None;
        for group in PACEMAKER_GROUPS {
            for &i in order.iter() {
                if group.contains(&self.strategies[i]) {
                    result = Some(i);
                    break;
                }
            }
            if result.is_some() {
                break;
            }
        }
        self.pacemaker_idx.set(result);
        self.pacemaker_valid.set(true);
        result
    }

    pub fn gap_to_pacemaker(&self, i: usize, my_pos: f64) -> f64 {
        match self.pacemaker() {
            Some(pm) if pm != i => self.solvers[pm].borrow().pos - my_pos,
            _ => 0.0,
        }
    }

    /// Doc: near = |distGap| < 3m AND |laneGap| < 3 horse-lanes.
    pub fn near_count(&self, i: usize, pos: f64, lane: f64) -> i32 {
        let lane_tol = 3.0 * HORSE_LANE;
        let mut count = 0;
        for (_, other) in self.running_others(i) {
            if (other.pos - pos).abs() < 3.0 && (other.lane - lane).abs() < lane_tol {
                count += 1;
            }
        }
        count
    }

    /// Doc: near_infront_count -- same "near" definition as near_count
    /// (|distGap|<3m, |laneGap|<3 horse-lanes) but restricted to horses AHEAD.
    pub fn near_infront_count(&self, i: usize, pos: f64, lane: f64) -> i32 {
        let lane_tol = 3.0 * HORSE_LANE;
        let mut count = 0;
        for (_, other) in self.running_others(i) {
            let dist_gap = other.pos - pos;
            if dist_gap > 0.0 && dist_gap < 3.0 && (other.lane - lane).abs() < lane_tol {
                count += 1;
            }
        }
        count
    }

    /// Doc: temptation_count_behind -- the number of horses ranked behind
    /// `i` (by finishing-position rank, not physical distance) that are
    /// currently rushing (kakari).
    pub fn temptation_count_behind(&self, i: usize) -> i32 {
        let r = self.rank_of.borrow()[i];
        let order = self.order.borrow();
        order[r..].iter().filter(|&&j| self.solvers[j].borrow().is_kakari).count() as i32
    }

    /// Doc: temptation_count_infront -- the number of horses ranked ahead
    /// of `i` that are currently rushing (kakari).
    pub fn temptation_count_infront(&self, i: usize) -> i32 {
        let r = self.rank_of.borrow()[i];
        let order = self.order.borrow();
        order[..r - 1].iter().filter(|&&j| self.solvers[j].borrow().is_kakari).count() as i32
    }

    /// Doc: running_style_temptation_count_{nige,senko,sashi,oikomi} -- the
    /// number of horses in the field (the querying horse counts too) with
    /// the given running strategy that are currently rushing. `self_idx`/
    /// `self_is_kakari` come from the caller directly (rather than
    /// re-borrowing `self.solvers[self_idx]`) since this is called from a
    /// condition check while that very solver is already mutably borrowed
    /// mid-`step()`.
    pub fn activated_any_advantage(&self, index: usize) -> bool {
        self.advantage_prev.borrow().iter().any(|(i,types)|*i==index && !types.is_empty())
    }

    pub fn running_style_temptation_count(&self, strategy: Strategy, self_idx: usize, self_is_kakari: bool) -> i32 {
        let others = (0..self.n)
            .filter(|&j| j != self_idx && strategy_matches(self.strategies[j], strategy) && self.solvers[j].borrow().is_kakari)
            .count() as i32;
        let self_counts = strategy_matches(self.strategies[self_idx], strategy) && self_is_kakari;
        others + self_counts as i32
    }
}
