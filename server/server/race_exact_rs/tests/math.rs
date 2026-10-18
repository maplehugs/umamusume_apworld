use race_exact_rs::math;
#[test]
fn global_native_reference_vectors() {
    let vectors:serde_json::Value=serde_json::from_str(include_str!("math_vectors.json")).unwrap();
    for v in vectors.as_array().unwrap() {
        let x=v["x"].as_f64().unwrap() as f32;
        let actual=if v["function"]=="log10f" {math::log10(x)} else {math::pow(x,v["y"].as_f64().unwrap() as f32)};
        let expected=u32::from_le_bytes(std::array::from_fn(|i|u8::from_str_radix(&v["bits"].as_str().unwrap()[i*2..i*2+2],16).unwrap()));
        assert_eq!(actual.to_bits(),expected,"{v}");
    }
}
