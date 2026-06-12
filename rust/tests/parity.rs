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
fn mds_reconstructs_euclidean_distances() {
    // a Euclidean-embeddable dissimilarity matrix (right triangle (0,0),(1,0),(0,1)):
    // classical MDS must reproduce the pairwise distances.
    let s2 = 2.0_f64.sqrt();
    let dissim = vec![
        vec![0.0, 1.0, 1.0],
        vec![1.0, 0.0, s2],
        vec![1.0, s2, 0.0],
    ];
    let c = kernel::mds_2d(&dissim);
    assert_eq!(c.len(), 3);
    let d = |i: usize, j: usize| (c[i][0] - c[j][0]).hypot(c[i][1] - c[j][1]);
    assert!((d(0, 1) - 1.0).abs() < 1e-6, "d01={}", d(0, 1));
    assert!((d(0, 2) - 1.0).abs() < 1e-6, "d02={}", d(0, 2));
    assert!((d(1, 2) - s2).abs() < 1e-6, "d12={}", d(1, 2));
}

#[test]
fn mds_degenerate_inputs() {
    assert!(kernel::mds_2d(&[]).is_empty());
    assert_eq!(kernel::mds_2d(&[vec![0.0]]), vec![[0.0, 0.0]]);
}

#[test]
fn field_peaks_at_node_and_decays() {
    // one full-match node at the grid center: brightest at the node, darker at the rim
    let g = kernel::field_grid(&[50.0], &[50.0], &[1.0], 11, 11, 0.0, 0.0, 9.0909, 9.0909, 25.0, 6);
    assert_eq!(g.len(), 121);
    let center = g[5 * 11 + 5];
    let corner = g[0];
    assert_eq!(center, 5, "center cell should hit the top glyph level");
    assert!(corner < center, "field must decay away from the node ({corner} !< {center})");
}

#[test]
fn field_takes_max_not_sum() {
    // two coincident half-matches must read exactly like one — crowding can't fake strength
    let one = kernel::field_grid(&[50.0], &[50.0], &[0.6], 8, 8, 0.0, 0.0, 12.5, 12.5, 30.0, 6);
    let two = kernel::field_grid(&[50.0, 50.0], &[50.0, 50.0], &[0.6, 0.6], 8, 8, 0.0, 0.0, 12.5, 12.5, 30.0, 6);
    assert_eq!(one, two);
}

#[test]
fn field_empty_and_zero_values_are_silent() {
    assert!(kernel::field_grid(&[], &[], &[], 4, 4, 0.0, 0.0, 1.0, 1.0, 10.0, 6)
        .iter()
        .all(|&l| l == 0));
    assert!(kernel::field_grid(&[1.0], &[1.0], &[0.0], 4, 4, 0.0, 0.0, 1.0, 1.0, 10.0, 6)
        .iter()
        .all(|&l| l == 0));
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
