#!/bin/bash
# Usage: mark.sh <phase>   -> appends "<phase> <epoch>" to timing.log
B="$(cd "$(dirname "$0")" && pwd)"
echo "${1:-mark} $(date +%s)" >> "$B/timing.log"
