use pyo3::prelude::*;

#[pyfunction]
fn kelly_fraction(edge: f64, odds: f64, max_frac: f64) -> f64 {
    if odds <= 1.0 || edge <= 0.0 { return 0.0; }
    let b = odds - 1.0;
    let p = (0.5 + edge).clamp(0.01, 0.99);
    let q = 1.0 - p;
    let f = (b * p - q) / b;
    f.clamp(0.0, max_frac)
}

#[pyfunction]
fn risk_score(odds_velocity: f64, pressure: f64, edge: f64) -> f64 {
    let v = odds_velocity.abs();
    let p = pressure.clamp(0.0, 1.0);
    (0.4 * p + 0.3 * (v / 5.0).min(1.0) + 0.3 * edge.max(0.0)).clamp(0.0, 1.0)
}

#[pyfunction]
fn orderbook_imbalance(bids_vol: f64, asks_vol: f64) -> f64 {
    let t = bids_vol + asks_vol;
    if t <= 0.0 { return 0.0; }
    (bids_vol - asks_vol) / t
}

#[pymodule]
fn risk_core_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(kelly_fraction, m)?)?;
    m.add_function(wrap_pyfunction!(risk_score, m)?)?;
    m.add_function(wrap_pyfunction!(orderbook_imbalance, m)?)?;
    Ok(())
}
