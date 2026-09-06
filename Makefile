# EVPN multihoming vs MLAG: two containerlab labs with identical wiring.
#
#   make up            both labs
#   make mlag-up       one of them
#   make green         convergence check on both
#   make drills        every failure drill, both labs, about 55 minutes
#   make results       print the comparison from whatever is under results/
#   make down          tear both down
.PHONY: up down green drills results \
        mlag-up mlag-down mlag-green evpn-up evpn-down evpn-green gen

up: mlag-up evpn-up
down: mlag-down evpn-down
green: mlag-green evpn-green

mlag-up:   ; $(MAKE) -C mlag up
mlag-down: ; $(MAKE) -C mlag down
mlag-green:; $(MAKE) -C mlag green

evpn-up:   ; $(MAKE) -C evpn-mh up
evpn-down: ; $(MAKE) -C evpn-mh down
evpn-green:; $(MAKE) -C evpn-mh green

# Runs both labs through every drill and writes results/ plus results/run_all.log.
drills:
	scripts/run_all.sh

results:
	python3 scripts/summarize.py

# Rewrites both topologies and all ten bootstrap configs from one description.
gen:
	python3 gen.py
