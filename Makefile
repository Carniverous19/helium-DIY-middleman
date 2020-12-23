PY_SOURCES= \
	gateways2miners.py \
	src/messages.py \
	src/modify_rxpk.py \
	src/vgateway.py

DESTROOT?= /home/middleman

install: run.sh middleman.service $(PY_SOURCES)
	mkdir -p $(DESTROOT)
	mkdir -p $(DESTROOT)/src
	for pysrc in $(PY_SOURCES); do \
		install $$pysrc $(DESTROOT)/$$pysrc; \
	done
	install run.sh $(DESTROOT)
	install middleman.service /etc/systemd/system

run.sh: run.sh.in
	sed -e s,@@DESTROOT@@,$(DESTROOT),g < $< > $@

middleman.service: middleman.service.in
	sed -e s,@@DESTROOT@@,$(DESTROOT),g < $< > $@
