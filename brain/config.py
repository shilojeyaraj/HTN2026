"""Local mission-start exploration settings."""

STARTUP_SCAN_ENABLED = True
SCAN_STEP_DEG = 60
# CAMERA TUNING: edit these three numbers, then restart main.py.
# All values are millimetres from the homed arm, NOT camera angles.
# X: positive = forward (-80 to 80). Heights: positive = up (0 < LOW < HIGH <= 80).
# Start with small changes (e.g. 10 mm) and check the camera image after each run.
# The initial x=40/y=30 offset comes from robomaster_smoke_test.py; the mount's
# viewing angle is uncalibrated, so these are starting values, not verified views.
CAMERA_SCAN_X_MM = 40
CAMERA_LOW_HEIGHT_MM = 30
CAMERA_HIGH_HEIGHT_MM = 60

CAMERA_NEUTRAL_HEIGHT = CAMERA_LOW_HEIGHT_MM
CAMERA_SCAN_HEIGHTS_MM = {"LOW": CAMERA_LOW_HEIGHT_MM, "HIGH": CAMERA_HIGH_HEIGHT_MM}
