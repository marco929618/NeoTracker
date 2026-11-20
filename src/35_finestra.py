# ==========================================================================================
# 5c. LIFE OF THE WINDOW: how the program understands that you closed the app window
# ==========================================================================================
# IDEA (explained simply)
# ------------------------
# NeoTracker is made of two parts that talk to each other:
# - the "engine" (this Python program), which saves the data and analyses the photos;
# - the "window" (Edge or Chrome opened in app mode, i.e. without an address bar
# and without tabs), which shows the page.
# When you close the window, the engine must shut itself down. But the engine cannot
# "hear" the closing directly: so the page sends it a small signal ("heartbeat")
# every few seconds, like a beating heart. If the heartbeats stop, the window is closed.
#
# - every open page has its own random number (id) and sends a "heartbeat" every ~5 seconds;
# - when the page is closed it also tries to send a "goodbye" (immediate close);
# - if for 6 seconds there is NO page open any more, the engine shuts down (the 6 seconds
# are needed because pressing F5 / "reload" makes the page disappear and reappear in an instant:
# we do not want to shut everything down for a reload);
# - if the window freezes or the PC goes to sleep without a "goodbye", after 3 minutes of
# silence the page is considered closed;
# - if the engine is STILL analysing a photo, it waits for the analysis to finish and then shuts down
# (so you do not lose the work); if in the meantime you reopen the icon, the window comes back.

GRAZIA_CHIUSURA_S = 6          # seconds without open pages before shutting down (covers reloading)
SILENZIO_MASSIMO_S = 180       # a page that stays silent for 3 minutes is considered closed (frozen window)
FINESTRA_APERTA_S = 90         # within how many seconds of the last heartbeat we say "the window is open"
ATTESA_PRIMA_FINESTRA_S = 600  # if no window opens within 10 minutes of start-up, we shut down


class StatoFinestra:
    """Keeps count of the open pages and says when the program must shut down.

    The time is always passed by the caller (parameter `adesso`, in seconds): so in the tests
    we can simulate minutes and hours in an instant, without really waiting.
    """

    def __init__(self, adesso=None):
        self._blocco = threading.Lock()                       # prevents two requests from modifying at the same time
        self.avviato = time.monotonic() if adesso is None else adesso
        self.pagine = {}                                      # page id -> instant of the last heartbeat
        self.vista_almeno_una = False                         # has a window ever appeared?
        self.vuoto_da = None                                  # since when there have been no pages (None = there is at least one)
        self.chiuse = {}                                      # pages that said "goodbye": they can no longer "reopen"

    def azzera(self, adesso=None):
        """Starts over (called when the server starts): no page, no window ever seen."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.avviato, self.pagine, self.vista_almeno_una, self.vuoto_da = adesso, {}, False, None
            self.chiuse = {}

    # ---- signals coming from the page ----
    def battito(self, id_pagina, adesso=None):
        """A page says "I am still here"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            if id_pagina in self.chiuse:
                return          # a late heartbeat (arrived after the goodbye) must not "resurrect" a closed page
            self.pagine[id_pagina] = adesso
            self.vista_almeno_una = True
            self.vuoto_da = None                              # there is at least one page: cancels any pending shutdown

    def addio(self, id_pagina, adesso=None, definitivo=False):
        """A page is gone.
        definitivo=True: the page itself tells us "I am closing" -> from now on its possible late heartbeats
        are ignored. definitivo=False: we infer it from the dropped connection (it could
        be just a momentary interruption: if the page reappears with the same number, it counts)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.pagine.pop(id_pagina, None)
            if definitivo:
                self.chiuse[id_pagina] = adesso
                while len(self.chiuse) > 500:                 # we do not keep the list forever
                    del self.chiuse[next(iter(self.chiuse))]
            if not self.pagine and self.vuoto_da is None:
                self.vuoto_da = adesso                        # the 6-second countdown starts

    # ---- questions the program asks ----
    def _togli_pagine_mute(self, adesso):
        """Forgets the pages that have not beaten for too long (window frozen or closed by force)."""
        mute = [i for i, t in self.pagine.items() if adesso - t > SILENZIO_MASSIMO_S]
        for i in mute:
            del self.pagine[i]
        if mute and not self.pagine and self.vuoto_da is None:
            self.vuoto_da = adesso

    def finestra_aperta(self, adesso=None):
        """True if there is a page that has beaten recently (needed when the icon is opened a second time)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            return any(adesso - t <= FINESTRA_APERTA_S for t in self.pagine.values())

    def dopo_sospensione(self, adesso=None):
        """The PC has just woken up: during sleep no page could beat,
        so we pretend that all of them have beaten now (otherwise they would seem closed)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            for i in self.pagine:
                self.pagine[i] = adesso
            if self.vuoto_da is not None:
                self.vuoto_da = adesso
            self.avviato = max(self.avviato, adesso - 1)

    def da_spegnere(self, adesso=None, analisi_in_corso=False):
        """True when the program must close. Called every second by the "supervisor"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self._togli_pagine_mute(adesso)
            if self.pagine:
                return False                                  # there is still at least one open window
            if analisi_in_corso:
                return False                                  # do not interrupt an analysis: it will finish and then we shut down
            if self.vista_almeno_una:
                return self.vuoto_da is not None and adesso - self.vuoto_da >= GRAZIA_CHIUSURA_S
            return adesso - self.avviato >= ATTESA_PRIMA_FINESTRA_S   # no window has ever appeared


STATO_FINESTRA = StatoFinestra()
