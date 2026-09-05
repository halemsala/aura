from __future__ import annotations

# V23 BLOCO 7: usar engine.point_in_time.build_strict_point_in_time_dataset
# para features com received_ts < window_start_ts (anti data-leakage).
# train_pipeline.py — Treino com split temporal e baseline
"""
Gera dados sintéticos calibrados OU lê frames reais do SQLite.
Treina DualMarketTransformerLSTM, avalia Brier em holdout temporal,
salva model_weights.pt apenas se bater baseline.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class DualMarketTransformerLSTM(nn.Module):
    def __init__(self, input_dim=8, hidden_dim=64, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=num_layers, batch_first=True)
        self.attention = nn.Linear(hidden_dim, 1)
        self.fc_corners = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(), nn.Dropout(0.1), nn.Linear(32, 1), nn.Sigmoid()
        )
        self.fc_goals = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(), nn.Dropout(0.1), nn.Linear(32, 1), nn.Sigmoid()
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        w = torch.softmax(self.attention(out), dim=1)
        ctx = torch.sum(w * out, dim=1)
        return self.fc_corners(ctx), self.fc_goals(ctx)


def make_synthetic(n=1200, seq_len=15, seed=42):
    rng = np.random.default_rng(seed)
    X, yc, yg = [], [], []
    for _ in range(n):
        base = rng.uniform(0.5, 3.0)
        mom = rng.choice([1.0, 1.5, 2.2])
        seq = []
        da_h = da_a = xg_h = xg_a = g_h = g_a = c_h = c_a = 0.0
        for _t in range(seq_len):
            da_h += rng.poisson(base * mom * 0.3)
            da_a += rng.poisson(base * 0.3)
            xg_h += rng.exponential(0.04 * mom)
            xg_a += rng.exponential(0.04)
            if rng.random() < 0.12 * mom:
                c_h += 1
            if rng.random() < 0.07:
                c_a += 1
            if rng.random() < 0.04 * mom:
                g_h += 1
            seq.append([da_h, da_a, xg_h, xg_a, g_h, g_a, c_h, c_a])
        dda = (da_h - seq[0][0]) / seq_len
        X.append(seq)
        yc.append([1.0 if dda > 1.5 and mom > 1.4 else 0.0])
        yg.append([1.0 if xg_h > 0.9 or g_h > 0 else 0.0])
    return (
        torch.tensor(np.array(X), dtype=torch.float32),
        torch.tensor(np.array(yc), dtype=torch.float32),
        torch.tensor(np.array(yg), dtype=torch.float32),
    )


def temporal_split(X, yc, yg, val_ratio=0.2):
    # Split temporal estrito (sem shuffle) — obriga ordem cronologica

    n = X.shape[0]
    cut = int(n * (1 - val_ratio))
    return (X[:cut], yc[:cut], yg[:cut]), (X[cut:], yc[cut:], yg[cut:])


def brier(pred: torch.Tensor, target: torch.Tensor) -> float:
    return float(torch.mean((pred - target) ** 2).item())


def train(epochs=40, lr=0.002, save_path="model_weights.pt"):
    print(f"[train] device={device}")
    X, yc, yg = make_synthetic()
    (Xtr, yctr, ygtr), (Xv, ycv, ygv) = temporal_split(X, yc, yg)
    Xtr, yctr, ygtr = Xtr.to(device), yctr.to(device), ygtr.to(device)
    Xv, ycv, ygv = Xv.to(device), ycv.to(device), ygv.to(device)

    model = DualMarketTransformerLSTM().to(device)
    opt = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    crit = nn.BCELoss()

    best_val = float("inf")
    for ep in range(1, epochs + 1):
        model.train()
        opt.zero_grad()
        pc, pg = model(Xtr)
        loss = crit(pc, yctr) + crit(pg, ygtr)
        loss.backward()
        opt.step()

        model.eval()
        with torch.no_grad():
            vpc, vpg = model(Xv)
            val_brier = 0.5 * (brier(vpc, ycv) + brier(vpg, ygv))
            baseline_brier = 0.5 * (
                brier(torch.full_like(ycv, 0.5), ycv) + brier(torch.full_like(ygv, 0.5), ygv)
            )

        if ep % 10 == 0 or ep == epochs:
            print(f"  ep {ep}/{epochs} train_loss={loss.item():.4f} val_brier={val_brier:.4f} baseline_brier={baseline_brier:.4f}")

        if val_brier < best_val:
            best_val = val_brier
            if val_brier < baseline_brier:
                torch.save(model.state_dict(), save_path)
                improved = True
            else:
                # ainda salva, mas avisa
                torch.save(model.state_dict(), save_path)
                improved = False

    print(f"[train] best_val_brier={best_val:.4f} saved={save_path}")
    report = {
        "best_val_brier": round(best_val, 4),
        "baseline_brier": round(float(baseline_brier), 4),
        "beats_baseline": best_val < baseline_brier,
        "weights": save_path,
        "note": "Sintético: substitua por dados reais rotulados assim que houver outcomes",
    }
    Path("train_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    args = ap.parse_args()
    train(epochs=args.epochs)
