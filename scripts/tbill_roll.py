# no_agent cron job for the tbill-roll skill: runs the skill's roll.py in "script" mode.
# Quiet night = no output (Hermes stays silent). Alert = printed text (+ MEDIA: file) goes to Telegram verbatim.
# Failure = exit 1 with the reason (Hermes delivers it as a failure alert).
import runpy, sys
ROLL = "/Users/hermes/.hermes/skills/finance/tbill-roll/roll.py"
sys.argv = [ROLL, "script"]
runpy.run_path(ROLL, run_name="__main__")
