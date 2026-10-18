use race_exact_rs::math::gate_movement;

#[test]
fn global_server_gate_exit_rounding_matches_replay_samples() {
    // speed bits, delay bits, expected first distance bits. Observations from
    // real Global replays 1d3d564e6f29aae8 (gate 13), e8cbbcb628dcab48
    // (gates 4 and 9). No replay state is read by the simulator.
    let dt = 0.0666f32;
    for (speed, delay, expected) in [
        (0x4093d3aa, 0x3d8543a7, 0x3be7895b),
        (0x4093b225, 0x3d81d9a7, 0x3c71b9fa),
        (0x4093cddc, 0x3d4ff3d5, 0x3d95bf28),
    ] {
        let movement = f32::from_bits(speed) * dt;
        let remainder = f32::from_bits(delay) - dt;
        assert_eq!(gate_movement(movement, remainder, dt).to_bits(), expected);
        assert_ne!((movement * (remainder.abs() / dt)).to_bits(), expected);
    }
}
