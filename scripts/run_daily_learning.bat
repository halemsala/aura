@echo off
cd /d %~dp0..
echo === Feedback ===
python engine\agents\feedback_connector.py --once
echo === Threshold Tuner (proposta) ===
python engine\agents\threshold_tuner.py --days 7
echo.
echo Revise: engine\data\tuning\tuning_report_*.md
echo Revise: engine\data\tuning\glm_config.tomorrow.yaml
echo Para aplicar (manual): python engine\agents\threshold_tuner.py --promote
