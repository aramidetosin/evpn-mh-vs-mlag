LAB   = vs-mlag
PASS ?= Clab123!
SSH   = sshpass -p $(PASS) ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null cumulus@clab-$(LAB)-
.PHONY: up down status green ssh-% shell-%
up:
	sudo containerlab deploy -t topo.clab.yml --reconfigure
	../scripts/post-deploy.sh mlag
down:
	sudo containerlab destroy -t topo.clab.yml
status:
	sudo containerlab inspect -t topo.clab.yml
green:
	../scripts/green.sh mlag
ssh-%:
	$(SSH)$*
shell-%:
	docker exec -it clab-$(LAB)-$* sh
