//! Independently generated Global client-core candidate. Missing server logic is
//! reported explicitly in diagnostics; this module never reads replay outcomes.
use std::collections::{BTreeSet,HashMap};
use serde_json::{Value,json};
use crate::{data::{Assets,Master,RaceIn,HorseIn,Tree,ival,sval,f32_of},course::Course,geometry::Geometry,
    math,rng::RaceRandom,modifiers::{Modifiers,Operation},triggers::{self,Condition},netsort};

pub const DT:f32=0.0666;
const PHASE_NAMES:[&str;4]=["Start","Middle","End","Last"];
const STYLE_NAMES:[&str;4]=["Nige","Senko","Sashi","Oikomi"];
#[derive(Clone)]
struct Detail {
    pre:Condition, condition:Condition, pre_passed:bool, active:bool,
    left:f32, cooldown:f32, uid:u64, number:usize, additional_seen:i32, additional_used:[i32;3],
}
#[derive(Clone)]
struct Skill { id:i32, level:i32, row:HashMap<String,Value>, enabled:bool, details:Vec<Detail>, cooldown:f32 }
/// AroundHorse snapshot (Global field layout 0x10..0x30), taken in PreUpdate.
#[derive(Clone,Copy)]
struct Around { i:usize, gap:f32, gap_abs:f32, lane:f32, lane_abs:f32, speed_gap:f32, back:bool }
/// Research toggles for measuring each lane port separately (default on).
fn flag(name:&str)->bool {
    thread_local!(static FLAGS:std::cell::RefCell<HashMap<String,bool>>=Default::default());
    if let Some(v)=FLAGS.with(|f|f.borrow().get(name).copied()) {return v;}
    let v=std::env::var(name).map_or(true,|v|v!="0");FLAGS.with(|f|f.borrow_mut().insert(name.to_string(),v));v
}
/// Opt-in research toggles (`RX_D*=1`): C# statement evaluated in double,
/// rounded to float on assignment or float argument passing.
fn opt(name:&str)->bool {
    thread_local!(static FLAGS:std::cell::RefCell<HashMap<String,bool>>=Default::default());
    if let Some(v)=FLAGS.with(|f|f.borrow().get(name).copied()) {return v;}
    // Adopted after measurement (on unless `=0`); see RACE_GLOBAL_SOURCE_SEARCH.md.
    const ADOPTED:&[&str]=&["RX_D3A","RX_D3C","RX_D4","RX_D5C","RX_D7","RX_NEARPRE","RX_COMPETE","RX_T21","RX_TEND","RX_SLOPEMUL","RX_T4","RX_RESLOT","RX_SKCD","RX_GOALSPD","RX_GOALKEEP","RX_GOALLANE2","RX_GOALLANE3","RX_GOALLANE4","RX_GOALBLOCK","RX_GOALOT","RX_CT_EXPIRED_PEER","RX_SKILL_GAP_FLOOR","RX_PM_RANGE_LEAD","RX_GLOBAL_EVENT_FIRST","RX_GLOBAL_FINISH_GAP","RX_GLOBAL_TOP_EVENT_ORDER","RX_GLOBAL_PM_RECALC"];
    let v=match std::env::var(name) {Ok(v)=>v=="1",Err(_)=>ADOPTED.contains(&name)};
    FLAGS.with(|f|f.borrow_mut().insert(name.to_string(),v));v
}
#[derive(Clone)]
struct Horse {
    input:HorseIn, base:[f32;5], adjusted:[f32;5], mods:Modifiers, skills:Vec<Skill>,
    /// IsOrderInContinueArray / IsOrderOutContinueArray (OrderIn10..90, OrderOut10..90).
    order_continue:[[bool;9];2],
    distance:f32, prev_distance:f32, lane:f32, prev_lane:f32, lane_max:f32, target_lane:f32, lane_speed:f32,
    position:[f32;3], pos64:[f64;3], speed:f32, cf_speed:f32, cf_hp:f32, cf_pos:[f32;2], self_speed:f32, min_speed:f32, hp:f32, max_hp:f32,
    delay:f32, original_delay:f32, phase:usize, start_dash:bool, finished:bool,
    order:usize, prev_order:usize, guts_order:usize, wiz_order:usize,
    front:Option<usize>, inside:Option<usize>, outside:Option<usize>, near_count:usize,
    front_time:f32, side_time:f32, near_front_time:f32, near_behind_time:f32,
    /// _behindHorseNearLaneContinueTimeArray (Skill.BehindNearParamArray sets).
    near_behind_set:Vec<f32>, surround:[bool;3], reserved:Vec<i32>,
    corner:i32, corner_end:f32, final_corner:bool, straight:bool, front_type:i32,
    slope:f32, slope_end:f32, called_event:i32,
    /// Upper race-stat clamp: 2000 on Global; JP removed it (RX_JP_STATCAP=1 restores 2000).
    stat_max:f32,
    force_in:f32, ex:bool, style_rate:f32, dist_speed:f32, dist_power:f32, ground_coef:f32,
    section_speed:[f32;24], section_base:[f32;24], sec_rand:[f32;3], sec_drawn:u32, temptation_section:i32, temptation_mode:i32, temptation_active:bool,
    temptation_count:i32, temptation_timer:f32, temptation_check:f32, temptation_forced:bool, temptation_end:u8,
    downhill:bool, downhill_check:f32, spurt_result:i32, spurt_start:f32, spurt_speed:f32,
    spurt_calculated:bool, skill_time:f32, target_speed:f32, after_goal:f32, extra_lane:Option<f32>, force_lane:bool, raw_time:f32, scaled_time:f32,
    around:Vec<Around>, visible:Vec<usize>, in_space:f32, out_space:f32, overtake:Vec<usize>, ot_cool:f32, move_time:f32, move_dir:i32,
    /// HorseOrderChangeCounterUp: [PhaseStart, PhaseMiddle, PhaseEndAfter, Corner,
    /// CornerPhaseEndAfter, LastSpurt, Distance1, FinalCornerAfter] and per-runner cooldowns.
    order_up:[i32;8], order_up_cool:Vec<f32>, ot_target_time:f32, fight_count:i32, lane_move:f32,
    /// HorseDefeatCalculator inputs: IsHpEmptyOnRace, BlockFrontAccumulateTime, ActiveProper{Distance,GroundType}.
    hp_empty:bool, block_front_acc:f32, apt_distance:i32, apt_ground:i32,
    dbg:[f32;16], activate_count:i32, activate_phase:[i32;4], activate_half:[i32;2], heal_count:i32, keep:crate::position_keep::Keep, cp:Conserve,
}
/// Server-only ConservePower (脚をためる / 脚色十分) state; inferred from replays.
#[derive(Clone,Default)]
struct Conserve { end:Option<[f32;6]>, top:bool, pow:f32, mt:[f32;10], log:Vec<u32>, value:f32, timer:f32, released:bool, accel:f32, left:f32, dbg_p2:bool, dbg_sp:bool,
    /// RX_CPSPEC: KuromiAK-spec credit, cooldown ticks, previous rushed/CompeteTop flags.
    spec:f32, scd:i32, ctimer:f32, last_credit:f32, s_init:bool, s_tm:bool, s_tp:bool, probe_keep_mode:i32, lag_mode:i32,
    /// RX_CPDBG: per-tick [distance, self speed, target speed, pacemaker gap] alongside `log`.
    dlog:Vec<[f32;18]> }
impl Horse {
    // Native IsTemptation is independent of Mode (Senko can draw Null).
    fn tempted(&self)->bool {if opt("RX_TEMPT_ACTIVE") {self.temptation_active} else {self.temptation_mode!=0}}
    fn stat(&self,i:usize)->f32 {self.mods.apply(i,self.adjusted[i]).clamp(1.0,self.stat_max)}
    fn ex(&self)->bool {self.ex || self.mods.apply(20,0.0)!=0.0}
    /// JP servers encode lane/speed in single precision (speed 16.4899997 -> 1649, not 1648).
    fn frame(&self,jp:bool)->Value {
        if std::env::var("RX_HPDBG").is_ok() && (self.hp-self.hp.floor()<0.01 || self.hp.ceil()-self.hp<0.01) && self.hp.fract()!=0.0 {eprintln!("HPF {} d={}",self.hp,self.distance);}
        let mut v=json!({"distance":self.distance,
        "lane":if jp {(self.lane*10000.0) as i32} else {(self.lane as f64*10000.0) as i32},
        "speed":if jp {(self.speed*100.0) as i32} else {(self.speed as f64*100.0) as i32},"hp":self.hp as i32,"tempt":self.temptation_mode,
        "block":self.front.map_or(-1,|i|i as i32)});
        // RX_FRAMEDBG (debug only): x = [capped, corner, lane, self_speed, movement, speed].
        if std::env::var("RX_FRAMEDBG").is_ok() {v["x"]=json!([self.dbg[5],self.corner,self.lane,self.self_speed,self.dbg[6],self.speed]);v["dbg"]=json!(self.dbg);}
        v }
}
pub struct Simulator<'a> {
    input:RaceIn, master:&'a Master, assets:&'a Assets, course:Course, geometry:Geometry,
    horses:Vec<Horse>, random:RaceRandom, time:f32, events:Vec<Value>,
    unsupported:BTreeSet<String>, distance_diff_max:f32, compete:crate::compete::State, pacemaker:usize, pm_ready:bool, pm_section:i32, pm_not_forward:i32, pm_handed:bool, cur_skill:i32,
    /// JP is_activate_other_skill_detail: bitmask of details fired per (runner, skill); current detail.
    fired:HashMap<(usize,i32),u32>, cur_detail:usize,
}
impl<'a> Simulator<'a> {
    pub fn new(mut input:RaceIn,master:&'a Master,assets:&'a Assets,trace:bool)->Result<Self,String> {
        let expected_region=match input.region.as_deref() {
            Some("jp")=>"JP", None|Some("global")=>"Global",
            Some(region)=>return Err(format!("unknown race region {region}")),
        };
        if assets.root["source_region"]!=expected_region {
            return Err(format!("race region {expected_region} does not match asset source_region"));
        }
        if input.horses.is_empty() || input.horses.len()>255 {return Err("race requires 1..255 runners".into());}
        if input.seed<i32::MIN as i64 || input.seed>i32::MAX as i64 {return Err("seed exceeds int32".into());}
        if !matches!(input.seed_mode.as_str(),"logged"|"recovered") {return Err("unknown seed mode".into());}
        if input.seed_mode=="logged" && input.seed!=input.logged_seed {return Err("logged seed was substituted".into());}
        if !(1..=4).contains(&input.ground_condition) {return Err("ground condition outside 1..4".into());}
        input.horses.sort_by_key(|h|h.frame_order);
        for (i,h) in input.horses.iter().enumerate() {
            if h.frame_order!=i as i32+1 || !(1..=4).contains(&h.running_style) {
                return Err("runners require contiguous gates and running styles 1..4".into());
            }
        }
        let course=Course::load(assets,input.course_set)?;
        let geometry=Geometry::load(assets,&course,input.region.as_deref()==Some("jp"))?;
        let mut s=Self {random:RaceRandom::new(input.seed as i32,trace),input,master,assets,course,geometry,
            horses:vec![],time:0.0,events:vec![],unsupported:BTreeSet::new(),distance_diff_max:0.0,compete:crate::compete::State::new(0),pacemaker:0,pm_ready:false,pm_section:0,pm_not_forward:0,pm_handed:false,cur_skill:0,fired:HashMap::new(),cur_detail:0};
        // Null in the client. Do not invent activation rules or consume guessed draws.
        for mechanic in ["server:CompeteTop","server:CompeteFight","server:ConservePower","server:PaseMaker",
            "client:overtake_lane_search","results:defeat","skills:additional_activation","client:post_goal_targets","events:score",
            "skills:random_reservations","skills:event_target_flags"] {
            s.unsupported.insert(mechanic.into());
        }
        s.initialize()?;Ok(s)
    }
    fn p(&self)->Tree<'_> {self.assets.params()}
    fn jp(&self)->bool {self.input.region.as_deref()==Some("jp")}
    fn build_details(&mut self,hi:usize,id:i32,row:&std::collections::HashMap<String,Value>)->Vec<Detail> {
        let mut details=vec![];
        for d in 1..=2 {
            let text=sval(row,&format!("condition_{d}"));if text.is_empty() {continue;}
            let tag=format!("h{hi}:{id}:detail{d}");
            // Global replay 259f542a: skill trigger windows round the double-scaled draw once
            // (RX_LOT_WIDE=0 keeps float arithmetic).
            self.random.wide=!self.jp() && flag("RX_LOT_WIDE");
            let pre=triggers::build(sval(row,&format!("precondition_{d}")),&self.course,&mut self.random,&tag);
            let condition=triggers::build(text,&self.course,&mut self.random,&tag);
            self.random.wide=false;
            details.push(Detail {pre_passed:pre.is_empty(),pre,condition,active:false,left:0.0,cooldown:0.0,
                uid:((hi as u64)<<48)|((id as u64)<<8)|d as u64,number:d,additional_seen:0,additional_used:[0;3]});
        }
        // JP: detail 2 random tokens reuse detail 1's window for the same token name (draws are
        // still consumed, so the RNG stream is unchanged). Two-detail fallbacks such as 203992
        // otherwise fired detail 2 early; CP runners matched through section 10: 120 -> 213.
        if self.jp() && flag("RX_JP_SHAREWIN") && details.len()==2 {
            let first:Vec<(String,Vec<(f32,f32)>)>=details[0].condition.iter().flatten().filter(|t|t.randomized).map(|t|(t.name.clone(),t.windows.clone())).collect();
            for t in details[1].condition.iter_mut().flatten().filter(|t|t.randomized) {
                if let Some((_,w))=first.iter().find(|(n,_)|*n==t.name) {t.windows=w.clone();}
            }
        }
        details
    }
    /// JP probe: every activation lot first, then triggers only for skills that passed.
    fn jp_lots_then_triggers(&mut self,lot_pass:&impl Fn(&mut RaceRandom,&std::collections::HashMap<String,Value>,f32,String)->bool) {
        for hi in 0..self.horses.len() {
            for si in 0..self.horses[hi].skills.len() {
                let (row,id,wiz)=(self.horses[hi].skills[si].row.clone(),self.horses[hi].skills[si].id,self.horses[hi].base[4]);
                self.horses[hi].skills[si].enabled=lot_pass(&mut self.random,&row,wiz,format!("lot{hi}:{id}"));
            }
        }
        for hi in 0..self.horses.len() {
            for si in 0..self.horses[hi].skills.len() {
                if !self.horses[hi].skills[si].enabled {continue;}
                let (row,id)=(self.horses[hi].skills[si].row.clone(),self.horses[hi].skills[si].id);
                self.horses[hi].skills[si].details=self.build_details(hi,id,&row);
            }
        }
    }
    fn race_base(&self)->f32 {
        let p=self.p();
        if opt("RX_D8") {return (p.f("raceBaseSpeedBaseSpeed") as f64-(self.course.distance as f64-p.f("raceBaseSpeedBaseDistance") as f64)/p.f("raceBaseSpeedDistanceRate") as f64) as f32;}
        p.f("raceBaseSpeedBaseSpeed")-(self.course.distance-p.f("raceBaseSpeedBaseDistance"))/p.f("raceBaseSpeedDistanceRate")
    }
    fn rate(&self,table:&str,id:i32,column:&str)->Result<f32,String> {
        let r=self.master.find(table,"id",id as i64).ok_or_else(||format!("missing {table}:{id}"))?;
        // RX_RATE_DIV: master per-mille rates as int/10000 (0.6f, not 6000f*0.0001f = 0.59999996).
        Ok(match std::env::var("RX_RATE_DIV").ok().as_deref() {
            Some("1")=>ival(r,column) as f32/10000.0,
            Some("2")=>(ival(r,column) as f64*0.0001) as f32,
            _=>ival(r,column) as f32*0.0001,
        })
    }
    fn initialize(&mut self)->Result<(),String> {
        let p=self.assets.params();let c=&self.course;
        let track=self.master.find("race_track","id",c.master["race_track_id"].as_i64().unwrap()).ok_or("race track")?;
        let half=self.input.horses.len()<=9 && ival(track,"enable_half_gate")==1;
        let stat_max=if self.jp() && !std::env::var("RX_JP_STATCAP").is_ok_and(|v|v=="1") {f32::MAX} else {2000.0};
        let mut horses=vec![];
        for (i,h) in self.input.horses.iter().enumerate() {
            let mood=self.rate("race_motivation_rate",h.motivation,"motivation_rate")?;
            let bonus=if h.team_rank==0 {0} else {self.master.rows("race_single_mode_team_status").iter()
                .find(|r|(h.team_rank as i64)<ival(r,"team_rank_threshold")).map_or(0,|r|ival(r,"add_status"))};
            // Server conversion, before mood and career additions. Retain raw
            // input stats for mechanics that explicitly use unhalved power.
            // Corpus probe: 187/187 initial HP and 1766/1775 opening movement
            // samples, with the latter's residuals all missing Groundwork.
            let base=[h.speed,h.stamina,h.pow,h.guts,h.wiz].map(|v|{
                let raw=if v>1200 {1200.0+(v-1200) as f32*0.5} else {v as f32};
                ((bonus as f32+raw)*mood).clamp(1.0,stat_max)
            });
            let style=h.running_style as usize-1;
            let style_apt=[h.proper_running_style_nige,h.proper_running_style_senko,h.proper_running_style_sashi,h.proper_running_style_oikomi][style];
            let distance_apt=if c.distance<=1400.0 {h.proper_distance_short} else if c.distance<=1800.0 {h.proper_distance_mile}
                else if c.distance<=2400.0 {h.proper_distance_middle} else {h.proper_distance_long};
            let ground_apt=if c.ground==1 {h.proper_ground_turf} else {h.proper_ground_dirt};
            let mut course_coef=1.0;
            let sid=c.master["course_set_status_id"].as_i64().unwrap();
            if sid!=0 {
                let row=self.master.find("race_course_set_status","course_set_status_id",sid).ok_or("course stat adjust")?;
                let targets=[ival(row,"target_status_1"),ival(row,"target_status_2")];let count=targets.iter().filter(|t|**t!=0).count() as f32;
                for t in targets.into_iter().filter(|t|*t!=0) {
                    let coef=p.arr("CourseSetAdjust.CoefAndThresholdArray").iter()
                        .find(|r|r["StatusThreshold"].as_i64().unwrap() as f32>=base[t as usize-1]).map_or(0.0,|r|f32_of(&r["Coef"]));
                    course_coef+=coef/count;
                }
            }
            let ground=Tree(&p.arr(if c.ground==1 {"_groundModifierParamTurf"} else {"_groundModifierParamDirt"})[self.input.ground_condition as usize-1]);
            let mode=matches!(self.input.race_type,6|7);
            let add=|name:&str|if mode {p.f(&format!("Global.SingleModeAdd{name}"))} else {0.0};
            // InitBaseStatusAdjust (Global client 0x3436430) stores each adjusted
            // field after the full expression. Global server retains the product
            // and additions in double until that store. Premature product rounding
            // shifts career wisdom/speed by one ULP (1fd80833 / 3f359e91).
            let wide=self.input.region.as_deref()!=Some("jp") && flag("RX_GLOBAL_ADJUSTED_STAT");
            let adjusted=[
                adjusted_stat(base[0],course_coef,ground.f("addSpeed"),add("Speed"),wide,stat_max),
                adjusted_stat(base[1],1.0,0.0,add("Stamina"),wide,stat_max),
                adjusted_stat(base[2],1.0,ground.f("addPower"),add("Pow"),wide,stat_max),
                adjusted_stat(base[3],1.0,0.0,add("Guts"),wide,stat_max),
                adjusted_stat(base[4],self.rate("race_proper_runningstyle_rate",style_apt,"proper_rate")?,0.0,add("Wiz"),wide,stat_max),
            ];
            let outside=self.input.region.as_deref()==Some("jp") && c.turn==4
                && c.master["run_outside"].as_i64()==Some(1)
                && flag("RX_JP_OUTSIDE_GATE");
            let lane=initial_lane(i as i32,ival(track,"initial_lane_type"),half,c.lane_max,self.input.horses.len() as i32,outside);
            if !h.item_id_array.is_empty() {self.unsupported.insert("init:race_items".into());}
            let ex=h.running_style==1 && h.skill_array.iter().any(|sk|self.master.find("skill_data","id",sk.skill_id as i64)
                .is_some_and(|r|(1..=2).any(|d|(1..=3).any(|a|ival(r,&format!("ability_type_{d}_{a}"))==6))));
            // ConservePower stat: motivation scales only the halved base; the other half of the
            // excess over 1200 is added unscaled (KuromiAK; 117 Global CP-release divergences
            // fit). RX_CPPOW=0 restores raw*mood.
            let raw=h.pow as f32;
            let cp_pow=if flag("RX_CPPOW") && raw>1200.0 {(1200.0+(raw-1200.0)*0.5)*mood+(raw-1200.0)*0.5} else {raw*mood};
            horses.push(Horse {input:h.clone(),base,adjusted,mods:Modifiers::default(),skills:vec![],distance:0.0,prev_distance:0.0,
                order_continue:[[true;9];2],lane,prev_lane:lane,lane_max:c.lane_max,target_lane:lane,lane_speed:0.0,position:self.geometry.world(0.0,lane),pos64:self.geometry.world64(0.0,lane,std::env::var("RX_POS64").ok().and_then(|v|v.parse().ok()).unwrap_or(1)),speed:p.f("StartSpeed"),
                self_speed:p.f("StartSpeed"),min_speed:p.f("StartSpeed"),hp:0.0,max_hp:0.0,delay:0.0,original_delay:0.0,
                phase:0,start_dash:true,finished:false,order:i,prev_order:i,ot_target_time:0.0,fight_count:0,cf_speed:0.0,cf_hp:0.0,cf_pos:[0.0;2],lane_move:0.0,hp_empty:false,block_front_acc:0.0,apt_distance:distance_apt,apt_ground:ground_apt,order_up:[0;8],order_up_cool:vec![0.0;self.input.horses.len()],guts_order:0,wiz_order:0,
                front:None,inside:None,outside:None,near_count:0,around:vec![],visible:vec![],in_space:0.0,out_space:0.0,overtake:vec![],ot_cool:0.0,move_time:0.0,move_dir:0,front_time:0.0,side_time:0.0,near_front_time:0.0,near_behind_time:0.0,near_behind_set:vec![],surround:[false;3],reserved:vec![],
                corner:0,corner_end:0.0,final_corner:false,straight:false,front_type:0,slope:0.0,slope_end:0.0,called_event:-1,
                stat_max,force_in:0.0,ex,style_rate:self.rate("race_proper_runningstyle_rate",style_apt,"proper_rate")?,dist_speed:self.rate("race_proper_distance_rate",distance_apt,"proper_rate_speed")?,
                dist_power:self.rate("race_proper_distance_rate",distance_apt,"proper_rate_power")?,
                ground_coef:self.rate("race_proper_ground_rate",ground_apt,"proper_rate")?,section_speed:[0.0;24],section_base:[0.0;24],sec_rand:[0.0;3],sec_drawn:0,
                temptation_section:0,temptation_mode:0,temptation_active:false,temptation_count:0,temptation_timer:0.0,temptation_check:0.0,temptation_forced:false,temptation_end:0,
                // HorseRaceAIBase ctor leaves the downhill countdown at zero.
                downhill:false,downhill_check:0.0,spurt_result:8,spurt_start:-1.0,spurt_speed:0.0,spurt_calculated:false,skill_time:-1.0,target_speed:0.0,after_goal:0.0,extra_lane:None,force_lane:false,
                raw_time:-1.0,scaled_time:-1.0,dbg:[0.0;16],activate_count:0,activate_phase:[0;4],activate_half:[0;2],heal_count:0,keep:crate::position_keep::Keep::default(),cp:Conserve {pow:cp_pow,..Default::default()}});
        }
        self.horses=horses;
        self.compete=crate::compete::State::new(self.horses.len());
        // Opening server evidence selects the first gate of the most forward
        // strategy (Oonige before normal Nige). Retain that initial reference;
        // server switching rules remain explicitly unsupported. Dynamic leader
        // selection prematurely changed the reference in two no-Nige races.
        self.pacemaker=self.horses.iter().enumerate().min_by_key(|(i,h)|
            (if h.ex() {0} else {h.input.running_style},*i)).unwrap().0;
        // Probe: RX_PMFIX=i pins runner i (gate order) as the pacemaker.
        if let Some(i)=std::env::var("RX_PMFIX").ok().and_then(|v|v.parse::<usize>().ok()) {
            if i<self.horses.len() {self.pacemaker=i;}
        }
        // CreateSkill for the entire gate-ordered field before CreateAI.
        // RX_JP_LOTFIRST (JP probe): 1 = per skill, activation lot then triggers only if
        // it passed; 2 = force-in, all lots, then triggers for passed skills;
        // 3 = all lots, triggers for passed skills, then force-in. 0 = Global order.
        let lot_first=if self.jp() {std::env::var("RX_JP_LOTFIRST").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(0)} else {0};
        let lot_k={let p=self.assets.params();(p.f("Skill.LotActivatePerVal1"),p.f("Skill.LotActivatePerVal2"),p.i("Skill.ActivatePerMin") as f32)};
        let lot_pass=move |r:&mut RaceRandom,row:&std::collections::HashMap<String,Value>,wiz:f32,tag:String|ival(row,"activate_lot")!=1 || r.float_max(100.0,&||tag.clone())<
            (lot_k.0-lot_k.1/wiz).max(lot_k.2);
        for hi in 0..self.horses.len() {
            for sk in self.horses[hi].input.skill_array.clone() {
                let row=self.master.find("skill_data","id",sk.skill_id as i64).ok_or_else(||format!("missing skill {}",sk.skill_id))?.clone();
                let enabled=lot_first==1 && lot_pass(&mut self.random,&row,self.horses[hi].base[4],format!("lot{hi}:{}",sk.skill_id));
                let details=if matches!(lot_first,0) || enabled {self.build_details(hi,sk.skill_id,&row)} else {vec![]};
                self.horses[hi].skills.push(Skill{id:sk.skill_id,level:sk.level,row,enabled,details,cooldown:0.0});
            }
        }
        if lot_first==3 {self.jp_lots_then_triggers(&lot_pass);}
        let p=self.assets.params();let range=p.f("forceInMoveTargetSpeedAddRandomRange");
        for (hi,h) in self.horses.iter_mut().enumerate() {
            let name=["RunningOut","Proceding","Insertion","Chasing"][h.input.running_style as usize-1];
            let v=p.f(&format!("forceInMoveTargetSpeedAdd{name}"));
            h.force_in=if math::approximately(v,0.0) {0.0} else {
                self.random.float_range(if v<=0.0 {-range} else {0.0},if v>0.0 {range} else {0.0},&||format!("forcein{hi}"))+v
            };
        }
        if lot_first==2 {self.jp_lots_then_triggers(&lot_pass);}
        if lot_first==0 {
            for (hi,h) in self.horses.iter_mut().enumerate() {
                for sk in &mut h.skills {
                    sk.enabled=lot_pass(&mut self.random,&sk.row,h.base[4],format!("lot{hi}:{}",sk.id));
                }
            }
        }
        self.skills_pass(0.0,1);self.skills_pass(0.0,0);
        if self.jp() {
            // JP StaminaLimitBreakBuff: two raw samples per runner whose f32(raw stamina * mood)
            // plus guaranteed basis-distance stamina passives exceeds 1200, on every course,
            // just before the start delays (RACE_SERVER_MECHANICS.md section 2).
            let basis=((self.course.distance as i32)%400<100) as i64;
            for hi in 0..self.horses.len() {
                let h=&self.horses[hi];
                let mut s=h.input.stamina as f32*self.rate("race_motivation_rate",h.input.motivation,"motivation_rate").unwrap_or(1.0);
                for sk in &h.input.skill_array {
                    let Some(r)=self.master.find("skill_data","id",sk.skill_id as i64) else {continue};
                    if ival(r,"activate_lot")!=0 || !sval(r,"precondition_1").is_empty()
                        || sval(r,"condition_1")!=format!("is_basis_distance=={basis}") {continue;}
                    for a in 1..=3 {
                        if ival(r,&format!("ability_type_1_{a}"))==2 {s+=ival(r,&format!("float_ability_value_1_{a}")) as f32*0.0001;}
                    }
                }
                if s>1200.0 {for k in 0..2 {self.random.raw(&||format!("slb{hi}:{k}"));}}
            }
        }
        for (hi,h) in self.horses.iter_mut().enumerate() {
            let fixed=h.mods.consume(22,0.0);let scale=h.mods.consume(15,1.0);
            h.delay=(if fixed>0.0 {fixed} else {self.random.float_max(p.f("startDelayMax"),&||format!("delay{hi}"))})*scale;
            h.original_delay=h.delay;
        }
        let race_base=self.race_base();
        for (hi,h) in self.horses.iter_mut().enumerate() {
            let style=if h.ex() {"OoNige"} else {STYLE_NAMES[h.input.running_style as usize-1]};
            // Server rounds once after this expression. Float32 intermediate
            // products left one early HP sample one unit too high; preserving
            // them in double precision matches all 21,864 opening HP samples.
            h.max_hp=(h.stat(1) as f64*p.f("Hp.HpInitialVal1") as f64*
                p.f(&format!("Hp.HpMaxCoef{style}")) as f64+self.course.distance as f64) as f32;
            h.hp=h.max_hp;
            let jp_secrand=if self.input.region.as_deref()==Some("jp") {std::env::var("RX_JP_SECRAND").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(0)} else {0};
            let array=if h.ex() {"PhaseBaseTargetSpeedPerExArray[0]".to_owned()}
                else {format!("PhaseBaseTargetSpeedPerArray[{}]",h.input.running_style-1)};
            for i in 0..24 {
                let phase=self.course.phase(i as f32*(self.course.distance/24.0));
                let per=if phase<4 {p.f(&format!("BasetTargetSpeed.{array}.{}",PHASE_NAMES[phase]))} else {0.0};
                // CalcPhaseEndAdd (0x34273b0): sqrt has float argument/result;
                // remaining products round at the float helper return. Isolated
                // Global corpus: 436 -> 440 perfect, 0 earlier/lost; dense misses
                // 127 -> 97 (docs/RACE_ULP_PARITY_2026-10-08.md).
                let add=if phase==2 || phase==3 {
                    let v=(h.stat(0)*p.f("BasetTargetSpeed.PhaseEndBaseTargetSpeedCoef")).sqrt();
                    if self.input.region.as_deref()!=Some("jp") && flag("RX_ULP_PHASE_END_RETURN") {
                        (v as f64*h.dist_speed as f64*p.f("addSpeedParamCoef") as f64) as f32
                    } else {v*h.dist_speed*p.f("addSpeedParamCoef")}
                } else {0.0};
                let l=math::log10(h.stat(4)*0.1);
                // JP probe RX_JP_SECRAND: 1 = draw section i's random on entry (section 0 at
                // init), 2 = every section on entry. Section speeds hold the base until drawn.
                let lazy=if jp_secrand==0 {false} else {jp_secrand==2 || i>0};
                if lazy {
                    let c=0.01f32 as f64;
                    h.sec_rand=[l*(h.stat(4)/p.f("BasetTargetSpeed.BaseTargetSpeedRandomMinusVal2"))+p.f("BasetTargetSpeed.BaseTargetSpeedRandomMinusVal1"),
                        l*(h.stat(4)/p.f("BasetTargetSpeed.BaseTargetSpeedRandomPlusVal1")),(c*race_base as f64) as f32];
                    h.section_base[i]=(per as f64*c*race_base as f64+add as f64) as f32;
                    h.section_speed[i]=h.section_base[i];
                    continue;
                }
                h.sec_drawn|=1<<i;
                // Global replays fit the section random in double: bounds l*wiz/val (+val1) rounded once,
                // then the float draw scaled in double and rounded once (30 later / 0 earlier on 673).
                // RX_SECRAND_WIDE=0 restores float arithmetic; JP is unchanged.
                let wide=self.input.region.as_deref()!=Some("jp") && flag("RX_SECRAND_WIDE");
                let (w,v2,v1,p1)=(h.stat(4) as f64,p.f("BasetTargetSpeed.BaseTargetSpeedRandomMinusVal2") as f64,p.f("BasetTargetSpeed.BaseTargetSpeedRandomMinusVal1") as f64,p.f("BasetTargetSpeed.BaseTargetSpeedRandomPlusVal1") as f64);
                let (lo,up)=if wide {((l as f64*w/v2+v1) as f32,(l as f64*w/p1) as f32)}
                    else {(l*(h.stat(4)/p.f("BasetTargetSpeed.BaseTargetSpeedRandomMinusVal2"))+p.f("BasetTargetSpeed.BaseTargetSpeedRandomMinusVal1"),
                    l*(h.stat(4)/p.f("BasetTargetSpeed.BaseTargetSpeedRandomPlusVal1")))};
                let random=self.random.float_range_with(lo,up,if wide {crate::rng::Wide::FloatDraw} else {crate::rng::Wide::Float},&||format!("base{hi}:section{i}"));
                // BaseSpeedInfo fields (client 0x3426fa0: r*0.01f*raceBase and
                // per*0.01f*raceBase+add). Server replays fit these products
                // evaluated in double and rounded once at each field store:
                // steady pace-down speeds were 1-5 ULP high with float32 steps.
                let c=0.01f32 as f64;
                h.section_base[i]=(per as f64*c*race_base as f64+add as f64) as f32;
                h.section_speed[i]=(random as f64*c*race_base as f64) as f32+h.section_base[i];
            }
            h.self_speed=h.speed;
        }
        for stat in [3,4] {
            let mut indices=(0..self.horses.len()).collect::<Vec<_>>();
            netsort::sort(&mut indices,&|a,b| {let d=self.horses[*b].stat(stat)-self.horses[*a].stat(stat);
                if math::approximately(self.horses[*a].stat(stat),self.horses[*b].stat(stat)) {*a as i32-*b as i32} else if d>0.0 {1} else {-1}});
            for (order,i) in indices.into_iter().enumerate() {if stat==3 {self.horses[i].guts_order=order;} else {self.horses[i].wiz_order=order;}}
        }
        for (hi,h) in self.horses.iter_mut().enumerate() {
            let chance=math::pow(p.f("Temptation.TemptationStartPerVal1")/math::log10(math::pow(h.stat(4)*0.1+1.0,2.0)),2.0);
            let chance=h.mods.apply(8,chance);
            if (self.random.int_max(100,&||format!("temptation{hi}")) as f32)<chance {
                h.temptation_section=self.random.int_range(p.i("Temptation.TemptationLotSectionMin"),p.i("Temptation.TemptationLotSectionMax")+1,&||format!("temptation_section{hi}"));
            }
        }
        Ok(())
    }
    fn query(&self,hi:usize,n:&str,rhs:i32)->Option<f32> {
        let v=self.query_inner(hi,n,rhs);
        // Research: RX_QDBG=hi logs every condition value queried for that runner.
        if std::env::var("RX_QDBG").ok().and_then(|x|x.parse::<usize>().ok())==Some(hi) {
            let h=&self.horses[hi];eprintln!("Q {:.4} sk{} {}={:?} d={} ord={}",self.time,self.cur_skill,n,v,h.distance,h.order);
        }
        v
    }
    fn query_inner(&self,hi:usize,n:&str,rhs:i32)->Option<f32> {
        let h=&self.horses[hi];let c=&self.course;
        let boolean=|b:bool|if b {1.0} else {0.0};
        Some(match n {
            "always"=>1.0,"course_distance"=>c.distance,"ground_type"=>c.ground as f32,
            "track_id"=>c.master["race_track_id"].as_i64().unwrap() as f32,"rotation"=>c.turn as f32,
            "distance_type"=>if c.distance<=1400.0 {1.0} else if c.distance<=1800.0 {2.0} else if c.distance<=2400.0 {3.0} else {4.0},
            "is_basis_distance"=>boolean((c.distance as i32)%400<100),"ground_condition"=>self.input.ground_condition as f32,
            "weather"=>self.input.weather as f32,"season"=>self.input.season as f32,"motivation"=>h.input.motivation as f32,
            "running_style"=>h.input.running_style as f32,"post_number"=>post_number(hi,self.horses.len()) as f32,
            "popularity"=>((h.input.popularity-1).max(0)+1) as f32,"phase"=>h.phase as f32,"corner"=>h.corner as f32,
            "is_finalcorner"=>boolean(h.final_corner),"is_finalcorner_laterhalf"=>boolean(h.final_corner && c.final_corner().is_some_and(|s|h.distance>=(s.start+s.end)*0.5)),
            // Global: remain_distance = course length - integer-truncated distance (b708d901; 643 -> 644,
            // 0 lost; truncating or rounding the float remainder instead loses 500+).
            "remain_distance"=>if self.input.region.as_deref()!=Some("jp") && flag("RX_REMAIN_INT") {c.distance-(h.distance as i32) as f32} else {c.distance-h.distance},"distance_rate"=>{
                let threshold=(rhs as f32/100.0*c.distance+0.5) as i32;
                return Some((h.distance as i32-threshold+rhs) as f32);
            },
            "distance_diff_top"=>{
                let gap=self.horses.iter().map(|h|h.distance).fold(0.0,f32::max)-h.distance;
                // SkillTriggerDistanceDiffTop.GetValueLh (0x35dd090) floors to int.
                if opt("RX_SKILL_GAP_FLOOR") {gap.floor()} else {gap}
            },
            // SkillTriggerHorseDistanceDiffRate (0x35df5d0): against the current first-to-last
            // spread (CurOrder 0 and last), 0 when approximately zero, else truncated to int.
            "distance_diff_rate" if flag("RX_DDRATE")=>{
                let first=self.horses.iter().find(|o|o.order==0)?.distance;
                let last=self.horses.iter().find(|o|o.order==self.horses.len()-1)?.distance;
                let spread=first-last;
                if math::approximately(spread,0.0) {0.0} else {((first-h.distance)/spread*100.0) as i32 as f32}
            },
            "distance_diff_rate"=>if self.distance_diff_max>0.0 {(self.horses.iter().map(|h|h.distance).fold(0.0,f32::max)-h.distance)/self.distance_diff_max*100.0} else {0.0},
            "accumulatetime"=>self.time.floor(),"time"=>ival(self.master.find("race_instance","id",self.input.race_instance_id as i64)?,"time") as f32,
            "grade"=>ival(self.master.find("race","id",self.input.race_id as i64)?,"grade") as f32,
            "is_dirtgrade"=>ival(self.master.find("race","id",self.input.race_id as i64)?,"is_dirtgrade") as f32,
            "order"=>h.order as f32+1.0,"order_rate"=>{
                // Compare internal order against a once-rounded runner-count threshold.
                let threshold=(rhs as f32/100.0*self.horses.len() as f32+0.5) as i32;
                return Some((h.order as i32+1-threshold+rhs) as f32);
            },
            n if flag("RX_ORDCONT") && n.starts_with("order_rate_") && n.ends_with("_continue") => {
                let out=n.starts_with("order_rate_out");let rate:usize=n.trim_start_matches(if out {"order_rate_out"} else {"order_rate_in"}).trim_end_matches("_continue").parse().ok()?;
                boolean(h.order_continue[usize::from(out)][rate/10-1])
            },
            // SkillTriggerHorseBehindIn (0x35e0560): false for the last runner, else whether the
            // runner at CurOrder+1 has a smaller lane distance than the owner.
            "is_behind_in" if flag("RX_BEHINDIN")=>{
                match self.horses.iter().find(|o|o.order==h.order+1) {Some(b)=>boolean(b.lane<h.lane),None=>return None}
            },
            "hp_per"=>if h.max_hp>0.0 {(h.hp/h.max_hp*100.0) as i32 as f32} else {100.0},
            "is_last_straight_onetime"=>boolean(h.straight && c.final_corner().is_some_and(|s|h.distance>=s.end)),
            "base_speed"=>h.base[0],"base_stamina"=>h.base[1],"base_power"=>h.base[2],"base_guts"=>h.base[3],"base_wiz"=>h.base[4],
            // lastspurt (unlike is_lastspurt) is 2 for a full max-speed spurt and 1 for a reduced one
            // (JP detail choice of e.g. 204122: 87 -> 12 mismatches). RX_LASTSPURT=0 restores the
            // boolean; =2 probes the raw calc result.
            "lastspurt" if std::env::var("RX_LASTSPURT").map_or(true,|v|v!="0")=>{
                let on=h.spurt_start>0.0 && h.spurt_result&12==0 && h.distance>=h.spurt_start;
                if !on {0.0} else if std::env::var("RX_LASTSPURT").as_deref()==Ok("2") {h.spurt_result as f32} else if h.spurt_result==1 {2.0} else {1.0}
            }
            "is_lastspurt"|"lastspurt"=>boolean(h.spurt_start>0.0 && h.spurt_result&12==0 && h.distance>=h.spurt_start),
            "slope"=>if h.slope>0.0 {1.0} else if h.slope<0.0 {2.0} else {0.0},
            "is_badstart"=>boolean(h.original_delay>=0.08),"is_temptation"=>boolean(h.tempted()),
            // HorseRaceAIBase.IsOverTake (0x3431370): OverTakeHorseList.Count > 0.
            "is_overtake" if flag("RX_ISOT")=>boolean(!h.overtake.is_empty()),
            "temptation_opponent_count_infront"|"temptation_opponent_count_behind"|"temptation_count_infront"|"temptation_count_behind" if flag("RX_TINF")=>{
                // SkillTriggerTemptationInfront/Behind (0x35e2ae0/0x35e2920): runners in
                // temptation ahead of / behind the owner's CurOrder; opponent filter by team.
                let opp=n.contains("opponent");let team=h.input.team_id;let infront=n.ends_with("infront");
                self.horses.iter().filter(|o|o.tempted() && (!opp || team==0 || o.input.team_id==0 || o.input.team_id!=team) &&
                    if infront {o.order<h.order} else {o.order>h.order}).count() as f32
            },
            "is_surrounded" if flag("RX_SURR")=>boolean(h.surround.iter().all(|b|*b)),
            // SkillTriggerRunningStyleTemptationCount (0x35e2c70): opponents
            // (other runner; no shared non-zero team) of the style in temptation.
            "running_style_temptation_opponent_count_nige"|"running_style_temptation_opponent_count_senko"|
            "running_style_temptation_opponent_count_sashi"|"running_style_temptation_opponent_count_oikomi" if flag("RX_TCNT")=>{
                let style=if n.ends_with("nige") {1} else if n.ends_with("senko") {2} else if n.ends_with("sashi") {3} else {4};
                let team=h.input.team_id;
                self.horses.iter().enumerate().filter(|(i,o)|*i!=hi && o.input.running_style==style && o.tempted() &&
                    (team==0 || o.input.team_id==0 || o.input.team_id!=team)).count() as f32
            },
            "temptation_count"=>h.temptation_count as f32,"blocked_front"=>boolean(h.front.is_some()),
            "is_move_lane"=>if h.move_time<1.0 {0.0} else {(h.move_dir!=0) as i32 as f32+1.0},"blocked_front_continuetime"=>h.front_time as i32 as f32,"blocked_side_continuetime"=>h.side_time as i32 as f32,
            "near_count"=>h.near_count as f32,"straight_front_type"=>h.front_type as f32,
            "activate_count_all"=>h.activate_count as f32,"activate_count_heal"=>h.heal_count as f32,
            "activate_count_start"=>h.activate_phase[0] as f32,
            "activate_count_middle"=>h.activate_phase[1] as f32,
            "activate_count_end_after"=>(h.activate_phase[2]+h.activate_phase[3]) as f32,
            "activate_count_laterhalf"|"activate_count_later_half"=>h.activate_half[1] as f32,
            "infront_near_lane_time"=>h.near_front_time as i32 as f32,"behind_near_lane_time"=>h.near_behind_time as i32 as f32,
            // SkillTriggerHorseBehindNearLaneTimeParamSet (0x35e0500): floor of the set's timer.
            n if n.starts_with("behind_near_lane_time_set") && flag("RX_NEARSET")=>{
                let k:usize=n.trim_start_matches("behind_near_lane_time_set").parse().ok()?;
                (*h.near_behind_set.get(k.checked_sub(1)?)?).floor()
            },
            "change_order_up_middle" if flag("RX_ORDERUP")=>h.order_up[1] as f32,
            "change_order_up_end_after" if flag("RX_ORDERUP")=>h.order_up[2] as f32,
            "change_order_up_corner" if flag("RX_ORDERUP")=>h.order_up[3] as f32,
            "change_order_up_lastspurt" if flag("RX_ORDERUP")=>h.order_up[5] as f32,
            "change_order_up_finalcorner_after" if flag("RX_ORDERUP")=>h.order_up[7] as f32,
            "overtake_target_time" if flag("RX_OTTIME")=>h.ot_target_time,
            // HorseRaceInfo.get_Lane (0x3439900).
            "lane_type" if flag("RX_LANETYPE")=>if h.lane<=0.2 {0.0} else if h.lane<=0.4 {1.0} else if h.lane<=0.6 {2.0} else {3.0},
            "is_activate_any_skill" if flag("RX_ANYSKILL")=>h.activate_count as f32,
            // HorseRaceInfo.CompeteFightCount (server-incremented; assumed +1 per CompeteFight start).
            "compete_fight_count" if flag("RX_FIGHTCNT") && opt("RX_COMPETE")=>h.fight_count as f32,
            "change_order_onetime"=>(h.order as i32-h.prev_order as i32) as f32,
            // JP-only tokens (JP client triggers are Null; semantics inferred, RX_JP_TOK=0 disables).
            // JP: another detail of this skill has activated earlier in the race.
            "is_activate_other_skill_detail" if self.jp() && flag("RX_JP_TOK")=>boolean(self.fired.get(&(hi,self.cur_skill)).is_some_and(|m|m & !(1u32<<self.cur_detail)!=0)),
            "is_last_straight" if self.jp() && flag("RX_JP_TOK")=>boolean(h.straight && c.final_corner().is_some_and(|s|h.distance>=s.end)),
            "furlong" if self.jp() && flag("RX_JP_TOK")=>{
                // JP replay boundaries use whole-metre rounding: 199.5 m enters furlong 1.
                // RX_JP_FURLONG_ROUND=0 restores the unrounded distance boundary.
                let d=h.distance+if self.jp() && flag("RX_JP_FURLONG_ROUND") {0.5} else {0.0};
                ((d/200.0) as i32+i32::from(opt("RX_JP_FURLONG1"))) as f32
            },
            "near_infront_count" if self.jp() && flag("RX_JP_TOK")=>{
                let p=self.p();let (dg,lg)=(p.f("Near.DistanceThreshold"),p.f("Near.LaneDistanceThreshold"));
                self.horses.iter().enumerate().filter(|(i,n)|*i!=hi && n.distance-h.distance>0.0 && n.distance-h.distance<=dg && (n.lane-h.lane).abs()<=lg).count() as f32
            },
            "phase_firsthalf"|"phase_laterhalf"|"phase_firstquarter" if self.jp() && flag("RX_JP_TOK")=>{
                let (lo,up)=c.bounds(h.phase as i32);let x=(h.distance-lo)/(up-lo);
                let inside=match n {"phase_firsthalf"=>x<0.5,"phase_laterhalf"=>x>=0.5,_=>x<0.25};
                if inside {h.phase as f32} else {-1.0}
            },
            "distance_diff_top_float" if self.jp() && flag("RX_JP_TOK")=>self.horses.iter().map(|h|h.distance).fold(0.0,f32::max)-h.distance,
            "bashin_diff_infront"=>{let n=self.horses.iter().find(|n|n.order+1==h.order)?;(n.distance-h.distance).max(0.0)/2.5},
            "bashin_diff_behind"=>{let n=self.horses.iter().find(|n|n.order==h.order+1)?;(h.distance-n.distance).max(0.0)/2.5},
            "is_exist_chara_id"=>boolean(self.horses.iter().any(|n|n.input.chara_id==rhs)),
            "running_style_count_same"=>self.horses.iter().filter(|n|n.input.running_style==h.input.running_style).count() as f32,
            "running_style_count_same_rate"=>{
                // SkillTriggerRunningStyleCountSameRate ctor (0x35e0e10)
                // rounds the RHS into a runner count, then compares integers.
                let threshold=(rhs as f32/100.0*self.horses.len() as f32+0.5) as i32;
                let count=self.horses.iter().filter(|n|n.input.running_style==h.input.running_style).count() as i32;
                return Some((count-threshold+rhs) as f32);
            },
            "running_style_count_nige_otherself"|"running_style_count_senko_otherself"|"running_style_count_sashi_otherself"|"running_style_count_oikomi_otherself"=>{
                let style=if n.contains("nige") {1} else if n.contains("senko") {2} else if n.contains("sashi") {3} else {4};
                self.horses.iter().enumerate().filter(|(i,n)|*i!=hi && n.input.running_style==style).count() as f32
            },
            // SkillTriggerRunningStyleEqualPopularityOne ctor (0x35e0ef0):
            // RaceInfo.InitHorseIndexByPopularity (0x35fdad0) stores
            // index[max(popularity-1,0)] = gate index (last write wins;
            // unset entries stay 0); compares RunningStyle, not Ex.
            "running_style_equal_popularity_one"=>{
                let one=self.horses.iter().rposition(|n|(n.input.popularity-1).max(0)==0).unwrap_or(0);
                boolean(self.horses[one].input.running_style==h.input.running_style)
            },
            // SkillTriggerSameSkillHorseCount (0x35e3f50): runners, self
            // included, whose SkillManager.GetSkill(owner skill id) is set.
            // The evaluating horse's skills are detached during the pass.
            "same_skill_horse_count"=>self.horses.iter().enumerate().filter(|(i,n)|*i==hi || n.skills.iter().any(|k|k.id==self.cur_skill)).count() as f32,
            _=>return None,
        })
    }
    fn skills_pass(&mut self,dt:f32,priority:i64) {
        for hi in 0..self.horses.len() {
            if opt("RX_GOALSKILL") && self.horses[hi].finished {continue;}
            if priority==0 {self.horses[hi].mods.update_timed(dt);}
            let mut skills=std::mem::take(&mut self.horses[hi].skills);
            // Exact Global expiry evidence: 174ef16df8e466ef h7 at 73.52652 s,
            // and 78/81 late evok+dbig cases follow a type-22 skill end.
            // Fold the current-speed add into self speed, then decelerate normally.
            // Isolated 673-race corpus: 447 -> 582 perfect, 4 later / 0 earlier,
            // 136 exact-frame gains / 0 losses. RX_GLOBAL_CS22FOLD=0 reverts.
            let jp_fold=if self.jp() {flag("RX_JP_CS22FOLD")} else {flag("RX_GLOBAL_CS22FOLD")};
            // SkillManagerSimulate.UpdateRandomActivateSkillIdList (0x35d4760): clear, then
            // pass 1 (modifier 0x19, ability 37) and pass 2 (0x18, ability 36) each pick
            // min(count, candidates) skills with GetRandom(0, n) without replacement.
            // IsRandomActivateTargetSkill (0x35d45a0): rarity in the pass list,
            // FloatAbilityTime1 != -1, cooldown <= 0, IsGeneralSkill == 1.
            // UpdateSecondGroup (0x35d4150) draws the reservations after the priority-0 skills
            // (same tick as the granting skill); RX_RANDEND=0 restores the next-tick
            // first-group draw (28 of 707 corpus picks wrong).
            if priority==1 && !flag("RX_RANDEND") {self.reserve_random(hi,&skills);}
            for skill in &mut skills {
                if ival(&skill.row,"priority")!=priority {continue;}
                // SkillBase.Update (0x35d1f30): while any detail is active, only update
                // active details (expiry sets the *skill* cooldown) and skip activation;
                // otherwise tick the skill cooldown and activate the first passing detail.
                let skill_cd=opt("RX_SKCD");
                if skill_cd && skill.details.iter().any(|d|d.active) {
                    for d in &mut skill.details {
                        if d.active && d.left>=0.0 {
                            if !self.jp() && flag("RX_GLOBAL_ADDITIONAL") {
                                // SkillBase.Update removes each detail from the previous-activation
                                // list before updating it. Activations since this detail's last
                                // update therefore include later skills on the activation tick,
                                // but exclude the owner and skills preceding its initial activation.
                                let now=self.horses[hi].activate_count;
                                let pending=(now-d.additional_seen).max(0);
                                d.additional_seen=now;
                                for a in 1..=3 {
                                    if ival(&skill.row,&format!("additional_activate_type_{}_{}",d.number,a))!=3 {continue;}
                                    let cap=global_additional_cap(self.p(),3);
                                    let count=take_additional_count(pending,cap,&mut d.additional_used[a-1]);
                                    for _ in 0..count {
                                        self.ability_activate(hi,skill.id,skill.level,&skill.row,d,a,true);
                                    }
                                }
                            }
                            d.left-=dt;
                            if d.left<=0.0 {
                                d.active=false;
                                stop_effect(&mut self.horses,d.uid,jp_fold);
                                skill.cooldown=ival(&skill.row,&format!("float_cooldown_time_{}",d.number)) as f32*0.0001*
                                    (self.course.distance/self.p().i("Skill.CoolDownTimeDivideDistance") as f32);
                            }
                        }
                    }
                    continue;
                }
                if skill_cd && skill.cooldown>0.0 {skill.cooldown=(skill.cooldown-dt).max(0.0);if skill.cooldown>0.0 {continue;}}
                for d in &mut skill.details {
                    if d.active && d.left>=0.0 {
                        d.left-=dt;
                        if d.left<=0.0 {
                            d.active=false;
                            stop_effect(&mut self.horses,d.uid,jp_fold);
                            d.cooldown=ival(&skill.row,&format!("float_cooldown_time_{}",d.number)) as f32*0.0001*
                                (self.course.distance/self.p().i("Skill.CoolDownTimeDivideDistance") as f32);
                        }
                    } else if d.cooldown>0.0 {d.cooldown=(d.cooldown-dt).max(0.0);}
                    let reserved=d.number==1 && self.horses[hi].reserved.contains(&skill.id);
                    // IsReservedRandomActivate bypasses the ordinary activation
                    // lottery, including a failed pre-race skill lottery.
                    if (!skill.enabled && !(reserved && opt("RX_RESLOT"))) || d.active || d.cooldown>0.0 || self.horses[hi].finished {continue;}
                    self.cur_skill=skill.id;self.cur_detail=d.number;
                    let mut unsupported=std::mem::take(&mut self.unsupported);
                    if !d.pre_passed {d.pre_passed=triggers::evaluate(&mut d.pre,self.horses[hi].distance,&|n,r|self.query(hi,n,r),&mut unsupported);}
                    // SkillDetail.IsReservedRandomActivate (0x35cfc80): detail 0 of a reserved skill.
                    let activate=reserved || d.pre_passed && triggers::evaluate(&mut d.condition,self.horses[hi].distance,&|n,r|self.query(hi,n,r),&mut unsupported);
                    self.unsupported=unsupported;
                    if activate {
                        let raw=ival(&skill.row,&format!("float_ability_time_{}",d.number));
                        d.left=if raw==-1 {-1.0} else {raw as f32*0.0001*(self.course.distance/self.p().i("Skill.AbilityTimeDivideDistance") as f32)};
                        // Probe: RX_SKEND=k shifts every timed skill end by k ticks.
                        if raw!=-1 && let Some(k)=std::env::var("RX_SKEND").ok().and_then(|v|v.parse::<f32>().ok()) {d.left+=k*dt;}
                        let usage=ival(&skill.row,&format!("ability_time_usage_{}",d.number));
                        // Global SkillAbilityTimeMultiplyRemainHp.GetMultiply (0x35ca8a0):
                        // IHorseRaceInfo slot 16 is GetHp (absolute HP), sampled by
                        // SkillDetail.Activate before installing the abilities.
                        // The first strict threshold wins; exhaustion returns 1.
                        if !self.jp() && usage==3 && flag("RX_GLOBAL_TIME_HP") {
                            let mult=global_hp_duration_multiplier(self.p(),self.horses[hi].hp);
                            if raw!=-1 {d.left*=mult;}
                        } else if usage>1 {self.unsupported.insert(format!("skill_time_usage:{usage}"));}
                        d.active=true;
                        *self.fired.entry((hi,skill.id)).or_default()|=1<<d.number;
                        let h=&mut self.horses[hi];h.activate_count+=1;
                        h.activate_phase[h.phase.min(3)]+=1;
                        h.activate_half[usize::from(h.distance>=self.course.distance*0.5)]+=1;
                        d.additional_seen=h.activate_count;
                        let mut mask=0i64;
                        for a in 1..=3 {
                            let targets=self.ability(hi,skill.id,skill.level,&skill.row,d,a);
                            // SkillDetail.CalcTargetFlags (0x35cf050) uses FirstOrDefault
                            // ability, then its AbilityTargets. Later effects still apply.
                            // JP replays also record only the first ability's targets (RX_JP_SKILLPARAM).
                            if (self.jp() && !flag("RX_JP_SKILLPARAM")) || (!self.jp() && !opt("RX_GLOBAL_EVENT_FIRST")) || a==1 {
                                // The replay mask is int32: runners past gate 32 cannot be flagged.
                                for t in targets {if t<32 {mask|=1<<t;}}
                            }
                        }
                        // Global replay convention: skills activated on the pre-race tick (t = 0) record
                        // duration -1 and an empty target mask (5411/5411 corpus events). JP records the
                        // real duration and mask, encoded as int(f32(duration * 10000)) (236/236 distinct
                        // JP base-time/distance pairs; the f64 product truncates one lower).
                        let jp_enc=self.jp() && flag("RX_JP_SKILLPARAM");
                        let t0=self.time==0.0 && !jp_enc;
                        // JP t = 0: passives (-1) and zero-duration skills record an empty mask.
                        if jp_enc && self.time==0.0 && raw<=0 {mask=0;}
                        let enc=if jp_enc {(d.left*10000.0) as i32} else {(d.left as f64*10000.0) as i32};
                        self.horses[hi].skill_time=self.time;
                        self.events.push(json!({"t":self.time,"type":3,"name":"Skill","params":[hi as i32,skill.id,if raw==-1 || t0 {-1} else {enc},d.number as i32-1,if t0 {0} else {mask as i32},0],"horse":hi,"extra":""}));
                        if skill_cd {break;}
                    }
                }
            }
            if priority==0 && flag("RX_RANDEND") {self.reserve_random(hi,&skills);}
            self.horses[hi].skills=skills;
        }
    }
    /// SkillManagerSimulate.UpdateRandomActivateSkillIdList (0x35d4760): clear, then
    /// pass 1 (modifier 0x19, ability 37) and pass 2 (0x18, ability 36) each pick
    /// min(count, candidates) skills with GetRandom(0, n) without replacement.
    /// IsRandomActivateTargetSkill (0x35d45a0): rarity in the pass list,
    /// FloatAbilityTime1 != -1, cooldown <= 0, IsGeneralSkill == 1, not active.
    fn reserve_random(&mut self,hi:usize,skills:&[Skill]) {
        if !flag("RX_RANDACT") {return;}
        self.horses[hi].reserved.clear();
        for (index,rarity) in [(25usize,2i64),(24,1)] {
            let count=self.horses[hi].mods.consume(index,0.0) as i32;
            if count<=0 {continue;}
            let mut cand=skills.iter().filter(|k|ival(&k.row,"rarity")==rarity && ival(&k.row,"float_ability_time_1")!=-1 &&
                ival(&k.row,"is_general_skill")==1 && (if opt("RX_SKCD") {k.cooldown<=0.0 && !k.details.iter().any(|d|d.active)} else {k.details.first().is_some_and(|d|d.cooldown<=0.0 && !d.active)}) &&
                !self.horses[hi].reserved.contains(&k.id)).map(|k|k.id).collect::<Vec<_>>();
            if std::env::var("RX_RANDDBG").is_ok() {
                let st=self.random.peek_doubles(4);
                eprintln!("RANDACT {} {} {} {} {:?} | {}",self.input.replay_sha,self.time,hi,json!(st),cand,json!(skills.iter().map(|k|json!([k.id,ival(&k.row,"rarity"),ival(&k.row,"float_ability_time_1"),ival(&k.row,"is_general_skill"),k.cooldown,k.enabled,k.details.iter().any(|d|d.active),k.details.iter().map(|d|d.cooldown).collect::<Vec<_>>()])).collect::<Vec<_>>()));
            }
            for _ in 0..count.min(cand.len() as i32) {
                let i=self.random.int_range(0,cand.len() as i32,&||format!("h{hi}:random_activate")) as usize;
                self.horses[hi].reserved.push(cand.remove(i));
            }
        }
    }
    /// Returns the runners this ability targeted (for the event's target bitmask).
    fn ability(&mut self,hi:usize,id:i32,level:i32,row:&HashMap<String,Value>,detail:&Detail,a:usize)->Vec<usize> {
        self.ability_activate(hi,id,level,row,detail,a,false)
    }
    fn ability_activate(&mut self,hi:usize,id:i32,level:i32,row:&HashMap<String,Value>,detail:&Detail,a:usize,is_additional:bool)->Vec<usize> {
        let suffix=format!("{}_{}",detail.number,a);let kind=ival(row,&format!("ability_type_{suffix}"));if kind==0 {return vec![];}
        let target=ival(row,&format!("target_type_{suffix}"));let tv=ival(row,&format!("target_value_{suffix}"));
        let mut targets=match target {
            1=>vec![hi],2=>(0..self.horses.len()).collect(),3=>(0..self.horses.len()).filter(|i|*i!=hi).collect(),
            // SkillTargetVisible: visible prefix sorted by world-position
            // distance (selector 0x35d64d0), capped by target_value.
            4 if opt("RX_T4")=>{
                let pos=self.horses[hi].position;
                let mut v=self.horses[hi].visible.clone();
                let distance=|i:usize| {let n=self.horses[i].position;
                    let [dx,dy,dz]=std::array::from_fn::<_,3,_>(|k|pos[k]-n[k]);
                    ((dy*dy+dx*dx+dz*dz) as f64).sqrt() as f32};
                v.sort_by(|a,b|distance(*a).total_cmp(&distance(*b)));
                v.truncate(tv.max(0) as usize);v
            },
            5=>{
                let count=tv.min(self.horses.len() as i64-1);let mut selected=vec![];
                for _ in 0..count {
                    let start=self.random.int_max(self.horses.len() as i32,&||format!("target{hi}:{}:{}",detail.number,a)) as usize;
                    for offset in 0..self.horses.len() {
                        let i=(start+offset)%self.horses.len();
                        if i!=hi && !selected.contains(&i) {selected.push(i);break;}
                    }
                } selected
            },
            6|7|8=>self.horses.iter().enumerate().filter(|(_,h)|match target {6=>h.order as i64+1==tv,7=>(h.order as i64+1)<tv,_=>tv<h.order as i64+1}).map(|(i,_)|i).collect(),
            // SkillTargetSelfInfront/SelfBehind (0x35d70b0/0x35d72e0): the next target_value
            // runners by CurOrder ahead of / behind the owner, stopping at the field's end.
            9|10 if flag("RX_T910")=>{
                let o=self.horses[hi].order as i64;let n=self.horses.len() as i64;
                (1..=tv).map(|k|if target==9 {o-k} else {o+k}).take_while(|x|*x>=0 && *x<n)
                    .filter_map(|x|self.horses.iter().position(|h|h.order as i64==x)).collect()
            },
            // SkillTargetSelf{Infront,Behind}Temptation (0x35d78e0/0x35d7e10): GetTemptationHorseList
            // filtered to runners ahead of / behind the owner, then target_value draws without
            // replacement (RaceRandom.GetValue(count), RemoveAt).
            19|20 if flag("RX_T1920")=>{
                let o=self.horses[hi].order;
                let mut pool:Vec<usize>=(0..self.horses.len()).filter(|i|self.horses[*i].tempted()
                    && if target==19 {self.horses[*i].order<o} else {self.horses[*i].order>o}).collect();
                let mut v=vec![];
                for _ in 0..(tv.max(0) as usize).min(pool.len()) {
                    let k=self.random.int_max(pool.len() as i32,&||format!("target{hi}:{}:{}",detail.number,a)) as usize;
                    v.push(pool.remove(k));
                } v
            },
            13=>{let mut v=vec![hi];if let Some(i)=self.horses[hi].front {v.push(i);}v},
            14=>[self.horses[hi].inside,self.horses[hi].outside].into_iter().flatten().collect(),
            17=>self.horses.iter().enumerate().filter(|(_,h)|h.input.running_style as i64==tv).map(|(i,_)|i).collect(),
            // SkillTargetRunningStyleOtherSelf (0x35d9c70): running-style list minus the owner.
            18 if flag("RX_T18")=>self.horses.iter().enumerate().filter(|(i,h)|*i!=hi && h.input.running_style as i64==tv).map(|(i,_)|i).collect(),
            // RunningStyleTemptationOtherSelf (0x35d7550): style list,
            // filtered by IsTemptation. The owner's skill requires !IsTemptation.
            21 if opt("RX_T21")=>self.horses.iter().enumerate().filter(|(i,h)|*i!=hi && h.input.running_style as i64==tv && h.tempted()).map(|(i,_)|i).collect(),
            22=>self.horses.iter().enumerate().filter(|(_,h)|h.input.chara_id as i64==tv).map(|(i,_)|i).collect(),
            _=>{self.unsupported.insert(format!("skill_target:{target}"));vec![]},
        };
        let mut value=ival(row,&format!("float_ability_value_{suffix}")) as f32*0.0001;
        if value<0.0 {
            let team=self.horses[hi].input.team_id;
            targets.retain(|i|self.horses[*i].mods.apply(18,0.0)==0.0 && (*i==hi || team==0 || self.horses[*i].input.team_id==0 || self.horses[*i].input.team_id!=team));
        }
        if target==4 && std::env::var_os("RX_T4DBG").is_some() {
            eprintln!("{}",json!({"replay_sha":self.input.replay_sha,"t":self.time,"horse":hi,"skill":id,"ability":a,"targets":targets}));
        }
        let usage=ival(row,&format!("ability_value_usage_{suffix}"));
        if usage>1 && !((3..=7).contains(&usage) && flag("RX_USAGE")) && !(matches!(usage,8|9) && flag("RX_USAGE8")) && !(usage==10 && flag("RX_USAGE10")) && !(usage==12 && flag("RX_USAGE12")) && !(usage==13 && flag("RX_USAGE13")) && !(matches!(usage,22|23) && flag("RX_USAGE22")) && !(matches!(usage,27|31|32|37|40) && self.jp() && flag("RX_JP_SCEN")) {self.unsupported.insert(format!("skill_value_usage:{usage}"));}
        let coef=self.master.rows("skill_level_value").iter().find(|r|ival(r,"ability_type")==kind && ival(r,"level")==level as i64)
            .map_or(1.0,|r|ival(r,"float_ability_value_coef") as f32*0.0001);
        match ival(row,&format!("ability_value_level_usage_{suffix}")) {1=>value=coef*value,3=>value=(1.0/coef)*value,_=>()};
        // Global MultiplySingleModeWinCount.GetMultiply (0x35cc390):
        // first strict count threshold, exhaustion returns 1. Saved HorseData
        // count is used directly, including zero outside career races.
        if usage==10 && flag("RX_USAGE10") {
            let wins=self.horses[hi].input.single_mode_win_count;
            let mult=self.p().arr("Skill.RaceWinCountCoefAscArray").iter()
                .find(|r|wins<r["WinCountThreshold"].as_i64().unwrap() as i32)
                .map_or(1.0,|r|f32_of(&r["Multiply"]));
            value*=mult;
        }
        // SkillAbilityValueMultiplyFanCount (usage 12): first strict FanCountThreshold
        // in Skill.FanCountCoefAscArray; exhaustion or a missing table returns 1.
        if usage==12 && flag("RX_USAGE12") {
            let fans=self.horses[hi].input.fan_count;
            let mult=self.p().arr("Skill.FanCountCoefAscArray").iter()
                .find(|r|fans<r["FanCountThreshold"].as_i64().unwrap())
                .map_or(1.0,|r|f32_of(&r["Multiply"]));
            value*=mult;
        }
        // SkillAbilityValueMultiplyMaximumRawStatus (usage 13, ctor 0x35cc7c0): Max of
        // IRaceParameter.Raw{Speed,Guts,Pow,Stamina,Wiz}; first strict BaseStatusThreshold
        // in Skill.MaximumRawStatusCoefAscArray, exhaustion 1.
        if usage==13 && flag("RX_USAGE13") {
            let h=&self.horses[hi].input;
            let max=[h.speed,h.guts,h.pow,h.stamina,h.wiz].into_iter().max().unwrap() as f32;
            let mult=self.p().arr("Skill.MaximumRawStatusCoefAscArray").iter()
                .find(|r|max<f32_of(&r["BaseStatusThreshold"]))
                .map_or(1.0,|r|f32_of(&r["Multiply"]));
            value*=mult;
        }
        // SkillAbilityValueMultiplyTeamTotalStatus{Speed..Wiz} (usage 3-7, ctor 0x35cbd60):
        // sum IRaceParameter.Base<stat> over the team (team 0 = self only), then the
        // first TeamTotalStatusCoefAscArray row with sum < StatusThreshold; else 1.
        if (3..=7).contains(&usage) && flag("RX_USAGE") {
            let k=(usage-3) as usize;let team=self.horses[hi].input.team_id;
            let sum=if team==0 {self.horses[hi].base[k]} else {
                self.horses.iter().filter(|h|h.input.team_id==team).fold(0.0f32,|a,h|a+h.base[k])};
            let mult=self.p().arr("Skill.TeamTotalStatusCoefAscArray").iter()
                .find(|r|sum<f32_of(&r["StatusThreshold"])).map_or(1.0,|r|f32_of(&r["Multiply"]));
            value*=mult;
        }
        // SkillAbilityValueMultiplyRandom (usage 8/9, 0x35cbaa0): GetRandom(sum of Per)
        // then subtract each Per until the remainder is < 1 (Skill.AbiiltyValueUsageRandom{1,2}Array).
        // Nothing Ventured / Risky Business: -100% max HP x {0, 0.02, 0.04}.
        if matches!(usage,8|9) && flag("RX_USAGE8") {
            let arr=self.assets.params().arr(if usage==8 {"Skill.AbiiltyValueUsageRandom1Array"} else {"Skill.AbiiltyValueUsageRandom2Array"}).clone();
            let total=arr.iter().map(|r|r["Per"].as_i64().unwrap() as i32).sum::<i32>();
            let mut r=self.random.int_max(total,&||format!("h{hi}:value_random"));let mut mult=1.0;
            for row in &arr {r-=row["Per"].as_i64().unwrap() as i32;if r<1 {mult=f32_of(&row["AbilityValueCoef"]);break;}}
            value*=mult;
        }
        // SkillAbilityValueMultiplySpeed (usage 22/23, 0x35ccfd0): first row of
        // Skill.SpeedAbilityValueCoefAscArray{1,2} with IHorseRaceInfo.Speed < SpeedThreshold.
        if matches!(usage,22|23) && flag("RX_USAGE22") {
            let sp=self.horses[hi].stat(0);
            let mult=self.p().arr(if usage==22 {"Skill.SpeedAbilityValueCoefAscArray1"} else {"Skill.SpeedAbilityValueCoefAscArray2"}).iter()
                .find(|r|sp<r["SpeedThreshold"].as_i64().unwrap() as f32).map_or(1.0,|r|f32_of(&r["Multiply"]));
            value*=mult;
        }
        // JP scenario value usages: the runner's scenario_data value (type = scenario * 1000 + 1)
        // against that scenario's LevelThreshold table, first strict row, like the Global usages.
        // Usage <-> scenario matched by which scenario data every owner carries.
        let scen=match usage {27=>Some(("Skill.CookCookingPtCoefArray",8001)),31=>Some(("Skill.PioneerTotalPointCoefArray",11001)),
            32=>Some(("Skill.OnsenRyokanRankCoefArray",12001)),37=>Some(("Skill.BreedersTeamRankCoefArray",13001)),
            40=>Some(("Skill.RamenTotalPointCoefArray",14001)),_=>None};
        if let Some((table,kind))=scen && self.jp() && flag("RX_JP_SCEN") {
            let v=self.horses[hi].input.scenario_data_array.iter().find(|d|d.kind==kind).map_or(0,|d|d.value);
            let mult=self.p().arr(table).iter().find(|r|v<r["LevelThreshold"].as_i64().unwrap()).map_or(1.0,|r|f32_of(&r["Multiply"]));
            value*=mult;
        }
        // JP WizLimitBreakBuff (JP-only RaceParamDefine block): speed (27) and current-speed (22)
        // values of rarity 2-6 skills (rarity 6 excluding succession) scale by
        // 1 + PhaseCoef(phase, style) * WizCoef(wiz - 1200) * CourseDistanceCoef.
        // RX_JP_WLB: 10 = ceil(raw wiz * mood) + passive skill wiz (default). Passives: best for
        // runners with wiz passives in every mood group. Ceil: 246 runners later, 40 earlier vs
        // unrounded (1443 * 1.04 = 1500.7 must reach the 301 row). Probes: 9 round, 6 floor,
        // 5 unrounded, 7 (raw + passives) * mood, 2 raw * mood, 1 raw, 3 raw + passives,
        // 4 full stat, 0 off.
        let wlb=if self.jp() {std::env::var("RX_JP_WLB").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(10)} else {0};
        if wlb!=0 && value>0.0 {
            let p=self.p();let w=Tree(p.get("WizLimitBreakBuff"));
            let rarity=ival(row,"rarity");
            let rule=w.arr("SkillSelectionRuleArray").iter().find(|r|r["Rarity"].as_i64()==Some(rarity));
            let eligible=w.arr("TargetAbilityTypeArray").iter().any(|t|t.as_i64()==Some(kind))
                && rule.is_some_and(|r|r["SelectionRule"]["IsExcludeSuccessionSkill"].as_i64()!=Some(1) || ival(row,"unique_skill_id_1")==0);
            let h=&self.horses[hi];
            let mood=self.rate("race_motivation_rate",h.input.motivation,"motivation_rate").unwrap_or(1.0);
            let wiz=match wlb {2=>h.input.wiz as f32*mood, 3=>h.mods.apply(4,h.input.wiz as f32), 4=>h.stat(4), 5=>h.mods.apply(4,h.input.wiz as f32*mood), 6=>h.mods.apply(4,(h.input.wiz as f32*mood).floor()),
                7=>h.mods.apply(4,h.input.wiz as f32)*mood, 8=>h.mods.apply(4,h.input.wiz as f32*mood).floor(), 9=>h.mods.apply(4,(h.input.wiz as f32*mood).round()), 10=>h.mods.apply(4,(h.input.wiz as f32*mood).ceil()), _=>h.input.wiz as f32};
            let over=wiz-1200.0;
            if eligible && over>=1.0 {
                let wc=w.arr("WizCoefArray").iter().filter(|r|f32_of(&r["WizThreshold"])<=over).last().map_or(0.0,|r|f32_of(&r["Multiply"]));
                let (ex,style)=(h.ex() as i64,h.input.running_style as i64);
                let pc=w.arr("PhaseParamArray").iter().find(|r|r["Phase"].as_i64()==Some(h.phase.min(3) as i64))
                    .and_then(|r|r["RunningStyleParamArray"].as_array().unwrap().iter().find(|x|x["RunningStyleEx"].as_i64()==Some(ex) && x["RunningStyle"].as_i64()==Some(style)))
                    .map_or(0.0,|x|f32_of(&x["Coef"]));
                let d=self.course.distance;
                let dc=w.arr("CourseDistanceCoefArray").iter().find(|r|d<=f32_of(&r["CourseDistanceThreshold"])).map_or(1.0,|r|f32_of(&r["Multiply"]));
                value*=1.0+pc*wc*dc;
            }
        }
        if ival(row,&format!("additional_activate_type_{suffix}"))!=0 {
            if !is_additional {return targets;}
        }
        // SkillDetail.Activate (0x35cf2d0): owner's heal count +1 when a type-9 value is positive.
        if kind==9 && value>0.0 && flag("RX_HEALCNT") {self.horses[hi].heal_count+=1;}
        for &i in &targets {
            let h=&mut self.horses[i];let uid=detail.uid;
            let effect=match kind {
                1..=5=>Some((kind as usize-1,Operation::Add,false,value)),
                6=>Some((20,Operation::Set,false,1.0)),7=>Some((13,Operation::Set,false,value)),8=>Some((19,Operation::Add,false,value)),
                9=>{if !flag("RX_HEALCNT") {h.heal_count+=1;}Some((12,Operation::Add,true,h.max_hp*value))},
                10=>Some((15,Operation::Set,true,value.max(0.0))),11=>Some((16,Operation::Set,false,1.0)),12=>Some((17,Operation::Set,false,1.0)),
                13=>Some((14,Operation::Set,true,value)),14=>Some((22,Operation::Set,true,value)),
                21=>Some((5,Operation::Add,false,value)),22=>{
                    // CurrentSpeed is a lasting add on top of self speed, not also a one-time self-speed
                    // jump (647 races: 64 later / 0 earlier). RX_CS22=0 restores both; =1 keeps only the jump.
                    let m=std::env::var("RX_CS22").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(2);
                    if m!=2 {h.mods.add(23,value,Operation::Add,uid,true);}
                    if m==1 {None} else {Some((23,Operation::Add,false,value))}},
                27=>Some((6,Operation::Add,false,value)),28=>{if value>0.0 {h.mods.add(21,1.0,Operation::Set,uid,false);}Some((7,Operation::Add,false,value))},
                29=>Some((8,Operation::Add,false,value)),30=>Some((9,Operation::Add,false,value)),31=>Some((10,Operation::Add,false,value)),
                32=>{for k in 0..5 {h.mods.add(k,value,Operation::Add,uid,false);}None},
                35=>Some((11,Operation::Add,false,value)),36=>Some((24,Operation::Set,true,value)),37=>Some((25,Operation::Set,true,value)),38=>Some((18,Operation::Set,false,1.0)),
                _=>None,
            };
            if let Some((index,op,once,value))=effect {
                if is_additional && self.input.region.as_deref()!=Some("jp") && flag("RX_GLOBAL_ADDITIONAL_TIME") {
                    h.mods.add_timed(index,value,op,uid,once,detail.left);
                } else {h.mods.add(index,value,op,uid,once);}
            }
        }
        targets
    }
    fn ground_multi(&self)->f32 {
        let p=self.p();let a=p.arr(if self.course.ground==1 {"_groundModifierParamTurf"} else {"_groundModifierParamDirt"});
        f32_of(&a[self.input.ground_condition as usize-1]["multiHpSub"])
    }
    fn hp_rate(&self,h:&Horse,speed:f32,base:f32,rate:f32)->f32 {
        let p=self.p();
        if opt("RX_D2") || opt("RX_HPRATE_D") {
            let x=math::pow((speed as f64-base as f64+p.f("Hp.SpeedGapParam1") as f64) as f32,2.0) as f64;
            let v=(x/p.f("Hp.SpeedGapParam1Pow") as f64*p.f("Hp.HpDecBase") as f64*rate as f64*self.ground_multi() as f64) as f32;
            if h.phase<2 {return v;}
            let s=(h.stat(3)*p.f("Hp.HpGutsCoefSqrt")).sqrt() as f64;
            return (v as f64*(p.f("Hp.HpGutsCoef") as f64/s+1.0)) as f32;
        }
        // Global: gap^2/SpeedGapParam1Pow stays float; the rest of the drain
        // (*HpDecBase*rate*ground) is a double expression rounded once.
        // 1073 races: +6 (all hp), none lost or earlier. RX_HP_DEC_LOCAL=0 reverts.
        let hpv=std::env::var("RX_HPV").ok().and_then(|x|x.parse::<i32>().ok())
            .unwrap_or(if self.input.region.as_deref()!=Some("jp") && flag("RX_HP_DEC_LOCAL") {3} else {0});
        let mut v=if hpv>0 {
            let x=math::pow(speed-base+p.f("Hp.SpeedGapParam1"),2.0);let (pp,dd,g)=(p.f("Hp.SpeedGapParam1Pow"),p.f("Hp.HpDecBase"),self.ground_multi());
            let (xd,pd,ddd,rd,gd)=(x as f64,pp as f64,dd as f64,rate as f64,g as f64);
            match hpv {
                1=>((x/pp*dd) as f64*rd*gd) as f32,
                2=>((xd/pd*ddd*rd) as f32)*g,
                3=>((x/pp) as f64*ddd*rd*gd) as f32,
                4=>(xd*ddd*rd*gd/pd) as f32,
                5=>x/pp*dd*(rate*g),
                6=>x/pp*(dd*rate)*g,
                7=>x*dd/pp*rate*g,
                8=>((xd/pd*ddd) as f32)*rate*g,
                9=>((x/pp*dd*rate) as f64*gd) as f32,
                10=>(xd*(ddd/pd)*rd*gd) as f32,
                11=>x*(dd/pp)*rate*g,
                12=>((xd/pd) as f32)*dd*rate*g,
                _=>(((x as f64/pd) as f32*dd) as f64*rd*gd) as f32,
            }
        } else if opt("RX_HPV2") || opt("RX_HPV2P") && h.phase>=2 || opt("RX_HPV2Q") && h.phase<2 {let x=math::pow(speed-base+p.f("Hp.SpeedGapParam1"),2.0);
            (x as f64/p.f("Hp.SpeedGapParam1Pow") as f64*p.f("Hp.HpDecBase") as f64*rate as f64*self.ground_multi() as f64) as f32}
            else {math::pow(speed-base+p.f("Hp.SpeedGapParam1"),2.0)/p.f("Hp.SpeedGapParam1Pow")*
            p.f("Hp.HpDecBase")*rate*self.ground_multi()};
        if h.phase>=2 {
            // Global: the guts factor is a float local evaluated in double (coef/sqrt+1 rounded
            // once; sqrt keeps its float argument and result), then float * drain.
            // 657 races: +4, none lost or earlier. RX_HP_GUTS_LOCAL=0 reverts.
            if self.input.region.as_deref()!=Some("jp") && flag("RX_HP_GUTS_LOCAL") {v*=(p.f("Hp.HpGutsCoef") as f64/(h.stat(3)*p.f("Hp.HpGutsCoefSqrt")).sqrt() as f64+1.0) as f32;}
            else if opt("RX_HPG3") {v*=(p.f("Hp.HpGutsCoef") as f64/((h.stat(3)*p.f("Hp.HpGutsCoefSqrt")) as f64).sqrt()+1.0) as f32;}
            else if opt("RX_HPGUTS_D") {v=(v as f64*(p.f("Hp.HpGutsCoef") as f64/(h.stat(3)*p.f("Hp.HpGutsCoefSqrt")).sqrt() as f64+1.0)) as f32;}
            else {v*=p.f("Hp.HpGutsCoef")/(h.stat(3)*p.f("Hp.HpGutsCoefSqrt")).sqrt()+1.0;}
        }
        v
    }
    fn spurt(&mut self,hi:usize) {
        let h=&self.horses[hi];let p=self.p();let base=self.race_base();
        let normal=h.section_base.iter().enumerate().find(|(i,_)|self.course.phase(*i as f32*(self.course.distance/24.0))==h.phase).map_or(base,|(_,v)|*v);
        // CalcBaseTargetSpeedAndStatusSpeed (0x342a390): base+cached add crosses
        // a float argument store; pow/sqrt return floats, then the helper's
        // expression rounds once on return. Global replay evidence: 016e4ad9 h2
        // and 19e82683 h4 had opposite one-ULP speed errors; 264 -> 436 perfect,
        // 19 later / 0 earlier (docs/RACE_ULP_PARITY_2026-10-08.md).
        let max=if !self.jp() && flag("RX_ULP_SPURT_ARGS") {
            let guts=math::pow(h.stat(3)*p.f("LastSpurtTargetSpeedGutsCoef1"),p.f("LastSpurtTargetSpeedGutsPow"));
            let speed=(h.stat(0)*p.f("LastSpurtTargetSpeedCoefSqrt")).sqrt();
            let cached_add=base*p.f("lastSpurtBaseTargetSpeedAddCoef");
            let base_arg=cached_add+normal;
            (guts as f64*p.f("LastSpurtTargetSpeedGutsCoef2") as f64+
                speed as f64*h.dist_speed as f64*p.f("addSpeedParamCoef") as f64+
                base_arg as f64*p.f("baseTargetSpeedCoef") as f64) as f32
        } else {math::pow(h.stat(3)*p.f("LastSpurtTargetSpeedGutsCoef1"),p.f("LastSpurtTargetSpeedGutsPow"))*p.f("LastSpurtTargetSpeedGutsCoef2")+
            (h.stat(0)*p.f("LastSpurtTargetSpeedCoefSqrt")).sqrt()*h.dist_speed*p.f("addSpeedParamCoef")+
            (base*p.f("lastSpurtBaseTargetSpeedAddCoef")+normal)*p.f("baseTargetSpeedCoef")};
        let remain=(self.course.distance-h.distance-p.i("LastSpurtDistanceGoalBuffer") as f32).max(0.0);
        let need=|speed:f32|remain/speed*self.hp_rate(h,speed,base,p.f("Hp.HpDecRateBaseNormal"));
        let (result,start,speed)=if h.hp<need(h.min_speed) {(4,-1.0,base)}
            else if need(max)<=h.hp {(1,h.distance,max)}
            else {
                let wide=!self.jp() && flag("RX_SPURT_D");
                let candidate=|speed:f32|->Option<(f32,f32)> {
                    let spurt_rate=self.hp_rate(h,speed,base,p.f("Hp.HpDecRateBaseNormal"));
                    let normal_rate=self.hp_rate(h,normal,base,p.f("Hp.HpDecRateBaseNormal"));
                    let goal=self.course.distance-p.i("LastSpurtDistanceGoalBuffer") as f32;
                    let mut d=remain;
                    while d>0.0 {
                        let spurt_time=d/speed;let normal_time=(remain-d)/normal;
                        if std::env::var("RX_HDBG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("CAND sp={speed} st={} need={} hp={} sr={spurt_rate} nr={normal_rate}",goal-d,spurt_rate*spurt_time+normal_time*normal_rate,h.hp);}
                        // Global: the HP feasibility sum is evaluated in double from the distances
                        // (two exact-zero f32 margins, 1e4397d3 and 43305753, split by it; 646 -> 647, 0 lost).
                        let fits=if wide {d as f64/speed as f64*spurt_rate as f64+(remain as f64-d as f64)/normal as f64*normal_rate as f64<=h.hp as f64}
                            else {spurt_rate*spurt_time+normal_time*normal_rate<=h.hp};
                        if fits && goal-d<self.course.distance-p.f("lastSpurtDistanceMaxFromGoal") {
                            let normal_time=if opt("RX_SPURT_CUR") {(remain-d)/h.speed} else {normal_time};
                            return Some((goal-d,normal_time+spurt_time));
                        } d-=30.0;
                    } None
                };
                let floor=normal.min(max);let mut speed=max;let mut first=None;
                for _ in 0..=100 {
                    if candidate(speed).is_some() {first=Some(speed);break;}
                    speed-=p.f("lastSpurtSpeedDelta");if speed<=floor {break;}
                }
                if let Some(mut speed)=first {
                    let mut candidates=vec![];
                    for _ in 0..=100 {
                        if let Some((start,time))=candidate(speed) {candidates.push((start,speed,time));}
                        speed-=p.f("lastSpurtStep2SpeedDelta");if speed<=floor {break;}
                    }
                    let mul=std::env::var("RX_SPURT_MUL").ok().and_then(|v|v.parse::<f32>().ok()).unwrap_or(10000.0);netsort::sort(&mut candidates,&|a,b|((a.2-b.2)*mul) as i32);
                    let threshold=h.stat(4)*p.f("lastSpurtStep2PerVal2")+p.f("lastSpurtStep2PerVal1");
                    let mut chosen=candidates.last().copied().unwrap_or((h.distance,first.unwrap(),0.0));
                    if std::env::var("RX_HDBG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("CANDS thr={} adj4={} mod4={} {:?}",threshold,self.horses[hi].adjusted[4],self.horses[hi].mods.apply(4,0.0),candidates);}
                    for c in candidates {
                        let roll=self.random.int_range(0,100,&||format!("spurt{hi}"));if std::env::var("RX_HDBG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("ROLL {roll}");} if (roll as f32)<threshold {chosen=c;break;}
                    }
                    (2,chosen.0.max(h.distance),chosen.1)
                } else {(8,-1.0,base)}
            };
        if std::env::var("RX_HDBG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("SPURT {:.4} d={} hp={} res={} start={} speed={} max={} normal={} base={} v={} tv={} sb={:?} ss={:?}",self.time,self.horses[hi].distance,self.horses[hi].hp,result,start,speed,max,normal,base,self.horses[hi].speed,self.horses[hi].target_speed,self.horses[hi].section_base,self.horses[hi].section_speed);}
        let h=&mut self.horses[hi];
        if !h.spurt_calculated || result&3!=0 {
            h.spurt_result=result;h.spurt_speed=speed;
            if !h.spurt_calculated || h.spurt_start<0.0 {h.spurt_start=start;}
        } h.spurt_calculated=true;
    }
    fn around(&mut self,hi:usize,dt:f32) {
        let p=self.p();let h=&self.horses[hi];let mut front=None;let mut inside=None;let mut outside=None;let mut nearest=f32::MAX;let mut near=0;
        let mut near_front=false;let mut near_behind=false;
        // HorseRaceAIBase.UpdateAroundHorsesParam (Global 0x342ff40).
        let side_gap=p.f("Block.SideBlockDistanceGap");let zero_fix=flag("RX_SIDE0");
        let mut around=Vec::with_capacity(self.horses.len());let mut visible=vec![];
        let mut in_space=h.lane;let mut out_space=h.lane_max-h.lane;
        let vis=h.mods.apply(19,p.f("visibleDistance")).max(0.0);
        for (i,n) in self.horses.iter().enumerate() {
            if i==hi {continue;}
            let gap=n.distance-h.distance;let lane=n.lane-h.lane;let abs=lane.abs();
            let back=gap< -side_gap;
            around.push(Around{i,gap,gap_abs:gap.abs(),lane,lane_abs:abs,speed_gap:h.speed-n.speed,back});
            if gap.abs()<=p.f("Near.DistanceThreshold") && abs<=p.f("Near.LaneDistanceThreshold") {near+=1;}
            if gap>0.0 && gap<p.f("Block.FrontBlockDistanceGap") && abs<=(1.0-gap/p.f("Block.FrontBlockDistanceGap")*0.6)*p.f("Block.FrontBlockLaneGap") && gap<nearest {
                nearest=gap;front=Some(i);
            }
            // _CheckSideBlock (0x34305e0): a runner at exactly laneGap 0 is no side block.
            if gap.abs()<side_gap && abs<p.f("Block.SideBlockLaneGap") && (!zero_fix || lane!=0.0) {
                if lane<0.0 {inside=Some(i);} else {outside=Some(i);}
            }
            if !back {
                if gap.abs()<side_gap {
                    if lane<0.0 {if abs<in_space {in_space=abs;}} else if lane>0.0 && abs<out_space {out_space=abs;}
                }
                // HorseVisibleCalculator.CheckVisible (0x3445100).
                if vis>0.0 && gap>=0.0 && gap<=vis &&
                    abs<=((gap/vis)*f32::from_bits(0x3f238e39)+f32::from_bits(0x3de38e39))*0.5 {visible.push(i);}
            }
            if abs<=p.f("Skill.InfrontHorseNearLaneDistance") && gap>0.0 && gap<=p.f("Skill.InfrontHorseNearDistance") {near_front=true;}
            if abs<=p.f("Skill.BehindHorseNearLaneDistance") && gap<0.0 && -gap<=p.f("Skill.BehindHorseNearDistance") {near_behind=true;}
        }
        let h=&mut self.horses[hi];h.front=front;h.inside=inside;h.outside=outside;h.near_count=near;
        // HorseRaceAISimulate.UpdateSurrounded (0x3432cc0): flags 1 and 3 reset
        // each update; flag 2 (runner ahead) is never cleared by the client.
        let sp=self.assets.params();
        let (g1,l1,g2,l2)=(sp.f("Surrounded.DistanceGapAbs1"),sp.f("Surrounded.LaneGap1"),sp.f("Surrounded.DistanceGap2"),sp.f("Surrounded.LaneGapAbs2"));
        let h=&mut self.horses[hi];
        h.surround[0]=false;h.surround[2]=false;if !opt("RX_SURR2KEEP") {h.surround[1]=false;}
        for a in &around {
            if !h.surround[0] && a.gap_abs<=g1 && 0.0<=a.lane && a.lane<=l1 {h.surround[0]=true;}
            if !h.surround[1] && a.gap>0.0 && a.gap<=g2 && a.lane_abs<=l2 {h.surround[1]=true;}
            if !h.surround[2] && a.gap<0.0 && -g2<=a.gap && a.lane_abs<=l2 {h.surround[2]=true;}
        }
        h.around=around;h.visible=visible;h.in_space=in_space;h.out_space=out_space;
        if !flag("RX_BLOCKT") {
            h.front_time=if front.is_some() {h.front_time+dt} else {0.0};
            h.side_time=if inside.is_some() || outside.is_some() {h.side_time+dt} else {0.0};
        }
        if !flag("RX_NEAR") {
            h.near_front_time=if near_front {h.near_front_time+dt} else {0.0};
            h.near_behind_time=if near_behind {h.near_behind_time+dt} else {0.0};
        }
    }
    /// HorseRaceInfoSimulate.PostUpdate (0x343e430) / UpdateBehindHorseNearTime
    /// (0x343efc0): only the order-adjacent runner counts; an order change resets.
    fn compete_runner(&self,hi:usize,stale:bool)->crate::compete::Runner {
        use crate::compete::Style;
        let h=&self.horses[hi];let c=&self.course;
        crate::compete::Runner {style:if h.ex() {Style::Oonige} else if h.input.running_style==1 {Style::Nige} else {Style::Other},
            distance:if stale {h.cf_pos[0]} else {h.distance},lane:if stale {h.cf_pos[1]} else {h.lane},speed:if stale {h.cf_speed} else {h.speed},hp:if stale && opt("RX_CFHP") {h.cf_hp} else {h.hp},max_hp:h.max_hp,guts:h.stat(3),strategy_proficiency:h.style_rate,
            // Probe RX_CFRANK: rank from this tick's distances instead of the previous order.
            rank:h.order+1,final_straight:h.straight && c.final_corner().is_some_and(|s|h.distance>=s.end),tempted:h.tempted()}
    }
    /// Server-only CompeteTop/CompeteFight (docs/RACE_GLOBAL_COMPETE.md prototype).
    fn compete_step(&mut self,dt:f32) {
        let runners=(0..self.horses.len()).map(|i|self.compete_runner(i,false)).collect::<Vec<_>>();
        let params=crate::compete::Params{
            fight_exit_inclusive: !self.jp() && flag("RX_CF_EXIT_INCLUSIVE"),
            fight_select_before_history: !self.jp() && flag("RX_CF_TARGET_HISTORY"),
            top_cohort:!self.jp() && flag("RX_CT_COHORT"),top_end_exit:!self.jp() && flag("RX_CT_END_EXIT"),top_requires_lead:std::env::var("RX_CTLEAD").ok().and_then(|v|v.parse().ok()).unwrap_or(1),..Default::default()};
        let (mut next,mut changes)=crate::compete::step(&self.compete,&runners,self.course.distance,dt,&params);
        // CompeteFight reads the start-of-tick snapshot (positions/speed before this
        // tick's movement); CompeteTop keeps current values. RX_CFSTALE=0 reverts.
        if flag("RX_CFSTALE") {
            let stale=(0..self.horses.len()).map(|i|self.compete_runner(i,true)).collect::<Vec<_>>();
            let (fs,_)=crate::compete::step(&self.compete,&stale,self.course.distance,dt,&params);
            changes.retain(|c|!matches!(c,crate::compete::Change::FightEnter(_)|crate::compete::Change::FightExit(_)));
            // Entry uses the snapshot; exit (hp / 5 m separation) keeps current values (RX_CFEXIT=1 makes exit stale too).
            for i in 0..runners.len() {
                if !self.compete.modes[i].fight || opt("RX_CFEXIT") {next.modes[i].fight=fs.modes[i].fight;next.modes[i].fight_count=fs.modes[i].fight_count;next.modes[i].fight_group=fs.modes[i].fight_group;}
                if self.compete.modes[i].fight!=next.modes[i].fight {
                    changes.push(if next.modes[i].fight {crate::compete::Change::FightEnter(i)} else {crate::compete::Change::FightExit(i)});
                }
            }
            // Global: a fighter whose same-group partner entered this tick within the
            // exit distance keeps fighting (73ca040f: runner 2 joins 16 as 16's last
            // peer drops back). RX_CF_JOIN_KEEP=0 restores the separate exit check.
            if !self.jp() && flag("RX_CF_JOIN_KEEP") {
                for i in 0..runners.len() {
                    if !(self.compete.modes[i].fight && !next.modes[i].fight) || runners[i].hp<runners[i].max_hp*params.fight_exit_hp_percent/100.0 {continue;}
                    let g=self.compete.modes[i].fight_group;
                    if (0..runners.len()).any(|k|k!=i && !self.compete.modes[k].fight && fs.modes[k].fight && fs.modes[k].fight_group==g
                        && (runners[k].distance-runners[i].distance).abs()<=params.fight_exit_distance) {
                        next.modes[i].fight=true;
                        changes.retain(|c|*c!=crate::compete::Change::FightExit(i));
                    }
                }
            }
            next.near=fs.near;
            // compete::step emits per runner: top change, then fight change.
            changes.sort_by_key(|c|match c {crate::compete::Change::TopEnter(i)|crate::compete::Change::TopExit(i)=>(*i,0),
                crate::compete::Change::FightEnter(i)|crate::compete::Change::FightExit(i)=>(*i,1)});
            // Global emits CompeteFight entries in pairing order: each entrant, then its target
            // (14 frame-exact races swapped same-tick events). RX_CFSEQ=0 keeps gate order.
            if flag("RX_CFSEQ") {
                let seq:Vec<usize>=fs.enter_seq.iter().copied().filter(|i|changes.contains(&crate::compete::Change::FightEnter(*i))).collect();let mut seq=seq.into_iter();
                for c in &mut changes {
                    if matches!(c,crate::compete::Change::FightEnter(_)) {*c=crate::compete::Change::FightEnter(seq.next().unwrap());}
                }
            }
        }
        // Preserve the original cohort for separation checks even after a
        // partner's timer expires. Natural expiry alone still permits solo time.
        if opt("RX_CT_EXPIRED_PEER") {
            let params=crate::compete::Params::default();
            for i in 0..runners.len() {
                if !self.compete.modes[i].top || !next.modes[i].top {continue;}
                let peers=(0..runners.len()).filter(|&j|j!=i && self.compete.modes[j].top_group==self.compete.modes[i].top_group).collect::<Vec<_>>();
                // Expired peers use the same symmetric separation as live peers.
                // Global 2e8ffe7d / f2c84706 kept draining HP with an expired
                // partner >5 m behind; full corpus: 585 -> 592, no losses/earlier.
                // RX_CT_EXPIRED_ABS=0 restores the signed-gap control; JP is unchanged.
                if !peers.is_empty() && peers.iter().all(|&j|
                    (if !self.jp() && flag("RX_CT_EXPIRED_ABS") {(runners[j].distance-runners[i].distance).abs()}
                        else {runners[j].distance-runners[i].distance})>=params.top_exit_distance ||
                    (runners[j].lane-runners[i].lane).abs()>=params.top_exit_lane) {
                    next.modes[i].top=false;
                    next.modes[i].top_distance_exit=true;
                    changes.push(crate::compete::Change::TopExit(i));
                }
            }
        }
        self.compete=next;
        for h in &mut self.horses {h.cf_speed=h.speed;h.cf_hp=h.hp;h.cf_pos=[h.distance,h.lane];}
        if !self.jp() && opt("RX_GLOBAL_TOP_EVENT_ORDER") {
            let mut entering=changes.iter().filter_map(|c|match c {crate::compete::Change::TopEnter(i)=>Some(*i),_=>None}).collect::<Vec<_>>();
            // Leader as in the trigger: best cached rank (RX_CTRANKLEAD=0: greatest distance).
            let leader=if flag("RX_CTRANKLEAD") {entering.iter().copied().min_by_key(|i|(runners[*i].rank,*i))}
                else {entering.iter().copied().max_by(|a,b|runners[*a].distance.total_cmp(&runners[*b].distance).then(b.cmp(a)))};
            // Global groups emit their leader first, then the remaining gate list.
            entering.sort_by_key(|i|(Some(*i)!=leader,*i));
            let mut ordered=entering.into_iter();
            for change in &mut changes {
                if matches!(change,crate::compete::Change::TopEnter(_)) {*change=crate::compete::Change::TopEnter(ordered.next().unwrap());}
            }
        }
        for ch in changes {
            let (ty,name,i)=match ch {crate::compete::Change::TopEnter(i)=>(4,"CompeteTop",i),crate::compete::Change::FightEnter(i)=>(5,"CompeteFight",i),_=>continue};
            if ty==5 {self.horses[i].fight_count+=1;}
            // RX_CFDBG: per-partner near time, speed gap, rank, hp% and final-straight at entry.
            let extra=if ty==5 && std::env::var("RX_CFDBG").is_ok() {
                let r=&runners[i];
                json!((0..runners.len()).filter_map(|j|self.compete.near[i][j].map(|t|{let q=&runners[j];
                    json!([j,t,q.speed-r.speed,q.rank,r.rank,q.hp/q.max_hp,self.compete.modes[j].fight,q.distance-r.distance,q.lane-r.lane,r.final_straight,q.final_straight])})).collect::<Vec<_>>()).to_string()
            } else {String::new()};
            self.events.push(json!({"t":self.time,"type":ty,"name":name,"params":[i as i32],"horse":i,"extra":extra}));
        }
    }
    fn compete_effects(&self,hi:usize)->crate::compete::Effects {
        if !opt("RX_COMPETE") || self.compete.modes.len()<=hi {return crate::compete::Effects{target_speed_add:0.0,acceleration_add:0.0,hp_base_rate:None};}
        crate::compete::effects(&self.compete_runner(hi,false),&self.compete.modes[hi],&crate::compete::Params::default())
    }
    fn near_times(&mut self,dt:f32) {
        let p=self.p();
        let (fd,fl,bd,bl)=(p.f("Skill.InfrontHorseNearDistance"),p.f("Skill.InfrontHorseNearLaneDistance"),
            p.f("Skill.BehindHorseNearDistance"),p.f("Skill.BehindHorseNearLaneDistance"));
        let n=self.horses.len();
        let mut by_order=vec![0;n];for (i,h) in self.horses.iter().enumerate() {by_order[h.order]=i;}
        for hi in 0..n {
            let (o,po,d,l)={let h=&self.horses[hi];(h.order,h.prev_order,h.distance,h.lane)};
            let (mut f,mut b)=(None,None);
            if o!=0 && o==po {
                let a=&self.horses[by_order[o-1]];let gap=a.distance-d;
                f=Some(if gap>fd {None} else {Some((l-a.lane).abs()<=fl)});
            }
            if o!=n-1 && o==po {
                let a=&self.horses[by_order[o+1]];let gap=d-a.distance;
                b=Some(if gap<=bd {Some((l-a.lane).abs()<=bl)} else {None});
            }
            // UpdateBehindHorseNearTimeParamSet (0x343f200): per Skill.BehindNearParamArray set,
            // reset when last or the order changed, else reset if the runner behind is more
            // than Distance back or more than LaneDistance aside, otherwise += dt.
            let sets=self.assets.params().arr("Skill.BehindNearParamArray").iter().map(|r|(f32_of(&r["Distance"]),f32_of(&r["LaneDistance"]))).collect::<Vec<_>>();
            let behind=(o!=n-1 && o==po).then(||{let a=&self.horses[by_order[o+1]];(d-a.distance,(l-a.lane).abs())});
            let h=&mut self.horses[hi];
            h.near_front_time=match f {Some(Some(true))=>h.near_front_time+dt,_=>0.0};
            h.near_behind_time=match b {Some(Some(true))=>h.near_behind_time+dt,_=>0.0};
            h.near_behind_set.resize(sets.len(),0.0);
            for (k,(sd,sl)) in sets.into_iter().enumerate() {
                h.near_behind_set[k]=match behind {Some((g,lg)) if !(sd<g || sl<lg)=>h.near_behind_set[k]+dt,_=>0.0};
            }
        }
    }
    fn temptation(&mut self,hi:usize,dt:f32) {
        let p=self.assets.params();let h=&mut self.horses[hi];
        if h.finished {return;}
        // One-time TemptationEndTime Set from a skill switches termination
        // to a fixed countdown, suppressing the regular end lotteries.
        // Global class layout has _isForceEndTimeBySkillEnable / _forceEndTimeBySkill.
        if opt("RX_TEND") && h.mods.has(14) {
            h.temptation_timer=h.mods.consume(14,0.0);h.temptation_forced=true;
        }
        if h.tempted() {
            h.temptation_timer=(h.temptation_timer-dt).max(0.0);
            if h.temptation_timer<=0.0 {h.temptation_mode=0;h.temptation_active=false;h.temptation_end=if h.temptation_forced {3} else {1};return;}
            if opt("RX_TEND") && h.temptation_forced {return;}
            h.temptation_check=(h.temptation_check-dt).max(0.0);
            if h.temptation_check<=0.0 {
                h.temptation_check=p.f("Temptation.TemptationEndCheckTime");
                if (self.random.int_max(100,&||format!("temptation_end{hi}")) as f32)<p.f("Temptation.TemptationEndPer") {h.temptation_mode=0;h.temptation_active=false;h.temptation_end=2;}
            }
        } else if h.temptation_section>0 && (h.distance/(self.course.distance/24.0)).floor() as i32+1>=h.temptation_section {
            let mode=if h.input.running_style==1 {4} else {
                let r=self.random.int_max(100,&||format!("temptation_mode{hi}")) as f32;
                match h.input.running_style {
                    2=>if r<p.f("Temptation.SenkoToNigePer") {3} else {0},
                    3=>if r<p.f("Temptation.SashiToSenkoPer") {2} else {3},
                    _=>if r<p.f("Temptation.OikomiToSashiPer") {1} else if r<p.f("Temptation.OikomiToSashiPer")+p.f("Temptation.OikomiToSenkoPer") {2} else {3},
                }
            };
            h.temptation_section=0;h.temptation_mode=mode;h.temptation_active=true;h.temptation_count+=1;
            h.temptation_forced=false;
            h.temptation_timer=p.f("Temptation.TemptationForceEndTime");h.temptation_check=p.f("Temptation.TemptationEndCheckTime");
        }
    }
    fn downhill(&mut self,hi:usize,dt:f32) {
        let p=self.assets.params();let h=&mut self.horses[hi];
        if h.slope>=0.0 {if h.downhill {h.downhill=false;h.downhill_check=1.0;}return;}
        if h.downhill_check>0.0 {h.downhill_check-=dt;return;}
        h.downhill_check=1.0;
        let threshold=if h.downhill {p.f("Slope.DownSlopeAddSpeedEndPer")} else {(h.stat(4)*p.f("Slope.DownSlopeAddSpeedStartWizRate")).min(100.0)};
        if self.random.float_range(0.0,100.0,&||format!("downhill{hi}"))<threshold {h.downhill=!h.downhill;}
    }
    /// HorseOvertakeTargetCalculator.CheckOvertakeTarget (Global 0x342d9a0).
    fn ot_check(&self,hi:usize,o:usize)->bool {
        let h=&self.horses[hi];
        let Some(a)=h.around.iter().find(|a|a.i==o).copied() else {return false};
        if a.gap< -1.0 {return false;}
        let other=&self.horses[o];
        // GetTargetSpeedWithSkill (0x34387f0) applies modifier 5 to the cached AI target; Global 209 -> 256, 75 later / 0 earlier.
        let own_target=if flag("RX_OT_SKILL_TARGET") {h.mods.apply(5,h.target_speed)} else {h.target_speed};
        if h.front==Some(o) {return own_target>other.speed;}
        if a.gap<1.0 || a.gap>20.0 || a.speed_gap<0.0 {return false;}
        if a.gap/a.speed_gap>self.p().f("overTakeDistPerSpeed") {return false;}
        own_target>if other.front.is_some() {other.speed} else if flag("RX_OT_SKILL_TARGET") {other.mods.apply(5,other.target_speed)} else {other.target_speed}
    }
    /// HorseRaceAIBase.UpdateOverTake (0x34311b0) + CollectOvertakeTarget (0x342d670).
    fn update_overtake(&mut self,hi:usize,dt:f32) {
        let mut list=std::mem::take(&mut self.horses[hi].overtake);
        for v in self.horses[hi].visible.clone() {if self.ot_check(hi,v) && !list.contains(&v) {list.push(v);}}
        list.retain(|&o|self.ot_check(hi,o));
        // GetBlockHorse is appended unconditionally after RemoveAll.
        if let Some(f)=self.horses[hi].front {if !list.contains(&f) {list.push(f);}}
        let cool=self.p().f("overTakeCoolDownTime");let h=&mut self.horses[hi];
        if !list.is_empty() {h.ot_cool=cool;}
        else if h.ot_cool>0.0 {h.ot_cool-=dt;if h.ot_cool<=0.0 {h.force_lane=true;}}
        h.overtake=list;
    }
    fn enable_in(&self,hi:usize)->bool {let h=&self.horses[hi];h.inside.is_none() && h.lane>0.0001}
    fn enable_out(&self,hi:usize)->bool {let h=&self.horses[hi];h.outside.is_none() && h.lane<h.lane_max}
    /// TargetLaneStrategyOverTake.CheckEnableMoveLane (0x34520d0).
    fn ot_enable(&self,hi:usize,l:f32)->bool {
        let h=&self.horses[hi];
        if l<0.0 || l>self.course.lane_max {return false;}
        let d=l-h.lane;
        if d<0.0 {self.enable_in(hi) && -d<=h.in_space} else if d<=0.0 {true} else {self.enable_out(hi) && d<=h.out_space}
    }
    /// CalcIn/OutHorseRecursively (0x34526b0 / 0x3452880).
    fn ot_chain(&self,mut x:usize,inward:bool)->usize {
        let range=f32::from_bits(0x3de38e39);
        loop {
            let mut best=self.horses[x].lane;let mut next=None;
            for a in &self.horses[x].around {
                if a.gap>=0.0 && a.gap<=3.0 && (if inward {a.lane<0.0} else {a.lane>0.0}) && a.lane_abs<range {
                    let l=self.horses[a.i].lane;
                    if if inward {l<best} else {best<l} {best=l;next=Some(a.i);}
                }
            }
            match next {Some(n)=>x=n,None=>return x}
        }
    }
    /// TargetLaneStrategyOverTake.CheckHorseExist (0x3452230) over the visible list.
    fn ot_exist(&self,hi:usize,d0:f32,d1:f32,l0:f32,l1:f32)->bool {
        self.horses[hi].visible.iter().any(|&v|{let n=&self.horses[v];d0<=n.distance && n.distance<=d1 && l0<=n.lane && n.lane<=l1})
    }
    /// TargetLaneStrategyOverTake.Search (0x3451150), asm-checked.
    fn ot_search(&self,hi:usize,fixed:f32)->f32 {
        let p=self.p();let h=&self.horses[hi];
        let c1=f32::from_bits(0x3d638e3a);let c2=f32::from_bits(0x3d638e39);let w=f32::from_bits(0x3d360b62);
        let mut cands=vec![];let mut min_dist=f32::MAX;
        for &t in &h.overtake {
            let td=self.horses[t].distance;if td<min_dist {min_dist=td;}
            let a=self.ot_chain(t,true);let b=self.ot_chain(t,false);
            let inl=self.horses[a].lane-c1;let outl=self.horses[b].lane+c1;
            if 0.0<=inl && !self.ot_exist(hi,h.distance,self.horses[a].distance+0.5,inl-w,inl+w) {cands.push(inl);}
            if outl<=h.lane_max && !self.ot_exist(hi,h.distance,self.horses[b].distance+0.5,outl-w,outl+w) {cands.push(outl);}
        }
        if h.phase<2 && self.enable_in(hi) && h.lane>c2 {
            if !self.ot_exist(hi,h.distance,min_dist+3.0,(h.lane-w)-c2,(h.lane+w)-c2) {cands.push(h.lane-c2);}
        } else if !self.ot_exist(hi,h.distance,min_dist+3.0,h.lane-w,h.lane+w) {cands.push(h.lane);}
        let (m_in,m_out)=(h.mods.apply(16,0.0)!=0.0,h.mods.apply(17,0.0)!=0.0);
        let mut chosen=h.lane;let mut best=f32::MAX;
        for c in cands {
            let d=h.lane-c;
            let phase=if h.phase==0 {if d>0.0 {100.0} else {1.0}} else if h.phase<2 {1.0}
                else if d>0.0 {p.f("overTakeOutLaneCoefEnd")} else {p.f("overTakeInLaneCoefEnd")};
            let skill=if m_in!=m_out && ((m_in && d>0.0) || (m_out && d<0.0)) {1.5} else {1.0};
            let cost=(phase*d*skill).abs();
            if cost<best && self.ot_enable(hi,c) {best=cost;chosen=c;}
        }
        if let Some(extra)=h.extra_lane {
            if chosen<h.lane || extra<=chosen || !self.ot_enable(hi,extra) {chosen} else {extra}
        } else if !math::approximately(fixed,0.0) {
            if chosen<h.lane || fixed<=chosen || !self.ot_enable(hi,fixed) {chosen} else {fixed}
        } else {chosen}
    }
    fn move_lane(&mut self,hi:usize,dt:f32,plan:bool) {
        let jp=self.jp();
        let inside_lane=self.horses[hi].inside.map(|i|self.horses[i].lane);
        let p=self.assets.params();let h=&mut self.horses[hi];
        let enable_in=h.inside.is_none() && h.lane>0.0001;let enable_out=h.outside.is_none() && h.lane<h.lane_max;
        let end=self.course.final_corner().map(|c|c.start+(c.end-c.start)*p.f("LastMoveOutStartFinalCornerRate"));
        // HorseTargetLaneCalculatorRace.Update (0x34422a0) also searches
        // again when the current target's direction has become blocked.
        let blocked_target=(h.target_lane<h.lane && !enable_in) ||
            (h.target_lane>h.lane && !enable_out);
        // HorseRaceAISimulate.CreateTargetLaneCalculator (0x34323e0): without
        // IsEmptyInMove the Null calculator keeps the initial target lane.
        if plan && flag("RX_NULLLANE") && !(self.course.empty_in_move && self.course.first_move>0.0) {return;}
        let ot=flag("RX_OT");let fix=flag("RX_FIX");
        let overtaking=ot && !h.overtake.is_empty();
        
        if plan && (h.force_lane || blocked_target || overtaking || (h.target_lane-h.lane).abs()<0.02777777798473835) {
            h.force_lane=false;h.target_lane=h.lane;
            if h.extra_lane.is_none() && end.is_some_and(|d|h.distance>=d) {
                let norm=p.f("lastMoveOutLaneNormalizeVal");let norm=if math::approximately(norm,0.0) {0.2} else {norm};
                h.extra_lane=Some(((h.lane/norm).clamp(0.0,1.0)*p.f("lastMoveOutLaneCoef")+
                    self.random.float_range(0.0,p.f("lastMoveOutLaneAddRandom"),&||format!("extra_lane{hi}"))).clamp(0.0,h.lane_max));
            }
            let fixed=h.mods.apply(11,0.0);
            let first=self.course.first_move;
            // HorseTargetLaneCalculatorRace.Update (0x34422a0) strategy choice.
            let use_ot=ot && (!h.overtake.is_empty() || h.ot_cool>0.0) &&
                !(h.phase<2 && h.distance<=first && first-200.0<=h.distance);
            if use_ot {
                let t=self.ot_search(hi,fixed);
                let h=&mut self.horses[hi];h.target_lane=t.clamp(0.0,h.lane_max);
                return;
            }
            let h=&mut self.horses[hi];
            if fix && !math::approximately(fixed,0.0) {
                // TargetLaneStrategyFixed.Search (0x34505c0): no hp test.
                h.target_lane=if fixed<h.lane {if enable_in {fixed.max(h.lane-0.05)} else {h.lane}}
                    else if h.lane<fixed {if enable_out {fixed.min(h.lane+0.05)} else {h.lane}} else {h.lane};
            } else if h.hp>0.0 {
                if !math::approximately(fixed,0.0) {h.target_lane=h.lane+(fixed-h.lane).clamp(-0.05,0.05);}
                // TargetLaneStrategyNormal.Search, Global RVA 0x3450800.
                else if h.keep.mode==4 {h.target_lane=p.f("PositionKeep.PositionKeepPaseDownTargetLane");}
                else if let Some(extra)=h.extra_lane {if extra>h.lane && enable_out {h.target_lane=extra.min(h.lane+0.05);}}
                else if h.phase<2 && enable_in {h.target_lane=h.lane-0.05;}
                // TargetLaneStrategyNormal.Search: during the middle phase,
                // create room beside an inside blocker that is sufficiently
                // far away laterally. Actual movement still checks blocking.
                else if h.phase==1 {
                    if let Some(lane)=inside_lane {
                        let gap=p.f("Block.SideBlockLaneGap");
                        // Client tests the in-blocker's tick-start laneGapAbs < gap - 1/72.
                        let snap=h.inside.and_then(|i|h.around.iter().find(|a|a.i==i)).map_or((lane-h.lane).abs(),|a|a.lane_abs);
                        let room=if fix {snap<gap-f32::from_bits(0x3c638e39)} else {(lane-h.lane).abs()>gap-0.013888888992369175};
                        if room {
                            h.target_lane=(lane+gap).min(h.lane+0.05);
                        }
                    }
                }
            }
            h.target_lane=h.target_lane.clamp(0.0,h.lane_max);
        }
        if plan {return;}
        let h=&mut self.horses[hi];
        h.prev_lane=h.lane;
        if math::approximately(h.lane,h.target_lane) {h.lane=h.lane.clamp(0.0,h.lane_max);h.move_time=0.0;return;}
        // HorseRaceInfo.MoveLane (0x34372c0): MoveLaneContinueDirection/Time.
        let prev_dir=h.move_dir;h.move_dir=(h.lane<=h.target_lane) as i32;
        if h.finished && h.after_goal>=1.0 && opt("RX_GOALLANE4") {
            // HorseRaceInfo.MoveLane (0x34372c0) in IsOverRunSpeedDownMode: _laneMoveSpeed = +-deltaTime.
            let old=h.lane;let m=if h.target_lane<old {-dt} else {dt};h.lane_move=m;
            let next=if opt("RX_GOALLANE4F") {dt*m+old} else {(dt as f64*m as f64+old as f64) as f32};
            let next=if h.target_lane<old {next.max(h.target_lane)} else {next.min(h.target_lane)}.clamp(0.0,h.lane_max);
            if (next>old && !enable_out) || (next<old && !enable_in) {return;}
            h.lane=next;if prev_dir==h.move_dir {h.move_time+=dt;}
            if math::approximately(h.lane,h.target_lane) {h.lane_speed=0.0;}
            return;
        }
        let mut base;
        if opt("RX_D7") || opt("RX_D7A") || opt("RX_D7B") || opt("RX_D7C") {
            let (a,b,c)=(opt("RX_D7")||opt("RX_D7A"),opt("RX_D7")||opt("RX_D7B"),opt("RX_D7")||opt("RX_D7C"));
            base=if !a {(h.stat(2)*p.f("laneMoveSpeedPowCoef")+p.f("laneMoveSpeedAdd"))*p.f("laneMoveSpeedBase")} else {((h.stat(2) as f64*p.f("laneMoveSpeedPowCoef") as f64+p.f("laneMoveSpeedAdd") as f64)*p.f("laneMoveSpeedBase") as f64) as f32};
            if h.phase<2 && h.distance<=self.course.first_move && opt("RX_D7B2") {base*=((h.lane as f64/h.lane_max as f64*p.f("laneMoveSpeedOutCoef") as f64+1.0) as f32);}
            else if h.phase<2 && h.distance<=self.course.first_move {base=if !b {base*(h.lane/h.lane_max*p.f("laneMoveSpeedOutCoef")+1.0)} else {
                // CalcLaneMoveSpeedBeforeFirstMoveLanePoint (0x362c840): the lane
                // ratio crosses a float local before the remaining double expression.
                // 1073 Global races: +13 exact, zero lost or earlier; =0 reverts.
                let ratio=if !jp && flag("RX_LANE_RATIO_LOCAL") {(h.lane/h.lane_max) as f64}
                    else {h.lane as f64/h.lane_max as f64};
                (base as f64*(ratio*p.f("laneMoveSpeedOutCoef") as f64+1.0)) as f32
            };}
            if h.phase>=2 && opt("RX_D7C2") {base*=((h.order as f64*0.01f32 as f64+1.0) as f32);}
            else if h.phase>=2 {base=if !c {base*(h.order as f32*0.01+1.0)} else {(base as f64*(h.order as f64*0.01f32 as f64+1.0)) as f32};}
        } else {
        base=(h.stat(2)*p.f("laneMoveSpeedPowCoef")+p.f("laneMoveSpeedAdd"))*p.f("laneMoveSpeedBase");
        if h.phase<2 && h.distance<=self.course.first_move {base*=h.lane/h.lane_max*p.f("laneMoveSpeedOutCoef")+1.0;}
        if h.phase>=2 {base*=h.order as f32*0.01+1.0;}
        }
        let accel=p.f("laneMoveAccelMoveSpeedBaseCoef")*p.f("laneMoveSpeedBase");
        let d3=opt("RX_D3")||opt("RX_D3A");let d3b=opt("RX_D3")||opt("RX_D3B");
        h.lane_speed=if d3 {if h.lane_speed<base {((h.lane_speed as f64+accel as f64*dt as f64) as f32).min(base)} else {((h.lane_speed as f64-accel as f64*dt as f64) as f32).max(base)}}
            else if h.lane_speed<base {(h.lane_speed+accel*dt).min(base)} else {(h.lane_speed-accel*dt).max(base)};
        h.lane_speed=h.lane_speed.max(0.0);
        let speed=h.mods.apply(7,h.lane_speed).clamp(0.0,0.6);
        let old=h.lane;
        // HorseRaceInfo._laneMoveSpeed (signed, per second) as last applied by MoveLane.
        if h.target_lane<old && enable_in {h.lane_move=((old as f64+1.0)*(-speed as f64)) as f32;}
        else if h.target_lane>old && enable_out {h.lane_move=speed;}
        if opt("RX_D3C") {
            // HorseRaceInfo.MoveLane (0x34372c0): _laneMoveSpeed is a field
            // (rounded), then dt*_laneMoveSpeed + prev in one statement.
            let m=if h.target_lane<old {((old as f64+1.0)*(-speed as f64)) as f32} else {speed};
            let next=(dt as f64*m as f64+old as f64) as f32;
            if h.target_lane<old && enable_in {h.lane=next.max(h.target_lane).clamp(0.0,h.lane_max);}
            else if h.target_lane>old && enable_out {h.lane=next.min(h.target_lane).clamp(0.0,h.lane_max);}
        } else if h.target_lane<old && enable_in {h.lane=if d3b {((old as f64+dt as f64*((old as f64+1.0)*(-speed as f64))) as f32)} else {old+dt*((old+1.0)*(-speed))}.max(h.target_lane).clamp(0.0,h.lane_max);}
        else if h.target_lane>old && enable_out {h.lane=if d3b {(old as f64+dt as f64*speed as f64) as f32} else {old+dt*speed}.min(h.target_lane).clamp(0.0,h.lane_max);}
        let moved=if h.target_lane<old {enable_in} else if h.target_lane>old {enable_out} else {true};
        if moved && !math::approximately(speed,0.0) && prev_dir==h.move_dir {h.move_time+=dt;}
        if std::env::var("RX_LANEDBG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("LANE {:.4} old={:e} new={:e} tl={:e} ls={:e} base={:e} sp={:e} lm={:e} ph={} d={} in={:?} out={:?}",self.time,old,h.lane,h.target_lane,h.lane_speed,base,speed,h.lane_move,h.phase,h.distance,h.inside,h.outside);}
        if math::approximately(h.lane,h.target_lane) {h.lane_speed=0.0;}
    }
    fn update_horse(&mut self,hi:usize,dt:f32) {
        let p=self.assets.params();let race_base=self.race_base();
        let default_min=race_base*p.f("Speed.MinSpeedRate");
        let front_min=self.horses[hi].front.map(|i|self.horses[i].min_speed);
        let h=&mut self.horses[hi];
        h.min_speed=if h.finished {5.0} else if h.start_dash {p.f("StartSpeed")} else {
            // Preserve the server expression's final multiply/add until its
            // float32 result; sqrt retains its float32 argument and result.
            // JP UpdateMinSpeed (0x3c2d180) uses sqrtss, mulss and addss.
            // Global's replay-supported double expression remains regional.
            let v=if self.input.region.as_deref()==Some("jp") && flag("RX_JP_MIN_FLOAT") {
                default_min+(h.stat(3)*p.f("Speed.MinSpeedGutsCoefSqrt")).sqrt()*p.f("Speed.MinSpeedGutsCoef")
            } else {(default_min as f64+(h.stat(3)*p.f("Speed.MinSpeedGutsCoefSqrt")).sqrt() as f64*
                p.f("Speed.MinSpeedGutsCoef") as f64) as f32};
            front_min.map_or(v,|m|v.min(m))
        };
        let heal=h.mods.consume(12,0.0);h.hp=(h.hp+heal).clamp(0.0,h.max_hp);
        let recalc=heal>0.0 && h.phase>=2;
        if h.delay>0.0 {h.delay-=dt;if h.delay>0.0 || dt==0.0 {return;}}
        if dt==0.0 {return;}
        // Real Global replays: after the finish tick, speed, lane and HP stay frozen and the
        // runner advances speed*dt through the ordinary world-displacement cap.
        if self.horses[hi].finished && flag("RX_GOALRUN") {
            if opt("RX_GOALSPD") {
                // _UpdateSelfSpeed (0x3437970) once finished: accel 1/s (CalcAccelPerSec),
                // decel a flat 4/s (no declBase), toward the frozen target: the server's
                // HorseRaceAISimulate over-run calculator is HorseTargetSpeedCalculatorNull,
                // which returns the AI's current target. Min speed 5.
                // The front-block cap (RaceUtil.CalcMaxSpeedBlock) still applies (RX_GOALBLOCK).
                let max=match self.horses[hi].front.filter(|_|opt("RX_GOALBLOCK")) {
                    Some(i)=>{
                        let (h,front)=(&self.horses[hi],&self.horses[i]);let p=self.assets.params();
                        let g=h.around.iter().find(|a|a.i==i).map_or(front.distance-h.distance,|a|a.gap);
                        let t=(g/p.f("Block.FrontBlockDistanceGap")).clamp(0.0,1.0);
                        let (mx,mn)=(p.f("Block.FrontBlockMaxSpeedRateMax"),p.f("Block.FrontBlockMaxSpeedRateMin"));
                        (front.speed*((mx-mn)*t+mn)).max(h.min_speed)
                    },
                    None=>30.0,
                };
                let h=&mut self.horses[hi];let target=h.target_speed;
                let mut v=h.self_speed;
                if v<target {v=(v+dt).min(target);} else if v>target {v=(v-4.0*dt).max(target);}
                v=v.clamp(5.0,max.max(5.0));h.self_speed=v;h.speed=(h.mods.apply(23,0.0)+h.mods.apply(5,0.0)+v).clamp(5.0,max.max(5.0));
            }
            // HorseRaceAIBase.UpdateAfterGoalTime (0x342fc40): the race lane calculator keeps
            // running until afterGoalTime reaches 1 s, then switches to the over-run one.
            // HorseRaceAISimulate.CreateTargetLaneCalculatorOverRun (0x3433a30) builds
            // HorseTargetLaneCalculatorNull: the target freezes, MoveLane continues (RX_GOALLANE3).
            let plan=self.horses[hi].after_goal<1.0;
            let lane_ai=opt("RX_GOALLANE2") && (plan || opt("RX_GOALLANE3"));
            if lane_ai && plan && opt("RX_GOALOT") && flag("RX_OT") {self.update_overtake(hi,dt);}
            if lane_ai {if plan {self.move_lane(hi,dt,true);}if !opt("RX_GOALLANE2B") {self.move_lane(hi,dt,false);}}
            let h=&self.horses[hi];let mut movement=h.speed*dt;
            let position=self.geometry.world(h.distance,h.lane);let dx=position[0]-h.position[0];let dz=position[2]-h.position[2];
            let jp=self.geometry.jp;
            let displacement=if jp {(dx*dx+dz*dz).sqrt()} else {((dx as f64)*(dx as f64)+(dz as f64)*(dz as f64)).sqrt() as f32};
            let cap=movement*self.geometry.distance_to_world;
            let (mv0,old)=(movement,self.horses[hi].position);
            if cap<displacement {movement=if jp {movement*(cap/displacement)} else {((movement as f64)*(cap as f64)/(displacement as f64)) as f32};}
            let h=&mut self.horses[hi];
            h.dbg[5]=if cap<displacement {1.0} else {0.0};h.dbg[6]=mv0;h.dbg[7..10].copy_from_slice(&old);h.dbg[10..13].copy_from_slice(&position);h.dbg[13]=self.geometry.distance_to_world;
            h.position=position;h.prev_distance=h.distance;h.distance+=movement;
            if lane_ai && opt("RX_GOALLANE2B") {self.move_lane(hi,dt,false);return;}
            if lane_ai {return;}
            if h.lane_move!=0.0 && flag("RX_GOALLANE") {h.prev_lane=h.lane;h.lane=((dt as f64*h.lane_move as f64+h.lane as f64) as f32).clamp(0.0,h.lane_max);}
            return;
        }
        if !self.horses[hi].finished {self.horses[hi].lane_move=0.0;}
        if !self.horses[hi].finished {
            let runners=self.horses.iter().map(|h|crate::position_keep::Runner {
                distance:h.distance,order:h.order,style:h.input.running_style,ex:h.ex(),phase:h.phase,
                wiz:h.stat(4),temptation:if h.tempted() && h.temptation_mode==0 {3} else {h.temptation_mode},
                speed_skill:h.mods.apply(6,0.0)>0.0 || h.mods.apply(5,0.0)>0.0,
            }).collect::<Vec<_>>();
            self.horses[hi].keep.update(&Tree(p.get("PositionKeep")),self.course.distance as i32,24,
                &runners,hi,self.pacemaker,&mut self.random,dt,!(opt("RX_PMFIRST") && !self.pm_ready));
        }
        if flag("RX_CP") && !self.horses[hi].finished && !self.horses[hi].cp.released {
            // Inferred accumulation (284 verified durations; see RACE_GLOBAL_SOURCE_SEARCH.md):
            // seconds of normal position keep (mode 0) and pace-down (mode 4) in sections
            // 0..9, not while rushed, weighted by the fitted per-second activity time and
            // ConservePowerRunningStyleCoef.
            if self.compete.modes.get(hi).is_some_and(|m|m.top) {self.horses[hi].cp.top=true;}
            let cp=Tree(p.get("ConservePower"));let h=&self.horses[hi];
            let section=(h.distance/(self.course.distance/24.0)) as i32;
            let in_top=self.compete.modes.get(hi).is_some_and(|m|m.top) && flag("RX_CPTOP");
            let inc=if h.tempted() || in_top || section>=10 {0.0} else if h.keep.mode==4 {0.211} else if h.keep.mode==0 {0.1817} else {0.0};
            if inc>0.0 {
                let style=h.input.running_style as i64;
                let sc=cp.arr("ConservePowerRunningStyleCoefArray").iter().find(|r|r["RunningStyle"].as_i64()==Some(style)).map_or(1.0,|r|f32_of(&r["Coef"]));
                self.horses[hi].cp.value+=inc*sc*dt;
            }
            if flag("RX_CPSPEC") {
                // KuromiAK spec (4.2/s normal, 6.7/s pace-down, x style, sections 0..9, x0.8 on
                // rushing entry, x0.95 on CompeteTop entry) with tick cooldowns fitted on 341
                // verified durations: 32 after speed-up/overtake/pace-up EX, 28 after pace-up,
                // 23 (1.5 s) after rushing/CompeteTop, 8 at race start. Duration offset -0.5 tick
                // (RX_CPSPECB) maximises corpus boost coverage (260 vs 137 runners matched 4.5 s on).
                let h=&self.horses[hi];let style=h.input.running_style as i64;
                let sc=cp.arr("ConservePowerRunningStyleCoefArray").iter().find(|r|r["RunningStyle"].as_i64()==Some(style)).map_or(1.0,|r|f32_of(&r["Coef"]));
                let rate=|m:i64|cp.arr("ConservePowerIncreaseCoefArray").iter().find(|r|r["Mode"].as_i64()==Some(m)).map_or(0.0,|r|f32_of(&r["Coef"]));
                let dec=|m:i64|cp.arr("ConservePowerDecreaseCoefArray").iter().find(|r|r["Mode"].as_i64()==Some(m)).map_or(1.0,|r|f32_of(&r["Coef"]));
                let (tm,tp,m)=(h.tempted(),self.compete.modes.get(hi).is_some_and(|m|m.top),h.keep.mode);
                let (r_pd,r_n,d_tp,d_tm)=(rate(1),rate(2),dec(3),dec(4));
                let cp_cool=cp.f("ConservePowerDefaultCoolDownTime");
                let rush_prev=!self.jp() && flag("RX_CP_RUSH_PREV_TICK");
                let rush_timer_exit=!self.jp() && flag("RX_CP_RUSH_TIMER_EXIT");
                let end_kind=self.horses[hi].temptation_end;
                let m0=!self.jp() && flag("RX_CP_RUSH_EXIT_M0");
                let c=&mut self.horses[hi].cp;
                // Research-only tick probes; defaults retain the measured model.
                let cooldown=|name:&str,default:i32|std::env::var(name).ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(default).max(0);
                if !c.s_init {c.s_init=true;c.scd=cooldown("RX_CPSPECSTART",8);}
                // Rush entry is visible to accrual on its own tick (Global): a whole-second credit
                // earned on the tick before rushing begins is withdrawn before the x0.8 decay.
                // Corpus-supported inference (+3 / 0 lost); CompeteTop and pace-mode entries do not.
                if tm && !c.s_tm && rush_prev {c.spec-=c.last_credit;}
                if tm && !c.s_tm {c.spec*=d_tm;}
                c.last_credit=0.0;
                // Likewise a rush ended by TemptationForceEndTime expiry is visible on its own tick
                // (one extra tick of accrual); a lottery end is not (+1/-2 when included).
                // Global: also for a lottery end when the previous tick had no keep mode (2a661b2d; the three
                // lottery exits that lose all leave keep mode 1 on the exit tick). Timer exits are
                // neutral under the same gate. 673 races: +1, none lost. RX_CP_RUSH_EXIT_M0=0 reverts.
                let rush_exit=!tm && c.s_tm && rush_timer_exit && (if m0 {matches!(end_kind,1|2) && c.lag_mode==0} else {end_kind==1});
                if tp && !c.s_tp {c.spec*=d_tp;}
                // Opt-in structural screens: fixed cost or decay on pace-up entry.
                let cost=std::env::var("RX_CP_PACE_COST").ok().and_then(|v|v.parse::<f32>().ok());
                let decay=std::env::var("RX_CP_PACE_ENTRY_DECAY").ok().and_then(|v|v.parse::<f32>().ok())
                    .filter(|_| !opt("RX_CP_PACE_ENTRY_LONG") || self.course.distance>=3000.0);
                if cost.is_some() || decay.is_some() {
                    if m==3 && c.probe_keep_mode!=3 {c.spec=(c.spec*decay.unwrap_or(1.0)-cost.unwrap_or(0.0)*sc).max(0.0);}
                    c.probe_keep_mode=m;
                }
                c.s_tm=tm;c.s_tp=tp;
                if flag("RX_CPSEC") {
                    // Whole-second credit (1544 exact JP labels: 98.3% tick-exact, 99.4% on 1 cm runners).
                    // Any blocker sets the timer to -ConservePowerDefaultCoolDownTime (1.5 s); each eligible
                    // tick adds dt; each full second earns one second of the current mode's rate. Accrual ends
                    // at section 10 of integer-length sections: distance >= (L / 24, integer) * 10.
                    let lag=opt("RX_CP_PACE_LAG") && std::env::var("RX_CPLAGM").ok().and_then(|v|v.parse::<i32>().ok()).map_or(matches!(m,1|2|3|5),|x|x==m) && !matches!(c.lag_mode,1|2|3|5) && !tm && !tp;
                    let m_eff=if lag {c.lag_mode} else {m};c.lag_mode=m;
                    if tm || tp || (!lag && matches!(m,1|2|3|5)) {c.ctimer=-cp_cool;}
                    else if lag && self.horses[hi].distance<(self.course.distance as i32/24*10) as f32 {
                        let c=&mut self.horses[hi].cp;c.ctimer+=dt;
                        if c.ctimer>=1.0 {let g=(if m_eff==4 {r_pd} else {r_n})*sc;c.spec+=g;c.last_credit=g;}
                        c.ctimer=-cp_cool;
                    }
                    else if (if opt("RX_CPCUTPREV") {self.horses[hi].prev_distance} else {self.horses[hi].distance})<(self.course.distance as i32/24*10) as f32 {
                        let c=&mut self.horses[hi].cp;c.ctimer+=dt;if rush_exit {c.ctimer+=dt;}
                        if c.ctimer>=1.0 {let g=(if m==4 {r_pd} else {r_n})*sc;c.spec+=g;c.last_credit=g;c.ctimer-=1.0;}
                    }
                }
                else if tm || tp {c.scd=cooldown("RX_CPSPECTOP",23);}
                else if matches!(m,1|2|3|5) && !(style==1 && matches!(m,1|2) && opt("RX_CP_NIGE_ACTIVE")) {c.scd=if m==3 {28} else {cooldown("RX_CPSPECKEEP",32)};}
                else if c.scd>0 {c.scd-=1;}
                else if section<10 {c.spec+=(if m==4 {r_pd} else {r_n})*sc*dt;}
            }
        }
        if std::env::var("RX_CPDBG").is_ok() && !self.horses[hi].finished {
            let pm_d=self.horses[self.pacemaker].distance;
            let kt=Tree(p.get("PositionKeep"));let ins=crate::position_keep::Keep::in_section(&kt,self.course.distance as i32,24,self.horses[hi].distance);
            let top=self.compete.modes.get(hi).is_some_and(|m|m.top);let fight=self.compete.modes.get(hi).is_some_and(|m|m.fight);
            let (me_d,me_l)=(self.horses[hi].distance,self.horses[hi].lane);
            let others=||self.horses.iter().enumerate().filter(move |(i,_)|*i!=hi).map(|(_,o)|(o.distance-me_d,o.lane-me_l));
            let near_ahead=others().filter(|(dd,dl)|*dd>0.0 && *dd<3.0 && dl.abs()<0.15).count() as f32;
            let near_any=others().filter(|(dd,dl)|dd.abs()<2.0 && dl.abs()<0.15).count() as f32;
            let gap_ahead=others().filter(|(dd,dl)|*dd>0.0 && dl.abs()<0.15).map(|(dd,_)|dd).fold(99.0f32,f32::min);
            let h=&mut self.horses[hi];let m=h.keep.mode as usize;
            if m==0 && !ins {h.cp.mt[9]+=dt;} else {h.cp.mt[m.min(5)]+=dt;}
            if h.tempted() {h.cp.mt[6]+=dt;} if top {h.cp.mt[7]+=dt;} if fight {h.cp.mt[8]+=dt;}
            let code=(m as u32).min(7)|(ins as u32)<<3|((h.tempted()) as u32)<<4|(top as u32)<<5|(fight as u32)<<6
                |(h.mods.has(6) as u32)<<7|(h.mods.has(10) as u32)<<8|(h.mods.has(21) as u32)<<9|(h.phase as u32)<<10
                |((h.self_speed<h.target_speed) as u32)<<12|((h.self_speed>h.target_speed) as u32)<<15|(h.front.is_some() as u32)<<13|(h.mods.has(5) as u32)<<14|(((h.distance/(self.course.distance/24.0)) as u32).min(31))<<16|(((h.keep.checked+1) as u32)&7)<<24|(h.start_dash as u32)<<27|((h.delay>0.0) as u32)<<28|((h.keep.cooldown>0.0) as u32)<<29
                |((h.corner!=0) as u32)<<21|((h.slope>0.0) as u32)<<22|((h.slope<0.0) as u32)<<23|(h.downhill as u32)<<30|(h.straight as u32)<<31;
            h.cp.log.push(code);let dl=[h.distance,h.self_speed,h.target_speed,pm_d-h.distance,h.keep.wanted as f32,h.keep.cooldown,h.order as f32,h.lane,h.hp,self.pacemaker as f32,h.keep.rng_probe_state()[4],h.keep.rng_probe_state()[3],near_ahead,near_any,gap_ahead,h.cp.ctimer,h.cp.spec,self.time];h.cp.dlog.push(dl);
        }
        // HorseRaceAISimulate.Update: position keep -> UpdateOverTake -> temptation -> lane.
        if flag("RX_OT") {self.update_overtake(hi,dt);}
        self.temptation(hi,dt);
        self.move_lane(hi,dt,true);
        if self.horses[hi].phase>=2 && (!self.horses[hi].spurt_calculated || recalc) {self.spurt(hi);}
        if flag("RX_CP") {
            let h=&self.horses[hi];
            if !h.cp.released && h.spurt_start>0.0 && h.spurt_result&12==0 && h.distance>=h.spurt_start {
                let pow=h.cp.pow+h.mods.apply(2,0.0);
                let cp=Tree(p.get("ConservePower"));
                let dt_=if self.course.distance<=1400.0 {1} else if self.course.distance<=1800.0 {2} else if self.course.distance<=2400.0 {3} else {4};
                let style=h.input.running_style as i64;
                let coef=cp.arr("ReleaseConservePowerAccelRunningStyleAndDistanceTypeCoefArray").iter()
                    .find(|r|r["RunningStyle"].as_i64()==Some(style) && r["DistanceType"].as_i64()==Some(dt_)).map_or(1.0,|r|f32_of(&r["Coef"]));
                let dc_=cp.arr("ReleaseConservePowerActivityTimeDistanceTypeCoefArray").iter().find(|r|r["DistanceType"].as_i64()==Some(dt_)).map_or(1.0,|r|f32_of(&r["Coef"]));
                // Empirical fit (284 verified durations, median error 0.055 s); exact server rule unresolved.
                let sc=cp.arr("ConservePowerRunningStyleCoefArray").iter().find(|r|r["RunningStyle"].as_i64()==Some(style)).map_or(1.0,|r|f32_of(&r["Coef"]));
                let mut dur=std::env::var("RX_CPDUR").ok().and_then(|v|v.parse::<f32>().ok()).unwrap_or(dc_*(h.cp.value-2.262*sc).max(0.0));
                if flag("RX_CPSPEC") {dur=h.cp.spec*self.course.distance.sqrt()*dc_/cp.f("ReleaseConservePowerActivityTimeCoef")+std::env::var("RX_CPSPECB").ok().and_then(|v|v.parse::<f32>().ok()).unwrap_or(if flag("RX_CPSEC") {0.0} else {-0.5})*dt;}
                // Probe: RX_CPOFF="c0,c1" replaces the -0.5 tick offset with (c0 + c1*DistanceTypeCoef) ticks.
                if flag("RX_CPSPEC") && let Some((c0,c1))=std::env::var("RX_CPOFF").ok().and_then(|v|{let (a,b)=v.split_once(',')?;Some((a.parse::<f32>().ok()?,b.parse::<f32>().ok()?))}) {
                    dur=h.cp.spec*self.course.distance.sqrt()*dc_/cp.f("ReleaseConservePowerActivityTimeCoef")+(c0+c1*dc_)*dt;
                }
                // Probe: RX_CPOFF1=x sets the offset (ticks) for DistanceType 1 (<=1400 m) only.
                if flag("RX_CPSPEC") && dt_==1 && let Some(x)=std::env::var("RX_CPOFF1").ok().and_then(|v|v.parse::<f32>().ok()) {
                    dur=h.cp.spec*self.course.distance.sqrt()*dc_/cp.f("ReleaseConservePowerActivityTimeCoef")+x*dt;
                }
                // Probe: RX_CPDURFILE={sha:{horse:seconds}} per-runner duration override.
                if let Ok(f)=std::env::var("RX_CPDURFILE") {
                    let v:Value=serde_json::from_slice(&std::fs::read(f).unwrap_or_default()).unwrap_or(Value::Null);
                    if let Some(d)=v[self.input.replay_sha.as_str()][hi.to_string()].as_f64() {dur=d as f32;}
                }
                let rushed=h.temptation_count>0 && flag("RX_CPRUSH");
                // ConservePowerDecreaseAccelCoef: mode 3 after a lead competition (CompeteTop), mode 4 after rushing.
                let dec=|m:i64|cp.arr("ConservePowerDecreaseAccelCoefArray").iter().find(|r|r["Mode"].as_i64()==Some(m)).map_or(1.0,|r|f32_of(&r["Coef"]));
                let mode_coef=(if h.cp.top && flag("RX_CPTOP") {dec(3)} else {1.0})*(if rushed {dec(4)} else {1.0});
                let accel=if std::env::var("RX_CPORD").as_deref()==Ok("3") {
                    (((pow-1200.0) as f64*cp.f("ReleaseConservePowerDeclCoef") as f64).sqrt()*cp.f("ReleaseConservePowerAccelCoef") as f64*coef as f64*mode_coef as f64) as f32
                } else if std::env::var("RX_CPORD").as_deref()==Ok("4") {
                    ((pow-1200.0)*cp.f("ReleaseConservePowerDeclCoef")).sqrt()*(cp.f("ReleaseConservePowerAccelCoef")*coef*mode_coef)
                } else {((pow-1200.0)*cp.f("ReleaseConservePowerDeclCoef")).sqrt()*cp.f("ReleaseConservePowerAccelCoef")*coef*mode_coef}*std::env::var("RX_CPK").ok().and_then(|v|v.parse::<f32>().ok()).unwrap_or(1.0);
                let t=self.time;let h=&mut self.horses[hi];h.cp.released=true;
                if pow>1200.0 && (!flag("RX_IPA_CP_THRESHOLD") || dur>cp.f("ConservePowerReleasableActivityTimeThreshold")) {
                    h.cp.accel=accel;h.cp.left=dur;
                    let mut ev=json!({"t":t,"type":6,"name":"ReleaseConservePower","params":[hi],"horse":hi,"extra":""});
                    if std::env::var("RX_CPDBG").is_ok() {ev["dur"]=json!(dur);ev["spec"]=json!(h.cp.spec);ev["mt"]=json!(h.cp.mt);ev["pow"]=json!(pow);ev["value"]=json!(h.cp.value);ev["log"]=json!(std::mem::take(&mut h.cp.log));ev["dlog"]=json!(std::mem::take(&mut h.cp.dlog));}
                    self.events.push(ev);
                }
            }
        }
        if std::env::var("RX_CPDBG").is_ok() {
            if let Some(e)=self.horses[hi].cp.end.take() {let t=self.time;let h=&mut self.horses[hi];let (lg,dl)=(std::mem::take(&mut h.cp.log),std::mem::take(&mut h.cp.dlog));self.events.push(json!({"t":t,"type":108,"name":"DbgCpEnd","params":[hi],"horse":hi,"extra":"","end":e,"log":lg,"dlog":dl}));}
            let (t,h)=(self.time,&mut self.horses[hi]);
            if h.phase>=2 && !h.cp.dbg_p2 {h.cp.dbg_p2=true;self.events.push(json!({"t":t,"type":106,"name":"DbgPhase2","params":[hi],"horse":hi,"extra":""}));}
            let h=&mut self.horses[hi];
            if h.spurt_start>0.0 && h.distance>=h.spurt_start && !h.cp.dbg_sp {h.cp.dbg_sp=true;self.events.push(json!({"t":t,"type":107,"name":"DbgSpurt","params":[hi,h.input.pow,h.base[2],h.adjusted[2],h.stat(2),h.mods.apply(2,0.0)],"horse":hi,"extra":""}));}
        }
        self.downhill(hi,dt);
        // Global: divide in f64, but retain the float _sectionChangeDistance
        // field store. Keeping the length in double delays section 16 at the
        // exact 3200 m phase boundary (7a0b6189). The cached phase timing stays intact.
        let section=(if !self.jp() && flag("RX_SEC_DIVL") {
            let length=if flag("RX_SECTION_LENGTH_LOCAL") {(self.course.distance/24.0) as f64}
                else {self.course.distance as f64/24.0};
            (self.horses[hi].distance as f64/length) as usize
        } else {(self.horses[hi].distance/(self.course.distance/24.0)) as usize}).min(23);
        if self.horses[hi].sec_drawn>>section&1==0 {
            let [lo,up,scale]=self.horses[hi].sec_rand;
            let random=self.random.float_range(lo,up,&||format!("base{hi}:section{section}"));
            let h=&mut self.horses[hi];h.sec_drawn|=1<<section;
            h.section_speed[section]=if opt("RX_SECSPD1") {(random as f64*scale as f64+h.section_base[section] as f64) as f32}
                else if opt("RX_SECSPD2") {random*scale+h.section_base[section]}
                else {(random as f64*scale as f64) as f32+h.section_base[section]};
        }
        if let Some(x)=std::env::var("RX_PERTURB").ok().and_then(|v|{let x:Vec<i64>=v.split(',').filter_map(|a|a.parse().ok()).collect();(x.len()>=4 && x[3]==5).then(||x)})
            .filter(|x|x[0]==hi as i64 && x[1]==(self.time/dt).round() as i64) {let h=&mut self.horses[hi];h.section_speed[section]=f32::from_bits((h.section_speed[section].to_bits() as i64+x[2]) as u32);}
        let h=&self.horses[hi];
        let mut target=if h.spurt_start>0.0 && h.spurt_result&12==0 && h.distance>=h.spurt_start {h.spurt_speed} else {h.section_speed[section]};
        let mut dbg=[target,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0];
        if h.keep.mode!=0 {target*=h.keep.multiply;dbg[1]=h.keep.multiply;}
        if self.course.empty_in_move && h.phase==0 && h.lane>=p.f("forceInMoveLaneThreshold") && (h.inside.is_some() || h.lane<=0.0001) {target+=h.force_in;dbg[2]=h.force_in;}
        target=h.mods.apply(6,target);
        let ce=self.compete_effects(hi);let h=&self.horses[hi];
        // Global adds the compete (CompeteTop/CompeteFight) target bonus after the slope
        // term; float order changes the last bit (32 one-ULP replays, 0 lost).
        // RX_CE_AFTER_SLOPE=0 restores the earlier order; JP is unchanged.
        let ce_late=!self.jp() && flag("RX_CE_AFTER_SLOPE");
        if !ce_late {target+=ce.target_speed_add;}
        // HorseTargetSpeedCalculatorRace.Update (0x3443320) / CalcAddTargetSpeedOnLaneMove
        // (0x3443750): lane changed in the last MoveLane and HasModifier(0x15) ->
        // + Pow(Pow * LaneMoveAddParam1, LaneMoveAddParam2).
        if flag("RX_LANEADD") && !math::approximately(h.lane,h.prev_lane) && h.mods.apply(21,0.0)!=0.0 {
            target+=math::pow(h.stat(2)*p.f("Skill.LaneMoveAddParam1"),p.f("Skill.LaneMoveAddParam2"));
        }
        dbg[3]=target;
        if h.slope>0.0 {
            // Server arithmetic fit: float multiply before divide, rather
            // than slope * (coefficient / power). See 647-race ablation.
            if opt("RX_U1") {target+=((-(h.slope.abs() as f64)*p.f("Slope.UpSlopeAddSpeedVal1") as f64/h.stat(2) as f64) as f32).min(0.0);}
            else if opt("RX_SLOPEMUL") {target+=(-h.slope.abs()*p.f("Slope.UpSlopeAddSpeedVal1")/h.stat(2)).min(0.0);}
            else {target+=(-h.slope.abs()*(p.f("Slope.UpSlopeAddSpeedVal1")/h.stat(2))).min(0.0);}
        }
        else if h.downhill && opt("RX_U2") {target+=((h.slope.abs() as f64/p.f("Slope.DownSlopeAddSpeedVal2") as f64+p.f("Slope.DownSlopeAddSpeedVal1") as f64) as f32).max(0.0);}
        else if h.downhill {target+=(h.slope.abs()/p.f("Slope.DownSlopeAddSpeedVal2")+p.f("Slope.DownSlopeAddSpeedVal1")).max(0.0);}
        if ce_late {target+=ce.target_speed_add;}
        dbg[4]=target;
        if h.hp<=0.0 {target=h.min_speed;}
        target=target.clamp(p.f("Speed.TargetSpeedMin"),30.0);
        if h.finished {target=if h.after_goal<1.0 {h.target_speed} else if h.input.viewer_id!=0 {6.0} else {hi as f32*0.05+6.75};}
        let max=if let Some(i)=h.front {
            let front=&self.horses[i];
            if opt("RX_D5B") || opt("RX_D5C") {
                // RaceUtil.CalcMaxSpeedBlock (0x362c5e0): the AroundHorse snapshot
                // gap (PreUpdate), Clamp01(gap/blockGap); D5B evaluates the rate
                // expression in double, D5C in float.
                let g=h.around.iter().find(|a|a.i==i).map_or(front.distance-h.distance,|a|a.gap);
                let t=(g/p.f("Block.FrontBlockDistanceGap")).clamp(0.0,1.0);
                let (mx,mn)=(p.f("Block.FrontBlockMaxSpeedRateMax"),p.f("Block.FrontBlockMaxSpeedRateMin"));
                // Global: the rate is a float local evaluated in double ((max-min)*t+min rounded
                // once), then float * front speed. 1f2cb7c4 runner 3 was 1 ULP slow after a
                // block clamp at 8.59 s; 673 races: +10, none lost or earlier. RX_BLOCK_RATE_D=0 reverts.
                let v=if !self.jp() && flag("RX_BLOCK_RATE_D") {front.speed*(((mx as f64-mn as f64)*t as f64+mn as f64) as f32)} else if opt("RX_D5B") {(front.speed as f64*((mx as f64-mn as f64)*t as f64+mn as f64)) as f32} else {front.speed*((mx-mn)*t+mn)};
                v.max(h.min_speed)
            } else if opt("RX_D5") {
                let gap=((front.distance as f64-h.distance as f64)/p.f("Block.FrontBlockDistanceGap") as f64) as f32;
                let (mx,mn)=(p.f("Block.FrontBlockMaxSpeedRateMax") as f64,p.f("Block.FrontBlockMaxSpeedRateMin") as f64);
                ((front.speed as f64*((mx-mn)*gap.clamp(0.0,1.0) as f64+mn)) as f32).max(h.min_speed)
            } else {
            let gap=(front.distance-h.distance)/p.f("Block.FrontBlockDistanceGap");

            (front.speed*((p.f("Block.FrontBlockMaxSpeedRateMax")-p.f("Block.FrontBlockMaxSpeedRateMin"))*gap.clamp(0.0,1.0)+p.f("Block.FrontBlockMaxSpeedRateMin"))).max(h.min_speed)
            }
        } else {30.0};
        let array=if h.ex() {"PhaseAccelCoefExArray[0]".into()} else {format!("PhaseAccelCoefArray[{}]",h.input.running_style-1)};
        let mut accel=if h.finished {1.0} else if opt("RX_D4") && !(self.jp() && flag("RX_JP_ACCEL_FLOAT")) {
            ((h.stat(2)*p.f("AccelPowCoefSqrt")).sqrt() as f64*p.f(if h.slope>0.0 {"accelPowCoefUpSlope"} else {"accelPowCoef"}) as f64*
                h.ground_coef as f64*h.dist_power as f64*p.f(&format!("Speed.{array}.{}",PHASE_NAMES[h.phase.min(3)])) as f64) as f32
        } else {
            (h.stat(2)*p.f("AccelPowCoefSqrt")).sqrt()*p.f(if h.slope>0.0 {"accelPowCoefUpSlope"} else {"accelPowCoef"})*
                h.ground_coef*h.dist_power*p.f(&format!("Speed.{array}.{}",PHASE_NAMES[h.phase.min(3)]))
        };
        if std::env::var("RX_ACCDBG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("ACC {:.4} acc={:e} pow={:e} gc={:e} dp={:e} m10={:e} ce={:e} cp={:e} sd={} slope={}",self.time,accel,h.stat(2),h.ground_coef,h.dist_power,h.mods.apply(10,accel),ce.acceleration_add,h.cp.accel*(h.cp.left>0.0) as i32 as f32,h.start_dash,h.slope);}
        // Probe RX_CPORD: 1 = CP added before skills, 2 = CP before compete add.
        let cpo=std::env::var("RX_CPORD").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(0);
        let cpa=if h.cp.left>0.0 {h.cp.accel} else {0.0};
        if !h.finished && cpo==1 {accel=h.mods.apply(10,accel+cpa)+ce.acceleration_add;if h.start_dash {accel+=p.f("StartAccelAdd");}accel=accel.max(0.0);}
        else if !h.finished && cpo==2 {accel=h.mods.apply(10,accel)+cpa+ce.acceleration_add;if h.start_dash {accel+=p.f("StartAccelAdd");}accel=accel.max(0.0);}
        else if !h.finished {accel=h.mods.apply(10,accel)+ce.acceleration_add;if h.cp.left>0.0 {accel+=h.cp.accel;}if h.start_dash {accel+=p.f("StartAccelAdd");}accel=accel.max(0.0);}
        let rate=if h.finished {4.0/p.f("declBase")} else {
            // _UpdateSelfSpeed, Global RVA 0x3437970: pace-down overrides
            // the phase rate before the exhausted-HP floor is applied.
            let rate=p.f(if h.keep.mode==4 {"DeclRatePositionKeepPaseDown"}
                else if h.phase==0 {"declRateStart"} else if h.phase==1 {"declRateMiddle"} else {"declRateEnd"});
            if h.hp<=0.0 {rate.max(p.f("declRateHpZero"))} else {rate}
        };
        self.move_lane(hi,dt,false);
        if let Some(x)=std::env::var("RX_PERTURB").ok().and_then(|v|{let x:Vec<i64>=v.split(',').filter_map(|a|a.parse().ok()).collect();(x.len()>=4 && x[3]==2).then(||x)})
            .filter(|x|x[0]==hi as i64 && x[1]==(self.time/dt).round() as i64) {let h=&mut self.horses[hi];h.lane=f32::from_bits((h.lane.to_bits() as i64+x[2]) as u32);}
        let h=&mut self.horses[hi];h.target_speed=target;h.dbg=dbg;
        let mut v=h.self_speed+h.mods.consume(23,0.0);
        if opt("RX_D1") {
            if v<target {v=((v as f64+accel as f64*dt as f64) as f32).min(target);}
            else if v>target {v=((v as f64-rate as f64*p.f("declBase") as f64*dt as f64) as f32).max(target);}
        } else if v<target && !h.start_dash && opt("RX_D1A") {v=((v as f64+accel as f64*dt as f64) as f32).min(target);}
        else if v<target && !h.start_dash && opt("RX_D1B") {v=((v as f64+(accel*dt) as f64) as f32).min(target);}
        else if v<target {v=(v+accel*dt).min(target);} else if v>target {v=(v-rate*p.f("declBase")*dt).max(target);}
        if h.start_dash {v=v.min(default_min);}v=v.clamp(h.min_speed,max);
        // Diagnostic RX_PERTURB="horse,tick,ulps[,field]": nudge one runner's latent value on one tick
        // (field 0 = self speed, 1 = movement). Research only; never set in validation runs.
        let perturb=std::env::var("RX_PERTURB").ok().and_then(|v|{let x:Vec<i64>=v.split(',').filter_map(|a|a.parse().ok()).collect();(x.len()>=3).then(||x)})
            .filter(|x|x[0]==hi as i64 && x[1]==(self.time/dt).round() as i64);
        if let Some(x)=&perturb && x.get(3).copied().unwrap_or(0)==0 {v=f32::from_bits((v.to_bits() as i64+x[2]) as u32);}
        h.self_speed=v;if h.cp.left>0.0 {h.cp.left-=dt;if h.cp.left<=0.0 && std::env::var("RX_CPDBG").is_ok() {h.cp.end=Some([h.self_speed,target,h.hp,h.distance,h.spurt_speed,h.max_hp]);}}
        h.speed=if opt("RX_D6") {((h.mods.apply(23,0.0) as f64+h.mods.apply(5,0.0) as f64+v as f64) as f32).clamp(h.min_speed,max)}
            else {(h.mods.apply(23,0.0)+h.mods.apply(5,0.0)+v).clamp(h.min_speed,max)};
        let mut movement=h.speed*dt;
        if let Some(x)=&perturb && x.get(3).copied()==Some(1) {movement=f32::from_bits((movement.to_bits() as i64+x[2]) as u32);}
        if h.delay<0.0 {
            // Global server replay evidence: preserve the fractional gate tick
            // in double precision. The Windows client uses divss/mulss here;
            // that path differs by one ULP in 430 corpus opening samples.
            // JP server: single precision movement*(|delay|/dt) (1530 races later, 0 earlier
            // vs the Global double path). RX_JP_GATE=0/2 keep the alternatives as probes.
            movement=match if self.input.region.as_deref()==Some("jp") {std::env::var("RX_JP_GATE").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(1)} else {0} {
                1=>movement*(h.delay.abs()/dt),
                2=>movement*h.delay.abs()/dt,
                _=>crate::math::gate_movement(movement,h.delay,dt),
            };
            h.delay=0.0;
        }
        let mut drain_rate=h.mods.apply(13,0.0);
        if drain_rate<=0.0 && let Some(r)=ce.hp_base_rate {drain_rate=r;}
        if drain_rate<=0.0 {drain_rate=p.f(if h.tempted() {"Hp.HpDecRateBaseTemptation"}
            else if h.keep.mode==4 {"Hp.HpDecRateBasePositionKeepPaseDown"} else {"Hp.HpDecRateBaseNormal"});}
        if h.downhill {drain_rate*=p.f("Hp.HpDecRateMultiplyDownSlopeAccelMode");}
        let drain_base=if h.start_dash {v} else {race_base};
        let drain=self.hp_rate(&self.horses[hi],v,drain_base,drain_rate);
        let h=&mut self.horses[hi];
        if !h.finished && h.hp>0.0 {h.hp=if opt("RX_D2") || opt("RX_HPSUB") {((h.hp as f64-drain as f64*dt as f64) as f32).clamp(0.0,h.max_hp)} else if opt("RX_HPSUB2") {(h.hp-((drain as f64*dt as f64) as f32)).clamp(0.0,h.max_hp)} else {(h.hp-drain*dt).clamp(0.0,h.max_hp)};}
        if !h.finished && h.hp<=0.0 {h.hp_empty=true;}
        h.phase=self.course.phase(h.distance);
        let mut position=self.geometry.world(h.distance,h.lane);
        if let Some(x)=std::env::var("RX_PERTURB").ok().and_then(|v|{let x:Vec<i64>=v.split(',').filter_map(|a|a.parse().ok()).collect();(x.len()>=4 && (x[3]==3||x[3]==4)).then(||x)})
            .filter(|x|x[0]==hi as i64 && x[1]==(self.time/dt).round() as i64) {let k=if x[3]==3 {0} else {2};position[k]=f32::from_bits((position[k].to_bits() as i64+x[2]) as u32);}
        let p64mode=std::env::var("RX_POS64").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(0);
        let np64=if p64mode>0 {self.geometry.world64(h.distance,h.lane,p64mode)} else {[0.0;3]};
        let d64=if p64mode>0 {Some(((np64[0]-h.pos64[0]).powi(2)+(np64[2]-h.pos64[2]).powi(2)).sqrt() as f32)} else {None};
        let h=&mut self.horses[hi];if p64mode>0 {h.pos64=np64;}
        let dx=position[0]-h.position[0];let dz=position[2]-h.position[2];
        // Server fit (Session 5, 331 capped ticks): squares summed in double,
        // disp rounded to float, then movement*cap/disp in double, rounded once.
        let server_cap=flag("RX_CAP");
        // RX_JP_CAP3D=1 (research): include the height delta in the displacement.
        let dy=if std::env::var("RX_JP_CAP3D").is_ok_and(|v|v=="1") {position[1]-h.position[1]} else {0.0};
        let displacement=if self.geometry.jp {(dx*dx+dz*dz).sqrt()} else if opt("RX_SQ1") {(((dx as f64)*(dx as f64)+(dy as f64)*(dy as f64)+(dz as f64)*(dz as f64)) as f32).sqrt()}
            else if opt("RX_SQ2") {((dx*dx+dz*dz) as f64).sqrt() as f32}
            else if opt("RX_SQ3") {(((dx*dx) as f64)+((dz*dz) as f64)).sqrt() as f32}
            else if server_cap {((dx as f64)*(dx as f64)+(dy as f64)*(dy as f64)+(dz as f64)*(dz as f64)).sqrt() as f32}
            else {((dx*dx+dy*dy+dz*dz) as f64).sqrt() as f32};
        let displacement=d64.unwrap_or(displacement);
        let cap=movement*self.geometry.distance_to_world;
        h.dbg[6]=movement;h.dbg[7]=h.position[0];h.dbg[8]=h.position[1];h.dbg[9]=h.position[2];h.dbg[10]=position[0];h.dbg[11]=position[1];h.dbg[12]=position[2];h.dbg[13]=self.geometry.distance_to_world;h.dbg[14]=h.distance;h.dbg[15]=h.lane;
        // Diagnostic: RX_FLIPCAP="runner,time" inverts the cap decision on that one tick.
        static FLIP:std::sync::OnceLock<Option<(usize,f32)>>=std::sync::OnceLock::new();
        let flip=FLIP.get_or_init(|| std::env::var("RX_FLIPCAP").ok().and_then(|v|{let (a,b)=v.split_once(',')?;Some((a.parse().ok()?,b.parse().ok()?))}))
            .is_some_and(|(fh,ft)|fh==hi && (self.time-ft).abs()<0.005);
        if std::env::var("RX_WVLOG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {let v=self.geometry.world_variants(h.distance,h.lane);
            let bits:Vec<String>=v.iter().map(|p|format!("{:+}/{:+}",p[0].to_bits() as i64-v[0][0].to_bits() as i64,p[2].to_bits() as i64-v[0][2].to_bits() as i64)).collect();eprintln!("WV {:.4} x={:e} z={:e} {}",self.time,v[0][0],v[0][2],bits.join(" "));}
        if std::env::var("RX_CAPLOG").ok().and_then(|v|v.parse::<usize>().ok())==Some(hi) {eprintln!("CAPLOG {:.4} cap={:e} disp={:e} d2={:e} mv={:e} dx={:e} dz={:e}",self.time,cap,displacement,(dx as f64)*(dx as f64)+(dz as f64)*(dz as f64),movement,dx,dz);}
        let d2sq=(dx as f64)*(dx as f64)+(dz as f64)*(dz as f64);
        let capped=match std::env::var("RX_CAPSQ").ok().as_deref() {
            Some("1")=>(cap as f64)*(cap as f64)<d2sq,
            Some("2")=>cap*cap<(d2sq as f32),
            Some("3")=>cap*cap<dx*dx+dz*dz,
            Some("4")=>cap<=displacement,
            _=>cap<displacement,
        };
        if capped!=flip {
            movement=if self.geometry.jp {movement*(cap/displacement)} else if opt("RX_CAPR1") {movement*(((cap as f64)/(displacement as f64)) as f32)}
                else if opt("RX_CAPR2") {movement*(cap/displacement)}
                else if opt("RX_CAPR3") {((movement as f64)*((movement as f64)*(self.geometry.distance_to_world as f64))/(displacement as f64)) as f32}
                else if opt("RX_CAPR4") {((movement as f64)*((cap as f64)/(displacement as f64))) as f32}
                else if server_cap {((movement as f64)*(cap as f64)/(displacement as f64)) as f32} else {movement*(cap/displacement)};
            h.dbg[5]=1.0;
        }
        h.position=position;h.prev_distance=h.distance;h.distance+=movement;
        if h.speed>=default_min {h.start_dash=false;}
        if h.slope!=0.0 && h.distance>h.slope_end {h.slope=0.0;}
        if !h.finished && h.distance>self.course.distance {
            h.finished=true;
            let fraction=((h.distance-self.course.distance)/(h.distance-h.prev_distance)).clamp(0.0,1.0);
            // The finish-time store rounds once: time - fraction*dt in double (ed5ecd6e461b9bfd
            // runner 16 was 1 ULP late; 673 races: +1, none lost). RX_FINT64=0 keeps float.
            h.raw_time=if flag("RX_FINT64") {(self.time as f64-fraction as f64*dt as f64) as f32} else {self.time-fraction*dt};h.scaled_time=h.raw_time*p.f("Global.FinishTimeCoef");
            if !opt("RX_GOALKEEP") {for sk in &mut h.skills {for d in &mut sk.details {if d.active {h.mods.stop(d.uid);d.active=false;}}}}
        }
    }
    fn course_events(&mut self) {
        let jp=self.jp();
        for (ei,e) in self.course.events.iter().enumerate() {
            for h in &mut self.horses {
                if ei as i32<=h.called_event || h.distance<e.distance {continue;}
                h.called_event=ei as i32;
                match (e.kind,e.values.as_slice()) {
                    (0,[number,..])=>{
                        h.corner=*number;h.straight=false;
                        if flag("RX_CORNERSEG") {
                            // The segment this event starts (corner numbers repeat on long courses).
                            let seg=self.course.corners.iter().find(|s|s.number==*number && s.start==e.distance);
                            h.corner_end=seg.map_or(e.distance+200.0,|s|s.end);
                            h.final_corner=self.course.final_corner().is_some_and(|f|f.start==e.distance);
                        } else {
                        h.corner_end=self.course.corner(*number).map_or(e.distance+200.0,|s|s.end);
                        h.final_corner=self.course.corners.iter().any(|s|s.number==*number && s.number>=4 && self.course.distance-s.end<=1000.0);
                        }
                    },
                    // A straight start inside a corner's nominal length ends that corner
                    // (course 11102: corner 2 500-650, straight 2 from 600; Sparkly Stardom
                    // corner==0 fires at 600). RX_STRAIGHT_CLR=0 keeps the corner to its end.
                    (2,[1,front,..])=>{h.straight=true;h.front_type=*front;if !jp && flag("RX_STRAIGHT_CLR") {h.corner=0;}},
                    // RaceManager.EventStraightChange (0x3602f00): a start with < 2 values is
                    // ignored; an end clears IsStraight and CurStraightFrontType.
                    (2,[1]) if flag("RX_STRAIGHT0")=>(),
                    (2,_)=>{h.straight=false;if flag("RX_STRAIGHT0") {h.front_type=0;}},
                    (11,[per,_])=>{
                        let sign=per.signum();if let Some(s)=self.course.slopes.iter().find(|s|s.number==sign && s.start<=h.distance && h.distance<=s.end) {h.slope=*per as f32/10000.0;h.slope_end=s.end;}
                    },
                    (3,[max,..]) if self.input.race_type!=3=>h.lane_max=*max as f32/10000.0,
                    _=>(),
                }
            }
        }
    }
    fn tick(&mut self,dt:f32) {
        for hi in 0..self.horses.len() {
            self.around(hi,dt);let h=&mut self.horses[hi];if !flag("RX_PO") {h.prev_order=h.order;}
            if h.finished {h.after_goal+=dt;}
            if h.distance>h.corner_end {h.corner=0;}
        }
        // Pacemaker hypotheses (server-only PaseMakerCalculator): RX_PM=1 frontmost
        // runner of the most forward style, RX_PM=2 overall frontmost (by order).
        let pm=std::env::var("RX_PM").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(6);
        if pm>=6 && dt>0.0 {
            // Public-oracle evidence: the pacemaker is re-selected when the leader
            // (RX_PM=6) or the current pacemaker (RX_PM=7) enters a new section.
            let style=|h:&Horse|if h.ex() {0} else {h.input.running_style};
            let sec=self.course.distance/24.0;
            let probe=if pm==6 {self.horses.iter().map(|h|h.distance).fold(f32::MIN,f32::max)} else {self.horses[self.pacemaker].distance};
            let s=if !self.jp() && opt("RX_PMSEC_D") {(probe as f64/(self.course.distance as f64/24.0)) as i32} else {(probe/sec) as i32};
            // First re-selection probes: a fixed check time/distance replaces only
            // section one; later sections retain the oracle-supported trigger.
            let fixed_first=opt("RX_PM_TIME3_LEAD") || opt("RX_PM_DISTANCE60_LEAD");
            let first_due=(opt("RX_PM_TIME3_LEAD") && self.time>=3.0) || (opt("RX_PM_DISTANCE60_LEAD") && probe>=60.0);
            let select=if fixed_first && self.pm_section==0 {first_due} else {s>self.pm_section};
            let first_selection=self.pm_section==0;
            if select {
                self.pm_section=if fixed_first && first_selection {s.max(1)} else {s};
                // RX_PMR=1: the most forward style is taken only among runners within
                // PaseMakerChangeMostForwardStyleRange of the leader.
                let lead=self.horses.iter().map(|h|h.distance).fold(f32::MIN,f32::max);
                let range=self.p().f("PositionKeep.PaseMakerChangeMostForwardStyleRange");
                let rr=std::env::var("RX_PMR").map_or(false,|v|v=="1");
                let near=|h:&Horse|!rr || lead-h.distance<=range;
                // A selected slower style persists in this probe; later section checks
                // still choose its frontmost runner without reverting to Nige.
                let retained_style=if opt("RX_PM_EARLY_STYLE") && !first_selection {style(&self.horses[self.pacemaker])} else {0};
                let best=self.horses.iter().filter(|h|!h.finished && near(h) && style(h)>=retained_style).map(style).min().unwrap_or(1);
                // A check whose leader is not the most forward style keeps the current pacemaker
                // (early pace-down HP fits, e.g. 787b27849eeab91f; 673 races: 5 later / 0 earlier).
                // RX_PMKEEP=0 re-selects the most forward style's frontmost runner every check.
                let lead_i=self.horses.iter().enumerate().filter(|(_,h)|!h.finished).min_by_key(|(_,h)|h.order).map(|(i,_)|i);
                let keep=flag("RX_PMKEEP") && lead_i.is_some_and(|i|style(&self.horses[i])!=best);
                // The frontmost runner is taken from the order one update older (PrevOrder): near-tied
                // Nige keep the earlier front runner (842ecad72f8d03f6, 9d9e2516b6863eca; 673 races:
                // 6 later / 0 earlier). RX_PMPREVORDER=0 uses the current order.
                let po=flag("RX_PMPREVORDER");
                // Re-selection stops at PositionKeepEndSection (10): position keep is over, so a Nige
                // that edges ahead later does not take the pacemaker (fdf73d4a9af4546a, 6accc5f7,
                // 20a9d1ff; 673 races: 3 later / 0 earlier). RX_PMENDSEC=0 re-selects every section.
                let ended=flag("RX_PMENDSEC") && s>=self.p().f("PositionKeep.PositionKeepEndSection") as i32;
                if !keep && !ended {if let Some((i,_))=self.horses.iter().enumerate().filter(|(_,h)|style(h)==best && near(h)).min_by_key(|(_,h)|if po {h.prev_order} else {h.order}) {self.pacemaker=i;}}
                // Probe: RX_PMLEAD=1 re-selects the overall frontmost runner instead.
                if std::env::var("RX_PMDBG").is_ok() {
                    let cur=self.pacemaker;let cd=self.horses[cur].distance;
                    let lead_i=self.horses.iter().enumerate().min_by_key(|(_,h)|h.order).unwrap().0;
                    let ahead:Vec<_>=self.horses.iter().enumerate().filter(|(_,h)|h.distance>cd).map(|(i,h)|json!([i,style(h),h.distance-cd])).collect();
                    let t=self.time;self.events.push(json!({"t":t,"type":109,"name":"DbgPm","params":[cur,lead_i,s],"horse":cur,"extra":"","ahead":ahead}));
                }
                // Pacemaker recovery probes: restrict the leader override by check time,
                // section, or the unused server forward-style distance/count parameters.
                let early_lead=(opt("RX_PM_EARLY_LEAD") || opt("RX_PM_EARLY_STYLE")) && self.time<=3.2 && s==1;
                let first_lead=opt("RX_PM_FIRST_LEAD") && s==1;
                let forward_gap=self.horses.iter().filter(|h|!h.finished).map(|h|h.distance).fold(f32::MIN,f32::max)-self.horses[self.pacemaker].distance;
                let range_lead=opt("RX_PM_RANGE_LEAD") && forward_gap>self.p().f("PositionKeep.PaseMakerChangeForwardRunningStyleRange");
                let count_lead=opt("RX_PM_COUNT_LEAD") && self.horses.iter().filter(|h|!h.finished && h.distance>self.horses[self.pacemaker].distance && style(h)!=best).count() as f32>=self.p().f("PositionKeep.PaseMakerChangeTopHorseNotMostForwardStyleCount");
                if opt("RX_PMLEAD") || early_lead || first_lead || range_lead || count_lead || (fixed_first && first_selection) {if let Some((i,_))=self.horses.iter().enumerate().filter(|(_,h)|!h.finished).min_by_key(|(_,h)|h.order) {self.pacemaker=i;}}
                // Global parameter prose distinguishes the recalculation trigger
                // from the selection rule for Sashi/Oikomi leaders. Native prose
                // plus corpus validation: docs/RACE_GLOBAL_PACEMAKER_RECALC.md.
                if !self.jp() && opt("RX_GLOBAL_PM_RECALC") {
                    let runners=self.horses.iter().map(|h|crate::pacemaker::Runner {
                        style:style(h),order:h.order,distance:h.distance,finished:h.finished,
                    }).collect::<Vec<_>>();
                    if let Some(i)=crate::pacemaker::recalculate_with(&runners,&mut self.pm_not_forward,
                        self.assets.params().f("PositionKeep.PaseMakerChangeTopHorseNotMostForwardStyleCount") as i32,
                        self.assets.params().f("PositionKeep.PaseMakerChangeForwardRunningStyleRange"),crate::pacemaker::Rules {
                        early_forward:self.pm_handed && flag("RX_PM_RECALC_RESET"),
                        // Corpus: a Nige-led check does not clear the count (f065ef65; 644 -> 645, 0 lost).
                        reset_on_forward:!flag("RX_PM_NORESET"),
                        // Corpus: every threshold recalculation clears the count and the frontmost
                        // eligible runner wins by order (fbfaa56d; 645 -> 646, 0 lost).
                        reset_on_recalc:flag("RX_PM_RESET_RECALC"),order_first:flag("RX_PM_RESET_RECALC"),
                        // Forward exception needs a Nige field (3d6f7f6a; 2,379 races: +1, 0 lost). RX_PM_FORWARD_NIGE=0 reverts.
                        forward_nige_only:flag("RX_PM_FORWARD_NIGE")}) {
                        if std::env::var("RX_PMLOG").is_ok() && (i!=self.pacemaker || std::env::var("RX_PMLOG").as_deref()==Ok("2")) {eprintln!("PMLOG {} {} recalc {}->{} lead_d {} pm_d {} styles {:?}",self.input.replay_sha,self.time,self.pacemaker,i,self.horses.iter().map(|h|h.distance).fold(0.0,f32::max),self.horses[self.pacemaker].distance,runners.iter().map(|r|(r.style,r.order,r.distance)).collect::<Vec<_>>());}
                        self.pacemaker=i;
                        // Corpus: a handover restarts the not-forward count (RX_PM_RECALC_RESET=0 keeps counting).
                        if flag("RX_PM_RECALC_RESET") && runners[i].style!=runners.iter().filter(|r|!r.finished).map(|r|r.style).min().unwrap_or(1) {self.pm_not_forward=0;self.pm_handed=true;}
                    }
                    if std::env::var("RX_PMLOG").as_deref()==Ok("3") {let li=self.horses.iter().enumerate().min_by_key(|(_,h)|h.order).unwrap().0;eprintln!("PMCHK {} s={} pm={} lead={} lstyle={} cnt={} handed={}",self.time,s,self.pacemaker,li,style(&self.horses[li]),self.pm_not_forward,self.pm_handed);}
                // Retain the earlier experiment for isolated ablation runs.
                } else if opt("RX_IPA_PM_COUNT") {
                    let leader=self.horses.iter().enumerate().filter(|(_,h)|!h.finished)
                        .min_by_key(|(_,h)|h.order).map(|(i,_)|i);
                    if let Some(i)=leader {
                        let forward=self.horses.iter().filter(|h|!h.finished).map(style).min().unwrap_or(1);
                        self.pm_not_forward=if style(&self.horses[i])!=forward {self.pm_not_forward+1} else {0};
                        if self.pm_not_forward as f32>=self.p().f("PositionKeep.PaseMakerChangeTopHorseNotMostForwardStyleCount") {
                            self.pacemaker=i;self.pm_not_forward=0;
                        }
                    }
                }
                // Probe: RX_PMCLEAR=1 ends every runner's pace-down/up at re-selection;
                // =2 ends all position-keep modes.
                let pc=std::env::var("RX_PMCLEAR").ok().and_then(|v|v.parse::<i32>().ok()).unwrap_or(0);
                if pc!=0 {
                    let kp=self.assets.params();let kt=Tree(kp.get("PositionKeep"));
                    for h in &mut self.horses {if pc==2 && h.keep.mode!=0 || matches!(h.keep.mode,3|4) {h.keep.clear(&kt);}}
                }
            }
        } else if pm!=0 && dt>0.0 {
            let style=|h:&Horse|if h.ex() {0} else {h.input.running_style};
            let lead=self.horses.iter().map(|h|h.distance).fold(f32::MIN,f32::max);
            let range=self.p().f("PositionKeep.PaseMakerChangeMostForwardStyleRange");
            let near=|h:&Horse|pm!=3 && pm!=5 || lead-h.distance<=range;
            let best=self.horses.iter().filter(|h|!h.finished && near(h)).map(style).min().unwrap_or(1);
            if pm<=3 {
                if let Some((i,_))=self.horses.iter().enumerate()
                    .filter(|(_,h)|pm==2 || (style(h)==best && near(h))).min_by_key(|(_,h)|h.order) {self.pacemaker=i;}
            } else {
                let cur=self.pacemaker;let cd=self.horses[cur].distance;let cs=style(&self.horses[cur]);
                let ahead=self.horses.iter().filter(|h|h.distance>cd && style(h)!=cs).count() as f32;
                if pm==5 {if let Some((i,_))=self.horses.iter().enumerate().filter(|(_,h)|style(h)==best && near(h)).min_by_key(|(_,h)|h.order) {self.pacemaker=i;}}
                if ahead>=self.p().f("PositionKeep.PaseMakerChangeTopHorseNotMostForwardStyleCount") {
                    if let Some((i,_))=self.horses.iter().enumerate().min_by_key(|(_,h)|h.order) {self.pacemaker=i;}
                }
            }
        }
        // After a recalculation hands the pacemaker to a slower style, it reverts on the tick the
        // most forward style leads again, not at the next section check (1cfcf88f94f9ca38: Nige 15
        // retakes the lead at 11.52 s; 673 races: 2 later / 0 earlier). RX_PMREVERT=0 disables.
        if dt>0.0 && !self.jp() && flag("RX_PMREVERT") && !(!self.jp() && flag("RX_PMREVERT_LATE")) && (self.pm_handed || self.pm_not_forward>=self.p().f("PositionKeep.PaseMakerChangeTopHorseNotMostForwardStyleCount") as i32) {
            let st=|h:&Horse|if h.ex() {0} else {h.input.running_style};
            let best=self.horses.iter().filter(|h|!h.finished).map(st).min().unwrap_or(1);
            if let Some((i,_))=self.horses.iter().enumerate().filter(|(_,h)|!h.finished).min_by_key(|(_,h)|h.order) {
                if st(&self.horses[i])==best && (!opt("RX_PMREVERT_SLOW") || st(&self.horses[self.pacemaker])>=3) {self.pacemaker=i;self.pm_not_forward=0;self.pm_handed=false;}
            }
        }
        self.skills_pass(dt,1);self.skills_pass(dt,0);
        for hi in 0..self.horses.len() {
            self.update_horse(hi,dt);
            // HorseRaceInfoSimulate.UpdateOvertakeTargetTime (0x343e960), inside the runner's
            // Update: += dt if the first runner (index order) behind that lists self; else 0.
            if dt>0.0 && flag("RX_OTTIME") {
                let o=self.horses[hi].order;
                let hit=self.horses.iter().any(|n|o<n.order && n.overtake.contains(&hi));
                let h=&mut self.horses[hi];h.ot_target_time=if hit {h.ot_target_time+dt} else {0.0};
            }
        }
        if dt>0.0 && !self.jp() && flag("RX_PMREVERT") && flag("RX_PMREVERT_LATE") && (self.pm_handed || self.pm_not_forward>=self.p().f("PositionKeep.PaseMakerChangeTopHorseNotMostForwardStyleCount") as i32) {
            let st=|h:&Horse|if h.ex() {0} else {h.input.running_style};
            let best=self.horses.iter().filter(|h|!h.finished).map(st).min().unwrap_or(1);
            if let Some((i,_))=self.horses.iter().enumerate().filter(|(_,h)|!h.finished).min_by_key(|(_,h)|h.order) {
                if st(&self.horses[i])==best && (!opt("RX_PMREVERT_SLOW") || st(&self.horses[self.pacemaker])>=3) {self.pacemaker=i;self.pm_not_forward=0;self.pm_handed=false;}
            }
        }
        // HorseRaceInfoSimulate._UpdateBlockTime (0x343ec10) runs inside Update,
        // after this tick's skill checks.
        // No finished check in _UpdateBlockTime (RX_BLOCKFIN=0 stops accumulating at the goal).
        if dt>0.0 {for h in &mut self.horses {if h.front.is_some() && (flag("RX_BLOCKFIN") || !h.finished) {h.block_front_acc+=dt;}}}
        if flag("RX_BLOCKT") {for h in &mut self.horses {
            h.front_time=if h.front.is_some() {h.front_time+dt} else {0.0};
            h.side_time=if h.inside.is_some() || h.outside.is_some() {h.side_time+dt} else {0.0};
        }}
        let mut overlap=(0..self.horses.len()).collect::<Vec<_>>();
        netsort::sort(&mut overlap,&|a,b|(self.horses[*a].lane as i32-self.horses[*b].lane as i32)*10000);
        for pair in overlap.windows(2) {
            let a=pair[0];let b=pair[1];
            if (self.horses[b].distance-self.horses[a].distance).abs()<0.4 && (self.horses[b].lane-self.horses[a].lane).abs()<1.0/45.0 {
                self.horses[b].lane=self.horses[a].lane+1.0/45.0;self.horses[b].force_lane=true;
            }
        }
        let mut order=(0..self.horses.len()).collect::<Vec<_>>();
        order.sort_by(|a,b|self.horses[*b].distance.total_cmp(&self.horses[*a].distance).then(a.cmp(b)));
        // RaceHorseManagerSimulate.UpdateHorse: UpdateOverlap -> CompeteTop/Fight (server).
        if dt>0.0 && opt("RX_COMPETE") {self.compete_step(dt);}
        if dt>0.0 && flag("RX_NEAR") && opt("RX_NEARPRE") {self.near_times(dt);}
        // HorseOrderCalculator.UpdateHorseOrder (0x342c2d0): PrevOrder = old CurOrder.
        let po=flag("RX_PO");
        for (i,hi) in order.iter().copied().enumerate() {let h=&mut self.horses[hi];if po {h.prev_order=h.order;}h.order=i;}
        // RaceHorseManagerBase.CalcHorseOrder (0x3447440) -> UpdateOrderChangeCount per runner:
        // HorseOrderChangeCounterBase.Update (0x342cb00) + Up.CheckChange (0x342d190).
        if flag("RX_ORDERUP") {
            let cool=self.p().f("overTakeCountCoolDownTime");
            for hi in 0..self.horses.len() {
                let h=&self.horses[hi];if h.finished {continue;}
                let (cur,prev)=(h.order,h.prev_order);
                let h=&mut self.horses[hi];
                for c in &mut h.order_up_cool {*c-=dt;if *c<=0.0 && *c!=0.0 {*c=0.0;}}
                if cur>=prev {continue;}
                let Some(&passed)=order.get(cur+1) else {continue};
                if h.order_up_cool[passed]>0.0 {continue;}
                h.order_up_cool[passed]=cool;
                let lastspurt=h.spurt_start>0.0 && h.spurt_result&12==0 && h.distance>=h.spurt_start;
                match h.phase {0=>h.order_up[0]+=1,1=>h.order_up[1]+=1,2|3=>h.order_up[2]+=1,_=>()}
                if h.corner!=0 {h.order_up[3]+=1;if matches!(h.phase,2|3) {h.order_up[4]+=1;}}
                if lastspurt {h.order_up[5]+=1;}
                if h.distance>=200.0 {h.order_up[6]+=1;}
                if h.final_corner {h.order_up[7]+=1;}
            }
        }
        let unfinished=self.horses.iter().filter(|h|!h.finished).map(|h|h.distance).collect::<Vec<_>>();
        if let (Some(max),Some(min))=(unfinished.iter().copied().reduce(f32::max),unfinished.iter().copied().reduce(f32::min)) {
            self.distance_diff_max=self.distance_diff_max.max(max-min);
        }
        // HorseRaceInfoSimulate.UpdateOrder{In,Out}Continue (0x343e070/0x343e250): from 5 s,
        // flag i (rate (i+1)*10) clears for good once CurOrder+1 > / < (int)(rate/100*N+0.5).
        if dt>0.0 && self.time>=5.0 && flag("RX_ORDCONT") {
            let n=self.horses.len() as f32;
            for h in &mut self.horses {
                for i in 0..9 {
                    let threshold=(((i+1) as f32*10.0)/100.0*n+0.5) as i32;let o=h.order as i32+1;
                    if threshold<o {h.order_continue[0][i]=false;}
                    if o<threshold {h.order_continue[1][i]=false;}
                }
            }
        }
        if dt>0.0 && flag("RX_NEAR") && !opt("RX_NEARPRE") {self.near_times(dt);}
        if dt>0.0 {self.course_events();self.pm_ready=true;}
    }
    fn record(&self)->Value {
        let jp=self.jp();let mut frame=json!({"t":self.time,"horses":self.horses.iter().map(|h|h.frame(jp)).collect::<Vec<_>>()});
        if self.random.trace.is_some() {
            frame["diagnostics"]=json!({"rng_calls":self.random.calls(),"pacemaker":self.pacemaker,"horses":self.horses.iter().map(|h|json!({
                "hp_float":h.hp,"speed_float":h.speed,"self_speed":h.self_speed,"target_speed":h.target_speed,"min_speed":h.min_speed,
                "lane_float":h.lane,"target_lane":h.target_lane,"lane_speed":h.lane_speed,"overtake":h.overtake,"ot_cool":h.ot_cool,"in_space":h.in_space,"out_space":h.out_space,"visible":h.visible,"inside":h.inside,"outside":h.outside,"phase":h.phase,"corner":h.corner,"final_corner":h.final_corner,"straight":h.straight,"front_type":h.front_type,"order":h.order,"slope":h.slope,"downhill":h.downhill,
                "spurt_start":h.spurt_start,"spurt_result":h.spurt_result,"position_keep":h.keep.mode,"dbg":h.dbg,"start_dash":h.start_dash,"front":h.front,
                "temptation_active":h.temptation_active,"temptation_mode":h.temptation_mode,"temptation_timer":h.temptation_timer,"temptation_check":h.temptation_check,"temptation_forced":h.temptation_forced})).collect::<Vec<_>>()});
            if opt("RX_RNG_KEEP_STATE") {
                frame["diagnostics"]["keep_states"]=json!(self.horses.iter().map(|h|h.keep.rng_probe_state()).collect::<Vec<_>>());
            }
            if opt("RX_HP_STATE") {
                frame["diagnostics"]["hp_inputs"]=json!(self.horses.iter().enumerate().map(|(i,h)|json!({
                    "guts":h.stat(3),"skill_rate":h.mods.apply(13,0.0),
                    "top":self.compete.modes[i].top,"top_remaining":self.compete.modes[i].top_remaining,
                    "top_group":self.compete.modes[i].top_group,"top_distance_exit":self.compete.modes[i].top_distance_exit
                })).collect::<Vec<_>>());
            }
        } frame
    }
    pub fn initialization(&self)->Value {
        json!({"seed":self.input.seed,"seed_mode":self.input.seed_mode,"rng_calls":self.random.calls(),
            "horses":self.horses.iter().map(|h|json!({"delay":h.original_delay,"base":h.base,"adjusted":h.adjusted,"effective":(0..5).map(|i|h.stat(i)).collect::<Vec<_>>(),
                "max_hp":h.max_hp,"lane":h.lane,"section_speed":h.section_speed,"section_base":h.section_base,"temptation_section":h.temptation_section})).collect::<Vec<_>>(),
            "unsupported":self.unsupported,"rng_trace":self.random.trace})
    }
    /// HorseDefeatCalculator.CalcDefeat (0x3429290), per runner after finish order.
    fn defeats(&self,finish:&[usize])->Vec<i32> {
        let d=Tree(self.assets.params().get("Defeat"));let n=self.horses.len();
        let mut finish_order=vec![0usize;n];for (o,&i) in finish.iter().enumerate() {finish_order[i]=o;}
        let per=|p:&str|((d.i(p) as f32/100.0)*n as f32+0.5) as i32;
        // CalcTopPassiveSkillNumAverage (0x34296a0): the first three finishers (98.9% vs 94.8%
        // for gate order over 7780 matched-order runners), excluding self; skill-array lengths.
        let top=|hi:usize|{
            let pick=|k:usize|finish[k];
            let (mut sum,mut cnt)=(0,0);
            for k in 0..3.min(n) {let i=pick(k);if i!=hi {sum+=self.horses[i].skills.len() as i32;cnt+=1;}}
            if cnt==0 {0} else {(sum as f32/cnt as f32+0.5) as i32}
        };
        (0..n).map(|hi|{
            let h=&self.horses[hi];let fo=finish_order[hi];
            if fo<1 {return 1;}
            if fo as i32<=d.i("DefeatLoseFinishOrder") as i32-1 {
                let prev=&self.horses[finish[fo-1]];
                let diff=h.scaled_time-prev.scaled_time;let x=diff*15.0;
                let b=if 0.0>x {0.0} else {x/2.5} as f64;
                // func_0x828260: (int)f(double); floor fits best (99.13% vs ceil 98.9, round 99.0).
                let b=b.floor() as i32;
                if b<=d.i("DefeatLoseBashinDiff") as i32 {return 2;}
            }
            if h.apt_distance<d.i("DefeatProperDistance") as i32 {return 12;}
            if h.apt_ground<d.i("DefeatProperGround") as i32 {return 13;}
            let same=self.horses.iter().filter(|o|o.input.running_style==h.input.running_style).count() as i32;
            if same>per("DefeatSameRunningStylePer") {return 3;}
            if h.hp_empty {
                if h.temptation_count>=d.i("DefeatTemptaionCount") as i32 {return 4;}
                return if (h.guts_order as i32+1)<per("DefeatGutsOrderPer") {6} else {5};
            }
            if h.spurt_result&0xc!=0 {return 7;}
            if h.spurt_result==2 {return 8;}
            if h.input.motivation<=d.i("DefeatMotivation") as i32 {return 14;}
            if (h.skills.len() as i32)<top(hi) {return 9;}
            if h.block_front_acc<d.f("DefeatFrontBlockAccumulateTime") {11} else {10}
        }).collect()
    }
    pub fn run(mut self,max_ticks:usize)->Result<Value,String> {
        self.tick(0.0);let mut frames=vec![self.record()];let mut interval=0.0;let mut all=false;
        // Handler scoring needs complete rushing episodes, including between wire samples.
        // These observations do not enter the race wire or any physics calculation.
        let mut rush_start=self.horses.iter().map(|h|if h.tempted() {Some(self.time)} else {None}).collect::<Vec<_>>();let mut rushing_events=Vec::new();
        for _ in 0..max_ticks {
            self.time+=DT;self.random.now=self.time;self.tick(DT);interval-=DT;all=self.horses.iter().all(|h|h.finished);
            for (hi,h) in self.horses.iter().enumerate() {
                if h.tempted() && !h.finished {
                    if rush_start[hi].is_none() {rush_start[hi]=Some(self.time);}
                } else if let Some(start)=rush_start[hi].take() {
                    let end=if h.finished {h.raw_time} else {self.time};
                    rushing_events.push(json!({"horse":hi,"t":start,"duration":(end-start).max(0.0)}));
                }
            }
            // Research: RX_HDBG=<horse index> prints that runner's per-tick state to stderr.
            if let Some(i)=std::env::var("RX_HDBG").ok().and_then(|v|v.parse::<usize>().ok()) {
                let h=&self.horses[i];
                eprintln!("HDBG {:.4} pm={} pmd={:.4} tg={:.4} ed={:.3} d={:.6} v={:.6} tv={:.6} ln={:.6} tl={:.6} pk={} tm={} ph={} sec={:.6} slope={} front={:?} fs={:.3} mods={:.6} dbg={:?} sl={} dh={} hp={:.6}",
                    self.time,self.pacemaker,self.horses[self.pacemaker].distance-h.distance,h.keep.target_gap,h.keep.end_distance,h.distance,h.speed,h.target_speed,h.lane,h.target_lane,h.keep.mode,h.temptation_mode,h.phase,
                    h.section_speed[((h.distance/self.course.distance*24.0) as usize).min(23)],h.slope,h.front,h.front_time,h.mods.apply(27,0.0),&h.dbg[..6],h.slope,h.downhill,h.hp);
            }
            if interval<=0.0 || all {
                frames.push(self.record());
                interval=if self.time<1.0 || (self.random.trace.is_some() && std::env::var("RX_TRACEALL").is_ok()) || self.horses.iter().any(|h|h.input.viewer_id!=0 && if flag("RX_FRAMEFIN") {(self.course.distance-h.distance).abs()<=25.0} else {self.course.distance-h.distance<=25.0}) {DT} else {1.0};
            }
            if all {break;}
        }
        if !all {return Err(format!("race did not finish within {max_ticks} ticks"));}
        let mut finish=(0..self.horses.len()).collect::<Vec<_>>();
        finish.sort_by(|a,b|self.horses[*a].scaled_time.total_cmp(&self.horses[*b].scaled_time).then(a.cmp(b)));
        let original_finish_times=self.horses.iter().map(|h|h.scaled_time).collect::<Vec<_>>();
        let winner=finish[0];let p=Tree(&self.course.master);
        let lo=p.i("finish_time_min") as f32*0.0001;let hi=p.i("finish_time_max") as f32*0.0001;
        let time=self.horses[winner].scaled_time;
        if time<lo || time>hi {
            let mut clamp=RaceRandom::new(self.input.seed as i32,false);
            let (bound,range)=if time<lo {(lo,p.i("finish_time_min_random_range") as f32*0.0001)} else {(hi,p.i("finish_time_max_random_range") as f32*0.0001)};
            let shift=clamp.float_range(-range,range,&||"finish_clamp".into())+bound-time;
            for h in &mut self.horses {h.scaled_time+=shift;}
        }
        let defeat=self.defeats(&finish);
        let mut results=vec![Value::Null;self.horses.len()];
        for (order,hi) in finish.iter().copied().enumerate() {
            let h=&self.horses[hi];let diff=if order==0 {0.0} else if !self.jp() && opt("RX_GLOBAL_FINISH_GAP") {
                // CalcFinishOrder (0x344e610) stores scaled-time differences before
                // RaceUtil.CalcClampedFinishTime subsequently adjusts finish times.
                original_finish_times[hi]-original_finish_times[finish[order-1]]
            } else {h.scaled_time-self.horses[finish[order-1]].scaled_time};
            results[hi]=json!({"order":order,"time":h.scaled_time,"diff":diff,"delay":h.original_delay,
                "guts_order":h.guts_order,"wiz_order":h.wiz_order,"last_spurt":h.spurt_start,
                "style":h.input.running_style,"defeat":defeat[hi],"raw_time":h.raw_time});
        }
        let region=if self.jp() {"jp"} else {"global"};
        Ok(json!({"schema":"race-wire-snapshot-v1","mode":"independent","version":if self.jp() {100000005} else {100000002},
            "runner_count":self.horses.len(),"distance_diff_max":self.distance_diff_max,
            "frames":frames,"events":self.events,"results":results,"rushing_events":rushing_events,
            "provenance":{"replay_sha":self.input.replay_sha,"logged_seed":self.input.logged_seed,
                "seed":self.input.seed,"seed_mode":self.input.seed_mode,"region":region,"input_sha256":self.input.input_sha256},
            "diagnostics":{"parity_verified":false,"unsupported":self.unsupported,"rng_calls":self.random.calls(),"rng_trace":self.random.trace}}))
    }
}

/// JP StandaloneSimulator.HorseInitialLaneCalculator.CalcInitialLane
/// (0x2533690). The ordinary branch is identical to the Global calculator.
pub fn initial_lane(gate:i32,lane_type:i64,half:bool,lane_max:f32,runners:i32,outside:bool)->f32 {
    let mut lane=if outside {lane_max-(runners-gate) as f32*(1.0/18.0)} else {gate as f32*(1.0/18.0)};
    match lane_type {
        1 if outside && gate<runners-9=>lane-=0.03333333507180214,
        1 if !outside && gate>8=>lane+=0.03333333507180214,
        3 if gate>13=>lane+=0.10333333164453506,
        4 if gate>7 && !half=>lane+=0.03333333507180214,
        _=>(),
    }
    lane
}

/// Ends a skill detail's effects. With `fold`, a type-22 current-speed add (index 23)
/// enters self speed at expiry and decelerates naturally. Exact replay evidence:
/// Global 174ef16df8e466ef h7 at 73.52652 s; JP 0174deaf483d70ef h4 at 17.2 s.
fn stop_effect(horses:&mut [Horse],uid:u64,fold:bool) {
    for h in horses {
        if fold {h.self_speed+=h.mods.entries.iter().filter(|m|m.owner==uid && (m.index==23 || (m.index==5 && std::env::var("RX_JP_FOLD5").is_ok_and(|v|v=="1"))) && !m.once).map(|m|m.value).sum::<f32>();}
        h.mods.stop(uid);
    }
}

/// Global static table at HorsePostNumberCalculator..cctor, verified by the
/// SHA256 field names of all sixteen serialized int arrays (counts 3..18).
pub fn post_number(index:usize,count:usize)->usize {
    if count<=8 {return index+1;}
    let (q,r)=(count/8,count%8);let mut end=0;
    for post in 1..=8 {end+=q+usize::from(post>8-r);if index<end {return post;}}
    1
}

// The native calculator consumes absolute current HP, not HP percent/max HP.
fn global_hp_duration_multiplier(params:Tree<'_>,hp:f32)->f32 {
    params.arr("Skill.TimeRemainHpCoefAscArray").iter()
        .find(|r|hp<f32_of(&r["HpThreshold"]))
        .map_or(1.0,|r|f32_of(&r["Multiply"]))
}

#[cfg(test)]
mod global_skill_tests {
    use super::*;
    #[test]
    fn additional_activation_budget_consumes_each_event_once() {
        let mut used=0;
        assert_eq!(take_additional_count(0,2,&mut used),0);
        assert_eq!(take_additional_count(1,2,&mut used),1);
        assert_eq!(take_additional_count(0,2,&mut used),0);
        assert_eq!(take_additional_count(3,2,&mut used),1);
        assert_eq!(take_additional_count(1,2,&mut used),0);
        assert_eq!(used,2);
        assert_eq!(take_additional_count(2,0,&mut 0),0);
    }
    #[test]
    fn hp_duration_native_strict_boundaries_and_exhaustion() {
        let assets=Assets::load(concat!(env!("CARGO_MANIFEST_DIR"),"/../data/race_param_define_global.json")).unwrap();
        let p=assets.params();
        assert_eq!(global_hp_duration_multiplier(p,1999.9999),1.0);
        assert_eq!(global_hp_duration_multiplier(assets.params(),2000.0),1.5);
        assert_eq!(global_hp_duration_multiplier(assets.params(),2400.0),2.0);
        assert_eq!(global_hp_duration_multiplier(assets.params(),3500.0),4.0);
        assert_eq!(global_hp_duration_multiplier(assets.params(),99999.0),1.0);
        assert_eq!(global_additional_cap(assets.params(),3),2);
        assert_eq!(global_additional_cap(assets.params(),99),0);
    }
}

// The native additional calculator's budget belongs to the ability instance,
// so restarting a timed detail must not replenish it.
fn take_additional_count(pending:i32,cap:i32,used:&mut i32)->i32 {
    let count=pending.max(0).min((cap-*used).max(0));
    *used+=count;
    count
}
fn global_additional_cap(params:Tree<'_>,kind:i64)->i32 {
    params.arr("Skill.AdditionalActivateAbilityMaxCountArray").iter()
        .find(|r|r["AdditionalActivateType"].as_i64()==Some(kind))
        .map_or(0,|r|r["AdditionalActivateMaxCount"].as_i64().unwrap_or(0) as i32)
}

/// Motivation-adjusted base is already a float field; round again only when
/// storing the complete course/ground/career adjustment on the Global server.
fn adjusted_stat(base:f32,coef:f32,ground:f32,career:f32,wide:bool,max:f32)->f32 {
    if wide {(base as f64*coef as f64+ground as f64+career as f64).clamp(1.0,max as f64) as f32}
    else {(base*coef+ground+career).clamp(1.0,max)}
}

#[cfg(test)]
mod adjusted_stat_tests {
    use super::adjusted_stat;
    #[test]
    fn career_wisdom_preserves_the_aptitude_product_until_the_field_store() {
        // Aoharu 1fd80833, runner 11: B style aptitude, neutral mood.
        let coef=8500.0f32*0.0001;
        assert_eq!(adjusted_stat(352.0,coef,0.0,400.0,true,2000.0).to_bits(),0x442ecccd);
        assert_eq!(adjusted_stat(352.0,coef,0.0,400.0,false,2000.0).to_bits(),0x442ecccc);
    }
    #[test]
    fn career_speed_keeps_the_motivation_field_store() {
        // Grand Live 3f359e91, runner 1: mood 4 then the course coefficient.
        let base=177.0f32*(10200.0f32*0.0001);
        assert_eq!(adjusted_stat(base,1.05,0.0,400.0,true,2000.0).to_bits(),0x44136449);
        assert_eq!(adjusted_stat(base,1.05,0.0,400.0,false,2000.0).to_bits(),0x4413644a);
    }
    #[test]
    fn adjusted_fields_clamp_after_ground_and_career_additions() {
        assert_eq!(adjusted_stat(1.0,0.1,-50.0,400.0,true,2000.0),350.1);
        assert_eq!(adjusted_stat(1.0,0.1,-50.0,0.0,true,2000.0),1.0);
        assert_eq!(adjusted_stat(1900.0,1.2,20.0,400.0,true,2000.0),2000.0);
    }
}
