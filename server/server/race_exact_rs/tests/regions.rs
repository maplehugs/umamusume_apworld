use race_exact_rs::{data::{Assets, Master, RaceIn}, simulator::Simulator};
use serde_json::json;
use std::collections::HashMap;

#[test]
fn rejects_cross_region_assets_before_initialization() {
    let master = Master { tables: HashMap::new() };
    for (region, asset_region) in [("jp", "Global"), ("global", "JP")] {
        let input: RaceIn = serde_json::from_value(json!({
            "replay_sha":"test", "logged_seed":1, "seed":1, "seed_mode":"logged",
            "race_type":14, "race_instance_id":1, "race_id":1, "course_set":1,
            "season":1, "weather":1, "ground_condition":1, "horses":[], "region":region
        })).unwrap();
        let assets = Assets { root: json!({"source_region":asset_region}) };
        let error = Simulator::new(input, &master, &assets, false).err().unwrap();
        assert!(error.contains("does not match asset source_region"), "{error}");
    }
}
