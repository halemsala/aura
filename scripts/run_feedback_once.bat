@echo off
cd /d %~dp0..
python engine\agents\feedback_connector.py --once
python engine\agents\threshold_tuner.py --report-dir engine\data\daily_learning
