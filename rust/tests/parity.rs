//! Cross-language parity: the Rust kernel must match the Python engine bit-for-bit (to f64
//! tolerance). Reference values were produced by running `common/taste` on these exact
//! inputs (see scripts notes); if either side drifts, this fails.

use echoes_kernel::kernel;

const EPS: f64 = 1e-9;

fn approx(a: f64, b: f64) {
    assert!((a - b).abs() < EPS, "expected {b}, got {a} (|Δ|={})", (a - b).abs());
}

#[test]
fn cosine_matches_python() {
    approx(kernel::cosine(&[1.0, 2.0, 3.0], &[4.0, 5.0, 6.0]), 0.9746318461970762);
}

#[test]
fn cosine_degenerate_is_zero() {
    approx(kernel::cosine(&[0.0, 0.0], &[1.0, 1.0]), 0.0);
}

#[test]
fn sinkhorn_matches_python() {
    let a = [0.5, 0.5];
    let b = [0.3, 0.3, 0.4];
    let cost = vec![vec![0.1, 0.7, 0.4], vec![0.6, 0.2, 0.9]];
    approx(kernel::sinkhorn(&a, &b, &cost, 0.1, 50), 0.35003403797338034);
}

#[test]
fn wmd_matches_python() {
    let a = vec![vec![1.0, 0.0, 0.0], vec![0.9, 0.2, 0.0], vec![0.2, 0.8, 0.1]];
    let b = vec![vec![0.95, 0.1, 0.0], vec![0.1, 0.9, 0.2]];
    let wa = [3.0, 2.0, 1.0];
    let wb = [2.0, 2.0];

    approx(
        kernel::wmd_distance(&a, &b, Some(&wa), Some(&wb), 0.1, 50),
        0.2550879610048264,
    );
    approx(
        kernel::wmd_similarity(&a, &b, Some(&wa), Some(&wb), 40, 0.1, 50),
        0.8724560194975868,
    );
    approx(kernel::mean_max_alignment(&a, &b), 0.9910479141204062);
}

#[test]
fn transport_plan_rows_sum_to_source_mass() {
    // The coupling's row marginals should recover `a` (within Sinkhorn tolerance).
    let a = [0.5, 0.5];
    let b = [0.3, 0.3, 0.4];
    let cost = vec![vec![0.1, 0.7, 0.4], vec![0.6, 0.2, 0.9]];
    let t = kernel::transport_plan(&a, &b, &cost, 0.05, 200);
    for (i, row) in t.iter().enumerate() {
        let s: f64 = row.iter().sum();
        assert!((s - a[i]).abs() < 1e-3, "row {i} mass {s} != {}", a[i]);
    }
}

#[test]
fn whiten_centers_and_projects() {
    let comps = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let mean = [1.0, 1.0];
    assert_eq!(kernel::whiten(&comps, &mean, &[2.0, 3.0]), vec![1.0, 2.0]);
    // identity transform passes through
    assert_eq!(kernel::whiten(&[], &[], &[2.0, 3.0]), vec![2.0, 3.0]);
}

#[test]
fn projection_is_2d_and_separates_clusters() {
    // two tight clusters far apart -> their 2D images should be far apart too
    let pts = vec![
        vec![0.0, 0.0, 0.0],
        vec![0.1, 0.0, 0.0],
        vec![10.0, 10.0, 10.0],
        vec![10.1, 10.0, 10.0],
    ];
    let coords = kernel::pca_project_2d(&pts);
    assert_eq!(coords.len(), 4);
    let d_within = (coords[0][0] - coords[1][0]).hypot(coords[0][1] - coords[1][1]);
    let d_across = (coords[0][0] - coords[2][0]).hypot(coords[0][1] - coords[2][1]);
    assert!(d_across > d_within, "clusters not separated: {d_across} !> {d_within}");
}
