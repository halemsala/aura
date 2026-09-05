### CORNERAI INGEST — skill manual
Analise com pipeline v9.3.1-TRADER. Não invente dados.
```json
{
  "schema": "cornerai-skill-manual-2",
  "exportedAt": "2026-09-05T07:15:15-03:00",
  "source": "bridge-auto-feed",
  "instruction": "Analise com CornerAI v9.3.1-TRADER (Timing, Gate 2/3, Score, MC, kills). Responda no formato operacional ENTRA|AGUARDA|NÃO ENTRA. Não invente stats ausentes. Use TODOS os campos (dashboard 100%).",
  "match": {
    "fixtureId": null,
    "league": null,
    "home": "Grange Thistle",
    "away": "Pine Hills",
    "minute": 14,
    "extra": 0,
    "period": null,
    "status": "live",
    "score_home": 2,
    "score_away": 3,
    "score": [
      2,
      3
    ],
    "dataMode": null,
    "url": "https://sokkerpro.com/"
  },
  "stats": {
    "corners": [
      null,
      null
    ],
    "attacks": [
      0,
      0
    ],
    "dangerous": [
      0,
      0
    ],
    "shotsOn": [
      0,
      0
    ],
    "shots": [
      null,
      null
    ],
    "shotsOff": [
      0,
      0
    ],
    "possession": [
      null,
      null
    ],
    "xg": [
      0,
      0
    ],
    "fouls": [
      null,
      null
    ],
    "offsides": [
      null,
      null
    ],
    "yellow": [
      null,
      null
    ],
    "red": [
      null,
      null
    ],
    "subs": [
      null,
      null
    ],
    "crosses": [
      null,
      null
    ],
    "saves": [
      null,
      null
    ],
    "passes": [
      null,
      null
    ],
    "passesFailed": [
      null,
      null
    ],
    "totalShots": [
      null,
      null
    ],
    "appm": [
      null,
      null
    ]
  },
  "pressure": {
    "attacks": [
      0,
      0
    ],
    "dangerous": [
      0,
      0
    ],
    "shotsOn": [
      0,
      0
    ],
    "possession": [
      null,
      null
    ],
    "xg": [
      0,
      0
    ]
  },
  "extendedStats": {},
  "corner_events": [],
  "match_events": [],
  "cpi": [
    null,
    null
  ],
  "cpi_detail": null,
  "pred": null,
  "quality": 0.8,
  "charts": null,
  "odds": null,
  "h2h": null,
  "teamHistory": null,
  "timeline": null,
  "diagnostics": null,
  "sources": null,
  "analyst_raw": {
    "schema": "cornerai-analyst-2",
    "capture_build": "V28-SOKKERPRO-DOM-HARDENED",
    "fixture_id": null,
    "home": "Grange Thistle",
    "away": "Pine Hills",
    "score_home": 2,
    "score_away": 3,
    "minute": 14,
    "extra": 0,
    "status": "live",
    "pressure_gauge": 51,
    "attacks_home": 0,
    "attacks_away": 0,
    "dangerous_home": 0,
    "dangerous_away": 0,
    "xg_home": 0,
    "xg_away": 0,
    "shots_on_home": 0,
    "shots_on_away": 0,
    "shots_off_home": 0,
    "shots_off_away": 0,
    "total_shots_home": null,
    "total_shots_away": null,
    "possession_home": null,
    "possession_away": null,
    "corners_home": null,
    "corners_away": null,
    "apm_home": 0,
    "apm_away": 0,
    "appm_1_home": null,
    "appm_1_away": null,
    "appm_3_home": null,
    "appm_3_away": null,
    "appm_5_home": null,
    "appm_5_away": null,
    "appm_10_home": null,
    "appm_10_away": null,
    "fouls_home": null,
    "fouls_away": null,
    "yellow_home": null,
    "yellow_away": null,
    "red_home": null,
    "red_away": null,
    "saves_home": null,
    "saves_away": null,
    "offsides_home": null,
    "offsides_away": null,
    "param_hits": 7,
    "quality": 0.8,
    "corner_events": [],
    "fixture": {
      "id": null,
      "home": "Grange Thistle",
      "away": "Pine Hills",
      "minute": 14,
      "extra": 0,
      "status": "live",
      "score": {
        "home": 2,
        "away": 3
      }
    },
    "pressure": {
      "gauge": 51,
      "attacks": {
        "home": 0,
        "away": 0
      },
      "dangerous": {
        "home": 0,
        "away": 0
      },
      "apm": {
        "home": 0,
        "away": 0
      },
      "xg": {
        "home": 0,
        "away": 0
      },
      "shotsOn": {
        "home": 0,
        "away": 0
      },
      "shotsOff": {
        "home": 0,
        "away": 0
      }
    },
    "corners": {
      "total": {
        "home": null,
        "away": null
      },
      "events": []
    },
    "stats": {
      "attacks": {
        "home": 0,
        "away": 0
      },
      "dangerous": {
        "home": 0,
        "away": 0
      },
      "xg": {
        "home": 0,
        "away": 0
      },
      "shotsOn": {
        "home": 0,
        "away": 0
      },
      "shotsOff": {
        "home": 0,
        "away": 0
      },
      "totalShots": {
        "home": null,
        "away": null
      },
      "possession": {
        "home": null,
        "away": null
      },
      "fouls": {
        "home": null,
        "away": null
      },
      "appm": {
        "m1": {
          "home": null,
          "away": null
        },
        "m3": {
          "home": null,
          "away": null
        },
        "m5": {
          "home": null,
          "away": null
        },
        "m10": {
          "home": null,
          "away": null
        }
      }
    },
    "source": "sokkerpro-dom",
    "url": "https://sokkerpro.com/",
    "ts": 1788603315388
  },
  "window": "OUT"
}
```
Responda no formato: DECISÃO | TIMING | LADO | GATE | PRESSÃO | MC | KILLS | JUSTIFICATIVA | REG
