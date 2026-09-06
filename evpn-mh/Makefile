LAB   = vs-evpnmh
PASS ?= Clab123!
SSH   = sshpass -p $(PASS) ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null cumulus@clab-$(LAB)-
.PHONY: up down status green ssh-% shell-%
up:
	sudo containerlab deploy -t topo.clab.yml --reconfigure
	../scripts/post-deploy.sh evpn-mh
down:
	sudo containerlab destroy -t topo.clab.yml
status:
	sudo containerlab inspect -t topo.clab.yml
green:
	../scripts/green.sh evpn-mh
ssh-%:
	$(SSH)$*
shell-%:
	docker exec -it clab-$(LAB)-$* sh
